"""Tests for libmatic.nodes.suggest_topics (A1-A6)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.runnables import RunnableConfig

from libmatic.config import GitHubConfig, LibmaticConfig
from libmatic.nodes.suggest_topics import (
    _coerce_topic_candidate,
    _extract_known_domains,
    _normalize_title,
    create_issues,
    dedup_against_issues,
    fetch_candidates,
    load_priorities,
    propose_new_sources,
    relevance_filter,
)
from libmatic.state.suggest_topics import SuggestTopicsState, TopicCandidate


def _make_config() -> LibmaticConfig:
    return LibmaticConfig(github=GitHubConfig(repo="OWNER/REPO"))


def _rc(lcfg: LibmaticConfig) -> RunnableConfig:
    return {"configurable": {"libmatic_config": lcfg}}


def _fake_agent_returning(content: str) -> Any:
    fake = MagicMock()
    fake.invoke = MagicMock(
        return_value={"messages": [MagicMock(content=content)]}
    )
    return fake


def _fake_completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["gh"], returncode=returncode, stdout=stdout, stderr=""
    )


# --- _normalize_title ---


def test_normalize_title_lowercases_and_strips_spaces() -> None:
    assert _normalize_title("  React 19 use API  ") == "react19useapi"


def test_normalize_title_handles_unicode() -> None:
    a = _normalize_title("React の議論")
    b = _normalize_title("React  の議論")
    assert a == b


# --- _coerce_topic_candidate ---


def test_coerce_topic_candidate_valid() -> None:
    c = _coerce_topic_candidate(
        {
            "title": "Test",
            "body": "Body",
            "lifespan": "universal",
            "source_urls": ["https://a"],
        }
    )
    assert c is not None
    assert c.title == "Test"
    assert c.lifespan == "universal"


def test_coerce_topic_candidate_missing_title() -> None:
    assert _coerce_topic_candidate({"body": "x"}) is None


def test_coerce_topic_candidate_missing_body() -> None:
    assert _coerce_topic_candidate({"title": "x"}) is None


def test_coerce_topic_candidate_default_lifespan() -> None:
    c = _coerce_topic_candidate({"title": "T", "body": "B"})
    assert c is not None
    assert c.lifespan == "universal"


def test_coerce_topic_candidate_filters_empty_urls() -> None:
    c = _coerce_topic_candidate(
        {"title": "T", "body": "B", "source_urls": ["a", "", None, "b"]}
    )
    assert c is not None
    assert c.source_urls == ["a", "b"]


# --- _extract_known_domains ---


def test_extract_known_domains() -> None:
    feeds = [
        "https://example.com/feed.xml",
        "https://blog.example.com/rss",
        "https://qiita.com/foo/feed.atom",
    ]
    domains = _extract_known_domains(feeds)
    assert "example.com" in domains
    assert "blog.example.com" in domains
    assert "qiita.com" in domains


# --- A1: load_priorities ---


def test_load_priorities_reads_yaml(tmp_path: Path) -> None:
    yml = tmp_path / "src.yml"
    yml.write_text(
        """
blogs:
  - name: Test
    feed: https://example.com/rss
zenn:
  users:
    - handle: mizchi
""",
        encoding="utf-8",
    )

    state = SuggestTopicsState(source_priorities_path=str(yml))
    result = load_priorities(state, _rc(_make_config()))
    assert "https://example.com/rss" in result["feeds"]
    assert any("mizchi" in f for f in result["feeds"])


def test_load_priorities_missing_file_returns_empty() -> None:
    state = SuggestTopicsState(source_priorities_path="/tmp/does-not-exist-xyz.yml")
    result = load_priorities(state, _rc(_make_config()))
    assert result["feeds"] == []


# --- A2: fetch_candidates ---


def test_fetch_candidates_empty_feeds_returns_empty() -> None:
    state = SuggestTopicsState(feeds=[])
    result = fetch_candidates(state, _rc(_make_config()))
    assert result["raw_candidates"] == []


def test_fetch_candidates_dedups_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    """同じ URL が複数 feed に現れても 1 度だけ採用される。"""
    import libmatic.nodes.suggest_topics as nodes_mod
    from libmatic.tools.search_sources import FeedEntry

    def fake_fetch_feed(feed_url: str) -> list[FeedEntry]:
        return [
            FeedEntry(title=f"shared {feed_url}", link="https://shared.com/post", published=""),
            FeedEntry(title=f"unique {feed_url}", link=f"{feed_url}/unique", published=""),
        ]

    monkeypatch.setattr(nodes_mod, "fetch_feed", fake_fetch_feed)

    state = SuggestTopicsState(feeds=["https://a.com", "https://b.com"])
    result = fetch_candidates(state, _rc(_make_config()))
    raw = result["raw_candidates"]
    urls = [c["url"] for c in raw]
    # shared.com/post は 1 度だけ
    assert urls.count("https://shared.com/post") == 1
    # unique は 2 件
    assert any("a.com/unique" in u for u in urls)
    assert any("b.com/unique" in u for u in urls)


def test_fetch_candidates_extracts_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    import libmatic.nodes.suggest_topics as nodes_mod
    from libmatic.tools.search_sources import FeedEntry

    monkeypatch.setattr(
        nodes_mod,
        "fetch_feed",
        lambda url: [FeedEntry(title="t", link="https://example.com/post", published="")],
    )

    state = SuggestTopicsState(feeds=["https://example.com/feed"])
    result = fetch_candidates(state, _rc(_make_config()))
    assert result["raw_candidates"][0]["domain"] == "example.com"


# --- A3: relevance_filter ---


def test_relevance_filter_parses_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import libmatic.nodes.suggest_topics as nodes_mod

    fake_output = json.dumps(
        [
            {
                "title": "テーマ A",
                "body": "## 背景\n本文",
                "lifespan": "universal",
                "source_urls": ["https://a"],
            },
            {
                "title": "テーマ B",
                "body": "ephemeral 用",
                "lifespan": "ephemeral",
                "source_urls": ["https://b"],
            },
        ],
        ensure_ascii=False,
    )
    monkeypatch.setattr(
        nodes_mod, "build_step_agent",
        lambda *a, **kw: _fake_agent_returning(fake_output),
    )

    state = SuggestTopicsState(
        raw_candidates=[
            {"url": "https://a", "title": "A", "domain": "a"},
            {"url": "https://b", "title": "B", "domain": "b"},
        ]
    )
    result = relevance_filter(state, _rc(_make_config()))
    assert len(result["filtered_candidates"]) == 2
    assert result["filtered_candidates"][0].lifespan == "universal"


def test_relevance_filter_empty_raw_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import libmatic.nodes.suggest_topics as nodes_mod

    def should_not_be_called(*a: Any, **kw: Any) -> Any:
        raise AssertionError("agent should not be built when raw is empty")

    monkeypatch.setattr(nodes_mod, "build_step_agent", should_not_be_called)

    state = SuggestTopicsState(raw_candidates=[])
    result = relevance_filter(state, _rc(_make_config()))
    assert result == {"filtered_candidates": []}


def test_relevance_filter_llm_failure_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import libmatic.nodes.suggest_topics as nodes_mod

    class Failing:
        def invoke(self, _: dict) -> dict:
            raise RuntimeError("LLM down")

    monkeypatch.setattr(nodes_mod, "build_step_agent", lambda *a, **kw: Failing())

    state = SuggestTopicsState(raw_candidates=[{"url": "x", "title": "y"}])
    result = relevance_filter(state, _rc(_make_config()))
    assert result["filtered_candidates"] == []


# --- A4: dedup_against_issues ---


def test_dedup_filters_existing_titles(monkeypatch: pytest.MonkeyPatch) -> None:
    """既存 issue タイトルと normalize 一致するものは除外。"""

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        # gh issue list の戻り値
        return _fake_completed(
            json.dumps(
                [
                    {"number": 1, "title": "Existing Topic React"},
                    {"number": 2, "title": "Other Topic"},
                ]
            )
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    candidates = [
        TopicCandidate(
            title="Existing Topic React",  # 重複
            body="x",
            lifespan="universal",
            source_urls=[],
        ),
        TopicCandidate(
            title="New Topic Vue",  # 新規
            body="x",
            lifespan="universal",
            source_urls=[],
        ),
    ]
    state = SuggestTopicsState(filtered_candidates=candidates)
    result = dedup_against_issues(state, _rc(_make_config()))
    titles = [c.title for c in result["filtered_candidates"]]
    assert titles == ["New Topic Vue"]


def test_dedup_empty_input_short_circuits() -> None:
    state = SuggestTopicsState(filtered_candidates=[])
    result = dedup_against_issues(state, _rc(_make_config()))
    assert result["filtered_candidates"] == []


def test_dedup_gh_failure_keeps_all_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gh CLI 失敗時は dedup 諦めて全 candidate を残す。"""

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        raise FileNotFoundError("gh")

    monkeypatch.setattr(subprocess, "run", fake_run)

    candidates = [
        TopicCandidate(title="A", body="x", lifespan="universal", source_urls=[])
    ]
    state = SuggestTopicsState(filtered_candidates=candidates)
    result = dedup_against_issues(state, _rc(_make_config()))
    assert len(result["filtered_candidates"]) == 1


# --- A5: create_issues ---


def test_create_issues_creates_each(monkeypatch: pytest.MonkeyPatch) -> None:
    issue_counter = iter([100, 101])

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        n = next(issue_counter)
        return _fake_completed(f"https://github.com/x/y/issues/{n}\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    candidates = [
        TopicCandidate(title="A", body="body A", lifespan="universal", source_urls=["https://a"]),
        TopicCandidate(title="B", body="body B", lifespan="ephemeral", source_urls=["https://b"]),
    ]
    state = SuggestTopicsState(filtered_candidates=candidates)
    result = create_issues(state, _rc(_make_config()))
    assert result["created_issues"] == [100, 101]


def test_create_issues_individual_failure_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """個別の起票失敗は skip して残りは継続。"""
    call_count = {"n": 0}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise subprocess.CalledProcessError(1, ["gh"], stderr="rate limit")
        return _fake_completed("https://github.com/x/y/issues/77\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    candidates = [
        TopicCandidate(title="A", body="x", lifespan="universal", source_urls=[]),
        TopicCandidate(title="B", body="x", lifespan="universal", source_urls=[]),
    ]
    state = SuggestTopicsState(filtered_candidates=candidates)
    result = create_issues(state, _rc(_make_config()))
    # 1 つ目は失敗、2 つ目は成功
    assert result["created_issues"] == [77]


def test_create_issues_appends_lifespan_and_sources_to_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        captured["cmd"] = args[0]
        return _fake_completed("https://github.com/x/y/issues/1\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    candidates = [
        TopicCandidate(
            title="T",
            body="本文",
            lifespan="ephemeral",
            source_urls=["https://a", "https://b"],
        ),
    ]
    state = SuggestTopicsState(filtered_candidates=candidates)
    create_issues(state, _rc(_make_config()))

    body_idx = captured["cmd"].index("--body") + 1
    body = captured["cmd"][body_idx]
    assert "本文" in body
    assert "**lifespan**: ephemeral" in body
    assert "https://a" in body
    assert "https://b" in body


# --- A6: propose_new_sources ---


def test_propose_new_sources_detects_unknown_domains() -> None:
    state = SuggestTopicsState(
        feeds=["https://known.com/feed"],
        raw_candidates=[
            {"url": "https://new.com/a", "domain": "new.com"},
            {"url": "https://new.com/b", "domain": "new.com"},
            {"url": "https://known.com/post", "domain": "known.com"},
            {"url": "https://once.com/x", "domain": "once.com"},  # 1 件のみは除外
        ],
    )
    result = propose_new_sources(state, _rc(_make_config()))
    detected_domains = {d["domain"] for d in result["new_sources_detected"]}
    assert "new.com" in detected_domains
    assert "known.com" not in detected_domains
    assert "once.com" not in detected_domains


def test_propose_new_sources_no_unknown_returns_empty() -> None:
    state = SuggestTopicsState(
        feeds=["https://known.com/feed"],
        raw_candidates=[
            {"url": "https://known.com/a", "domain": "known.com"},
            {"url": "https://known.com/b", "domain": "known.com"},
        ],
    )
    result = propose_new_sources(state, _rc(_make_config()))
    assert result["new_sources_detected"] == []
    assert result["proposal_pr_number"] is None


def test_propose_new_sources_v01_does_not_create_pr() -> None:
    """v0.1 では検出のみ、PR 作成は行わないので proposal_pr_number は常に None。"""
    state = SuggestTopicsState(
        feeds=["https://k.com/feed"],
        raw_candidates=[
            {"url": "https://new.com/a", "domain": "new.com"},
            {"url": "https://new.com/b", "domain": "new.com"},
        ],
    )
    result = propose_new_sources(state, _rc(_make_config()))
    assert result["proposal_pr_number"] is None
