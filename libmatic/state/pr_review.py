"""State schema for address-pr-comments workflow."""

from __future__ import annotations

from typing import Annotated, Literal

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

CommentClass = Literal["address", "reply", "ignore"]


class ReviewComment(BaseModel):
    id: int
    body: str
    path: str | None = None
    line: int | None = None
    author: str


class PRReviewState(BaseModel):
    pr_number: int
    comments: list[ReviewComment] = Field(default_factory=list)
    classified: dict[int, CommentClass] = Field(default_factory=dict)
    actions_log: list[dict] = Field(default_factory=list)
    committed: bool = False
    replied_comment_ids: list[int] = Field(default_factory=list)
    messages: Annotated[list, add_messages] = Field(default_factory=list)
