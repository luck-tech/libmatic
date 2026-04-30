"""Provider + model factory.

Phase 0 決定 (libmatic-oss-plan.md §3.3 f, §6.7):
- preset が default / cheap の 2 tier に展開
- 各 step はコード側で tier 固定
- user は config.models.overrides で step 単位で具体 model を指定

v0.1 Anthropic API tuning (2026-05-01):
- step 別 max_tokens を STEP_MAX_TOKENS で固定 (article_writer 64K 等)
- 16K 以上は streaming=True 自動付与 (SDK HTTP timeout 回避)
- step 別 effort を STEP_EFFORT_MAP で指定 (Sonnet 4.6 default high の調整)
- step 7/8 で adaptive thinking を STEP_THINKING_MAP で有効化 (長文の論理一貫性)
- effort / thinking は Haiku では非対応なので model 名で skip
"""

from __future__ import annotations

from typing import Any, Literal

from langchain.chat_models import init_chat_model

from libmatic.config import LibmaticConfig

Tier = Literal["default", "cheap"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]

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

# step 別の max_tokens (Anthropic API の output 上限指定)。
# article_writer / expanded_writer は 3000-5000 行の長文出力を想定するため大きめに。
# default ChatAnthropic max_tokens は 1024 で、明示しないと長文 step が truncate される。
STEP_MAX_TOKENS: dict[str, int] = {
    "step1_source_collector": 4000,
    "step4_fact_extractor": 16000,
    "step5_fact_merger": 8000,
    "step6_coverage_verifier": 2000,
    "step7_article_writer": 64000,
    "step8_expanded_writer": 64000,
    "suggest_a3_relevance_filter": 8000,
    "suggest_a6_propose_sources": 2000,
    "pr_c2_classify_comments": 2000,
    "pr_c3_address_each": 16000,
}

# 16K 超は SDK HTTP timeout を避けるため streaming 必須 (内部 SSE で受信)。
# invoke の同期 API は変わらないので呼出側のコード変更不要。
STREAMING_THRESHOLD = 16000

# step 別の effort (Anthropic 4.5+/4.6+/4.7 の output_config.effort)。
# Sonnet 4.6 / Opus 4.6 / Opus 4.5 / Opus 4.7 のみ対応、Haiku では非対応。
# Sonnet 4.6 default は "high" — 明示しないと試算より高コスト。
STEP_EFFORT_MAP: dict[str, Effort] = {
    "step1_source_collector": "medium",
    "step5_fact_merger": "medium",
    "step6_coverage_verifier": "medium",
    "step7_article_writer": "xhigh",
    "step8_expanded_writer": "xhigh",
    "suggest_a3_relevance_filter": "medium",
    "pr_c3_address_each": "high",
    # cheap tier (Haiku) の step は省略 (Haiku は effort 非対応)
}

# step 7/8 で adaptive thinking を有効化 (長文の論理一貫性が上がる)。
# Haiku 4.5 / Opus 4.5 以前では非対応のため model 名で skip。
# Opus 4.7 は thinking content default omitted、log 表示が要る場合は display=summarized。
STEP_THINKING_MAP: dict[str, dict[str, str]] = {
    "step7_article_writer": {"type": "adaptive"},
    "step8_expanded_writer": {"type": "adaptive"},
}

# `thinking: {type: "adaptive"}` 対応 model (prefix match)。
# Opus 4.5 以前は extended thinking only で adaptive 非対応のため除外。
# Haiku は thinking 完全非対応。
_THINKING_CAPABLE_PREFIXES = (
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
)

# 各 model が `output_config.effort` でサポートする level の集合。
# Opus 4.7 のみ "xhigh"、Opus 4.6/4.5 は "max" あるが "xhigh" 無し、
# Sonnet 4.6 は "high" まで (max / xhigh 非対応)、Haiku は effort 完全非対応。
_MODEL_EFFORT_LEVELS: dict[str, frozenset[Effort]] = {
    "claude-opus-4-7": frozenset(["low", "medium", "high", "xhigh", "max"]),
    "claude-opus-4-6": frozenset(["low", "medium", "high", "max"]),
    "claude-opus-4-5": frozenset(["low", "medium", "high", "max"]),
    "claude-sonnet-4-6": frozenset(["low", "medium", "high"]),
}

# clamp 用の昇順ランク。
_EFFORT_RANK_ORDER: tuple[Effort, ...] = ("low", "medium", "high", "xhigh", "max")


def _supports_thinking(model_name: str) -> bool:
    """model 名が adaptive thinking をサポートしているか (prefix で判定)."""
    return any(model_name.startswith(p) for p in _THINKING_CAPABLE_PREFIXES)


def _clamp_effort(effort: Effort, model_name: str) -> Effort | None:
    """step が要求する effort level を model の supported set 内に下方 clamp。

    例: step7 が "xhigh" を要求 → Sonnet 4.6 は "high" にクランプ、
        Opus 4.6 は "max" がより近いが安全側で "high" に下げる
        (xhigh > high で next-lower)。

    Returns:
        supported な Effort、または model が effort 非対応なら None。
    """
    supported: frozenset[Effort] | None = None
    for prefix, levels in _MODEL_EFFORT_LEVELS.items():
        if model_name.startswith(prefix):
            supported = levels
            break
    if supported is None:
        return None  # Haiku 等
    if effort in supported:
        return effort
    # 要求 level を下方 clamp (next-lower supported を探す)
    target_idx = _EFFORT_RANK_ORDER.index(effort)
    for i in range(target_idx - 1, -1, -1):
        candidate = _EFFORT_RANK_ORDER[i]
        if candidate in supported:
            return candidate
    return None


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


def build_model_kwargs(step_name: str, model_name: str) -> dict[str, Any]:
    """init_chat_model に渡す step 別の kwargs を組み立てる。

    - max_tokens: STEP_MAX_TOKENS から取得 (未登録 step は 8192 fallback)
    - streaming: max_tokens >= 16K なら True (SDK HTTP timeout 回避)
    - thinking: STEP_THINKING_MAP に登録あり、かつ model が対応していれば付与
      (Opus 4.7 / 4.6 / Sonnet 4.6)
    - output_config.effort: STEP_EFFORT_MAP に登録あり、かつ model が対応していれば
      _clamp_effort で model 上限に下方 clamp して付与
      (e.g. xhigh on Sonnet 4.6 → high)
    """
    max_tokens = STEP_MAX_TOKENS.get(step_name, 8192)
    kwargs: dict[str, Any] = {"max_tokens": max_tokens}
    if max_tokens >= STREAMING_THRESHOLD:
        kwargs["streaming"] = True

    if _supports_thinking(model_name):
        if thinking := STEP_THINKING_MAP.get(step_name):
            kwargs["thinking"] = dict(thinking)

    if requested_effort := STEP_EFFORT_MAP.get(step_name):
        if (clamped := _clamp_effort(requested_effort, model_name)) is not None:
            kwargs["output_config"] = {"effort": clamped}

    return kwargs


def get_model(step_name: str, config: LibmaticConfig, **extra: Any) -> Any:
    """Get LangChain chat model instance for the given step.

    `extra` で呼出側から個別 kwargs を上書きできる (step_kwargs を merge)。
    """
    model_name = resolve_model(step_name, config)
    base_kwargs = build_model_kwargs(step_name, model_name)
    merged: dict[str, Any] = {**base_kwargs, **extra}
    return init_chat_model(f"{config.provider}:{model_name}", **merged)
