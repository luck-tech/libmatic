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

    # A1 出力: priorities yml から展開された feed URL リスト
    feeds: list[str] = Field(default_factory=list)

    # A2 出力: 各 feed から拾った raw entry (まだフィルタ前)
    raw_candidates: list[dict] = Field(default_factory=list)

    # A3 出力: 起票価値ありと判定された TopicCandidate
    filtered_candidates: list[TopicCandidate] = Field(default_factory=list)

    # A6 用: priorities にない domain で 2 件以上登場したもの
    new_sources_detected: list[dict] = Field(default_factory=list)

    # A5 出力: 起票された issue 番号
    created_issues: list[int] = Field(default_factory=list)

    # A6 出力: source 追加 PR が作成された場合の番号
    proposal_pr_number: int | None = None

    messages: Annotated[list, add_messages] = Field(default_factory=list)
