"""Node implementations for topic-debate workflow.

実装状況 (Phase 1.3 残り):
- deterministic 完了: source_scorer (step 2), source_fetcher (step 3), pr_opener (step 9)
- hybrid 未実装: coverage_verifier (step 6) — 次 PR
- ReAct 未実装: source_collector / fact_extractor / fact_merger /
  article_writer / expanded_writer — 次 PR (prompts/ 執筆を伴う)
- conditional edge: coverage_gate は config から閾値を取る形に更新
"""

from __future__ import annotations

import json
import math
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from libmatic.agents.react import build_step_agent
from libmatic.config import LibmaticConfig
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
from libmatic.state.topic_debate import Fact, Source, TopicDebateState
from libmatic.tools.coverage import CoverageReport, verify_coverage_core
from libmatic.tools.fs import read_file
from libmatic.tools.github import gh_issue_edit_core, gh_pr_create_core
from libmatic.tools.search_sources import search_sources
from libmatic.tools.source import fetch_source_core
from libmatic.tools.web import web_fetch

# --- Step 1: source_collector (ReAct) ---


DEFAULT_SOURCE_PRIORITIES_PATH = "config/source_priorities.yml"


def _coerce_source_from_raw(raw: Any) -> Source | None:
    """LLM 出力の 1 要素 (dict) を Source に変換。失敗時は None。"""
    if not isinstance(raw, dict) or not raw.get("url"):
        return None
    try:
        return Source(
            url=str(raw["url"]),
            type=str(raw.get("type") or "generic"),  # type: ignore[arg-type]
            title=str(raw.get("title") or raw["url"]),
            published_at=(raw.get("published_at") or None) or None,
        )
    except Exception:
        return None


def source_collector(state: TopicDebateState, config: RunnableConfig) -> dict:
    """Step 1 (ReAct): 信頼発信者 + web 検索から candidate sources を収集。

    agent は `search_sources` / `web_fetch` / `read_file` を使って候補を探索し、
    最終 message で JSON array of {url, type, title, published_at} を返す。
    """
    lcfg = _get_libmatic_config(config)

    agent = build_step_agent(
        step_name="step1_source_collector",
        config=lcfg,
        tools=[search_sources, web_fetch, read_file],
        system_prompt=load_prompt("topic_debate/step1_source_collector.md"),
    )
    input_text = (
        f"## テーマ\n{state.issue_title}\n\n"
        f"## issue 本文\n{state.issue_body}\n\n"
        f"## lifespan\n{state.lifespan}\n\n"
        f"## source_priorities_path\n{DEFAULT_SOURCE_PRIORITIES_PATH}\n"
    )

    try:
        result = agent.invoke({"messages": [HumanMessage(content=input_text)]})
        content = _last_message_content(result)
        raw_candidates = _parse_json_array(content)
    except Exception:
        raw_candidates = []

    candidates: list[Source] = []
    for raw in raw_candidates:
        src = _coerce_source_from_raw(raw)
        if src is not None:
            candidates.append(src)
    return {"candidate_sources": candidates}


# --- Step 2: source_scorer (deterministic) ---


def _recency_decay(published_at: str | None, half_life_days: int = 180) -> float:
    """published_at からの経過日数で指数減衰 (半減期 half_life_days 日)."""
    if not published_at:
        return 1.0
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return 1.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta_days = (datetime.now(UTC) - dt).total_seconds() / 86400
    if delta_days < 0:
        return 1.0
    return math.exp(-delta_days / half_life_days)


def _tokenize(text: str) -> set[str]:
    """ASCII 英数 + 非 ASCII トークン (2 文字以上) を lowercase set で返す。"""
    words = re.findall(r"[A-Za-z0-9]+|[^\x00-\x7f]+", text)
    return {w.lower() for w in words if len(w) >= 2}


def _relevance(source_title: str, issue_title: str) -> float:
    """Theme title と source title の Jaccard 係数 (0 <= r <= 1)."""
    issue_tokens = _tokenize(issue_title)
    source_tokens = _tokenize(source_title)
    if not issue_tokens or not source_tokens:
        return 0.0
    overlap = issue_tokens & source_tokens
    return len(overlap) / len(issue_tokens)


def _priority_weight(source: Source) -> float:
    """source.score に priority 情報が乗っていればそれを使う。無ければ 1.0。"""
    return source.score if source.score > 0 else 1.0


def score_source(source: Source, issue_title: str) -> float:
    """source の総合スコア。priority × recency × relevance。"""
    return (
        _priority_weight(source)
        * _recency_decay(source.published_at)
        * _relevance(source.title, issue_title)
    )


def source_scorer(state: TopicDebateState, config: RunnableConfig) -> dict:
    """Step 2 (deterministic): candidate_sources をスコアリングして上位 N 件に絞る。"""
    lcfg = _get_libmatic_config(config)
    limit = lcfg.workflow.max_sources_per_topic

    scored_pairs: list[tuple[float, Source]] = [
        (score_source(s, state.issue_title), s) for s in state.candidate_sources
    ]
    scored_pairs.sort(key=lambda x: x[0], reverse=True)

    scored_sources = [
        s.model_copy(update={"score": sc}) for sc, s in scored_pairs[:limit]
    ]
    return {"scored_sources": scored_sources}


# --- Step 3: source_fetcher (deterministic, ThreadPoolExecutor で並列) ---


def _fetch_one(source: Source) -> Source:
    """単一 source を fetch。元の score を引き継ぐ。"""
    result = fetch_source_core(source.url)
    if source.score > 0:
        result = result.model_copy(update={"score": source.score})
    return result


def source_fetcher(state: TopicDebateState, config: RunnableConfig) -> dict:
    """Step 3 (deterministic + ThreadPool): scored_sources を並列 fetch する。"""
    lcfg = _get_libmatic_config(config)
    max_workers = max(1, lcfg.workflow.max_concurrent_fetches)

    if not state.scored_sources:
        return {"fetched_sources": []}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        fetched = list(executor.map(_fetch_one, state.scored_sources))

    # loop back 時は coverage_loop_count をインクリメント
    update: dict = {"fetched_sources": fetched}
    if state.coverage_loop_count > 0 or state.fetched_sources:
        # 2 周目以降: loop カウンタを維持 (step 6 側で +1 する設計)
        pass
    return update


# --- Step 4-8: ReAct / hybrid node (次 PR で実装) ---


FACT_CONTENT_TRUNCATE = 8000


def _coerce_fact_from_raw(raw: Any) -> Fact | None:
    """LLM 出力の 1 要素 (dict) を Fact に変換。失敗時は None。"""
    if not isinstance(raw, dict) or not raw.get("claim"):
        return None
    try:
        return Fact(
            claim=str(raw["claim"]),
            source_urls=[str(u) for u in (raw.get("source_urls") or []) if u],
            confidence=str(raw.get("confidence") or "medium"),  # type: ignore[arg-type]
            category=str(raw.get("category") or "general"),
        )
    except Exception:
        return None


def fact_extractor(state: TopicDebateState, config: RunnableConfig) -> dict:
    """Step 4 (ReAct): fetched_sources の全 source から facts を構造化抽出。

    v0.1 では per-source 並列化は諦め、全 source を 1 回の invoke に渡す。
    戻り値は state.raw_facts_per_source (list[list[Fact]]) に合わせて
    `[flat_facts]` の 1 要素 list に格納。
    """
    lcfg = _get_libmatic_config(config)

    valid_sources = [s for s in state.fetched_sources if s.fetched_content]
    if not valid_sources:
        return {"raw_facts_per_source": []}

    agent = build_step_agent(
        step_name="step4_fact_extractor",
        config=lcfg,
        tools=[],
        system_prompt=load_prompt("topic_debate/step4_fact_extractor.md"),
    )

    sources_payload: list[dict] = []
    for i, s in enumerate(valid_sources):
        content_trunc = (s.fetched_content or "")[:FACT_CONTENT_TRUNCATE]
        sources_payload.append(
            {
                "id": f"src{i}",
                "url": s.url,
                "type": s.type,
                "title": s.title,
                "fetched_content": content_trunc,
            }
        )

    input_text = (
        f"## テーマ\n{state.issue_title}\n\n"
        f"## lifespan\n{state.lifespan}\n\n"
        f"## sources\n{json.dumps(sources_payload, ensure_ascii=False)}\n"
    )

    try:
        result = agent.invoke({"messages": [HumanMessage(content=input_text)]})
        content = _last_message_content(result)
        raw_facts = _parse_json_array(content)
    except Exception:
        raw_facts = []

    facts: list[Fact] = []
    for raw in raw_facts:
        f = _coerce_fact_from_raw(raw)
        if f is not None:
            facts.append(f)

    return {"raw_facts_per_source": [facts] if facts else []}


def fact_merger(state: TopicDebateState, config: RunnableConfig) -> dict:
    """Step 5 (ReAct): raw_facts_per_source を dedup + 階層化 + 衝突解決。"""
    lcfg = _get_libmatic_config(config)

    all_raw_facts: list[Fact] = [
        f for per_source in state.raw_facts_per_source for f in per_source
    ]
    if not all_raw_facts:
        return {"merged_facts": []}

    agent = build_step_agent(
        step_name="step5_fact_merger",
        config=lcfg,
        tools=[],
        system_prompt=load_prompt("topic_debate/step5_fact_merger.md"),
    )

    raw_payload = [f.model_dump() for f in all_raw_facts]
    input_text = (
        f"## テーマ\n{state.issue_title}\n\n"
        f"## lifespan\n{state.lifespan}\n\n"
        f"## raw_facts_per_source\n{json.dumps(raw_payload, ensure_ascii=False)}\n"
    )

    try:
        result = agent.invoke({"messages": [HumanMessage(content=input_text)]})
        content = _last_message_content(result)
        merged_raw = _parse_json_array(content)
    except Exception:
        merged_raw = []

    merged: list[Fact] = []
    for raw in merged_raw:
        f = _coerce_fact_from_raw(raw)
        if f is not None:
            merged.append(f)

    return {"merged_facts": merged}


def _facts_to_claims_archive(facts: list[Fact]) -> list[dict]:
    """Fact のリストを verify_coverage_core が期待する claims_archive 形式に変換する。

    各 Fact の source_urls を見て source 単位でグルーピング。
    Fact に verbatim / relevance_to_theme フィールドが無い現行 v0.1 では:
      - verbatim は claim と同じ文字列を使う (coverage 検証では probe として使われる)
      - relevance_to_theme は 'primary' 固定 (将来 Fact に追加予定)
    """
    by_source: dict[str, list[tuple[int, Fact]]] = {}
    for i, f in enumerate(facts):
        source_urls = f.source_urls or ["unknown"]
        for url in source_urls:
            by_source.setdefault(url, []).append((i, f))

    archive: list[dict] = []
    for source_url, indexed in by_source.items():
        claims: list[dict] = []
        for i, f in indexed:
            claims.append(
                {
                    "id": f"c{i}",
                    "text": f.claim,
                    "verbatim": f.claim,
                    "relevance_to_theme": "primary",
                    "category": f.category,
                }
            )
        archive.append({"source_id": source_url, "claims": claims})
    return archive


def _format_step6_input(
    state: TopicDebateState, report: CoverageReport | None
) -> str:
    """LLM judge に渡す入力テキストを組み立てる。"""
    lines = [
        f"## テーマ\n{state.issue_title}",
        "",
        f"## issue 本文\n{state.issue_body}",
        "",
        f"## lifespan\n{state.lifespan}",
        "",
    ]
    if report is not None:
        lines.append(
            f"## 数値カバレッジ\n- 全体: {report.combined.covered}/{report.combined.total} "
            f"({report.combined.rate:.1f}%)"
        )
        lines.append("")
        lines.append(f"## 未反映 claim 一覧 ({len(report.combined.uncovered)} 件)")
        # 多すぎると token 食うので 40 件に truncate
        for u in report.combined.uncovered[:40]:
            lines.append(f"- [{u.relevance}/{u.category}] {u.text}")
    else:
        lines.append("## 数値カバレッジ\nfacts が空のため計算できず")
    return "\n".join(lines)


# NOTE: _last_message_content / _parse_json_array は libmatic.nodes._helpers
# に切り出し済み (import で参照)。

def _parse_gaps_json(content: str) -> list[str]:
    """LLM 出力から JSON array を抽出し、非空文字列のリストにする。"""
    data = _parse_json_array(content)
    return [str(x) for x in data if x]


def coverage_verifier(state: TopicDebateState, config: RunnableConfig) -> dict:
    """Step 6 (hybrid): verify_coverage で数値算出 + LLM judge で gap を言語化。

    - article_draft があればそれを検証対象、無ければ issue_body を対象にして
      「facts がテーマの論点をカバーできているか」を代理検証する
    - coverage_loop_count はこの node で +1 (次の coverage_gate で loop 判定に使う)
    - facts 空 / LLM 失敗 時は gap を空で返し、score は 0 か数値計算結果に従う
    """
    lcfg = _get_libmatic_config(config)

    # 1. 数値カバレッジ (verify_coverage tool を pure 関数として呼ぶ)
    claims_archive = _facts_to_claims_archive(state.merged_facts)
    article_text = state.article_draft or state.issue_body

    report: CoverageReport | None = None
    coverage_score = 0.0
    if claims_archive:
        try:
            report = verify_coverage_core(
                claims_archive=claims_archive,
                articles=[article_text],
                combined_threshold=lcfg.workflow.coverage_threshold * 100,
            )
            coverage_score = report.combined.rate / 100.0
        except ValueError:
            # articles 空の ValueError — article_text が "" のとき発生しうる
            coverage_score = 0.0
            report = None

    # 2. LLM judge で gap を言語化
    agent = build_step_agent(
        step_name="step6_coverage_verifier",
        config=lcfg,
        tools=[],
        system_prompt=load_prompt("topic_debate/step6_coverage_verifier.md"),
    )
    input_text = _format_step6_input(state, report)
    try:
        result = agent.invoke({"messages": [HumanMessage(content=input_text)]})
        last_content = _last_message_content(result)
        gaps = _parse_gaps_json(last_content)
    except Exception:
        # LLM 呼出が失敗しても node 全体は落とさない (数値側の判定だけ残す)
        gaps = []

    return {
        "coverage_score": coverage_score,
        "coverage_gaps": gaps,
        "coverage_loop_count": state.coverage_loop_count + 1,
    }


def _infer_category(title: str, body: str, categories: list[str]) -> str:
    """issue title + body から content category を推定 (v0.1 は簡易 token match)。

    カテゴリ名 (ハイフン含む・除く両方) が本文に含まれていれば採用、
    何もマッチしなければ `fundamentals` or categories[0]。
    """
    text = f"{title} {body}".lower()
    for cat in categories:
        cat_lower = cat.lower()
        if cat_lower in text or cat_lower.replace("-", " ") in text:
            return cat
    if "fundamentals" in categories:
        return "fundamentals"
    return categories[0] if categories else "fundamentals"


def _determine_output_path(state: TopicDebateState, lcfg: LibmaticConfig) -> str:
    """lifespan + category + slug から記事の保存先 path を決める。

    - universal: content/{category}/notes/<slug>.md
    - ephemeral: content/digest/{year}/Q{quarter}/<slug>.md
    """
    category = _infer_category(state.issue_title, state.issue_body, lcfg.content.categories)
    slug = _slugify(state.issue_title)

    if state.lifespan == "universal":
        rendered = lcfg.content.universal_dir.format(category=category)
    else:
        now = datetime.now(UTC)
        quarter = (now.month - 1) // 3 + 1
        rendered = lcfg.content.ephemeral_dir.format(year=now.year, quarter=quarter)

    return f"{rendered}/{slug}.md"


def article_writer(state: TopicDebateState, config: RunnableConfig) -> dict:
    """Step 7 (ReAct): merged_facts を元に原本記事 Markdown を執筆。

    出力先 `output_path` を lifespan と category から決定して state に格納する。
    """
    lcfg = _get_libmatic_config(config)

    agent = build_step_agent(
        step_name="step7_article_writer",
        config=lcfg,
        tools=[],
        system_prompt=load_prompt("topic_debate/step7_article_writer.md"),
    )

    facts_payload = [f.model_dump() for f in state.merged_facts]
    input_text = (
        f"## テーマ\n{state.issue_title}\n\n"
        f"## issue 本文\n{state.issue_body}\n\n"
        f"## lifespan\n{state.lifespan}\n\n"
        f"## merged_facts\n{json.dumps(facts_payload, ensure_ascii=False)}\n\n"
        f"## coverage_gaps\n{json.dumps(state.coverage_gaps, ensure_ascii=False)}\n"
    )

    try:
        result = agent.invoke({"messages": [HumanMessage(content=input_text)]})
        article = _last_message_content(result)
    except Exception:
        article = ""

    output_path = _determine_output_path(state, lcfg)

    return {
        "article_draft": article,
        "output_path": output_path,
    }


def expanded_writer(state: TopicDebateState, config: RunnableConfig) -> dict:
    """Step 8 (ReAct): article_draft を初学者向けに再構成した拡張版を執筆。"""
    lcfg = _get_libmatic_config(config)

    agent = build_step_agent(
        step_name="step8_expanded_writer",
        config=lcfg,
        tools=[],
        system_prompt=load_prompt("topic_debate/step8_expanded_writer.md"),
    )

    facts_payload = [f.model_dump() for f in state.merged_facts]
    input_text = (
        f"## テーマ\n{state.issue_title}\n\n"
        f"## lifespan\n{state.lifespan}\n\n"
        f"## article_draft\n{state.article_draft}\n\n"
        f"## merged_facts\n{json.dumps(facts_payload, ensure_ascii=False)}\n"
    )

    try:
        result = agent.invoke({"messages": [HumanMessage(content=input_text)]})
        expanded = _last_message_content(result)
    except Exception:
        expanded = ""

    return {"article_expanded": expanded}


# --- Step 9: pr_opener (deterministic) ---


def _slugify(title: str, max_len: int = 80) -> str:
    """タイトルから git branch 用の slug を作る。

    英数字 / ハイフン / 日本語文字を残し、それ以外は '-' に置換。
    連続ハイフンは 1 つに、前後のハイフンは除去。
    """
    s = title.lower()
    s = re.sub(r"[^a-z0-9぀-ヿ一-鿿]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:max_len] or "untitled"


def _run_git(args: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(["git", *args], check=True, cwd=cwd)


def pr_opener(state: TopicDebateState, config: RunnableConfig) -> dict:
    """Step 9 (deterministic): branch 切り → 2 ファイル commit → push → PR 作成。

    副作用:
    - state.output_path に原本を書き込み、同じディレクトリに
      '{stem}-explained.md' で拡張版を書き込む
    - git checkout -b topic/{slug} → add → commit → push
    - gh_pr_create_core で PR 作成
    - issue ラベル in_progress → review に遷移
    """
    lcfg = _get_libmatic_config(config)
    labels = lcfg.github.issue_labels

    slug = _slugify(state.issue_title)
    branch = f"topic/{slug}"

    original_path = Path(state.output_path)
    expanded_path = original_path.with_name(f"{original_path.stem}-explained.md")

    # 1. 記事 2 ファイルを書き出し
    original_path.parent.mkdir(parents=True, exist_ok=True)
    original_path.write_text(state.article_draft, encoding="utf-8")
    expanded_path.write_text(state.article_expanded, encoding="utf-8")

    # 2. git branch + commit + push
    commit_msg = f"feat(notes): {state.issue_title} (#{state.issue_number})"
    _run_git(["checkout", "-b", branch])
    _run_git(["add", str(original_path), str(expanded_path)])
    _run_git(["commit", "-m", commit_msg])
    _run_git(["push", "-u", "origin", branch])

    # 3. PR 作成
    pr_body = f"Closes #{state.issue_number}\n\n{state.issue_body}"
    pr = gh_pr_create_core(
        branch=branch,
        title=f"feat(notes): {state.issue_title}",
        body=pr_body,
    )

    # 4. issue ラベル遷移 (in_progress → review)
    gh_issue_edit_core(
        state.issue_number,
        add_labels=[labels.review],
        remove_labels=[labels.in_progress],
    )

    return {
        "pr_number": pr["number"],
        "pr_url": pr["url"],
    }


# --- Conditional edge: coverage_gate ---


def coverage_gate(state: TopicDebateState, config: RunnableConfig) -> str:
    """Step 6 の結果で step 3 ループ or step 7 へ進むかを決める。

    - coverage_score >= threshold → step 7 (article_writer)
    - coverage_loop_count >= max_coverage_loops → step 7 (諦めて進む)
    - それ以外 → step 3 (loop back)

    config から threshold / max_loops を取るので、LibmaticConfig の workflow
    設定で挙動が変わる。
    """
    lcfg = _get_libmatic_config(config)
    if state.coverage_score >= lcfg.workflow.coverage_threshold:
        return "step7_article_writer"
    if state.coverage_loop_count >= lcfg.workflow.max_coverage_loops:
        return "step7_article_writer"
    return "step3_source_fetcher"
