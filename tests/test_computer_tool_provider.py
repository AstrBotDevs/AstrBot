"""Computer tool selection and registration remain independent across requests."""

import pytest

from astrbot.core.astr_agent_runtime.computer.computer_tool_provider import (
    ComputerToolProvider,
    get_all_tools,
)
from astrbot.core.tool_provider import ToolProviderContext


def test_registration_returns_unique_inactive_fresh_instances():
    first = get_all_tools()
    second = ComputerToolProvider.get_all_tools()
    assert len(first) == len(second) == 19
    assert len({tool.name for tool in first}) == 19
    assert [tool.name for tool in first] == [tool.name for tool in second]
    assert all(not tool.active for tool in first + second)
    assert all(left is not right for left, right in zip(first, second, strict=True))
    first[0].active = True
    assert not second[0].active


def test_local_tools_include_filesystem_and_are_fresh():
    provider = ComputerToolProvider()
    context = ToolProviderContext(computer_use_runtime="local", sandbox_cfg={})
    first = provider.get_tools(context)
    second = provider.get_tools(context)
    assert {tool.name for tool in first} == {
        "astrbot_execute_shell",
        "astrbot_execute_python",
        "astrbot_shell_session",
        "astrbot_file_read_tool",
        "astrbot_file_write_tool",
        "astrbot_file_edit_tool",
        "astrbot_grep_tool",
    }
    assert all(tool.active for tool in first + second)
    assert all(left is not right for left, right in zip(first, second, strict=True))
    first[0].active = False
    assert second[0].active


@pytest.mark.parametrize("runtime", ["none", "unsupported"])
def test_unavailable_runtime_exposes_no_tools_or_prompt(runtime):
    context = ToolProviderContext(computer_use_runtime=runtime, sandbox_cfg={})
    provider = ComputerToolProvider()
    assert provider.get_tools(context) == []
    assert provider.get_system_prompt_addon(context) == ""


@pytest.mark.parametrize("missing", ["shipyard_endpoint", "shipyard_access_token"])
def test_shipyard_requires_both_connection_fields(missing):
    config = {
        "booter": "shipyard",
        "shipyard_endpoint": "http://localhost:8114",
        "shipyard_access_token": "test",
    }
    config.pop(missing)
    assert (
        ComputerToolProvider().get_tools(
            ToolProviderContext(computer_use_runtime="sandbox", sandbox_cfg=config)
        )
        == []
    )
