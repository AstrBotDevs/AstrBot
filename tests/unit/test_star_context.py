from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.provider.provider import Provider
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.star.context import Context
from astrbot.core.star.star import StarMetadata, star_registry
from astrbot.core.tools.computer_tools.shell import LocalExecuteShellTool
from astrbot.core.tools.computer_tools.util import LOCAL_NETWORK_POLICY_NOTICE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runtime", "allow_network", "include_tools", "existing_notice", "expected_count"),
    [
        ("local", False, True, False, 1),
        ("local", False, True, True, 1),
        ("local", True, True, False, 0),
        ("local", False, False, False, 0),
        ("sandbox", False, True, False, 0),
        ("none", False, True, False, 0),
    ],
)
async def test_tool_loop_agent_adds_network_policy_to_system_prompt(
    monkeypatch, runtime, allow_network, include_tools, existing_notice, expected_count
):
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
        get_config=lambda **_kwargs: {
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
        },
    )
    event = SimpleNamespace(role="member", unified_msg_origin="test")
    tools = ToolSet()
    if include_tools:
        tools.add_tool(LocalExecuteShellTool())
    system_prompt = "Agent instructions."
    if existing_notice:
        system_prompt += f"\n{LOCAL_NETWORK_POLICY_NOTICE}"

    await Context.tool_loop_agent(
        context,
        event=event,
        chat_provider_id="test",
        tools=tools,
        system_prompt=system_prompt,
        agent_context=SimpleNamespace(context=context, event=event),
    )

    request = runner.reset.await_args.kwargs["request"]
    assert request.system_prompt.startswith("Agent instructions.")
    assert request.system_prompt.count(LOCAL_NETWORK_POLICY_NOTICE) == expected_count


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
