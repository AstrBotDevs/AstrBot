from __future__ import annotations

from typing import Any

import pytest

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_main_agent import (
    MainAgentBuildConfig,
    _resolve_tool_capability_strategy,
)
from astrbot.core.exceptions import UnsupportedToolCapabilityError
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.provider.provider import Provider
from astrbot.core.utils.llm_metadata import LLM_METADATAS


class DummyProvider(Provider):
    def __init__(
        self,
        provider_id: str,
        model: str,
        modalities: list[str] | None = None,
    ) -> None:
        provider_config: dict[str, Any] = {
            "id": provider_id,
            "type": "openai_chat_completion",
            "model": model,
        }
        if modalities is not None:
            provider_config["modalities"] = modalities
        super().__init__(provider_config, {})
        self.set_model(model)

    def get_current_key(self) -> str:
        return "test-key"

    def set_key(self, key: str) -> None:
        return None

    async def get_models(self) -> list[str]:
        return [self.get_model()]

    async def text_chat(self, **kwargs):
        raise NotImplementedError


class DummyPluginContext:
    def __init__(self, providers: dict[str, Provider]) -> None:
        self.providers = providers

    def get_provider_by_id(self, provider_id: str) -> Provider | None:
        return self.providers.get(provider_id)


def _make_metadata(tool_call: bool) -> dict[str, Any]:
    return {
        "id": "test-model",
        "reasoning": False,
        "tool_call": tool_call,
        "knowledge": "none",
        "release_date": "",
        "modalities": {"input": ["text"], "output": ["text"]},
        "open_weights": False,
        "limit": {"context": 0, "output": 0},
    }


def _make_tool_set() -> ToolSet:
    return ToolSet(
        [
            FunctionTool(
                name="test_tool",
                description="Test tool",
                parameters={"type": "object", "properties": {}},
                handler=None,
            )
        ]
    )


def test_tool_capability_strategy_switches_to_fallback_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = DummyProvider("primary", "deepseek-r1:7b", ["text", "tool_use"])
    fallback = DummyProvider("fallback", "gpt-4.1-mini", ["text", "tool_use"])
    plugin_context = DummyPluginContext(
        {
            "primary": primary,
            "fallback": fallback,
        }
    )
    req = ProviderRequest(
        func_tool=_make_tool_set(),
        model="deepseek-r1:7b",
    )
    config = MainAgentBuildConfig(
        tool_call_timeout=30,
        tool_capability_strategy="fallback_provider",
        provider_settings={"fallback_chat_models": ["fallback"]},
    )

    monkeypatch.setitem(LLM_METADATAS, "deepseek-r1:7b", _make_metadata(False))
    monkeypatch.setitem(LLM_METADATAS, "gpt-4.1-mini", _make_metadata(True))

    selected_provider, allow_follow_up = _resolve_tool_capability_strategy(
        provider=primary,
        req=req,
        plugin_context=plugin_context,
        config=config,
    )

    assert selected_provider is fallback
    assert allow_follow_up is True
    assert req.func_tool is not None
    assert req.model == "gpt-4.1-mini"


def test_tool_capability_strategy_chat_only_clears_tool_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = DummyProvider("primary", "deepseek-r1:7b", ["text", "tool_use"])
    plugin_context = DummyPluginContext({"primary": primary})
    req = ProviderRequest(
        func_tool=_make_tool_set(),
        contexts=[
            {"role": "assistant", "tool_calls": [{"id": "call_1"}], "content": ""},
            {"role": "tool", "content": "tool output"},
            {"role": "user", "content": "Why?"},
            {"role": "assistant", "content": "Plain answer"},
        ],
    )
    config = MainAgentBuildConfig(
        tool_call_timeout=30,
        tool_capability_strategy="chat_only",
        provider_settings={},
    )

    monkeypatch.setitem(LLM_METADATAS, "deepseek-r1:7b", _make_metadata(False))

    selected_provider, allow_follow_up = _resolve_tool_capability_strategy(
        provider=primary,
        req=req,
        plugin_context=plugin_context,
        config=config,
    )

    assert selected_provider is primary
    assert allow_follow_up is False
    assert req.func_tool is None
    assert req.tool_calls_result is None
    assert req.contexts == [
        {"role": "user", "content": "Why?"},
        {"role": "assistant", "content": "Plain answer"},
    ]


def test_tool_capability_strategy_hard_fail_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = DummyProvider("primary", "deepseek-r1:7b", ["text", "tool_use"])
    plugin_context = DummyPluginContext({"primary": primary})
    req = ProviderRequest(func_tool=_make_tool_set())
    config = MainAgentBuildConfig(
        tool_call_timeout=30,
        tool_capability_strategy="hard_fail",
        provider_settings={},
    )

    monkeypatch.setitem(LLM_METADATAS, "deepseek-r1:7b", _make_metadata(False))

    with pytest.raises(UnsupportedToolCapabilityError):
        _resolve_tool_capability_strategy(
            provider=primary,
            req=req,
            plugin_context=plugin_context,
            config=config,
        )
