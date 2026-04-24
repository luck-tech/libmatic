"""State schema for topic-debate workflow (9 step).

See docs/SPEC.md §3 for details.
"""

from __future__ import annotations

from typing import Annotated, Literal

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

SourceType = Literal[
    "rss", "youtube", "x", "zenn", "qiita", "github", "rfc", "generic"
]
ConfidenceLevel = Literal["high", "medium", "low"]
Lifespan = Literal["universal", "ephemeral"]


class Source(BaseModel):
    url: str
    type: SourceType
    title: str
    published_at: str | None = None
    score: float = 0.0
    fetched_content: str | None = None


class Fact(BaseModel):
    claim: str
    source_urls: list[str]
    confidence: ConfidenceLevel
    category: str  # "design-principle" / "case" / "number" / "quote" / ...


class TopicDebateState(BaseModel):
    # 入力
    issue_number: int
    issue_title: str
    issue_body: str
    lifespan: Lifespan

    # step 1-3
    candidate_sources: list[Source] = Field(default_factory=list)
    scored_sources: list[Source] = Field(default_factory=list)
    fetched_sources: list[Source] = Field(default_factory=list)

    # step 4-5
    raw_facts_per_source: list[list[Fact]] = Field(default_factory=list)
    merged_facts: list[Fact] = Field(default_factory=list)

    # step 6
    coverage_score: float = 0.0
    coverage_gaps: list[str] = Field(default_factory=list)
    coverage_loop_count: int = 0

    # step 7-8
    article_draft: str = ""
    article_expanded: str = ""
    output_path: str = ""  # content/... or content/digest/...

    # step 9
    pr_number: int | None = None
    pr_url: str | None = None

    # メタ
    messages: Annotated[list, add_messages] = Field(default_factory=list)
    retries: dict[str, int] = Field(default_factory=dict)
