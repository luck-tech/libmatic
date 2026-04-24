"""Provider + model factory.

Phase 0 決定 (libmatic-oss-plan.md §3.3 f, §6.7):
- preset が default / cheap の 2 tier に展開
- 各 step はコード側で tier 固定
- user は config.models.overrides で step 単位で具体 model を指定
"""

from __future__ import annotations

from typing import Any, Literal

from langchain.chat_models import init_chat_model

from libmatic.config import LibmaticConfig

Tier = Literal["default", "cheap"]

# v0.1 は Anthropic のみ実装
PRESET_MODELS: dict[str, dict[str, dict[Tier, str]]] = {
    "anthropic": {
        "quality": {"default": "claude-opus-4-7", "cheap": "claude-haiku-4-5"},
        "balanced": {"default": "claude-sonnet-4-6", "cheap": "claude-haiku-4-5"},
        "economy": {"default": "claude-haiku-4-5", "cheap": "claude-haiku-4-5"},
    },
    # v0.2 で openai、v0.3 で google_genai を追加
}

# 各 step が default / cheap のどちらを使うか (コード側で固定)
STEP_TIER_MAP: dict[str, Tier] = {
    # topic-debate (LLM を使う step のみ)
    "step1_source_collector": "default",
    "step4_fact_extractor": "cheap",
    "step5_fact_merger": "default",
    "step6_coverage_verifier": "default",
    "step7_article_writer": "default",
    "step8_expanded_writer": "default",
    # suggest-topics
    "suggest_a3_relevance_filter": "default",
    "suggest_a6_propose_sources": "cheap",
    # address-pr-comments
    "pr_c2_classify_comments": "cheap",
    "pr_c3_address_each": "default",
}


def resolve_model(step_name: str, config: LibmaticConfig) -> str:
    """Resolve model name for the given step.

    優先順位: config.models.overrides > preset の tier 展開
    """
    override = config.models.overrides.get_override(step_name)
    if override:
        return override

    if step_name not in STEP_TIER_MAP:
        raise ValueError(
            f"Unknown step_name: {step_name}. "
            f"Add it to STEP_TIER_MAP in libmatic.providers.factory."
        )
    tier = STEP_TIER_MAP[step_name]

    if config.provider not in PRESET_MODELS:
        raise NotImplementedError(
            f"Provider {config.provider} はまだ実装されていない "
            f"(v0.1 は anthropic のみ)"
        )
    return PRESET_MODELS[config.provider][config.preset][tier]


def get_model(step_name: str, config: LibmaticConfig) -> Any:
    """Get LangChain chat model instance for the given step."""
    model_name = resolve_model(step_name, config)
    return init_chat_model(f"{config.provider}:{model_name}")
