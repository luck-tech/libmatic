"""Anthropic 固有の cache_control helper (per-message 用、v1.1 で実装予定).

Phase 0 決定 (libmatic-oss-plan.md §6.7):
- LangChain `@tool` + `bind_tools()` で provider 差を吸収し、
  cache_control のような Anthropic 固有拡張のみこの helper で扱う。

v0.1 のスコープ:
- system prompt の prefix cache は `libmatic.agents.react._make_cached_system_modifier`
  で既に実装済み (SystemMessage の content block + cache_control: ephemeral)。
- この module は v1.1 で AIMessage / ToolMessage 単位の cache_control attachment
  (大きな tool 結果を次 loop で cache hit させる用途) を入れる予定の stub。
"""

from __future__ import annotations

from langchain_core.messages import BaseMessage


def attach_cache_control(message: BaseMessage, ttl: str = "5m") -> BaseMessage:
    """Attach Anthropic cache_control marker to the message.

    v1.1 で本実装予定 (AIMessage / ToolMessage の content block への
    cache_control 挿入。tool 結果の cache hit を狙う)。
    System prompt の cache は agents/react.py 側で実装済みのため、ここは扱わない。
    """
    raise NotImplementedError("v1.1 で実装")
