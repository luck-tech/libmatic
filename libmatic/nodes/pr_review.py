"""Node implementations for address-pr-comments workflow (Phase 1.3 stub)."""

from __future__ import annotations

from libmatic.state.pr_review import PRReviewState


def collect_comments(state: PRReviewState) -> dict:
    """C1 (deterministic): gh api で PR の review comments を取得。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def classify_comments(state: PRReviewState) -> dict:
    """C2 (ReAct): 各 comment を address / reply / ignore に分類。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def address_each(state: PRReviewState) -> dict:
    """C3 (ReAct loop): address 分類された comment 毎に fetch → edit → stage。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def commit_push(state: PRReviewState) -> dict:
    """C4 (deterministic): git commit + git push。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")


def reply_comments(state: PRReviewState) -> dict:
    """C5 (deterministic): gh api で reply を投稿。"""
    raise NotImplementedError("Phase 1.3 の次段で実装")
