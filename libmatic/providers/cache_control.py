"""Anthropic 固有の cache_control helper.

Phase 0 決定 (libmatic-oss-plan.md §6.7):
- LangChain `@tool` + `bind_tools()` で provider 差を吸収し、
  cache_control のような Anthropic 固有拡張のみこの helper で扱う。
- v1.1 で本格的な prompt caching 最適化を入れる予定。
- v0.1 では API インタフェースのみ切り、実体は stub。
"""

from __future__ import annotations

from langchain_core.messages import BaseMessage


def attach_cache_control(message: BaseMessage, ttl: str = "5m") -> BaseMessage:
    """Attach Anthropic cache_control marker to the message.

    v1.1 で本実装予定 (AIMessage.additional_kwargs への cache_control 挿入)。
    """
    raise NotImplementedError("v1.1 で実装")
