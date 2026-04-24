"""State schema の instantiation test."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from libmatic.state.pr_review import PRReviewState, ReviewComment
from libmatic.state.suggest_topics import SuggestTopicsState, TopicCandidate
from libmatic.state.topic_debate import Fact, Source, TopicDebateState


def test_topic_debate_state_minimal() -> None:
    s = TopicDebateState(
        issue_number=18,
        issue_title="test",
        issue_body="body",
        lifespan="universal",
    )
    assert s.issue_number == 18
    assert s.coverage_score == 0.0
    assert s.coverage_loop_count == 0
    assert s.messages == []
    assert s.candidate_sources == []


def test_topic_debate_state_invalid_lifespan() -> None:
    with pytest.raises(ValidationError):
        TopicDebateState(
            issue_number=1,
            issue_title="t",
            issue_body="b",
            lifespan="unknown",  # type: ignore[arg-type]
        )


def test_source_instantiation() -> None:
    src = Source(url="https://example.com", type="rss", title="example")
    assert src.score == 0.0
    assert src.fetched_content is None


def test_source_invalid_type() -> None:
    with pytest.raises(ValidationError):
        Source(url="x", type="blog", title="t")  # type: ignore[arg-type]


def test_fact_instantiation() -> None:
    f = Fact(
        claim="X is Y",
        source_urls=["https://a", "https://b"],
        confidence="high",
        category="design-principle",
    )
    assert len(f.source_urls) == 2


def test_suggest_topics_state_defaults() -> None:
    s = SuggestTopicsState()
    assert s.source_priorities_path == "config/source_priorities.yml"
    assert s.created_issues == []


def test_topic_candidate_instantiation() -> None:
    c = TopicCandidate(
        title="t",
        body="b",
        lifespan="ephemeral",
        source_urls=["https://x"],
    )
    assert c.score == 0.0


def test_pr_review_state_requires_pr_number() -> None:
    with pytest.raises(ValidationError):
        PRReviewState()  # type: ignore[call-arg]


def test_pr_review_state_minimal() -> None:
    s = PRReviewState(pr_number=37)
    assert s.pr_number == 37
    assert s.committed is False
    assert s.comments == []


def test_review_comment_minimal() -> None:
    c = ReviewComment(id=1, body="LGTM", author="ユーザー名")
    assert c.path is None
    assert c.line is None
