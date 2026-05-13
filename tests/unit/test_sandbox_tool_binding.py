from astrbot.core.computer.sandbox_tool_binding import (
    resolve_all_sandbox_provider_bindings,
    resolve_effective_sandbox_provider_id,
    resolve_sandbox_provider_bindings,
    tool_matches_sandbox_provider,
)


class FakeTool:
    def __init__(
        self, name: str, active: bool = True, sandbox_provider_id: str | None = None
    ):
        self.name = name
        self.active = active
        self.sandbox_provider_id = sandbox_provider_id


class FakeToolMgr:
    def __init__(self, tools: dict[str, FakeTool]):
        self.tools = tools

    def get_func(self, tool_name: str):
        return self.tools.get(tool_name)


def test_resolve_sandbox_provider_bindings_uses_lookup_and_filters_inactive_tools():
    tool_mgr = FakeToolMgr(
        {
            "active": FakeTool("active"),
            "inactive": FakeTool("inactive", active=False),
        }
    )

    provider_info, tools = resolve_sandbox_provider_bindings(
        "Generic",
        tool_mgr,
        lambda provider_id: (
            {
                "provider_id": provider_id,
                "tool_names": ["active", "inactive", "missing"],
            }
            if provider_id == "generic"
            else None
        ),
    )

    assert provider_info == {
        "provider_id": "generic",
        "tool_names": ["active", "inactive", "missing"],
    }
    assert [tool.name for tool in tools] == ["active"]


def test_resolve_all_sandbox_provider_bindings_marks_provider_scope():
    provider_tool = FakeTool("provider_tool", sandbox_provider_id="provider_a")
    provider_tool.description = "Provider action."
    tool_mgr = FakeToolMgr({"provider_tool": provider_tool})

    tools = resolve_all_sandbox_provider_bindings(
        tool_mgr,
        lambda: [{"provider_id": "provider_a", "tool_names": ["provider_tool"]}],
    )

    assert [tool.name for tool in tools] == ["provider_tool"]
    assert tools[0] is not provider_tool
    assert provider_tool.description == "Provider action."
    assert "Sandbox provider-specific tool: provider_a" in tools[0].description
    assert "current sandbox uses provider 'provider_a'" in tools[0].description


def test_resolve_effective_sandbox_provider_id_prefers_current_provider_lookup():
    assert (
        resolve_effective_sandbox_provider_id(
            "session-a",
            "fallback",
            lambda session_id: "Current" if session_id == "session-a" else None,
        )
        == "current"
    )


def test_resolve_effective_sandbox_provider_id_falls_back_to_configured_provider():
    assert (
        resolve_effective_sandbox_provider_id(
            "session-a",
            "  Fallback  ",
            lambda session_id: None,
        )
        == "fallback"
    )


def test_tool_matches_sandbox_provider_normalizes_provider_id():
    tool = FakeTool("sandbox_tool", sandbox_provider_id="Generic")

    assert tool_matches_sandbox_provider(tool, "sandbox", "  generic  ")
    assert not tool_matches_sandbox_provider(tool, "local", "generic")
