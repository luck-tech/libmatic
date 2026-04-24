"""ReAct agent factory for libmatic nodes.

各 step 用に model (providers/factory の resolve_model で解決) と tools / prompt を
bind した LangGraph の ReAct subgraph を返す。

Phase 1.3 の残り: 各 ReAct step node はこの factory を使って agent を組み立て、
`.invoke({"messages": [...]})` で推論を回す。
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from libmatic.config import LibmaticConfig
from libmatic.providers.factory import get_model


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
        system_prompt: system prompt (None なら create_react_agent の default)

    Returns:
        LangGraph の compiled subgraph (.invoke / .stream できる)
    """
    model = get_model(step_name, config)
    kwargs: dict[str, Any] = {"model": model, "tools": tools}
    if system_prompt is not None:
        kwargs["prompt"] = system_prompt
    return create_react_agent(**kwargs)
