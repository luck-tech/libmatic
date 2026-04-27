"""SqliteSaver wrapper for v0.1 (local file checkpointer).

LangGraph の SqliteSaver を context manager として返すラッパー。
v0.1 は local sqlite のみ。GH Actions artifact 方式は v1.0 で追加予定。

使い方:

    from libmatic.checkpointer import open_checkpointer

    with open_checkpointer() as saver:
        graph = build_topic_debate_graph().compile(checkpointer=saver)
        graph.invoke(state, config={"configurable": {
            "libmatic_config": cfg,
            "thread_id": "topic-debate-18-20260424",
        }})
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver


def default_db_path() -> Path:
    """libmatic 標準の checkpointer 保存先 ~/.libmatic/state.sqlite。"""
    return Path.home() / ".libmatic" / "state.sqlite"


@contextmanager
def open_checkpointer(db_path: str | Path | None = None) -> Iterator[Any]:
    """SqliteSaver を context manager として開く。

    Args:
        db_path: 保存先 sqlite ファイル。None なら default_db_path()。
            ":memory:" を渡すと in-memory (test 用)。

    Yields:
        SqliteSaver: LangGraph compile() に渡せる checkpointer。

    親ディレクトリは自動作成される。
    """
    if db_path is None:
        path = default_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn_string = str(path)
    elif str(db_path) == ":memory:":
        conn_string = ":memory:"
    else:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn_string = str(path)

    with SqliteSaver.from_conn_string(conn_string) as saver:
        yield saver


def build_thread_id(workflow: str, primary_key: int | str, *, date: str | None = None) -> str:
    """libmatic 標準の thread_id を組み立てる。

    Format: `{workflow}-{primary_key}-{YYYYMMDD}`
    例: `topic-debate-18-20260424`
    """
    if date is None:
        from datetime import UTC, datetime
        date = datetime.now(UTC).strftime("%Y%m%d")
    return f"{workflow}-{primary_key}-{date}"
