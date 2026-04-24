"""State schema for suggest-topics workflow."""

from __future__ import annotations

from typing import Annotated, Literal

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

Lifespan = Literal["universal", "ephemeral"]


class TopicCandidate(BaseModel):
    title: str
    body: str
    lifespan: Lifespan
    source_urls: list[str]
    score: float = 0.0


class SuggestTopicsState(BaseModel):
    source_priorities_path: str = "config/source_priorities.yml"

    raw_candidates: list[dict] = Field(default_factory=list)
    filtered_candidates: list[TopicCandidate] = Field(default_factory=list)
    new_sources_detected: list[dict] = Field(default_factory=list)

    created_issues: list[int] = Field(default_factory=list)
    proposal_pr_number: int | None = None

    messages: Annotated[list, add_messages] = Field(default_factory=list)
