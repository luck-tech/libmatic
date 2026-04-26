"""Shared helpers for libmatic nodes.

state / config 取り出し、LLM 出力 parse などを集約。
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.runnables import RunnableConfig

from libmatic.config import LibmaticConfig


def get_libmatic_config(config: RunnableConfig) -> LibmaticConfig:
    """RunnableConfig から LibmaticConfig を取り出す。

    Raises:
        ValueError: configurable.libmatic_config がセットされていない / 型不一致
    """
    configurable = (config or {}).get("configurable") or {}
    lcfg = configurable.get("libmatic_config")
    if not isinstance(lcfg, LibmaticConfig):
        raise ValueError(
            "RunnableConfig.configurable.libmatic_config に "
            "LibmaticConfig インスタンスをセットしてください"
        )
    return lcfg


def last_message_content(result: Any) -> str:
    """LangGraph agent の invoke 結果から最後の message の content を string で取る。

    Anthropic 等の structured content (list of {type, text}) も平文化する。
    """
    messages = (result or {}).get("messages", []) if isinstance(result, dict) else []
    if not messages:
        return ""
    last = messages[-1]
    content = getattr(last, "content", None)
    if content is None and isinstance(last, dict):
        content = last.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content) if content is not None else ""


def parse_json_array(content: str) -> list[Any]:
    """LLM 出力から JSON array (`[...]`) を抽出。周辺に説明文があっても OK。

    - 最初の `[` と最後の `]` 区間を掴む
    - 解析失敗 / 見つからない → 空リスト
    - 非 array (dict など) が入っていたら [] を返す
    """
    if not content:
        return []
    start = content.find("[")
    end = content.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    snippet = content[start : end + 1]
    try:
        data = json.loads(snippet)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return data
