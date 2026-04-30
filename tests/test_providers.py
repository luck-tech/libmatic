"""Provider factory / resolve_model の test."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from libmatic.config import GitHubConfig, LibmaticConfig, ModelOverrides, ModelsConfig
from libmatic.providers.factory import (
    PRESET_MODELS,
    STEP_EFFORT_MAP,
    STEP_MAX_TOKENS,
    STEP_THINKING_MAP,
    STEP_TIER_MAP,
    STREAMING_THRESHOLD,
    _clamp_effort,
    _supports_thinking,
    build_model_kwargs,
    get_model,
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


# --- build_model_kwargs / _supports_thinking / _clamp_effort ---


def test_supports_thinking_modern_models() -> None:
    # adaptive thinking は Opus 4.6+ / Sonnet 4.6 で利用可
    assert _supports_thinking("claude-opus-4-7")
    assert _supports_thinking("claude-opus-4-6")
    assert _supports_thinking("claude-sonnet-4-6")


def test_supports_thinking_haiku_and_older_opus() -> None:
    # Haiku は thinking 非対応、Opus 4.5 は extended only (adaptive 非対応)
    assert not _supports_thinking("claude-haiku-4-5")
    assert not _supports_thinking("claude-opus-4-5")


def test_clamp_effort_opus_4_7_supports_xhigh_and_max() -> None:
    assert _clamp_effort("xhigh", "claude-opus-4-7") == "xhigh"
    assert _clamp_effort("max", "claude-opus-4-7") == "max"


def test_clamp_effort_sonnet_4_6_caps_at_high() -> None:
    # xhigh / max は Sonnet 4.6 で非対応 → high にクランプ
    assert _clamp_effort("xhigh", "claude-sonnet-4-6") == "high"
    assert _clamp_effort("max", "claude-sonnet-4-6") == "high"
    assert _clamp_effort("medium", "claude-sonnet-4-6") == "medium"


def test_clamp_effort_opus_4_6_skips_xhigh_to_high() -> None:
    # Opus 4.6 は xhigh 無し、max あり。次に低い supported は "high" (max は xhigh より上)
    assert _clamp_effort("xhigh", "claude-opus-4-6") == "high"
    assert _clamp_effort("max", "claude-opus-4-6") == "max"


def test_clamp_effort_haiku_returns_none() -> None:
    assert _clamp_effort("medium", "claude-haiku-4-5") is None


def test_build_model_kwargs_long_form_step_uses_streaming() -> None:
    # step7 article_writer は 64K → streaming 必須
    kwargs = build_model_kwargs("step7_article_writer", "claude-sonnet-4-6")
    assert kwargs["max_tokens"] == 64000
    assert kwargs["streaming"] is True


def test_build_model_kwargs_short_step_no_streaming() -> None:
    # step1 source_collector は 4K → streaming は付かない
    kwargs = build_model_kwargs("step1_source_collector", "claude-sonnet-4-6")
    assert kwargs["max_tokens"] == 4000
    assert "streaming" not in kwargs


def test_build_model_kwargs_threshold_boundary() -> None:
    # STREAMING_THRESHOLD ちょうど (16K) で streaming が付く
    assert STREAMING_THRESHOLD == 16000
    kwargs = build_model_kwargs("step4_fact_extractor", "claude-haiku-4-5")
    assert kwargs["max_tokens"] == 16000
    assert kwargs["streaming"] is True


def test_build_model_kwargs_attaches_thinking_for_writer_steps() -> None:
    kwargs = build_model_kwargs("step7_article_writer", "claude-sonnet-4-6")
    assert kwargs["thinking"] == {"type": "adaptive"}
    kwargs8 = build_model_kwargs("step8_expanded_writer", "claude-opus-4-7")
    assert kwargs8["thinking"] == {"type": "adaptive"}


def test_build_model_kwargs_attaches_clamped_effort_for_sonnet() -> None:
    # Sonnet 4.6 で xhigh 要求 → high にクランプ
    kwargs = build_model_kwargs("step7_article_writer", "claude-sonnet-4-6")
    assert kwargs["output_config"] == {"effort": "high"}


def test_build_model_kwargs_passes_xhigh_for_opus_4_7() -> None:
    # Opus 4.7 は xhigh をそのまま付与
    kwargs = build_model_kwargs("step7_article_writer", "claude-opus-4-7")
    assert kwargs["output_config"] == {"effort": "xhigh"}


def test_build_model_kwargs_skips_effort_thinking_on_haiku() -> None:
    # Haiku は thinking / effort を渡さない (API error 回避)
    kwargs = build_model_kwargs("step4_fact_extractor", "claude-haiku-4-5")
    assert "thinking" not in kwargs
    assert "output_config" not in kwargs


def test_build_model_kwargs_unknown_step_falls_back() -> None:
    # 未登録 step は max_tokens=8192 fallback
    kwargs = build_model_kwargs("step999_unknown", "claude-sonnet-4-6")
    assert kwargs["max_tokens"] == 8192
    assert "streaming" not in kwargs


def test_step_max_tokens_covers_all_tier_map_steps() -> None:
    # STEP_TIER_MAP に登録された step は全て max_tokens 設定が要る
    # (未登録 fallback は事故防止のため避ける)
    missing = [s for s in STEP_TIER_MAP if s not in STEP_MAX_TOKENS]
    assert missing == [], f"STEP_MAX_TOKENS に未登録: {missing}"


def test_step_effort_only_for_capable_steps() -> None:
    # STEP_EFFORT_MAP は STEP_TIER_MAP のサブセットであるべき
    extra = [s for s in STEP_EFFORT_MAP if s not in STEP_TIER_MAP]
    assert extra == [], f"STEP_TIER_MAP 外の step: {extra}"


def test_step_thinking_limited_to_long_writers() -> None:
    # adaptive thinking は step 7/8 のみ (cost 効率)
    assert set(STEP_THINKING_MAP.keys()) == {
        "step7_article_writer",
        "step8_expanded_writer",
    }


# --- get_model (extra kwargs) ---


def _make_simple_config() -> LibmaticConfig:
    return LibmaticConfig(
        preset="balanced",
        models=ModelsConfig(),
        github=GitHubConfig(repo="x/y"),
    )


def test_get_model_passes_step_kwargs_to_init_chat_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_init(model: str, **kwargs: Any) -> Any:
        captured["model"] = model
        captured["kwargs"] = kwargs
        return MagicMock()

    monkeypatch.setattr("libmatic.providers.factory.init_chat_model", fake_init)
    cfg = _make_simple_config()

    get_model("step7_article_writer", cfg)

    assert captured["model"] == "anthropic:claude-sonnet-4-6"
    assert captured["kwargs"]["max_tokens"] == 64000
    assert captured["kwargs"]["streaming"] is True
    assert captured["kwargs"]["thinking"] == {"type": "adaptive"}
    # Sonnet 4.6 は xhigh 非対応 → high にクランプ
    assert captured["kwargs"]["output_config"] == {"effort": "high"}


def test_get_model_extra_kwargs_override_step_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_init(model: str, **kwargs: Any) -> Any:
        captured["kwargs"] = kwargs
        return MagicMock()

    monkeypatch.setattr("libmatic.providers.factory.init_chat_model", fake_init)
    cfg = _make_simple_config()

    # extra で max_tokens を上書き
    get_model("step7_article_writer", cfg, max_tokens=2000)
    assert captured["kwargs"]["max_tokens"] == 2000
