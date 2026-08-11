from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.agent.tool_image_cache import ToolImageCache
from astrbot.core.computer.computer_client import ComputerRuntime
from astrbot.core.execution_context import CoreExecutionContext
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.send_result import PlatformSendResult
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.star.plugin_context import PluginContext
from astrbot.core.star.star import StarMetadata


def make_context() -> CoreExecutionContext:
    context = CoreExecutionContext.__new__(CoreExecutionContext)
    context.catalogs = RuntimeCatalogs()
    return context


def make_initialized_context() -> CoreExecutionContext:
    from asyncio import Queue

    return CoreExecutionContext(
        event_queue=Queue(),
        config=MagicMock(),
        db=MagicMock(),
        provider_manager=MagicMock(),
        platform_manager=MagicMock(),
        conversation_manager=MagicMock(),
        message_history_manager=MagicMock(),
        persona_manager=MagicMock(),
        astrbot_config_mgr=MagicMock(),
        knowledge_base_manager=MagicMock(),
        cron_manager=MagicMock(),
        preferences=MagicMock(),
        html_renderer=MagicMock(),
        file_token_service=MagicMock(),
        catalogs=RuntimeCatalogs(),
        computer_runtime=ComputerRuntime(),
        tool_image_cache=MagicMock(spec=ToolImageCache),
        metrics=SimpleNamespace(upload=AsyncMock()),
    )


def make_tool(name: str, module_path: str) -> FunctionTool:
    tool = FunctionTool(
        name=name,
        description="test tool",
        parameters={"type": "object", "properties": {}},
    )
    tool.__module__ = module_path
    return tool


def test_add_llm_tools_resolves_subdirectory_plugin_without_name_prefix():
    context = make_context()
    context.catalogs.plugins.publish(
        StarMetadata(
            name="Custom Plugin",
            root_dir_name="custom_plugin",
            module_path="data.plugins.custom_plugin.main",
        )
    )
    tool = make_tool("search", "custom_plugin.tools.search")

    context.add_llm_tools(tool)

    assert tool.handler_module_path == "data.plugins.custom_plugin.main"


def test_add_llm_tools_uses_registered_non_main_plugin_entrypoint():
    context = make_context()
    context.catalogs.plugins.publish(
        StarMetadata(
            name="Custom Plugin",
            module_path="data.plugins.custom_plugin.custom_plugin",
        )
    )
    tool = make_tool("search", "custom_plugin.tools.search")

    context.add_llm_tools(tool)

    assert tool.handler_module_path == "data.plugins.custom_plugin.custom_plugin"


def test_add_llm_tools_resolves_prefixed_subdirectory_tool_from_registry():
    context = make_context()
    context.catalogs.plugins.publish(
        StarMetadata(
            name="Custom Plugin",
            root_dir_name="custom_plugin",
            module_path="data.plugins.custom_plugin.custom_plugin",
        )
    )
    tool = make_tool("search", "data.plugins.custom_plugin.tools.search")

    context.add_llm_tools(tool)

    assert tool.handler_module_path == "data.plugins.custom_plugin.custom_plugin"


def test_add_llm_tools_does_not_treat_unknown_module_as_plugin():
    context = make_context()
    context.catalogs.plugins.publish(
        StarMetadata(
            name="Custom Plugin",
            root_dir_name="custom_plugin",
            module_path="data.plugins.custom_plugin.main",
        )
    )
    tool = make_tool("search", "external_package.tools.search")

    context.add_llm_tools(tool)

    assert tool.handler_module_path == "external_package.tools.search"


def test_add_llm_tools_handles_empty_tool_module_path():
    context = make_context()
    tool = make_tool("search", "")

    context.add_llm_tools(tool)

    assert tool.handler_module_path == ""


def test_context_mutable_state_is_not_shared_between_instances():
    first = make_initialized_context()
    second = make_initialized_context()

    first.register_task(SimpleNamespace(), "task")
    first._star_manager = object()

    assert second._register_tasks == []
    assert second._star_manager is None
    assert first.dashboard_extension_registry is not second.dashboard_extension_registry


def test_context_commit_event_returns_false_when_queue_is_full():
    from asyncio import Queue

    context = make_initialized_context()
    context._event_queue = Queue(maxsize=1)
    context._event_queue.put_nowait(SimpleNamespace(unified_msg_origin="first"))

    result = context.commit_event(SimpleNamespace(unified_msg_origin="second"))

    assert result is False


@pytest.mark.asyncio
async def test_send_message_returns_platform_send_result():
    context = make_initialized_context()
    context._platform_manager.send_to_session = AsyncMock(
        return_value=PlatformSendResult(
            platform_id="telegram",
            success=True,
            target="chat-1",
            message_count=1,
        )
    )
    session = MessageSession.from_str("telegram:FriendMessage:chat-1")
    message_chain = MessageChain(chain=[Plain("hello")])

    result = await context.send_message(session, message_chain)

    assert result.success is True
    assert result.platform_id == "telegram"
    assert result.target == "chat-1"
    context._platform_manager.send_to_session.assert_awaited_once_with(
        session, message_chain
    )


@pytest.mark.asyncio
async def test_send_message_returns_failure_when_platform_missing():
    context = make_initialized_context()
    context._platform_manager.send_to_session = AsyncMock(
        return_value=PlatformSendResult(
            platform_id="telegram",
            success=False,
            target="chat-1",
            message_count=1,
            error_message="platform adapter not found",
        )
    )
    session = MessageSession.from_str("telegram:FriendMessage:chat-1")
    message_chain = MessageChain(chain=[Plain("hello")])

    result = await context.send_message(session, message_chain)

    assert result == PlatformSendResult(
        platform_id="telegram",
        success=False,
        target="chat-1",
        message_count=1,
        error_message="platform adapter not found",
    )
    context._platform_manager.send_to_session.assert_awaited_once_with(
        session, message_chain
    )


@pytest.mark.asyncio
async def test_send_message_returns_failure_when_adapter_rejects_payload():
    context = make_initialized_context()
    context._platform_manager.send_to_session = AsyncMock(
        return_value=PlatformSendResult(
            platform_id="telegram",
            success=False,
            target="chat-1",
            message_count=1,
            error_message="adapter rejected payload",
        )
    )
    session = MessageSession.from_str("telegram:FriendMessage:chat-1")
    message_chain = MessageChain(chain=[Plain("hello")])

    result = await context.send_message(session, message_chain)

    assert result == PlatformSendResult(
        platform_id="telegram",
        success=False,
        target="chat-1",
        message_count=1,
        error_message="adapter rejected payload",
    )
    context._platform_manager.send_to_session.assert_awaited_once_with(
        session, message_chain
    )


@pytest.mark.asyncio
async def test_context_invoke_platform_action_delegates_to_platform_manager():
    context = make_initialized_context()
    context._platform_manager.invoke_action = AsyncMock(
        return_value={"status": "ok", "data": {"done": True}}
    )

    result = await context.invoke_platform_action(
        "telegram",
        "send_poke",
        user_id="123456",
    )

    assert result == {"status": "ok", "data": {"done": True}}
    context._platform_manager.invoke_action.assert_awaited_once_with(
        "telegram",
        "send_poke",
        user_id="123456",
    )


@pytest.mark.asyncio
async def test_context_invoke_event_platform_action_uses_event_platform_id():
    context = make_initialized_context()
    context.invoke_platform_action = AsyncMock(
        return_value={"status": "ok", "data": {"done": True}}
    )
    event = MagicMock()
    event.get_platform_id.return_value = "telegram"

    result = await context.invoke_event_platform_action(
        event,
        "send_poke",
        user_id="123456",
    )

    assert result == {"status": "ok", "data": {"done": True}}
    context.invoke_platform_action.assert_awaited_once_with(
        "telegram",
        "send_poke",
        user_id="123456",
    )


def test_plugin_messages_create_event_prefers_platform_id_lookup():
    context = make_initialized_context()
    context.create_platform_event = MagicMock()
    plugin_context = PluginContext.from_execution_context(context)
    payload = MagicMock()

    plugin_context.messages.create_event("telegram", payload, is_wake=False)

    context.create_platform_event.assert_called_once_with(
        "telegram",
        payload,
        is_wake=False,
    )


def test_context_create_platform_event_delegates_to_platform_manager():
    context = make_initialized_context()
    context._platform_manager.create_event = MagicMock()
    payload = MagicMock()

    context.create_platform_event("telegram", payload, is_wake=True)

    context._platform_manager.create_event.assert_called_once_with(
        "telegram",
        payload,
        is_wake=True,
    )


def test_context_create_platform_event_propagates_platform_error():
    context = make_initialized_context()
    context._platform_manager.create_event = MagicMock(
        side_effect=ValueError("Platform not found: telegram")
    )

    with pytest.raises(ValueError, match="Platform not found: telegram"):
        context.create_platform_event("telegram", MagicMock())


@pytest.mark.asyncio
async def test_plugin_platform_actions_use_context_boundary():
    context = make_initialized_context()
    context.invoke_platform_action = AsyncMock(
        return_value={"status": "ok", "data": {"done": True}}
    )

    plugin_context = PluginContext.from_execution_context(context)
    result = await plugin_context.platform_actions.invoke(
        "telegram",
        "send_poke",
        user_id="123456",
    )

    assert result == {"status": "ok", "data": {"done": True}}
    context.invoke_platform_action.assert_awaited_once_with(
        "telegram",
        "send_poke",
        user_id="123456",
    )


@pytest.mark.asyncio
async def test_plugin_event_platform_actions_use_context_boundary():
    context = make_initialized_context()
    context.invoke_event_platform_action = AsyncMock(
        return_value={"status": "ok", "data": {"done": True}}
    )
    event = MagicMock()

    plugin_context = PluginContext.from_execution_context(context)
    result = await plugin_context.platform_actions.invoke_for_event(
        event,
        "send_poke",
        user_id="123456",
    )

    assert result == {"status": "ok", "data": {"done": True}}
    context.invoke_event_platform_action.assert_awaited_once_with(
        event,
        "send_poke",
        user_id="123456",
    )


def test_plugin_context_exposes_capabilities_not_core_managers():
    context = make_initialized_context()
    plugin_context = PluginContext.from_execution_context(context)

    assert plugin_context.messages is not None
    assert plugin_context.models is not None
    assert plugin_context.tools is not None
    assert plugin_context.storage is not None
    assert plugin_context.config is not None
    assert plugin_context.cron is not None
    assert plugin_context.knowledge is not None
    assert plugin_context.platform_actions is not None
    assert plugin_context.onebot is not None
    assert plugin_context.dashboard_extensions is not None
    assert plugin_context.runtime_info is not None
    for forbidden in (
        "database",
        "provider_manager",
        "platform_manager",
        "catalogs",
        "get_db",
        "get_config",
        "send_message",
    ):
        assert not hasattr(plugin_context, forbidden)
