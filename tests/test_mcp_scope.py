from astrbot.core.agent.mcp_scope import (
    get_mcp_scopes_from_config,
    is_mcp_tool_visible_to_agent,
    is_scope_allowed_for_agent,
    normalize_mcp_scope_value,
    strip_mcp_scope_fields,
)


class _MockTool:
    def __init__(self, scopes):
        self.mcp_server_scopes = scopes


def test_normalize_scope_none_means_unrestricted():
    assert normalize_mcp_scope_value(None) is None


def test_normalize_scope_string():
    assert normalize_mcp_scope_value(" main ") == ("main",)


def test_normalize_scope_list_with_wildcard():
    assert normalize_mcp_scope_value(["agent_a", "ALL"]) == ("*",)


def test_normalize_scope_empty_list_means_no_visibility():
    assert normalize_mcp_scope_value([]) == ()


def test_get_mcp_scopes_prefers_scopes_field():
    cfg = {"agent_scope": "main", "scopes": ["agent_x"]}
    assert get_mcp_scopes_from_config(cfg) == ("agent_x",)


def test_get_mcp_scopes_from_agent_scope_string():
    cfg = {"agent_scope": "main"}
    assert get_mcp_scopes_from_config(cfg) == ("main",)


def test_get_mcp_scopes_returns_none_for_non_mapping_configs():
    assert get_mcp_scopes_from_config(None) is None
    assert get_mcp_scopes_from_config([]) is None


def test_get_mcp_scopes_returns_none_when_no_scope_keys():
    assert get_mcp_scopes_from_config({"command": "python"}) is None


def test_strip_scope_fields():
    cfg = {"agent_scope": "main", "scopes": ["x"], "command": "python"}
    strip_mcp_scope_fields(cfg)
    assert cfg == {"command": "python"}


def test_scope_allowed_matching_rules():
    assert is_scope_allowed_for_agent(None, "main") is True
    assert is_scope_allowed_for_agent((), "main") is False
    assert is_scope_allowed_for_agent(("*",), "any_agent") is True
    assert is_scope_allowed_for_agent(("main",), "main") is True
    assert is_scope_allowed_for_agent(("agent_x",), "main") is False


def test_mcp_tool_visibility():
    assert is_mcp_tool_visible_to_agent(_MockTool(None), "main") is True
    assert is_mcp_tool_visible_to_agent(_MockTool(("main",)), "main") is True
    assert is_mcp_tool_visible_to_agent(_MockTool(("agent_x",)), "main") is False
