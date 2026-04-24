"""Provider factory / resolve_model の test."""

from __future__ import annotations

from typing import Any

import pytest

from libmatic.config import GitHubConfig, LibmaticConfig, ModelOverrides, ModelsConfig
from libmatic.providers.factory import (
    PRESET_MODELS,
    STEP_TIER_MAP,
    resolve_model,
)


def _make_config(preset: str = "balanced", **overrides: Any) -> LibmaticConfig:
    return LibmaticConfig(
        preset=preset,  # type: ignore[arg-type]
        models=ModelsConfig(overrides=ModelOverrides(**overrides)),
        github=GitHubConfig(repo="x/y"),
    )


def test_preset_balanced_default_tier() -> None:
    cfg = _make_config("balanced")
    assert resolve_model("step7_article_writer", cfg) == "claude-sonnet-4-6"


def test_preset_balanced_cheap_tier() -> None:
    cfg = _make_config("balanced")
    assert resolve_model("step4_fact_extractor", cfg) == "claude-haiku-4-5"


def test_preset_quality_uses_opus() -> None:
    cfg = _make_config("quality")
    assert resolve_model("step7_article_writer", cfg) == "claude-opus-4-7"


def test_preset_economy_all_haiku() -> None:
    cfg = _make_config("economy")
    assert resolve_model("step7_article_writer", cfg) == "claude-haiku-4-5"
    assert resolve_model("step4_fact_extractor", cfg) == "claude-haiku-4-5"


def test_override_beats_preset() -> None:
    cfg = _make_config("balanced", step7_article_writer="claude-opus-4-7")
    assert resolve_model("step7_article_writer", cfg) == "claude-opus-4-7"


def test_override_isolated_to_named_step() -> None:
    cfg = _make_config("balanced", step7_article_writer="claude-opus-4-7")
    # step8 に override が無ければ preset の default tier が使われる
    assert resolve_model("step8_expanded_writer", cfg) == "claude-sonnet-4-6"


def test_resolve_unknown_step_raises() -> None:
    cfg = _make_config("balanced")
    with pytest.raises(ValueError):
        resolve_model("step999_unknown", cfg)


def test_step_tier_map_covers_topic_debate_llm_steps() -> None:
    # topic-debate で LLM を使う全 step が登録されている
    for step in (
        "step1_source_collector",
        "step4_fact_extractor",
        "step5_fact_merger",
        "step6_coverage_verifier",
        "step7_article_writer",
        "step8_expanded_writer",
    ):
        assert step in STEP_TIER_MAP


def test_fact_extractor_is_cheap_tier() -> None:
    assert STEP_TIER_MAP["step4_fact_extractor"] == "cheap"


def test_article_writer_is_default_tier() -> None:
    assert STEP_TIER_MAP["step7_article_writer"] == "default"


def test_preset_models_has_three_presets_for_anthropic() -> None:
    assert set(PRESET_MODELS["anthropic"].keys()) == {"quality", "balanced", "economy"}
