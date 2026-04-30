"""ReAct agent factory for libmatic nodes.

各 step 用に model (providers/factory の resolve_model で解決) と tools / prompt を
bind した LangGraph の ReAct subgraph を返す。

system_prompt は SystemMessage の content block 形式 + cache_control: ephemeral で
注入されるため、同 step 内 ReAct loop の 2 turn 目以降は system prefix が cache hit
する。`response.usage.cache_read_input_tokens` で確認可能。

Phase 1.3 の残り: 各 ReAct step node はこの factory を使って agent を組み立て、
`.invoke({"messages": [...]})` で推論を回す。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from libmatic.config import LibmaticConfig
from libmatic.providers.factory import get_model


def _make_cached_system_modifier(
    system_prompt: str,
) -> Callable[[dict[str, Any]], list[Any]]:
    """system_prompt を cache_control 付き SystemMessage で挿入する state_modifier.

    LangGraph create_react_agent の prompt パラメータが string と callable の両方を
    受けるのを利用。callable で SystemMessage の content を block 形式にして
    cache_control: ephemeral を attach することで、同一 step 内 ReAct loop の
    2 turn 目以降で system prefix が prompt cache に hit する。

    Anthropic の prefix-match cache 仕様 (render order: tools → system → messages)
    に従い、tools と system が一緒に cache される。
    """
    cached_system = SystemMessage(
        content=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]
    )

    def modifier(state: dict[str, Any]) -> list[Any]:
        messages = state.get("messages", []) if isinstance(state, dict) else []
        return [cached_system, *messages]

    return modifier


def build_step_agent(
    step_name: str,
    config: LibmaticConfig,
    tools: list[BaseTool],
    system_prompt: str | None = None,
) -> Any:
    """Step 用の ReAct agent を組み立てる。

    Args:
        step_name: STEP_TIER_MAP に登録された step 名
            (例: 'step1_source_collector', 'step4_fact_extractor')
        config: LibmaticConfig (provider / preset / overrides を保持)
        tools: agent に bind する LangChain tool のリスト
        system_prompt: system prompt。None なら create_react_agent の default。
            指定時は cache_control: ephemeral 付きで挿入される (同 step 内
            loop で system prefix が cache hit する)。

    Returns:
        LangGraph の compiled subgraph (.invoke / .stream できる)
    """
    model = get_model(step_name, config)
    kwargs: dict[str, Any] = {"model": model, "tools": tools}
    if system_prompt is not None:
        kwargs["prompt"] = _make_cached_system_modifier(system_prompt)
    return create_react_agent(**kwargs)
