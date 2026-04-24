"""Tests for libmatic.tools.x_fetch (Phase 1.4 PoC #3, X fetch)."""

from __future__ import annotations

import importlib

import pytest

from libmatic.state.topic_debate import Source
from libmatic.tools.x_fetch import (
    _author_full,
    collect_thread_urls,
    extract_quoted_urls,
    fetch_x_core,
    format_timestamp,
    parse_x_url,
    render_single,
    render_thread,
    try_backends,
    tweet_to_md,
)

# module object for monkeypatching http_get_json
xf_mod = importlib.import_module("libmatic.tools.x_fetch")


# --- parse_x_url ---


def test_parse_x_url_basic() -> None:
    assert parse_x_url("https://x.com/mizchi/status/1234567") == ("mizchi", "1234567")


def test_parse_x_url_with_photo_suffix() -> None:
    assert parse_x_url("https://x.com/foo/status/999/photo/1") == ("foo", "999")


def test_parse_x_url_invalid() -> None:
    with pytest.raises(ValueError):
        parse_x_url("https://x.com/mizchi")  # /status/ が無い


# --- format_timestamp ---


def test_format_timestamp_unix() -> None:
    # 2026-04-24T00:00:00+0000
    assert format_timestamp(1776988800).startswith("2026-04-24")


def test_format_timestamp_none_returns_empty() -> None:
    assert format_timestamp(None) == ""
    assert format_timestamp(0) == ""


# --- _author_full ---


def test_author_full_name_and_handle() -> None:
    assert _author_full({"name": "山田太郎", "screen_name": "taro"}) == "山田太郎 (@taro)"


def test_author_full_handle_only() -> None:
    assert _author_full({"screen_name": "taro"}) == "@taro"


def test_author_full_name_only() -> None:
    assert _author_full({"name": "山田太郎"}) == "山田太郎"


def test_author_full_empty() -> None:
    assert _author_full({}) == ""


# --- tweet_to_md ---


def test_tweet_to_md_simple() -> None:
    tweet = {
        "author": {"screen_name": "taro", "name": "Taro"},
        "created_timestamp": 1776988800,
        "text": "これは本文\n複数行ある",
        "url": "https://x.com/taro/status/1",
    }
    md = "\n".join(tweet_to_md(tweet))
    assert "**@taro**" in md
    assert "(Taro)" in md
    assert "2026-04-24" in md
    assert "これは本文" in md
    assert "複数行ある" in md
    assert "元URL: https://x.com/taro/status/1" in md


def test_tweet_to_md_with_quote_nesting() -> None:
    tweet = {
        "author": {"screen_name": "a"},
        "text": "本ツイート",
        "quote": {
            "author": {"screen_name": "b"},
            "text": "引用元ツイート",
        },
    }
    md = "\n".join(tweet_to_md(tweet))
    assert "**@a**" in md
    assert "**引用元**:" in md
    # 引用は level=1 で > prefix が付く
    assert "> **@b**" in md
    assert "> 引用元ツイート" in md


def test_tweet_to_md_with_media() -> None:
    tweet = {
        "author": {"screen_name": "c"},
        "text": "テスト",
        "media": {
            "photos": [{"url": "https://pbs.twimg.com/pic1.jpg"}],
            "videos": [{"url": "https://video.twimg.com/v1.mp4"}],
        },
    }
    md = "\n".join(tweet_to_md(tweet))
    assert "添付画像" in md
    assert "pic1.jpg" in md
    assert "添付動画" in md
    assert "v1.mp4" in md


# --- extract_quoted_urls ---


def test_extract_quoted_urls_entities_priority() -> None:
    tweet = {
        "entities": {
            "urls": [
                {"url": "https://t.co/abc", "expanded_url": "https://example.com/real"},
            ]
        },
        "text": "https://t.co/abc",
    }
    urls = extract_quoted_urls(tweet)
    assert urls == ["https://example.com/real"]  # t.co は除外、expanded が採用


def test_extract_quoted_urls_regex_fallback() -> None:
    # 空白/全角空白以外は URL として連結される (元 script と同じ挙動)。
    # 末尾の `.,)】）` は rstrip されるが、読点「、」などは含まれない。
    tweet = {"text": "記事 https://example.com/post) を参照"}
    urls = extract_quoted_urls(tweet)
    assert "https://example.com/post" in urls  # `)` が rstrip される


def test_extract_quoted_urls_excludes_x_and_media_hosts() -> None:
    tweet = {
        "text": (
            "https://x.com/user/status/1 "
            "https://pbs.twimg.com/image.jpg "
            "https://external.com/article "
            "https://t.co/xyz"
        )
    }
    urls = extract_quoted_urls(tweet)
    assert urls == ["https://external.com/article"]


def test_extract_quoted_urls_dedup() -> None:
    tweet = {
        "entities": {"urls": [{"expanded_url": "https://a.com"}]},
        "text": "see https://a.com and https://a.com again",
    }
    urls = extract_quoted_urls(tweet)
    assert urls == ["https://a.com"]


# --- collect_thread_urls ---


def test_collect_thread_urls_dedup_across_tweets() -> None:
    tweets = [
        {"text": "https://shared.com/a"},
        {"text": "https://shared.com/a と https://unique.com/b"},
    ]
    urls = collect_thread_urls(tweets)
    assert urls == ["https://shared.com/a", "https://unique.com/b"]


# --- render_single / render_thread ---


def test_render_single_contains_metadata() -> None:
    data = {
        "tweet": {
            "author": {"screen_name": "alice", "name": "Alice"},
            "created_timestamp": 1776988800,
            "text": "hello world",
        }
    }
    md = render_single(data, "https://x.com/alice/status/1")
    assert "# X ポスト: @alice" in md
    assert "**出典**: https://x.com/alice/status/1" in md
    assert "Alice (@alice)" in md
    assert "**公開日**: 2026-04-24" in md
    assert "hello world" in md


def test_render_thread_contains_count_and_numbering() -> None:
    data = {
        "tweets": [
            {
                "author": {"screen_name": "bob"},
                "created_timestamp": 1776988800,
                "text": "ツイート 1",
            },
            {"author": {"screen_name": "bob"}, "text": "ツイート 2"},
            {"author": {"screen_name": "bob"}, "text": "ツイート 3"},
        ]
    }
    md = render_thread(data, "https://x.com/bob/status/1")
    assert "# X スレッド: @bob" in md
    assert "**ツイート数**: 3" in md
    assert "## (1/3)" in md
    assert "## (2/3)" in md
    assert "## (3/3)" in md


def test_render_thread_falls_back_to_single_if_no_tweets() -> None:
    data = {"tweet": {"author": {"screen_name": "x"}, "text": "solo"}}
    md = render_thread(data, "https://x.com/x/status/1")
    assert "# X ポスト:" in md  # render_single にフォールバック


# --- try_backends (monkeypatched) ---


def test_try_backends_succeeds_on_first(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_http_get_json(url: str, timeout: int = 15) -> dict | None:
        calls.append(url)
        return {"code": 200, "tweet": {"author": {"screen_name": "a"}, "text": "ok"}}

    monkeypatch.setattr(xf_mod, "http_get_json", fake_http_get_json)

    data = try_backends("a", "1", thread=False)
    assert data is not None
    assert data["code"] == 200
    assert len(calls) == 1
    assert "api.fxtwitter.com" in calls[0]


def test_try_backends_falls_through_to_second(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_http_get_json(url: str, timeout: int = 15) -> dict | None:
        calls.append(url)
        if "fxtwitter" in url:
            return None  # 1 番目失敗
        return {"code": 200, "tweet": {"text": "ok"}}

    monkeypatch.setattr(xf_mod, "http_get_json", fake_http_get_json)

    data = try_backends("a", "1", thread=False)
    assert data is not None
    assert len(calls) == 2
    assert "vxtwitter" in calls[1]


def test_try_backends_all_fail_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(xf_mod, "http_get_json", lambda url, timeout=15: None)
    assert try_backends("a", "1", thread=False) is None


# --- fetch_x_core (monkeypatched) ---


def test_fetch_x_core_success_single(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_http_get_json(url: str, timeout: int = 15) -> dict | None:
        return {
            "code": 200,
            "tweet": {
                "author": {"screen_name": "carol", "name": "Carol"},
                "created_timestamp": 1776988800,
                "text": "ほげ",
            },
        }

    monkeypatch.setattr(xf_mod, "http_get_json", fake_http_get_json)

    src = fetch_x_core("https://x.com/carol/status/9", thread=False)
    assert isinstance(src, Source)
    assert src.type == "x"
    assert "@carol" in src.title
    assert src.fetched_content is not None
    assert "ほげ" in src.fetched_content
    assert src.published_at is not None


def test_fetch_x_core_failure_returns_source_without_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(xf_mod, "http_get_json", lambda url, timeout=15: None)

    src = fetch_x_core("https://x.com/dave/status/7", thread=True)
    assert isinstance(src, Source)
    assert src.type == "x"
    assert src.fetched_content is None
    assert "dave/status/7" in src.title
