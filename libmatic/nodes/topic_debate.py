"""Node implementations for topic-debate workflow (Phase 1.3 stub).

Phase 1.4 以降で各 node の中身を実装する。
Node 種別: SPEC.md §5 参照。
"""

from __future__ import annotations

from libmatic.state.topic_debate import TopicDebateState

# Default thresholds (config から注入する形で上書き可能)
DEFAULT_COVERAGE_THRESHOLD = 0.80
DEFAULT_MAX_COVERAGE_LOOPS = 2


def source_collector(state: TopicDebateState) -> dict:
    """Step 1 (ReAct): candidate sources を収集。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def source_scorer(state: TopicDebateState) -> dict:
    """Step 2 (deterministic): source をスコアリング。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def source_fetcher(state: TopicDebateState) -> dict:
    """Step 3 (deterministic, Send): 各 source を fetch (並列)。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def fact_extractor(state: TopicDebateState) -> dict:
    """Step 4 (ReAct, Send per source): 各 source から fact を抽出。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def fact_merger(state: TopicDebateState) -> dict:
    """Step 5 (ReAct): fact の dedup と衝突解決。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def coverage_verifier(state: TopicDebateState) -> dict:
    """Step 6 (hybrid): verify_coverage の数値 + LLM judge で gap 抽出。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def article_writer(state: TopicDebateState) -> dict:
    """Step 7 (ReAct): 原本記事を執筆。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def expanded_writer(state: TopicDebateState) -> dict:
    """Step 8 (ReAct): 初学者向け拡張版を執筆。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def pr_opener(state: TopicDebateState) -> dict:
    """Step 9 (deterministic): git + gh pr create で PR 発行。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def coverage_gate(state: TopicDebateState) -> str:
    """Conditional edge: step 6 の結果で step 3 ループ or step 7 へ進む。

    Phase 0 決定 (SPEC §7):
    - coverage_score >= threshold or loop_count >= max_loops → step 7
    - それ以外 → step 3 (loop back)
    """
    if state.coverage_score >= DEFAULT_COVERAGE_THRESHOLD:
        return "step7_article_writer"
    if state.coverage_loop_count >= DEFAULT_MAX_COVERAGE_LOOPS:
        return "step7_article_writer"
    return "step3_source_fetcher"
