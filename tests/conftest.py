"""pytest shared fixtures."""

from __future__ import annotations

import pytest

from libmatic.config import GitHubConfig, LibmaticConfig


@pytest.fixture
def default_config() -> LibmaticConfig:
    return LibmaticConfig(
        github=GitHubConfig(repo="OWNER/REPO"),
    )
