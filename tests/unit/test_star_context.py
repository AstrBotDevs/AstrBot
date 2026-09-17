from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.provider.provider import Provider
from astrbot.core.star.context import Context
from astrbot.core.star.star import StarMetadata, star_registry


@pytest.fixture(autouse=True)
def restore_star_registry():
    original_registry = list(star_registry)
    star_registry.clear()
    try:
        yield
    finally:
        star_registry[:] = original_registry


def make_context() -> Context:
    context = Context.__new__(Context)
    context.provider_manager = SimpleNamespace(llm_tools=FunctionToolManager())
    return context


def make_tool(name: str, module_path: str) -> FunctionTool:
    tool = FunctionTool(
        name=name,
        description="test tool",
        parameters={"type": "object", "properties": {}},
    )
    tool.__module__ = module_path
    return tool


class StubProvider(Provider):
    def get_current_key(self) -> str:
        return ""

    def set_key(self, key: str) -> None:
        return None

    async def get_models(self) -> list[str]:
        return []

    async def text_chat(self, **kwargs):
        return LLMResponse(role="assistant", completion_text="done")


def test_add_llm_tools_resolves_subdirectory_plugin_without_name_prefix():
    star_registry.append(
        StarMetadata(
            name="Custom Plugin",
            root_dir_name="custom_plugin",
            module_path="data.plugins.custom_plugin.main",
        )
    )
    context = make_context()
    tool = make_tool("search", "custom_plugin.tools.search")

    context.add_llm_tools(tool)

    assert tool.handler_module_path == "data.plugins.custom_plugin.main"


def test_add_llm_tools_uses_registered_non_main_plugin_entrypoint():
    star_registry.append(
        StarMetadata(
            name="Custom Plugin",
            module_path="data.plugins.custom_plugin.custom_plugin",
        )
    )
    context = make_context()
    tool = make_tool("search", "custom_plugin.tools.search")

    context.add_llm_tools(tool)

    assert tool.handler_module_path == "data.plugins.custom_plugin.custom_plugin"


def test_add_llm_tools_resolves_prefixed_subdirectory_tool_from_registry():
    star_registry.append(
        StarMetadata(
            name="Custom Plugin",
            root_dir_name="custom_plugin",
            module_path="data.plugins.custom_plugin.custom_plugin",
        )
    )
    context = make_context()
    tool = make_tool("search", "data.plugins.custom_plugin.tools.search")

    context.add_llm_tools(tool)

    assert tool.handler_module_path == "data.plugins.custom_plugin.custom_plugin"


def test_add_llm_tools_does_not_treat_unknown_module_as_plugin():
    star_registry.append(
        StarMetadata(
            name="Custom Plugin",
            root_dir_name="custom_plugin",
            module_path="data.plugins.custom_plugin.main",
        )
    )
    context = make_context()
    tool = make_tool("search", "external_package.tools.search")

    context.add_llm_tools(tool)

    assert tool.handler_module_path == "external_package.tools.search"


def test_add_llm_tools_handles_empty_tool_module_path():
    context = make_context()
    tool = make_tool("search", "")

    context.add_llm_tools(tool)

    assert tool.handler_module_path == ""


@pytest.mark.asyncio
async def test_llm_generate_applies_request_policy_scope():
    captured = []

    class PolicyProvider(StubProvider):
        async def text_chat(self, **kwargs):
            from astrbot.core.provider.sources.request_retry import (
                provider_oauth_web_search,
                provider_retry_rate_limits,
            )

            captured.append(
                (
                    provider_oauth_web_search.get(),
                    provider_retry_rate_limits.get(),
                    kwargs["oauth_web_search"],
                    kwargs["retry_rate_limits"],
                )
            )
            return LLMResponse(role="assistant", completion_text="done")

    context = Context.__new__(Context)
    context.provider_manager = SimpleNamespace(
        get_provider_by_id=AsyncMock(return_value=PolicyProvider({}, {})),
    )

    response = await context.llm_generate(
        chat_provider_id="provider-1",
        prompt="test",
        oauth_web_search="disabled",
        retry_rate_limits=False,
    )

    assert response.completion_text == "done"
    assert captured == [("disabled", False, "disabled", False)]


@pytest.mark.asyncio
async def test_tool_loop_agent_places_request_policies_on_provider_request(
    monkeypatch: pytest.MonkeyPatch,
):
    provider = StubProvider({}, {})
    reset_calls = []

    class FakeRunner:
        async def reset(self, **kwargs) -> None:
            reset_calls.append(kwargs)

        async def step_until_done(self, max_steps):
            if False:
                yield None

        def get_final_llm_resp(self) -> LLMResponse:
            return LLMResponse(role="assistant", completion_text="done")

    monkeypatch.setattr("astrbot.core.star.context.ToolLoopAgentRunner", FakeRunner)
    context = Context.__new__(Context)
    context.provider_manager = SimpleNamespace(
        get_provider_by_id=AsyncMock(return_value=provider),
    )

    await context.tool_loop_agent(
        event=SimpleNamespace(unified_msg_origin="test:policy"),
        chat_provider_id="provider-1",
        prompt="test",
        agent_context=SimpleNamespace(),
        oauth_web_search="disabled",
        retry_rate_limits=False,
        fallback_on_rate_limit=False,
    )

    request = reset_calls[0]["request"]
    assert request.oauth_web_search == "disabled"
    assert request.retry_rate_limits is False
    assert request.fallback_on_rate_limit is False
    assert "oauth_web_search" not in reset_calls[0]
    assert "retry_rate_limits" not in reset_calls[0]
    assert "fallback_on_rate_limit" not in reset_calls[0]
