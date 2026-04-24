"""Node implementations for suggest-topics workflow (Phase 1.3 stub)."""

from __future__ import annotations

from libmatic.state.suggest_topics import SuggestTopicsState


def load_priorities(state: SuggestTopicsState) -> dict:
    """A1 (deterministic): config/source_priorities.yml を読んで構造化。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def fetch_candidates(state: SuggestTopicsState) -> dict:
    """A2 (Send fan-out): 各 source から最新エントリを取得。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def relevance_filter(state: SuggestTopicsState) -> dict:
    """A3 (ReAct): lifespan 判定、ephemeral→universal 昇華、ジャンル別除外。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def dedup_against_issues(state: SuggestTopicsState) -> dict:
    """A4 (deterministic): 既存 open topic/* issue との類似度チェック。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def create_issues(state: SuggestTopicsState) -> dict:
    """A5 (deterministic): 生き残った候補を topic/pending として起票。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def propose_new_sources(state: SuggestTopicsState) -> dict:
    """A6 (conditional + deterministic): 条件を満たす未登録 source で PR 提案。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")
