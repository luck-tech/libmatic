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
from libmatic.prompts.loader import load_prompt
from libmatic.state.topic_debate import Fact, Source, TopicDebateState
from libmatic.tools.coverage import CoverageReport, verify_coverage_core
from libmatic.tools.github import gh_issue_edit_core, gh_pr_create_core
from libmatic.tools.source import fetch_source_core


def _get_libmatic_config(config: RunnableConfig) -> LibmaticConfig:
    """RunnableConfig から LibmaticConfig を取り出す。"""
    configurable = (config or {}).get("configurable") or {}
    lcfg = configurable.get("libmatic_config")
    if not isinstance(lcfg, LibmaticConfig):
        raise ValueError(
            "RunnableConfig.configurable.libmatic_config に "
            "LibmaticConfig インスタンスをセットしてください"
        )
    return lcfg


# --- Step 1: source_collector (ReAct, 次 PR で実装) ---


def source_collector(state: TopicDebateState, config: RunnableConfig) -> dict:
    """Step 1 (ReAct): candidate sources を収集。"""
    raise NotImplementedError(
        "Phase 1.3 次段で ReAct agent を build_step_agent で組み立てる予定"
    )


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


def fact_extractor(state: TopicDebateState, config: RunnableConfig) -> dict:
    """Step 4 (ReAct, Send per source): 各 source から fact を抽出。"""
    raise NotImplementedError("次 PR で ReAct agent として実装")


def fact_merger(state: TopicDebateState, config: RunnableConfig) -> dict:
    """Step 5 (ReAct): fact の dedup と衝突解決。"""
    raise NotImplementedError("次 PR で ReAct agent として実装")


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


def _last_message_content(result: Any) -> str:
    """LangGraph agent の invoke 結果から最後の message の content を string で取る。

    Anthropic 等の structured content (list of {type, text}) も平文化する。
    """
    messages = (result or {}).get("messages", []) if isinstance(result, dict) else []
    if not messages:
        return ""
    last = messages[-1]
    content = getattr(last, "content", None)
    if content is None and isinstance(last, dict):
        content = last.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content) if content is not None else ""


def _parse_gaps_json(content: str) -> list[str]:
    """LLM 出力から JSON array (`[...]`) を抽出し、文字列のリストに。

    - 周辺に余計な前置き/後置き文章があっても最初の `[` と最後の `]` 区間を掴む
    - 解析失敗 / 見つからない → 空リスト
    """
    if not content:
        return []
    # 最初の `[` から最後の `]` まで (貪欲マッチ) を取る
    start = content.find("[")
    end = content.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    snippet = content[start : end + 1]
    try:
        data = json.loads(snippet)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
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


def article_writer(state: TopicDebateState, config: RunnableConfig) -> dict:
    """Step 7 (ReAct): 原本記事を執筆。"""
    raise NotImplementedError("次 PR で ReAct agent として実装")


def expanded_writer(state: TopicDebateState, config: RunnableConfig) -> dict:
    """Step 8 (ReAct): 初学者向け拡張版を執筆。"""
    raise NotImplementedError("次 PR で ReAct agent として実装")


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
