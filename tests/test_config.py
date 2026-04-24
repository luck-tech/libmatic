"""LibmaticConfig の pydantic validation test."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from libmatic.config import GitHubConfig, LibmaticConfig


def test_config_defaults(default_config: LibmaticConfig) -> None:
    assert default_config.version == 1
    assert default_config.provider == "anthropic"
    assert default_config.preset == "balanced"
    assert default_config.workflow.coverage_threshold == 0.80
    assert default_config.workflow.max_coverage_loops == 2
    assert default_config.github.repo == "luck-tech/my_library"
    assert default_config.github.issue_labels.pending == "topic/pending"


def test_config_categories_include_expected() -> None:
    cfg = LibmaticConfig(github=GitHubConfig(repo="x/y"))
    assert "ai-ml" in cfg.content.categories
    assert "architecture" in cfg.content.categories


def test_invalid_provider_rejected() -> None:
    with pytest.raises(ValidationError):
        LibmaticConfig(
            provider="invalid_provider",  # type: ignore[arg-type]
            github=GitHubConfig(repo="x/y"),
        )


def test_invalid_preset_rejected() -> None:
    with pytest.raises(ValidationError):
        LibmaticConfig(
            preset="ultra",  # type: ignore[arg-type]
            github=GitHubConfig(repo="x/y"),
        )


def test_github_repo_required() -> None:
    with pytest.raises(ValidationError):
        LibmaticConfig()  # type: ignore[call-arg]
