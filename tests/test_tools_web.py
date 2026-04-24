"""Tests for libmatic.tools.web (Phase 1.4 PoC #4, web_fetch)."""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from libmatic.tools.web import _stdlib_html_to_text, web_fetch_core

web_mod = importlib.import_module("libmatic.tools.web")


SAMPLE_HTML = """<!DOCTYPE html>
<html>
<head><title>テスト</title></head>
<body>
  <nav>ナビ</nav>
  <article>
    <h1>見出し</h1>
    <p>本文段落 1</p>
    <p>本文段落 2</p>
  </article>
  <footer>フッター</footer>
</body>
</html>
"""


# --- _stdlib_html_to_text ---


def test_stdlib_html_to_text_extracts_article() -> None:
    text = _stdlib_html_to_text(SAMPLE_HTML)
    assert "本文段落 1" in text
    assert "本文段落 2" in text
    assert "ナビ" not in text
    assert "フッター" not in text


def test_stdlib_html_to_text_handles_entities() -> None:
    html = "<body><p>A &amp; B</p></body>"
    assert "A & B" in _stdlib_html_to_text(html)


def test_stdlib_html_to_text_falls_back_to_body() -> None:
    # article / main が無くても body から抽出
    html = "<body><p>body のみ</p></body>"
    assert "body のみ" in _stdlib_html_to_text(html)


def test_stdlib_html_to_text_removes_scripts() -> None:
    html = "<body><script>var x=1;</script><p>見える本文</p></body>"
    text = _stdlib_html_to_text(html)
    assert "見える本文" in text
    assert "var x=1" not in text


# --- web_fetch_core ---


def test_web_fetch_core_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_mod, "http_get", lambda url, timeout=30: SAMPLE_HTML)
    text = web_fetch_core("https://example.com/a")
    # trafilatura または stdlib fallback、いずれでも本文段落は残る
    assert "本文段落" in text


def test_web_fetch_core_http_failure_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(web_mod, "http_get", lambda url, timeout=30: None)
    assert web_fetch_core("https://bad.example/404") == ""


def test_web_fetch_core_falls_back_if_trafilatura_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """trafilatura が None を返す (抽出失敗) 場合、stdlib fallback に切り替わる。"""
    monkeypatch.setattr(web_mod, "http_get", lambda url, timeout=30: SAMPLE_HTML)
    if web_mod._HAS_TRAFILATURA:
        # trafilatura.extract を None を返すように差し替え
        def fake_extract(*args: Any, **kwargs: Any) -> str | None:
            return None

        monkeypatch.setattr(web_mod.trafilatura, "extract", fake_extract)
    text = web_fetch_core("https://example.com/a")
    # fallback で stdlib による抽出ができている
    assert "本文段落" in text


def test_web_fetch_core_trafilatura_exception_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """trafilatura が例外を上げても stdlib fallback で生き残る。"""
    monkeypatch.setattr(web_mod, "http_get", lambda url, timeout=30: SAMPLE_HTML)
    if web_mod._HAS_TRAFILATURA:
        def fake_extract(*args: Any, **kwargs: Any) -> str | None:
            raise RuntimeError("oops")

        monkeypatch.setattr(web_mod.trafilatura, "extract", fake_extract)
    text = web_fetch_core("https://example.com/a")
    assert "本文段落" in text


# --- @tool wrapper ---


def test_web_fetch_tool_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    from libmatic.tools.web import web_fetch

    monkeypatch.setattr(web_mod, "http_get", lambda url, timeout=30: SAMPLE_HTML)
    result = web_fetch.invoke({"url": "https://example.com/a"})
    assert isinstance(result, str)
    assert "本文段落" in result


def test_web_search_tool_raises_not_implemented() -> None:
    from libmatic.tools.web import web_search

    with pytest.raises(NotImplementedError):
        web_search.invoke({"query": "test"})
