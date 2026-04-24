"""Generic web fetch / search tools.

- web_fetch: URL → text (trafilatura 優先、stdlib fallback)
- web_search: v0.1 では LLM provider の built-in search (Anthropic web_search_*
    や tavily 相当) を ReAct agent に bind して使う前提で placeholder。
"""

from __future__ import annotations

import html as html_module
import re
import urllib.error
import urllib.request

try:
    import trafilatura  # type: ignore[import-untyped]

    _HAS_TRAFILATURA = True
except ImportError:
    _HAS_TRAFILATURA = False

from langchain_core.tools import tool

USER_AGENT = "Mozilla/5.0 (compatible; libmatic/0.1)"
DEFAULT_TIMEOUT = 30


def http_get(url: str, timeout: int = DEFAULT_TIMEOUT) -> str | None:
    """HTTP GET (UTF-8 decoded)。失敗時は None。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None
    except Exception:
        return None


def _stdlib_html_to_text(html: str) -> str:
    """trafilatura 不在時の fallback: 正規表現ベースの簡易抽出。"""
    cleaned = re.sub(
        r"<(script|style|nav|header|footer|aside|svg)[^>]*>.*?</\1>",
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    m = re.search(r"<(article|main)[^>]*>(.*?)</\1>", cleaned, re.DOTALL | re.IGNORECASE)
    if m:
        body = m.group(2)
    else:
        mb = re.search(r"<body[^>]*>(.*?)</body>", cleaned, re.DOTALL | re.IGNORECASE)
        body = mb.group(1) if mb else cleaned
    body = re.sub(r"<br\s*/?>", "\n", body, flags=re.IGNORECASE)
    body = re.sub(r"</p\s*>", "\n\n", body, flags=re.IGNORECASE)
    body = re.sub(r"</(div|section|li|h[1-6])\s*>", "\n", body, flags=re.IGNORECASE)
    body = re.sub(r"<[^>]+>", "", body)
    body = html_module.unescape(body)
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n[ \t]+", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def web_fetch_core(url: str) -> str:
    """URL を取得し、本文テキストを返す。失敗時は空文字列。"""
    html = http_get(url)
    if html is None:
        return ""
    if _HAS_TRAFILATURA:
        try:
            text = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=True,
                output_format="markdown",
                favor_precision=True,
            )
            if text:
                return text
        except Exception:
            pass
    return _stdlib_html_to_text(html)


@tool
def web_fetch(url: str) -> str:
    """URL を取得し、本文 Markdown / text を返す (trafilatura 優先)。

    取得失敗時は空文字列を返す (呼出側で判定)。
    """
    return web_fetch_core(url)


@tool
def web_search(query: str, max_results: int = 10) -> list[dict]:
    """Web 検索を実行して結果を list[dict] で返す (placeholder)。

    Phase 0 方針 (libmatic-oss-plan.md §3.2): v0.1 では LLM provider の
    built-in search (Anthropic の web_search_20250305 など) を ReAct agent に
    直接 bind する方針。このツールは将来的に tavily 等を使いたい人向けの
    拡張ポイントとして残す。node 実装時に provider-native 側で解決。
    """
    raise NotImplementedError(
        "v0.1 は LLM の built-in web search を ReAct agent に bind して使う想定。"
        "tavily 等を差し込みたい場合はこの関数を差し替える。"
    )
