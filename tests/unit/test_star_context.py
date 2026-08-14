from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlmodel import select

from astrbot.core.agent.response import AgentStats
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.db.po import ProviderStat
from astrbot.core.provider.entities import LLMResponse, ProviderMeta, TokenUsage
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


class StatsProvider(Provider):
    def __init__(self) -> None:
        super().__init__({"id": "provider-1", "type": "test"}, {})
        self.set_model("test-model")

    def get_current_key(self) -> str:
        return ""

    def set_key(self, key: str) -> None:
        return None

    async def get_models(self) -> list[str]:
        return [self.get_model()]

    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="provider-1",
            model=self.get_model(),
            type="test",
        )

    async def text_chat(self, **kwargs) -> LLMResponse:
        return LLMResponse(
            role="assistant",
            completion_text="ok",
            usage=TokenUsage(input_other=5, input_cached=2, output=3),
        )


async def get_provider_stats(temp_db) -> list[ProviderStat]:
    async with temp_db.get_db() as session:
        result = await session.execute(select(ProviderStat))
        return list(result.scalars().all())


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
async def test_llm_generate_persists_one_provider_stat(temp_db):
    provider = StatsProvider()
    context = Context.__new__(Context)
    context._db = temp_db
    context.provider_manager = SimpleNamespace(
        get_provider_by_id=AsyncMock(return_value=provider),
    )

    response = await context.llm_generate(
        chat_provider_id="provider-1",
        prompt="test",
        session_id="session-1",
    )

    records = await get_provider_stats(temp_db)
    assert response.completion_text == "ok"
    assert len(records) == 1
    record = records[0]
    assert record.agent_type == "internal"
    assert record.status == "completed"
    assert record.umo == "provider:provider-1:session-1"
    assert record.provider_id == "provider-1"
    assert record.provider_model == "test-model"
    assert record.token_input_other == 5
    assert record.token_input_cached == 2
    assert record.token_output == 3
    assert record.end_time >= record.start_time > 0


@pytest.mark.asyncio
async def test_tool_loop_agent_persists_one_aggregated_provider_stat(
    temp_db,
    monkeypatch: pytest.MonkeyPatch,
):
    provider = StatsProvider()
    final_response = LLMResponse(
        role="assistant",
        completion_text="done",
        usage=TokenUsage(input_other=8, input_cached=1, output=4),
    )

    class FakeRunner:
        def __init__(self) -> None:
            self.provider = provider
            self.stats = AgentStats(
                token_usage=TokenUsage(input_other=12, input_cached=3, output=7),
                start_time=100.0,
                end_time=106.0,
                time_to_first_token=0.4,
            )

        async def reset(self, **kwargs) -> None:
            return None

        async def step_until_done(self, max_steps):
            if False:
                yield None

        def get_final_llm_resp(self) -> LLMResponse:
            return final_response

        def was_aborted(self) -> bool:
            return False

    monkeypatch.setattr("astrbot.core.star.context.ToolLoopAgentRunner", FakeRunner)

    context = Context.__new__(Context)
    context._db = temp_db
    context.provider_manager = SimpleNamespace(
        get_provider_by_id=AsyncMock(return_value=provider),
    )
    event = SimpleNamespace(
        unified_msg_origin="webchat:FriendMessage:session-42",
    )

    response = await context.tool_loop_agent(
        event=event,
        chat_provider_id="provider-1",
        prompt="test",
        agent_context=SimpleNamespace(),
    )

    records = await get_provider_stats(temp_db)
    assert response is final_response
    assert len(records) == 1
    record = records[0]
    assert record.agent_type == "internal"
    assert record.umo == "webchat:FriendMessage:session-42"
    assert record.provider_id == "provider-1"
    assert record.token_input_other == 12
    assert record.token_input_cached == 3
    assert record.token_output == 7
    assert record.start_time == 100.0
    assert record.end_time == 106.0
