from dataclasses import dataclass, field

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.computer.sandbox_tool_binding import (
    get_sandbox_provider_tool_config_statuses,
    sandbox_provider_tool,
    tool_available_in_runtime,
)


class FakeTool:
    def __init__(
        self, name: str, active: bool = True, sandbox_provider_id: str | None = None
    ):
        self.name = name
        self.active = active
        self.sandbox_provider_id = sandbox_provider_id


def test_provider_scoped_tool_is_available_to_any_sandbox_runtime():
    tool = FakeTool("sandbox_tool", sandbox_provider_id="Generic")

    assert tool_available_in_runtime(tool, "sandbox")
    assert not tool_available_in_runtime(tool, "local")


def test_unscoped_tool_is_available_to_every_runtime():
    tool = FakeTool("regular_tool")

    assert tool_available_in_runtime(tool, "sandbox")
    assert tool_available_in_runtime(tool, "local")


def test_sandbox_provider_tool_marks_class_and_registers_config_rule():
    @sandbox_provider_tool(
        "Example",
        config={"provider_settings.sandbox.booter": "example"},
    )
    @dataclass
    class ExampleTool(FunctionTool):
        name: str = "example_sandbox_tool"
        description: str = "Example"
        parameters: dict = field(
            default_factory=lambda: {"type": "object", "properties": {}}
        )

    tool = ExampleTool()

    assert tool.sandbox_provider_id == "example"

    statuses = get_sandbox_provider_tool_config_statuses(
        "example_sandbox_tool",
        [
            {
                "conf_id": "conf-a",
                "conf_name": "Config A",
                "config": {"provider_settings": {"sandbox": {"booter": "example"}}},
            }
        ],
    )
    assert statuses[0]["enabled"] is True
