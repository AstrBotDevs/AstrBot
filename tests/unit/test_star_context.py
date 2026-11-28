from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_agent_runtime.tools.computer_tools.python import LocalPythonTool
from astrbot.core.astr_agent_runtime.tools.computer_tools.shell import (
    LocalExecuteShellTool,
    ShellSessionTool,
)
from astrbot.core.astr_agent_runtime.tools.computer_tools.util import (
    LOCAL_NETWORK_POLICY_NOTICE,
)
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.provider.provider import Provider
from astrbot.core.star.context import Context
from astrbot.core.star.star import StarMetadata, star_registry


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_class", [LocalExecuteShellTool, LocalPythonTool, ShellSessionTool])
@pytest.mark.parametrize("isolation_status", ["detected", "unavailable"])
@pytest.mark.parametrize(
    ("runtime", "allow_network", "tool_state", "existing_notice", "expected_count"),
    [
        ("local", False, "active", False, 1),
        ("local", False, "active", True, 1),
        ("local", True, "active", False, 0),
        ("local", False, "missing", False, 0),
        ("local", False, "inactive", False, 0),
        ("sandbox", False, "active", False, 0),
        ("none", False, "active", False, 0),
    ],
)
async def test_tool_loop_agent_adds_network_policy_to_system_prompt(
    monkeypatch, runtime, allow_network, tool_state, existing_notice, expected_count,
    tool_class, isolation_status,
):
    monkeypatch.setattr(
        "astrbot.core.astr_agent_runtime.tools.computer_tools.util.get_process_sandbox_status",
        lambda: {"status": isolation_status},
    )

    async def finished_steps(_max_steps):
        for response in ():
            yield response

    runner = MagicMock()
    runner.reset = AsyncMock()
    runner.step_until_done = finished_steps
    monkeypatch.setattr(
        "astrbot.core.star.context.ToolLoopAgentRunner", lambda: runner
    )
    context = SimpleNamespace(
        provider_manager=SimpleNamespace(
            get_provider_by_id=AsyncMock(return_value=MagicMock(spec=Provider))
        ),
        get_config=MagicMock(side_effect=AssertionError("Caller policy must not be used")),
    )
    agent_config = SimpleNamespace(
        get_config=MagicMock(return_value={
            "provider_settings": {
                "computer_use_runtime": runtime,
                "computer_use_local_permissions": {
                    "member": {
                        "allow_execution": True,
                        "allow_network": allow_network,
                        "filesystem_scope": "workspace",
                    }
                },
            }
        }),
    )
    event = SimpleNamespace(role="admin", unified_msg_origin="caller-test")
    agent_event = SimpleNamespace(role="member", unified_msg_origin="agent-test")
    tools = ToolSet()
    if tool_state != "missing":
        tools.add_tool(tool_class(active=tool_state == "active"))
    system_prompt = "Agent instructions."
    if existing_notice:
        system_prompt += f"\n{LOCAL_NETWORK_POLICY_NOTICE}"

    await Context.tool_loop_agent(
        context,
        event=event,
        chat_provider_id="test",
        tools=tools,
        system_prompt=system_prompt,
        agent_context=SimpleNamespace(context=agent_config, event=agent_event),
    )

    request = runner.reset.await_args.kwargs["request"]
    assert request.system_prompt.startswith("Agent instructions.")
    if isolation_status != "detected" and not existing_notice:
        expected_count = 0
    assert request.system_prompt.count(LOCAL_NETWORK_POLICY_NOTICE) == expected_count
    assert "The Agent Computer Use runtime is the local environment" not in request.system_prompt
    assert "These restrictions require Local process isolation" not in request.system_prompt
    context.get_config.assert_not_called()
    if tool_state == "active":
        agent_config.get_config.assert_called_with(umo="agent-test")
    else:
        agent_config.get_config.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config_payload", "expects_sandbox_writer"),
    [
        ({"provider_settings": {"computer_use_runtime": "sandbox"}}, True),
        ({"provider_settings": {"computer_use_runtime": "local"}}, False),
        ({"provider_settings": {"computer_use_runtime": "none"}}, False),
        ({"provider_settings": None}, False),
    ],
)
async def test_tool_loop_agent_configures_overflow_for_runtime(
    monkeypatch,
    config_payload: dict,
    expects_sandbox_writer: bool,
):
    from astrbot.core.astr_agent_runtime.computer import computer_client
    from astrbot.core.utils.astrbot_path import get_astrbot_system_tmp_path

    async def finished_steps(_max_steps):
        for response in ():
            yield response

    runner = MagicMock(reset=AsyncMock(), step_until_done=finished_steps)
    monkeypatch.setattr("astrbot.core.star.context.ToolLoopAgentRunner", lambda: runner)
    write_file = AsyncMock(return_value={"success": True})
    get_booter = AsyncMock(
        return_value=SimpleNamespace(fs=SimpleNamespace(write_file=write_file))
    )
    monkeypatch.setattr(computer_client, "get_booter", get_booter)

    caller_context = SimpleNamespace(
        provider_manager=SimpleNamespace(
            get_provider_by_id=AsyncMock(return_value=MagicMock(spec=Provider))
        ),
        get_config=MagicMock(
            side_effect=AssertionError("Caller config must not be used")
        ),
    )
    agent_config = SimpleNamespace(get_config=MagicMock(return_value=config_payload))
    read_tool = FunctionTool(
        name="astrbot_file_read_tool", description="read file", parameters={}
    )

    await Context.tool_loop_agent(
        caller_context,
        event=SimpleNamespace(role="admin", unified_msg_origin="caller-test"),
        chat_provider_id="test",
        tools=ToolSet([read_tool]),
        agent_context=SimpleNamespace(
            context=agent_config,
            event=SimpleNamespace(role="member", unified_msg_origin="agent-test"),
        ),
    )

    reset_kwargs = runner.reset.await_args.kwargs
    assert reset_kwargs["read_tool"] is read_tool
    agent_config.get_config.assert_called_once_with(umo="agent-test")
    caller_context.get_config.assert_not_called()

    if expects_sandbox_writer:
        assert "tool_result_overflow_dir" not in reset_kwargs
        writer = reset_kwargs["tool_result_overflow_writer"]
        get_booter.assert_not_called()
        assert await writer("call_abc.txt", "payload") == ".astrbot_tool_overflow_call_abc.txt"
        get_booter.assert_awaited_once_with(agent_config, "agent-test")
        write_file.assert_awaited_once_with(
            path=".astrbot_tool_overflow_call_abc.txt",
            content="payload",
            mode="w",
            encoding="utf-8",
        )
    else:
        assert reset_kwargs["tool_result_overflow_dir"] == get_astrbot_system_tmp_path()
        assert "tool_result_overflow_writer" not in reset_kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("active", "extra_kwargs"),
    [
        (False, {}),
        (True, {"read_tool": None}),
        (True, {"read_tool": FunctionTool(name="custom_read", description="", parameters={})}),
        (True, {"tool_result_overflow_dir": None}),
    ],
)
async def test_tool_loop_agent_respects_inactive_read_tool_and_explicit_overrides(
    monkeypatch,
    active: bool,
    extra_kwargs: dict,
):
    async def finished_steps(_max_steps):
        for response in ():
            yield response

    runner = MagicMock(reset=AsyncMock(), step_until_done=finished_steps)
    monkeypatch.setattr("astrbot.core.star.context.ToolLoopAgentRunner", lambda: runner)
    context = SimpleNamespace(
        provider_manager=SimpleNamespace(
            get_provider_by_id=AsyncMock(return_value=MagicMock(spec=Provider))
        ),
        get_config=MagicMock(
            side_effect=AssertionError("Config should not be read when overflow is bypassed")
        ),
    )
    event = SimpleNamespace(role="admin", unified_msg_origin="session-1")
    read_tool = FunctionTool(
        name="astrbot_file_read_tool",
        description="read file",
        parameters={},
        active=active,
    )

    await Context.tool_loop_agent(
        context,
        event=event,
        chat_provider_id="test",
        tools=ToolSet([read_tool]),
        agent_context=SimpleNamespace(context=context, event=event),
        **extra_kwargs,
    )

    reset_kwargs = runner.reset.await_args.kwargs
    assert "tool_result_overflow_writer" not in reset_kwargs
    if "tool_result_overflow_dir" in extra_kwargs:
        assert reset_kwargs["tool_result_overflow_dir"] is None
    else:
        assert "tool_result_overflow_dir" not in reset_kwargs
    if not active:
        assert "read_tool" not in reset_kwargs
    elif "read_tool" in extra_kwargs:
        assert reset_kwargs["read_tool"] is extra_kwargs["read_tool"]
    context.get_config.assert_not_called()


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
