"""Tests for libmatic.agents.react (ReAct agent factory)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from libmatic.agents.react import build_step_agent
from libmatic.config import GitHubConfig, LibmaticConfig


@pytest.fixture
def sentinel_tool() -> Any:
    tool = MagicMock()
    tool.name = "sentinel"
    return tool


@pytest.fixture
def default_config() -> LibmaticConfig:
    return LibmaticConfig(github=GitHubConfig(repo="x/y"))


def test_build_step_agent_resolves_model_and_passes_tools(
    monkeypatch: pytest.MonkeyPatch,
    default_config: LibmaticConfig,
    sentinel_tool: Any,
) -> None:
    """build_step_agent が get_model + create_react_agent を適切な引数で呼ぶ。"""
    captured: dict[str, Any] = {}

    def fake_get_model(step_name: str, cfg: LibmaticConfig) -> Any:
        captured["step_name"] = step_name
        captured["cfg"] = cfg
        return "fake-model-instance"

    def fake_create_react_agent(**kwargs: Any) -> Any:
        captured["kwargs"] = kwargs
        return "fake-subgraph"

    import libmatic.agents.react as react_mod

    monkeypatch.setattr(react_mod, "get_model", fake_get_model)
    monkeypatch.setattr(react_mod, "create_react_agent", fake_create_react_agent)

    result = build_step_agent(
        step_name="step7_article_writer",
        config=default_config,
        tools=[sentinel_tool],
        system_prompt="あなたは記事執筆者です。",
    )

    assert result == "fake-subgraph"
    assert captured["step_name"] == "step7_article_writer"
    assert captured["cfg"] is default_config
    assert captured["kwargs"]["model"] == "fake-model-instance"
    assert captured["kwargs"]["tools"] == [sentinel_tool]

    # prompt は cache_control 付き SystemMessage を返す callable
    prompt_fn = captured["kwargs"]["prompt"]
    assert callable(prompt_fn)
    user_msg = HumanMessage(content="hello")
    rendered = prompt_fn({"messages": [user_msg]})
    assert isinstance(rendered[0], SystemMessage)
    assert rendered[0].content == [
        {
            "type": "text",
            "text": "あなたは記事執筆者です。",
            "cache_control": {"type": "ephemeral"},
        }
    ]
    assert rendered[1] is user_msg


def test_build_step_agent_without_prompt_omits_kwarg(
    monkeypatch: pytest.MonkeyPatch,
    default_config: LibmaticConfig,
) -> None:
    """system_prompt が None なら create_react_agent の prompt kwarg は渡さない。"""
    captured: dict[str, Any] = {}

    def fake_create_react_agent(**kwargs: Any) -> Any:
        captured["kwargs"] = kwargs
        return "x"

    import libmatic.agents.react as react_mod

    monkeypatch.setattr(react_mod, "get_model", lambda step, cfg: "m")
    monkeypatch.setattr(react_mod, "create_react_agent", fake_create_react_agent)

    build_step_agent(
        step_name="step1_source_collector",
        config=default_config,
        tools=[],
        system_prompt=None,
    )

    assert "prompt" not in captured["kwargs"]
    assert captured["kwargs"]["model"] == "m"
    assert captured["kwargs"]["tools"] == []
