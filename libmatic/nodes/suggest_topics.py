"""Node implementations for suggest-topics workflow.

実装方針:
- A1 load_priorities (deterministic): config/source_priorities.yml から feed URL を抽出
- A2 fetch_candidates (deterministic): 各 feed から最新エントリを取得 (theme 非依存)
- A3 relevance_filter (ReAct): 議論価値 + lifespan 判定 + ephemeral 昇華
- A4 dedup_against_issues (deterministic): 既存 topic/* issue とのタイトル重複除去
- A5 create_issues (deterministic): TopicCandidate を topic/pending issue として起票
- A6 propose_new_sources (conditional): 未登録 domain で 2 件以上登場したものを検出
  (PR 自動作成は v0.1 では検出のみ、PR フローは将来拡張)
"""

from __future__ import annotations

import json
import re
from collections import Counter
from urllib.parse import urlparse

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from libmatic.agents.react import build_step_agent
from libmatic.nodes._helpers import (
    get_libmatic_config as _get_libmatic_config,
)
from libmatic.nodes._helpers import (
    last_message_content as _last_message_content,
)
from libmatic.nodes._helpers import (
    parse_json_array as _parse_json_array,
)
from libmatic.prompts.loader import load_prompt
from libmatic.state.suggest_topics import SuggestTopicsState, TopicCandidate
from libmatic.tools.github import (
    gh_issue_create_core,
    gh_issue_list_core,
)
from libmatic.tools.search_sources import (
    collect_feeds_from_priorities,
    fetch_feed,
)

# --- A1: load_priorities (deterministic) ---


def load_priorities(state: SuggestTopicsState, config: RunnableConfig) -> dict:
    """A1: source_priorities.yml から feed URL を展開して state.feeds に格納。"""
    _get_libmatic_config(config)  # config 検証 (使わなくても呼んで早期エラー)
    feeds = collect_feeds_from_priorities(state.source_priorities_path)
    return {"feeds": feeds}


# --- A2: fetch_candidates (deterministic) ---


def fetch_candidates(state: SuggestTopicsState, config: RunnableConfig) -> dict:
    """A2: 各 feed から最新エントリを取得して raw_candidates に格納 (URL dedup 込み)."""
    _get_libmatic_config(config)
    if not state.feeds:
        return {"raw_candidates": []}

    raw_candidates: list[dict] = []
    seen_urls: set[str] = set()
    for feed_url in state.feeds:
        entries = fetch_feed(feed_url)
        for e in entries:
            if e.link in seen_urls:
                continue
            seen_urls.add(e.link)
            raw_candidates.append(
                {
                    "url": e.link,
                    "title": e.title,
                    "published_at": e.published,
                    "feed": feed_url,
                    "domain": urlparse(e.link).netloc,
                }
            )
    return {"raw_candidates": raw_candidates}


# --- A3: relevance_filter (ReAct) ---


def _coerce_topic_candidate(raw: object) -> TopicCandidate | None:
    """LLM 出力の dict を TopicCandidate に変換。失敗時 None。"""
    if not isinstance(raw, dict):
        return None
    title = raw.get("title")
    body = raw.get("body")
    if not title or not body:
        return None
    try:
        return TopicCandidate(
            title=str(title),
            body=str(body),
            lifespan=str(raw.get("lifespan") or "universal"),  # type: ignore[arg-type]
            source_urls=[str(u) for u in (raw.get("source_urls") or []) if u],
        )
    except Exception:
        return None


def relevance_filter(state: SuggestTopicsState, config: RunnableConfig) -> dict:
    """A3 (ReAct): raw_candidates → TopicCandidate (議論価値 + lifespan 判定済)。"""
    lcfg = _get_libmatic_config(config)
    if not state.raw_candidates:
        return {"filtered_candidates": []}

    agent = build_step_agent(
        step_name="suggest_a3_relevance_filter",
        config=lcfg,
        tools=[],
        system_prompt=load_prompt("suggest_topics/a3_relevance_filter.md"),
    )
    input_text = (
        f"## raw_candidates\n{json.dumps(state.raw_candidates, ensure_ascii=False)}\n"
    )
    try:
        result = agent.invoke({"messages": [HumanMessage(content=input_text)]})
        raw = _parse_json_array(_last_message_content(result))
    except Exception:
        raw = []

    candidates: list[TopicCandidate] = []
    for r in raw:
        c = _coerce_topic_candidate(r)
        if c is not None:
            candidates.append(c)
    return {"filtered_candidates": candidates}


# --- A4: dedup_against_issues (deterministic) ---


def _normalize_title(t: str) -> str:
    """空白除去 + lowercase で title 比較用に normalize。"""
    return re.sub(r"\s+", "", t.lower().strip())


def dedup_against_issues(
    state: SuggestTopicsState, config: RunnableConfig
) -> dict:
    """A4: 既存 topic/* issue とタイトル比較して重複を除去。

    比較は normalize_title (空白除去 + lowercase) ベース。
    gh CLI 失敗時は dedup を諦めて全 candidates を通す。
    """
    lcfg = _get_libmatic_config(config)
    if not state.filtered_candidates:
        return {"filtered_candidates": []}

    labels = lcfg.github.issue_labels
    try:
        existing = gh_issue_list_core(
            labels=[
                labels.pending,
                labels.ready,
                labels.in_progress,
                labels.review,
            ],
            state="all",
            limit=200,
        )
    except Exception:
        existing = []

    existing_norms = {
        _normalize_title(str(i.get("title", ""))) for i in existing
    }

    deduplicated: list[TopicCandidate] = [
        c for c in state.filtered_candidates
        if _normalize_title(c.title) not in existing_norms
    ]
    return {"filtered_candidates": deduplicated}


# --- A5: create_issues (deterministic) ---


def create_issues(state: SuggestTopicsState, config: RunnableConfig) -> dict:
    """A5: filtered_candidates を topic/pending issue として起票。

    各 candidate の起票失敗は skip して残りを継続 (個別失敗で全体落とさない)。
    """
    lcfg = _get_libmatic_config(config)
    labels_cfg = lcfg.github.issue_labels

    created: list[int] = []
    for c in state.filtered_candidates:
        # body 末尾に source_urls / lifespan 情報を append
        body_lines = [c.body, ""]
        body_lines.append(f"**lifespan**: {c.lifespan}")
        if c.source_urls:
            body_lines.append("")
            body_lines.append("**source_urls**:")
            for u in c.source_urls:
                body_lines.append(f"- {u}")
        full_body = "\n".join(body_lines)

        try:
            num = gh_issue_create_core(
                title=c.title,
                body=full_body,
                labels=[labels_cfg.pending],
            )
            created.append(num)
        except Exception:
            continue
    return {"created_issues": created}


# --- A6: propose_new_sources (conditional + deterministic) ---


def _extract_known_domains(feeds: list[str]) -> set[str]:
    """priorities から展開された feed URL から host だけ取り出す。"""
    domains: set[str] = set()
    for f in feeds:
        try:
            d = urlparse(f).netloc.lower()
            if d:
                domains.add(d)
        except Exception:
            continue
    return domains


def propose_new_sources(
    state: SuggestTopicsState, config: RunnableConfig
) -> dict:
    """A6: priorities に未登録の domain で 2 件以上登場したものを検出。

    v0.1 では検出のみ (state.new_sources_detected に格納)。
    PR 自動作成は将来拡張 (proposal_pr_number は None のまま)。
    """
    _get_libmatic_config(config)

    known = _extract_known_domains(state.feeds)
    counts = Counter(
        c.get("domain", "") for c in state.raw_candidates if c.get("domain")
    )

    new_sources = [
        {"domain": d, "count": cnt}
        for d, cnt in counts.items()
        if d and d not in known and cnt >= 2
    ]

    return {
        "new_sources_detected": new_sources,
        "proposal_pr_number": None,
    }
