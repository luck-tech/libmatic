"""Tests for libmatic.nodes.topic_debate (deterministic nodes + coverage_gate)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.runnables import RunnableConfig

from libmatic.config import GitHubConfig, LibmaticConfig, WorkflowConfig
from libmatic.nodes.topic_debate import (
    _fetch_one,
    _recency_decay,
    _relevance,
    _slugify,
    _tokenize,
    coverage_gate,
    pr_opener,
    score_source,
    source_fetcher,
    source_scorer,
)
from libmatic.state.topic_debate import Source, TopicDebateState


def _make_config(**wf_kwargs: Any) -> LibmaticConfig:
    return LibmaticConfig(
        workflow=WorkflowConfig(**wf_kwargs) if wf_kwargs else WorkflowConfig(),
        github=GitHubConfig(repo="luck-tech/my_library"),
    )


def _rc(lcfg: LibmaticConfig) -> RunnableConfig:
    return {"configurable": {"libmatic_config": lcfg}}


def _make_state(**overrides: Any) -> TopicDebateState:
    base: dict[str, Any] = {
        "issue_number": 18,
        "issue_title": "test theme",
        "issue_body": "body",
        "lifespan": "universal",
    }
    base.update(overrides)
    return TopicDebateState(**base)


# --- _recency_decay ---


def test_recency_decay_no_date_returns_one() -> None:
    assert _recency_decay(None) == 1.0
    assert _recency_decay("") == 1.0


def test_recency_decay_today_is_one() -> None:
    now = datetime.now(UTC).isoformat()
    assert _recency_decay(now) == pytest.approx(1.0, abs=0.01)


def test_recency_decay_half_life_at_180_days() -> None:
    past = (datetime.now(UTC) - timedelta(days=180)).isoformat()
    val = _recency_decay(past)
    assert 0.35 < val < 0.4  # 1/e ≒ 0.368


def test_recency_decay_invalid_format_returns_one() -> None:
    assert _recency_decay("not-a-date") == 1.0


def test_recency_decay_future_treats_as_one() -> None:
    future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    assert _recency_decay(future) == 1.0


# --- _tokenize / _relevance ---


def test_tokenize_ascii_and_japanese() -> None:
    tokens = _tokenize("React 19 の use API")
    assert "react" in tokens
    assert "19" in tokens
    assert "use" in tokens
    assert "api" in tokens


def test_tokenize_drops_single_chars() -> None:
    # 1 文字の非 ASCII は len < 2 で除外
    tokens = _tokenize("a React b")
    assert "a" not in tokens
    assert "b" not in tokens
    assert "react" in tokens


def test_relevance_perfect_match() -> None:
    assert _relevance("React 19 use", "React 19 use") == 1.0


def test_relevance_no_overlap() -> None:
    assert _relevance("Vue 3 computed", "React 19 use") == 0.0


def test_relevance_partial_overlap() -> None:
    # issue_tokens = {react, 19, use} (3), overlap = {react} (1) → 1/3
    assert _relevance("React hooks", "React 19 use") == pytest.approx(1 / 3, rel=0.01)


# --- score_source ---


def test_score_source_combines_three_factors() -> None:
    src = Source(
        url="x",
        type="rss",
        title="React 19 use API",
        published_at=datetime.now(UTC).isoformat(),
        score=2.0,
    )
    # priority 2.0 * recency ~1 * relevance = 2.0 * 1.0 * 1.0 = 2.0
    assert score_source(src, "React 19 use") > 1.9


def test_score_source_default_priority_when_score_zero() -> None:
    src = Source(
        url="x",
        type="rss",
        title="React hooks",
        published_at=datetime.now(UTC).isoformat(),
        score=0.0,
    )
    # priority_weight = 1.0 (fallback), recency ≒ 1, relevance = 1/3
    result = score_source(src, "React 19 use")
    assert 0.3 < result < 0.4


# --- source_scorer (node) ---


def test_source_scorer_sorts_desc_and_limits() -> None:
    sources = [
        Source(url=f"u{i}", type="rss", title=f"React 19 item {i}", score=float(i))
        for i in range(1, 6)
    ]
    # issue_title と source title が lexical に重なる必要あり
    # (relevance が 0 だと全 source で score が 0 になって sort が無意味になる)
    state = _make_state(issue_title="React 19 use", candidate_sources=sources)
    cfg = _make_config(max_sources_per_topic=3)

    result = source_scorer(state, _rc(cfg))
    scored: list[Source] = result["scored_sources"]
    assert len(scored) == 3
    # score 降順 (priority 5 が最高)
    assert [s.url for s in scored] == ["u5", "u4", "u3"]
    # score フィールドが更新されている
    assert scored[0].score > 0


def test_source_scorer_empty_candidates() -> None:
    state = _make_state(candidate_sources=[])
    cfg = _make_config()
    result = source_scorer(state, _rc(cfg))
    assert result["scored_sources"] == []


def test_source_scorer_requires_libmatic_config() -> None:
    state = _make_state(candidate_sources=[])
    with pytest.raises(ValueError):
        source_scorer(state, {"configurable": {}})


# --- source_fetcher (node) ---


def test_source_fetcher_fetches_and_preserves_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fetch_source_core を monkeypatch して、score が引き継がれるか検証。"""

    def fake_fetch(url: str) -> Source:
        return Source(url=url, type="generic", title=f"fetched {url}", fetched_content="x")

    import libmatic.nodes.topic_debate as nodes_mod

    monkeypatch.setattr(nodes_mod, "fetch_source_core", fake_fetch)

    scored = [
        Source(url="https://a", type="generic", title="a", score=2.0),
        Source(url="https://b", type="generic", title="b", score=1.5),
    ]
    state = _make_state(scored_sources=scored)
    cfg = _make_config(max_concurrent_fetches=2)

    result = source_fetcher(state, _rc(cfg))
    fetched: list[Source] = result["fetched_sources"]
    assert len(fetched) == 2
    urls_to_scores = {s.url: s.score for s in fetched}
    assert urls_to_scores["https://a"] == 2.0
    assert urls_to_scores["https://b"] == 1.5
    for s in fetched:
        assert s.fetched_content == "x"


def test_source_fetcher_empty_input() -> None:
    state = _make_state(scored_sources=[])
    cfg = _make_config()
    result = source_fetcher(state, _rc(cfg))
    assert result["fetched_sources"] == []


def test_fetch_one_preserves_zero_score_as_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """score=0 の source は score 上書きせず、fetch_source_core の戻り値を使う。"""

    def fake_fetch(url: str) -> Source:
        return Source(url=url, type="rss", title="t", score=0.5)

    import libmatic.nodes.topic_debate as nodes_mod

    monkeypatch.setattr(nodes_mod, "fetch_source_core", fake_fetch)

    src = Source(url="u", type="rss", title="t", score=0.0)
    result = _fetch_one(src)
    assert result.score == 0.5  # fetch 側の値がそのまま使われる


# --- coverage_gate ---


def test_coverage_gate_passes_on_threshold_met() -> None:
    state = _make_state(coverage_score=0.9, coverage_loop_count=0)
    cfg = _make_config(coverage_threshold=0.80, max_coverage_loops=2)
    assert coverage_gate(state, _rc(cfg)) == "step7_article_writer"


def test_coverage_gate_loops_back_when_below_threshold() -> None:
    state = _make_state(coverage_score=0.5, coverage_loop_count=0)
    cfg = _make_config(coverage_threshold=0.80, max_coverage_loops=2)
    assert coverage_gate(state, _rc(cfg)) == "step3_source_fetcher"


def test_coverage_gate_gives_up_at_max_loops() -> None:
    state = _make_state(coverage_score=0.5, coverage_loop_count=2)
    cfg = _make_config(coverage_threshold=0.80, max_coverage_loops=2)
    # score 未達でも loop 上限なら step7 へ
    assert coverage_gate(state, _rc(cfg)) == "step7_article_writer"


def test_coverage_gate_respects_custom_thresholds() -> None:
    state = _make_state(coverage_score=0.65, coverage_loop_count=0)
    cfg = _make_config(coverage_threshold=0.60, max_coverage_loops=2)
    # threshold 0.60 なら 0.65 で pass
    assert coverage_gate(state, _rc(cfg)) == "step7_article_writer"


# --- _slugify ---


def test_slugify_ascii() -> None:
    assert _slugify("React 19 use API") == "react-19-use-api"


def test_slugify_japanese_preserves_chars() -> None:
    slug = _slugify("React の議論")
    # 日本語 2-3 文字も保持される
    assert "react" in slug
    assert "議論" in slug or "の議論" in slug


def test_slugify_empty_returns_untitled() -> None:
    assert _slugify("") == "untitled"
    assert _slugify("---") == "untitled"


def test_slugify_truncates_long_title() -> None:
    long_title = "a" * 200
    assert len(_slugify(long_title)) <= 80


# --- pr_opener (node) ---


def test_pr_opener_writes_files_and_creates_pr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """pr_opener が files 書き出し + git + gh 呼び出し + label 遷移を行う。"""
    import libmatic.nodes.topic_debate as nodes_mod

    git_calls: list[list[str]] = []
    pr_create_called: dict[str, Any] = {}
    issue_edit_called: dict[str, Any] = {}

    def fake_run(cmd: list[str], *, check: bool = True, cwd: Any = None) -> Any:
        git_calls.append(cmd)
        return MagicMock(returncode=0)

    def fake_pr_create(branch: str, title: str, body: str, base: str = "main") -> dict:
        pr_create_called["branch"] = branch
        pr_create_called["title"] = title
        pr_create_called["body"] = body
        return {"number": 99, "url": "https://github.com/x/y/pull/99"}

    def fake_issue_edit(
        num: int,
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
        body: str | None = None,
    ) -> None:
        issue_edit_called["num"] = num
        issue_edit_called["add"] = add_labels
        issue_edit_called["remove"] = remove_labels

    monkeypatch.setattr(nodes_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(nodes_mod, "gh_pr_create_core", fake_pr_create)
    monkeypatch.setattr(nodes_mod, "gh_issue_edit_core", fake_issue_edit)

    original = tmp_path / "content" / "dev" / "notes" / "example.md"
    state = _make_state(
        issue_number=18,
        issue_title="React 19 use API",
        issue_body="body text",
        article_draft="# 原本\n本文",
        article_expanded="# 拡張版\n本文詳細",
        output_path=str(original),
    )
    cfg = _make_config()

    result = pr_opener(state, _rc(cfg))

    # ファイル書き出し確認
    assert original.read_text(encoding="utf-8") == "# 原本\n本文"
    expanded = original.with_name("example-explained.md")
    assert expanded.read_text(encoding="utf-8") == "# 拡張版\n本文詳細"

    # git 呼び出しが 4 つ (checkout, add, commit, push)
    git_actions = [c[1] for c in git_calls]
    assert git_actions == ["checkout", "add", "commit", "push"]
    # branch 名に slug が反映される
    assert any("topic/react-19-use-api" in " ".join(c) for c in git_calls)

    # PR 作成呼出
    assert pr_create_called["branch"] == "topic/react-19-use-api"
    assert "React 19 use API" in pr_create_called["title"]
    assert "Closes #18" in pr_create_called["body"]

    # issue label 遷移 (in-progress → review)
    assert issue_edit_called["num"] == 18
    assert "topic/review" in issue_edit_called["add"]
    assert "topic/in-progress" in issue_edit_called["remove"]

    # 戻り値
    assert result == {"pr_number": 99, "pr_url": "https://github.com/x/y/pull/99"}


def test_pr_opener_unimplemented_steps_raise() -> None:
    """未実装 step は NotImplementedError を投げる (次 PR で実装予定の sanity check)。

    coverage_verifier は本 PR で実装済みなのでここから除外。
    """
    from libmatic.nodes.topic_debate import (
        article_writer,
        expanded_writer,
        fact_extractor,
        fact_merger,
        source_collector,
    )

    cfg = _make_config()
    state = _make_state()
    rc = _rc(cfg)

    for fn in (
        source_collector,
        fact_extractor,
        fact_merger,
        article_writer,
        expanded_writer,
    ):
        with pytest.raises(NotImplementedError):
            fn(state, rc)


# --- coverage_verifier (hybrid) ---


def _fake_agent_returning(content: str) -> Any:
    fake = MagicMock()
    fake.invoke = MagicMock(
        return_value={"messages": [MagicMock(content=content)]}
    )
    return fake


def test_coverage_verifier_computes_score_and_gaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """facts + article → verify_coverage_core で数値、LLM で gap 言語化。"""
    from libmatic.state.topic_debate import Fact

    facts = [
        Fact(
            claim="Next.js 15 の cache 戦略は段階的に変わる",
            source_urls=["s1"],
            confidence="high",
            category="design",
        ),
        Fact(
            claim="tsgo で 10 倍の高速化を達成",
            source_urls=["s2"],
            confidence="medium",
            category="number",
        ),
    ]
    state = _make_state(
        merged_facts=facts,
        article_draft="記事で Next.js 15 の cache 戦略は段階的に変わる ことに触れる。",
    )
    cfg = _make_config(coverage_threshold=0.80)

    import libmatic.nodes.topic_debate as nodes_mod
    from libmatic.nodes.topic_debate import coverage_verifier

    monkeypatch.setattr(
        nodes_mod,
        "build_step_agent",
        lambda step_name, config, tools, system_prompt: _fake_agent_returning(
            '以下が gap です: ["gap-1", "gap-2"]'
        ),
    )

    result = coverage_verifier(state, _rc(cfg))
    # 2 件中 1 件 match なので 50% 前後
    assert 0.3 < result["coverage_score"] < 0.7
    assert result["coverage_gaps"] == ["gap-1", "gap-2"]
    assert result["coverage_loop_count"] == 1


def test_coverage_verifier_empty_facts_returns_zero_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _make_state(merged_facts=[])
    cfg = _make_config()

    import libmatic.nodes.topic_debate as nodes_mod
    from libmatic.nodes.topic_debate import coverage_verifier

    monkeypatch.setattr(
        nodes_mod, "build_step_agent",
        lambda *a, **kw: _fake_agent_returning("[]"),
    )

    result = coverage_verifier(state, _rc(cfg))
    assert result["coverage_score"] == 0.0
    assert result["coverage_gaps"] == []
    assert result["coverage_loop_count"] == 1


def test_coverage_verifier_llm_failure_returns_empty_gaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 呼出が例外を投げても node 全体は落ちず、gaps=[] で返る。"""
    from libmatic.state.topic_debate import Fact

    # claim は probe match (>= 8 chars) するように長めに
    state = _make_state(
        merged_facts=[
            Fact(
                claim="重要な論点である claim",
                source_urls=["s"],
                confidence="high",
                category="c",
            )
        ],
        article_draft="記事の中で 重要な論点である claim に触れる。",
    )
    cfg = _make_config()

    class FailingAgent:
        def invoke(self, _: dict) -> dict:
            raise RuntimeError("LLM down")

    import libmatic.nodes.topic_debate as nodes_mod
    from libmatic.nodes.topic_debate import coverage_verifier

    monkeypatch.setattr(nodes_mod, "build_step_agent", lambda *a, **kw: FailingAgent())

    result = coverage_verifier(state, _rc(cfg))
    assert result["coverage_gaps"] == []
    # 数値側は引き続き計算される
    assert result["coverage_score"] > 0
    assert result["coverage_loop_count"] == 1


def test_coverage_verifier_increments_loop_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _make_state(merged_facts=[], coverage_loop_count=1)
    cfg = _make_config()

    import libmatic.nodes.topic_debate as nodes_mod
    from libmatic.nodes.topic_debate import coverage_verifier

    monkeypatch.setattr(
        nodes_mod, "build_step_agent",
        lambda *a, **kw: _fake_agent_returning("[]"),
    )

    result = coverage_verifier(state, _rc(cfg))
    assert result["coverage_loop_count"] == 2


def test_coverage_verifier_uses_issue_body_when_no_article(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """article_draft が空のとき、issue_body を検証対象にする (初回 step 6)."""
    from libmatic.state.topic_debate import Fact

    state = _make_state(
        issue_body="テーマの論点として foo bar baz claim が重要。",
        merged_facts=[
            Fact(
                claim="foo bar baz claim",
                source_urls=["s"],
                confidence="high",
                category="c",
            )
        ],
        article_draft="",
    )
    cfg = _make_config()

    import libmatic.nodes.topic_debate as nodes_mod
    from libmatic.nodes.topic_debate import coverage_verifier

    monkeypatch.setattr(
        nodes_mod, "build_step_agent",
        lambda *a, **kw: _fake_agent_returning("[]"),
    )

    result = coverage_verifier(state, _rc(cfg))
    # issue_body 内に claim が含まれるので cover される
    assert result["coverage_score"] > 0.5


# --- _facts_to_claims_archive ---


def test_facts_to_claims_archive_groups_by_source() -> None:
    from libmatic.nodes.topic_debate import _facts_to_claims_archive
    from libmatic.state.topic_debate import Fact

    facts = [
        Fact(claim="A", source_urls=["s1"], confidence="high", category="c"),
        Fact(claim="B", source_urls=["s1", "s2"], confidence="high", category="c"),
        Fact(claim="C", source_urls=["s2"], confidence="low", category="c"),
    ]
    archive = _facts_to_claims_archive(facts)
    source_ids = {a["source_id"] for a in archive}
    assert source_ids == {"s1", "s2"}
    s1_claims = next(a["claims"] for a in archive if a["source_id"] == "s1")
    s2_claims = next(a["claims"] for a in archive if a["source_id"] == "s2")
    assert {c["text"] for c in s1_claims} == {"A", "B"}
    assert {c["text"] for c in s2_claims} == {"B", "C"}


def test_facts_to_claims_archive_unknown_source_when_empty_urls() -> None:
    from libmatic.nodes.topic_debate import _facts_to_claims_archive
    from libmatic.state.topic_debate import Fact

    facts = [Fact(claim="X", source_urls=[], confidence="high", category="c")]
    archive = _facts_to_claims_archive(facts)
    assert len(archive) == 1
    assert archive[0]["source_id"] == "unknown"


# --- _parse_gaps_json ---


def test_parse_gaps_json_direct_array() -> None:
    from libmatic.nodes.topic_debate import _parse_gaps_json

    assert _parse_gaps_json('["a", "b", "c"]') == ["a", "b", "c"]


def test_parse_gaps_json_surrounded_by_text() -> None:
    from libmatic.nodes.topic_debate import _parse_gaps_json

    content = '以下が gap です:\n["x", "y"]\n以上。'
    assert _parse_gaps_json(content) == ["x", "y"]


def test_parse_gaps_json_invalid_returns_empty() -> None:
    from libmatic.nodes.topic_debate import _parse_gaps_json

    assert _parse_gaps_json("") == []
    assert _parse_gaps_json("no brackets here") == []
    assert _parse_gaps_json("[not valid json]") == []


def test_parse_gaps_json_filters_empty_and_null() -> None:
    from libmatic.nodes.topic_debate import _parse_gaps_json

    content = '["a", "", "b", null, "c"]'
    # 空文字列と None は除外
    assert _parse_gaps_json(content) == ["a", "b", "c"]
