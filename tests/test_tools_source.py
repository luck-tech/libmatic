"""Tests for libmatic.tools.source (Phase 1.4 PoC #3, URL dispatcher)."""

from __future__ import annotations

import importlib
import json
import subprocess
from typing import Any

import pytest

from libmatic.state.topic_debate import Source
from libmatic.tools.source import (
    classify,
    extract_published_at,
    extract_title,
    extract_youtube_id,
    fetch_github_core,
    fetch_qiita_core,
    fetch_rfc_core,
    fetch_source_core,
    fetch_web_core,
    fetch_youtube_core,
    fetch_zenn_core,
    strip_html_to_text,
)

# Module object for monkey-patching http_get and subprocess.run
source_mod = importlib.import_module("libmatic.tools.source")


# --- classify ---


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.youtube.com/watch?v=abc", "youtube"),
        ("https://youtu.be/abc", "youtube"),
        ("https://x.com/user/status/1", "x"),
        ("https://twitter.com/user/status/1", "x"),
        ("https://zenn.dev/foo/articles/bar", "zenn"),
        ("https://qiita.com/foo/items/bar", "qiita"),
        ("https://github.com/foo/bar", "github"),
        ("https://www.rfc-editor.org/rfc/rfc8707", "rfc"),
        ("https://datatracker.ietf.org/doc/html/rfc8707", "rfc"),
        ("https://example.com/post", "generic"),
    ],
)
def test_classify(url: str, expected: str) -> None:
    assert classify(url) == expected


# --- extract_youtube_id ---


def test_extract_youtube_id_from_v_param() -> None:
    assert extract_youtube_id("https://www.youtube.com/watch?v=abc123XYZ") == "abc123XYZ"


def test_extract_youtube_id_from_youtu_be() -> None:
    assert extract_youtube_id("https://youtu.be/xyz789ABC") == "xyz789ABC"


def test_extract_youtube_id_fallback_sha1() -> None:
    # v パラメータも youtu.be も無い場合は sha1 の先頭 11 文字
    vid = extract_youtube_id("https://www.youtube.com/some-other-path")
    assert len(vid) == 11


# --- strip_html_to_text ---


SAMPLE_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>テスト記事</title>
  <meta property="og:title" content="OG タイトル" />
  <meta property="article:published_time" content="2026-04-24T10:00:00Z" />
</head>
<body>
  <nav>ナビは除去される</nav>
  <article>
    <h1>本文見出し</h1>
    <p>本文段落 1</p>
    <p>本文段落 2</p>
  </article>
  <footer>フッターは除去される</footer>
</body>
</html>
"""


def test_strip_html_to_text_keeps_article_content() -> None:
    out = strip_html_to_text(SAMPLE_HTML)
    assert "本文段落 1" in out
    assert "本文段落 2" in out


def test_strip_html_to_text_removes_nav_and_footer() -> None:
    out = strip_html_to_text(SAMPLE_HTML)
    assert "ナビは除去される" not in out
    assert "フッターは除去される" not in out


# --- extract_title / extract_published_at ---


def test_extract_title_from_title_tag() -> None:
    assert extract_title(SAMPLE_HTML) == "テスト記事"


def test_extract_title_fallback_og() -> None:
    html = (
        '<html><head><meta property="og:title" content="OG だけ" /></head>'
        "<body></body></html>"
    )
    assert extract_title(html) == "OG だけ"


def test_extract_published_at_from_ogp() -> None:
    assert extract_published_at(SAMPLE_HTML) == "2026-04-24T10:00:00Z"


def test_extract_published_at_none_when_absent() -> None:
    assert extract_published_at("<html></html>") is None


# --- fetch_web_core (monkeypatched http_get) ---


def test_fetch_web_core_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_http_get(url: str, *, accept: Any = None, timeout: int = 30) -> str | None:
        return SAMPLE_HTML

    monkeypatch.setattr(source_mod, "http_get", fake_http_get)

    src = fetch_web_core("https://example.com/post")
    assert isinstance(src, Source)
    assert src.type == "generic"
    assert src.fetched_content is not None
    assert "本文段落" in src.fetched_content


def test_fetch_web_core_http_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(source_mod, "http_get", lambda *a, **kw: None)
    src = fetch_web_core("https://bad.example/404")
    assert src.fetched_content is None


def test_fetch_zenn_core_routes_with_zenn_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(source_mod, "http_get", lambda *a, **kw: SAMPLE_HTML)
    src = fetch_zenn_core("https://zenn.dev/foo/articles/bar")
    assert src.type == "zenn"


# --- fetch_qiita_core ---


def test_fetch_qiita_core_success(monkeypatch: pytest.MonkeyPatch) -> None:
    api_json = json.dumps(
        {
            "title": "Qiita 記事タイトル",
            "body": "## 本文\n\n内容",
            "user": {"id": "alice"},
            "created_at": "2026-04-24T10:00:00+0900",
        }
    )

    def fake_http_get(url: str, *, accept: Any = None, timeout: int = 30) -> str | None:
        assert "/api/v2/items/" in url
        return api_json

    monkeypatch.setattr(source_mod, "http_get", fake_http_get)

    src = fetch_qiita_core("https://qiita.com/alice/items/abc123")
    assert src.type == "qiita"
    assert src.title == "Qiita 記事タイトル"
    assert src.published_at == "2026-04-24T10:00:00+0900"
    assert "本文" in (src.fetched_content or "")
    assert "@alice" in (src.fetched_content or "")


def test_fetch_qiita_core_invalid_url_raises() -> None:
    with pytest.raises(ValueError):
        fetch_qiita_core("https://qiita.com/alice")  # /items/<id> が無い


def test_fetch_qiita_core_api_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(source_mod, "http_get", lambda *a, **kw: None)
    src = fetch_qiita_core("https://qiita.com/alice/items/xyz")
    assert src.fetched_content is None


# --- fetch_rfc_core ---


def test_fetch_rfc_core_txt_version(monkeypatch: pytest.MonkeyPatch) -> None:
    rfc_txt = "Internet Engineering Task Force (IETF)\n\nRFC 8707  OAuth Resource Indicators\n\n...本文..."

    def fake_http_get(url: str, *, accept: Any = None, timeout: int = 30) -> str | None:
        # html URL → txt URL に自動変換されること
        assert url.endswith(".txt")
        return rfc_txt

    monkeypatch.setattr(source_mod, "http_get", fake_http_get)

    src = fetch_rfc_core("https://www.rfc-editor.org/rfc/rfc8707.html")
    assert src.type == "rfc"
    assert src.fetched_content is not None
    assert "RFC 8707" in src.fetched_content
    assert "```" in src.fetched_content  # fenced code block


def test_fetch_rfc_core_datatracker_html(monkeypatch: pytest.MonkeyPatch) -> None:
    # datatracker は html のまま処理 → 汎用抽出
    monkeypatch.setattr(source_mod, "http_get", lambda *a, **kw: SAMPLE_HTML)
    src = fetch_rfc_core("https://datatracker.ietf.org/doc/html/rfc8707")
    assert src.type == "rfc"
    assert src.fetched_content is not None


# --- fetch_github_core ---


def _fake_completed(data: dict) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["gh"], returncode=0, stdout=json.dumps(data), stderr=""
    )


def test_fetch_github_core_issue_success(monkeypatch: pytest.MonkeyPatch) -> None:
    sample = {
        "number": 22,
        "title": "MCP trust boundary",
        "body": "## 背景\n本文",
        "author": {"login": "luck-tech"},
        "createdAt": "2026-04-22T10:00:00Z",
        "comments": [
            {"author": {"login": "reviewer"}, "createdAt": "2026-04-22T11:00:00Z", "body": "LGTM"}
        ],
        "labels": [{"name": "topic/review"}],
        "state": "OPEN",
    }

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        cmd = args[0]
        assert cmd[0] == "gh"
        assert cmd[1] == "issue"
        return _fake_completed(sample)

    monkeypatch.setattr(subprocess, "run", fake_run)

    src = fetch_github_core("https://github.com/luck-tech/my_library/issues/22")
    assert src.type == "github"
    assert "#22" in src.title
    assert "MCP trust boundary" in src.title
    assert src.published_at == "2026-04-22T10:00:00Z"
    assert "## 本文" in (src.fetched_content or "")
    assert "LGTM" in (src.fetched_content or "")


def test_fetch_github_core_pr_uses_pr_subcommand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        calls.append(args[0][1])  # "issue" or "pr"
        return _fake_completed({"number": 1, "title": "x", "author": {"login": "a"}})

    monkeypatch.setattr(subprocess, "run", fake_run)

    fetch_github_core("https://github.com/luck-tech/my_library/pull/1")
    assert calls == ["pr"]


def test_fetch_github_core_non_issue_url_falls_to_web(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """repo root などは gh api を呼ばず汎用 web fetch を使う。"""
    called = {"gh": False, "http": False}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        called["gh"] = True
        raise AssertionError("gh should not be called for repo URL")

    def fake_http_get(url: str, **kwargs: Any) -> str | None:
        called["http"] = True
        return SAMPLE_HTML

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(source_mod, "http_get", fake_http_get)

    src = fetch_github_core("https://github.com/luck-tech/my_library")
    assert src.type == "github"
    assert not called["gh"]
    assert called["http"]


def test_fetch_github_core_gh_cli_failure_falls_to_web(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gh CLI 失敗時は web fallback。"""

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        raise subprocess.CalledProcessError(1, ["gh"], stderr="auth failed")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(source_mod, "http_get", lambda *a, **kw: SAMPLE_HTML)

    src = fetch_github_core("https://github.com/luck-tech/my_library/issues/1")
    assert src.type == "github"
    assert src.fetched_content is not None  # web fallback で埋まる


# --- fetch_youtube_core (placeholder) ---


def test_fetch_youtube_core_placeholder() -> None:
    src = fetch_youtube_core("https://www.youtube.com/watch?v=abc")
    assert src.type == "youtube"
    assert src.fetched_content is None
    assert "libmatic-addon-youtube" in src.title


# --- fetch_source_core dispatcher ---


def test_fetch_source_core_routes_to_youtube() -> None:
    src = fetch_source_core("https://youtu.be/abc")
    assert src.type == "youtube"
    assert src.fetched_content is None


def test_fetch_source_core_routes_to_generic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(source_mod, "http_get", lambda *a, **kw: SAMPLE_HTML)
    src = fetch_source_core("https://example.com/post")
    assert src.type == "generic"


def test_fetch_source_core_routes_to_zenn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(source_mod, "http_get", lambda *a, **kw: SAMPLE_HTML)
    src = fetch_source_core("https://zenn.dev/foo/articles/bar")
    assert src.type == "zenn"


def test_fetch_source_core_routes_to_x(monkeypatch: pytest.MonkeyPatch) -> None:
    # x_fetch.http_get_json を patch
    xf_mod = importlib.import_module("libmatic.tools.x_fetch")
    monkeypatch.setattr(
        xf_mod,
        "http_get_json",
        lambda url, timeout=15: {
            "code": 200,
            "tweet": {"author": {"screen_name": "x"}, "text": "t"},
        },
    )
    src = fetch_source_core("https://x.com/user/status/1", thread=False)
    assert src.type == "x"


# --- @tool wrappers ---


def test_fetch_source_tool_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    from libmatic.tools.source import fetch_source

    monkeypatch.setattr(source_mod, "http_get", lambda *a, **kw: SAMPLE_HTML)
    result = fetch_source.invoke({"url": "https://example.com/a"})
    assert isinstance(result, dict)
    assert result["type"] == "generic"
    assert result["fetched_content"] is not None


def test_fetch_x_thread_tool_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    from libmatic.tools.source import fetch_x_thread

    xf_mod = importlib.import_module("libmatic.tools.x_fetch")
    monkeypatch.setattr(
        xf_mod,
        "http_get_json",
        lambda url, timeout=15: {
            "code": 200,
            "tweets": [{"author": {"screen_name": "a"}, "text": "t1"}],
        },
    )
    result = fetch_x_thread.invoke({"url": "https://x.com/a/status/1"})
    assert result["type"] == "x"
    assert result["fetched_content"] is not None
