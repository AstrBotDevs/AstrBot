from astrbot.core.computer.sandbox_tool_binding import tool_available_in_runtime


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
