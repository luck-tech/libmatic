"""libmatic configuration schema.

See docs/SPEC.md §10 for the user-facing yaml structure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

Provider = Literal["anthropic", "openai", "google_genai"]
Preset = Literal["quality", "balanced", "economy"]


class ModelOverrides(BaseModel):
    """Step-specific model override (optional).

    Keys must match STEP_TIER_MAP in libmatic.providers.factory.
    """

    # topic-debate
    step1_source_collector: str | None = None
    step4_fact_extractor: str | None = None
    step5_fact_merger: str | None = None
    step6_coverage_verifier: str | None = None
    step7_article_writer: str | None = None
    step8_expanded_writer: str | None = None
    # suggest-topics
    suggest_a3_relevance_filter: str | None = None
    suggest_a6_propose_sources: str | None = None
    # address-pr-comments
    pr_c2_classify_comments: str | None = None
    pr_c3_address_each: str | None = None

    def get_override(self, step_name: str) -> str | None:
        return getattr(self, step_name, None)


class ModelsConfig(BaseModel):
    overrides: ModelOverrides = Field(default_factory=ModelOverrides)


class ContentConfig(BaseModel):
    universal_dir: str = "content/{category}/notes"
    ephemeral_dir: str = "content/digest/{year}/Q{quarter}"
    categories: list[str] = Field(
        default_factory=lambda: [
            "ai-ml",
            "architecture",
            "case-studies",
            "development",
            "domains",
            "fundamentals",
            "infrastructure",
            "practices",
        ]
    )


class LifespanConfig(BaseModel):
    ephemeral_pruning_years: int = 2


class WorkflowConfig(BaseModel):
    max_sources_per_topic: int = 12
    max_concurrent_fetches: int = 6
    max_react_iterations: int = 15
    coverage_threshold: float = 0.80
    max_coverage_loops: int = 2


class GitHubLabels(BaseModel):
    pending: str = "topic/pending"
    ready: str = "topic/ready"
    in_progress: str = "topic/in-progress"
    review: str = "topic/review"
    failed: str = "topic/failed"


class GitHubConfig(BaseModel):
    repo: str
    issue_labels: GitHubLabels = Field(default_factory=GitHubLabels)


class LibmaticConfig(BaseModel):
    version: int = 1
    provider: Provider = "anthropic"
    preset: Preset = "balanced"
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    content: ContentConfig = Field(default_factory=ContentConfig)
    lifespan: LifespanConfig = Field(default_factory=LifespanConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    github: GitHubConfig

    @classmethod
    def load(cls, path: str | Path) -> LibmaticConfig:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)
