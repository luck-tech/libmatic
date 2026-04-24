"""Web fetch / search tools (Phase 1.3 stub, Phase 1.4 で本実装)."""

from __future__ import annotations

from langchain_core.tools import tool


@tool
def web_fetch(url: str) -> str:
    """URL を取得し、trafilatura で本文抽出した text を返す。"""
    raise NotImplementedError("Phase 1.4 で実装 (trafilatura 利用)")


@tool
def web_search(query: str, max_results: int = 10) -> list[dict]:
    """Web 検索を実行し、結果を list of dict で返す。

    v0.1 では Tavily or Anthropic built-in search を利用予定 (実装時に決定)。
    """
    raise NotImplementedError("Phase 1.4 で実装")
