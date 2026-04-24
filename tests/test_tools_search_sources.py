"""Tests for libmatic.tools.search_sources (Phase 1.4 PoC)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from libmatic.tools.search_sources import (
    Candidate,
    FeedEntry,
    classify_media,
    collect_feeds_from_priorities,
    extract_keywords,
    matches_theme,
    parse_atom,
    parse_feed,
    parse_rss,
    search_feeds,
)

# NOTE: libmatic.tools.__init__ が search_sources を @tool instance として
# attach するため、`import libmatic.tools.search_sources as ss_mod` では
# attribute 衝突で module ではなく tool 関数が入ることがある。
# monkeypatch 用に確実に module オブジェクトを取るために importlib を使う。
ss_mod = importlib.import_module("libmatic.tools.search_sources")


RSS_SAMPLE = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test Blog</title>
    <item>
      <title>React 19 の新機能 use API</title>
      <link>https://example.com/react-19</link>
      <pubDate>Wed, 23 Apr 2026 10:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Vue.js 3.5 リリース</title>
      <link>https://example.com/vue-3-5</link>
      <pubDate>Wed, 22 Apr 2026 10:00:00 +0000</pubDate>
    </item>
    <item>
      <title><![CDATA[Rust の async trait]]></title>
      <link>https://example.com/rust-async</link>
    </item>
  </channel>
</rss>"""

ATOM_SAMPLE = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Atom</title>
  <entry>
    <title>React Compiler の最適化戦略</title>
    <link href="https://example.com/compiler" />
    <published>2026-04-22T10:00:00Z</published>
  </entry>
  <entry>
    <title>Kotlin 2.0 Multiplatform</title>
    <link href="https://example.com/kotlin" />
    <updated>2026-04-20T10:00:00Z</updated>
  </entry>
</feed>"""


# --- extract_keywords / matches_theme ---


def test_extract_keywords_ascii_words() -> None:
    kws = extract_keywords("React 19 use API")
    assert "react" in kws
    assert "19" in kws
    assert "use" in kws
    assert "api" in kws


def test_extract_keywords_drops_single_chars() -> None:
    # 単文字は除外
    kws = extract_keywords("a React b")
    assert "react" in kws
    assert "a" not in kws
    assert "b" not in kws


def test_extract_keywords_handles_japanese() -> None:
    # 連続する非 ASCII は 1 トークンとして捉えられる。
    # ただし len < 2 は除外されるので単文字「の」は落ちる (意図的)。
    kws = extract_keywords("React の議論 API")
    assert "react" in kws
    # 「の議論」は連続非 ASCII 3 文字で 1 トークン扱い
    assert any("議論" in k for k in kws)


def test_extract_keywords_drops_single_char_japanese() -> None:
    # 1 文字の非 ASCII は len>=2 で除外される
    kws = extract_keywords("React の API")
    assert "react" in kws
    assert "api" in kws
    assert "の" not in kws


def test_matches_theme_partial_match() -> None:
    assert matches_theme("React 19 use API hook", ["react"])
    assert matches_theme("REACT 19", ["react"])  # case insensitive
    assert not matches_theme("Angular 20 の新機能", ["react", "vue"])


def test_matches_theme_empty_keywords() -> None:
    # キーワードが空なら何にも match しない
    assert not matches_theme("anything", [])


# --- classify_media ---


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.youtube.com/watch?v=abc", "youtube"),
        ("https://youtu.be/abc", "youtube"),
        ("https://x.com/someone/status/123", "x"),
        ("https://twitter.com/x/status/1", "x"),
        ("https://zenn.dev/article", "zenn"),
        ("https://qiita.com/foo/items/bar", "qiita"),
        ("https://github.com/foo/bar", "github"),
        ("https://www.rfc-editor.org/rfc/rfc8707", "rfc"),
        ("https://datatracker.ietf.org/doc/html/rfc8707", "rfc"),
        ("https://random.example.com/post", "web"),
    ],
)
def test_classify_media(url: str, expected: str) -> None:
    assert classify_media(url) == expected


# --- parse_rss / parse_atom / parse_feed ---


def test_parse_rss_basic() -> None:
    entries = parse_rss(RSS_SAMPLE)
    assert len(entries) == 3
    assert entries[0].title == "React 19 の新機能 use API"
    assert entries[0].link == "https://example.com/react-19"
    assert "Wed" in entries[0].published


def test_parse_rss_handles_cdata() -> None:
    entries = parse_rss(RSS_SAMPLE)
    # 3 番目のエントリは CDATA 込み
    third = [e for e in entries if "Rust" in e.title][0]
    assert third.title == "Rust の async trait"


def test_parse_atom_basic() -> None:
    entries = parse_atom(ATOM_SAMPLE)
    assert len(entries) == 2
    assert entries[0].title == "React Compiler の最適化戦略"
    assert entries[0].link == "https://example.com/compiler"
    assert entries[0].published == "2026-04-22T10:00:00Z"


def test_parse_atom_fallback_to_updated() -> None:
    entries = parse_atom(ATOM_SAMPLE)
    second = entries[1]
    # published が無ければ updated を採用
    assert second.published == "2026-04-20T10:00:00Z"


def test_parse_feed_auto_detects_atom() -> None:
    entries = parse_feed(ATOM_SAMPLE)
    assert len(entries) == 2
    assert entries[0].title == "React Compiler の最適化戦略"


def test_parse_feed_auto_detects_rss() -> None:
    entries = parse_feed(RSS_SAMPLE)
    assert len(entries) == 3


# --- collect_feeds_from_priorities ---


def test_collect_feeds_from_priorities(tmp_path: Path) -> None:
    yml = tmp_path / "src.yml"
    yml.write_text(
        """
blogs:
  - name: Test Blog
    feed: https://example.com/rss
  - name: No Feed
zenn:
  users:
    - handle: mizchi
qiita:
  users:
    - handle: someone
youtube:
  channels:
    - id: UCabc1234567890
    - id: XYZnotchannel
""",
        encoding="utf-8",
    )
    feeds = collect_feeds_from_priorities(yml)
    assert "https://example.com/rss" in feeds
    assert "https://zenn.dev/mizchi/feed" in feeds
    assert "https://qiita.com/someone/feed.atom" in feeds
    assert "https://www.youtube.com/feeds/videos.xml?channel_id=UCabc1234567890" in feeds
    # "UC" 始まりでない id は除外
    assert not any("XYZ" in f for f in feeds)
    # feed が無い blog は含まれない
    assert all(f.startswith(("https://example.com", "https://zenn.dev",
                              "https://qiita.com", "https://www.youtube.com")) for f in feeds)


def test_collect_feeds_from_nonexistent_path(tmp_path: Path) -> None:
    assert collect_feeds_from_priorities(tmp_path / "does-not-exist.yml") == []


def test_collect_feeds_from_empty_yaml(tmp_path: Path) -> None:
    yml = tmp_path / "empty.yml"
    yml.write_text("", encoding="utf-8")
    assert collect_feeds_from_priorities(yml) == []


# --- search_feeds (monkey patched http_get) ---


def test_search_feeds_empty_feeds_returns_empty() -> None:
    assert search_feeds(theme="anything", feeds=[]) == []


def test_search_feeds_with_monkeypatched_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全体フロー: feeds 一覧から keyword にマッチする candidate を抽出。"""

    def fake_http_get(url: str, timeout: int = 15) -> str | None:
        if "first" in url:
            return RSS_SAMPLE
        if "second" in url:
            return ATOM_SAMPLE
        return None

    monkeypatch.setattr(ss_mod, "http_get", fake_http_get)

    candidates = search_feeds(
        theme="React 19 use Compiler",
        feeds=["https://example.com/first", "https://example.com/second"],
    )

    titles = [c.title for c in candidates]
    # React 19 と React Compiler は拾われる
    assert "React 19 の新機能 use API" in titles
    assert "React Compiler の最適化戦略" in titles
    # Vue や Kotlin は theme に含まれないので除外
    assert not any("Vue" in t for t in titles)
    assert not any("Kotlin" in t for t in titles)


def test_search_feeds_deduplicates_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同じ URL が複数 feed に現れても 1 回しか採用されない。"""

    def fake_http_get(url: str, timeout: int = 15) -> str | None:
        return RSS_SAMPLE  # 全 feed から同じ RSS

    monkeypatch.setattr(ss_mod, "http_get", fake_http_get)

    candidates = search_feeds(
        theme="React use",
        feeds=["https://a.com/feed", "https://b.com/feed", "https://c.com/feed"],
    )
    urls = [c.url for c in candidates]
    assert len(urls) == len(set(urls))


def test_search_feeds_honors_extra_keywords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """extra_keywords で theme に無い語も match させられる。"""

    def fake_http_get(url: str, timeout: int = 15) -> str | None:
        return RSS_SAMPLE

    monkeypatch.setattr(ss_mod, "http_get", fake_http_get)

    # theme="async" だけでは React 19 は match しない
    candidates = search_feeds(theme="async", feeds=["https://x.com/feed"])
    assert any("Rust" in c.title for c in candidates)
    assert not any("React" in c.title for c in candidates)

    # extra_keywords に react を追加すると React もヒット
    candidates2 = search_feeds(
        theme="async",
        feeds=["https://x.com/feed"],
        extra_keywords=["react"],
    )
    titles = [c.title for c in candidates2]
    assert any("React" in t for t in titles)


def test_search_feeds_fetch_failure_skips_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """http_get が None を返す feed は skip される (エラーで止まらない)。"""

    def fake_http_get(url: str, timeout: int = 15) -> str | None:
        if "good" in url:
            return RSS_SAMPLE
        return None  # 失敗

    monkeypatch.setattr(ss_mod, "http_get", fake_http_get)

    candidates = search_feeds(
        theme="React use",
        feeds=["https://bad.example/feed", "https://good.example/feed"],
    )
    # "good" 側から拾える
    assert len(candidates) >= 1


def test_search_feeds_sets_media_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """YouTube feed からの結果は media=youtube になる。"""

    def fake_http_get(url: str, timeout: int = 15) -> str | None:
        return """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>React 19 解説動画</title>
    <link href="https://www.youtube.com/watch?v=abc123" />
    <published>2026-04-23T10:00:00Z</published>
  </entry>
</feed>"""

    monkeypatch.setattr(ss_mod, "http_get", fake_http_get)

    candidates = search_feeds(
        theme="React 19",
        feeds=["https://www.youtube.com/feeds/videos.xml?channel_id=UCxxx"],
    )
    assert len(candidates) == 1
    assert candidates[0].media == "youtube"
    assert candidates[0].domain == "www.youtube.com"


# --- Model dump ---


def test_candidate_model_dump_defaults() -> None:
    c = Candidate(
        url="https://example.com/x",
        title="Test",
        domain="example.com",
        media="web",
    )
    d = c.model_dump()
    assert d["url"] == "https://example.com/x"
    assert d["discovered_by"] == "feed"
    assert d["published_at"] == ""


def test_feed_entry_minimal() -> None:
    e = FeedEntry(title="t", link="https://a")
    assert e.published == ""
