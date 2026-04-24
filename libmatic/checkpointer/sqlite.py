"""SqliteSaver wrapper for v0.1 (local file checkpointer).

Phase 0 決定 (libmatic-oss-plan.md §3.3 b):
- v0.1 は local SqliteSaver のみ (~/.libmatic/state.sqlite)
- GH Actions での resume は v0.1 ではサポート外 (9 step で 30 分程度なので失敗時は最初から)
- v1.0 で GH Actions artifact 方式の wrapper を追加
"""

from __future__ import annotations

from pathlib import Path


def default_db_path() -> Path:
    """libmatic 標準の checkpointer 保存先。"""
    return Path.home() / ".libmatic" / "state.sqlite"


def get_checkpointer(db_path: str | Path | None = None):
    """Return a SqliteSaver instance for LangGraph checkpointing.

    Phase 1.3 では signature のみ。実装は Phase 1.6 (CLI resume 実装時) に確定させる
    (langgraph-checkpoint-sqlite のバージョンで context manager の要不要が変わるため)。
    """
    raise NotImplementedError(
        "Phase 1.6 で実装 (CLI の resume コマンド実装と合わせて確定)"
    )
