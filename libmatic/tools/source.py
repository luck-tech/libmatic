"""Source-specific fetch tools (Phase 1.3 stub).

Phase 1.4 で scripts/fetch_source.py と scripts/fetch_x.py を移植。
"""

from __future__ import annotations

from langchain_core.tools import tool


@tool
def fetch_source(url: str) -> dict:
    """URL の type (rss/youtube/x/zenn/qiita/github/rfc/generic) を判定し、取得。

    戻り値は Source スキーマ相当の dict:
    {url, type, title, published_at, fetched_content}
    """
    raise NotImplementedError("Phase 1.4 で実装 (scripts/fetch_source.py の移植)")


@tool
def fetch_x_thread(url: str) -> str:
    """X スレッドを fxtwitter 経由で取得し、text を返す。"""
    raise NotImplementedError("Phase 1.4 で実装 (scripts/fetch_x.py の移植)")
