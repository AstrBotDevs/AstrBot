"""Tests for ClaudeToolSearchStrategy -- Claude-native tool search path (CLN-01 through CLN-04)."""

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.tools.claude_strategy import ClaudeToolSearchStrategy
from astrbot.core.tools.strategy import ToolSearchStrategy
from astrbot.core.tools.tool_catalog import ToolCatalog
from astrbot.core.tools.tool_search_index import ToolSearchIndex
from astrbot.core.tools.tool_search_tool import ToolSearchTool

# ---------------------------------------------------------------------------
# Helpers (self-contained, copied pattern from test_tools_assembler.py)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "always_loaded_tools": [],
    "auto_always_load_builtin": True,
}


def _make_tool(
    name: str,
    *,
    description: str = "",
    handler_module_path: str | None = None,
    active: bool = True,
    params: dict | None = None,
) -> FunctionTool:
    """Create a minimal FunctionTool for testing."""
    if params is None:
        params = {"type": "object", "properties": {}}
    if not description:
        description = f"Description for {name}"
    return FunctionTool(
        name=name,
        description=description,
        parameters=params,
        handler_module_path=handler_module_path,
        active=active,
    )


def _build_catalog(
    core_names: list[str],
    deferred_names: list[str],
) -> ToolCatalog:
    """Build a ToolCatalog with specific core and deferred tools.

    Core tools: builtin (no handler_module_path) with auto_always_load_builtin=True.
    Deferred tools: plugin tools (with handler_module_path set).
    """
    tools = []
    for name in core_names:
        tools.append(_make_tool(name))  # builtin -> core
    for name in deferred_names:
        tools.append(
            _make_tool(
                name,
                description=f"Deferred tool that provides {name} functionality",
                handler_module_path=f"plugins.{name}",
            )
        )  # plugin -> deferred
    ts = ToolSet(tools=tools)
    return ToolCatalog.from_tool_set(ts, DEFAULT_CONFIG)


def _make_strategy(
    core_names: list[str],
    deferred_names: list[str],
    max_results: int = 5,
) -> ClaudeToolSearchStrategy:
    """Build a ClaudeToolSearchStrategy with catalog and index."""
    catalog = _build_catalog(core_names, deferred_names)
    index = ToolSearchIndex(tools=catalog.deferred_tools)
    return ClaudeToolSearchStrategy(
        catalog=catalog, index=index, max_results=max_results
    )


# ===========================================================================
# CLN-01: build_tool_dicts includes full catalog with defer_loading
# ===========================================================================


class TestBuildToolDicts:
    """CLN-01: build_tool_dicts() returns dicts for ALL tools with defer_loading on deferred only."""

    def test_total_count(self):
        """build_tool_dicts() returns 2 core + 3 deferred + 1 tool_search = 6 dicts."""
        strategy = _make_strategy(
            core_names=["core_a", "core_b"],
            deferred_names=["plugin_weather", "plugin_calendar", "plugin_email"],
        )
        dicts = strategy.build_tool_dicts()
        assert len(dicts) == 6

    def test_tool_search_no_defer_loading(self):
        """tool_search dict does NOT have 'defer_loading' key."""
        strategy = _make_strategy(
            core_names=["core_a", "core_b"],
            deferred_names=["plugin_weather", "plugin_calendar", "plugin_email"],
        )
        dicts = strategy.build_tool_dicts()
        tool_search_dict = next(d for d in dicts if d["name"] == "tool_search")
        assert "defer_loading" not in tool_search_dict

    def test_core_tools_no_defer_loading(self):
        """Core tool dicts do NOT have 'defer_loading' key."""
        strategy = _make_strategy(
            core_names=["core_a", "core_b"],
            deferred_names=["plugin_weather", "plugin_calendar", "plugin_email"],
        )
        dicts = strategy.build_tool_dicts()
        core_dicts = [d for d in dicts if d["name"] in {"core_a", "core_b"}]
        assert len(core_dicts) == 2
        for d in core_dicts:
            assert "defer_loading" not in d

    def test_deferred_tools_have_defer_loading(self):
        """Deferred tool dicts have 'defer_loading': True."""
        strategy = _make_strategy(
            core_names=["core_a", "core_b"],
            deferred_names=["plugin_weather", "plugin_calendar", "plugin_email"],
        )
        dicts = strategy.build_tool_dicts()
        deferred_names = {"plugin_weather", "plugin_calendar", "plugin_email"}
        deferred_dicts = [d for d in dicts if d["name"] in deferred_names]
        assert len(deferred_dicts) == 3
        for d in deferred_dicts:
            assert d["defer_loading"] is True

    def test_every_dict_has_name_and_input_schema(self):
        """Every dict has 'name' (str) and 'input_schema' (dict with 'type': 'object')."""
        strategy = _make_strategy(
            core_names=["core_a", "core_b"],
            deferred_names=["plugin_weather", "plugin_calendar", "plugin_email"],
        )
        dicts = strategy.build_tool_dicts()
        for d in dicts:
            assert isinstance(d["name"], str)
            assert isinstance(d["input_schema"], dict)
            assert d["input_schema"]["type"] == "object"

    def test_dicts_with_description_have_description_key(self):
        """Dicts for tools with description have 'description' key."""
        strategy = _make_strategy(
            core_names=["core_a"],
            deferred_names=["plugin_weather"],
        )
        dicts = strategy.build_tool_dicts()
        for d in dicts:
            # All our test tools have descriptions
            assert "description" in d
            assert isinstance(d["description"], str)


# ===========================================================================
# CLN-02: format_tool_result produces tool_reference blocks
# ===========================================================================


class TestFormatToolResult:
    """CLN-02: format_tool_result() converts ToolSearchTool JSON to tool_reference blocks."""

    def test_valid_json_with_matches(self):
        """Valid JSON with matches returns list of tool_reference dicts."""
        strategy = _make_strategy(
            core_names=["core_a"],
            deferred_names=["get_weather", "get_calendar"],
        )
        result = strategy.format_tool_result(
            '{"query":"weather","matches":[{"name":"get_weather","description":"...","score":1.5}],"total_found":1}'
        )
        assert result == [{"type": "tool_reference", "tool_name": "get_weather"}]

    def test_error_json_returns_empty(self):
        """JSON with 'error' key returns empty list."""
        strategy = _make_strategy(
            core_names=["core_a"],
            deferred_names=["get_weather", "get_calendar"],
        )
        result = strategy.format_tool_result('{"error":"empty query","matches":[]}')
        assert result == []

    def test_invalid_json_returns_empty(self):
        """Invalid JSON string returns empty list."""
        strategy = _make_strategy(
            core_names=["core_a"],
            deferred_names=["get_weather", "get_calendar"],
        )
        result = strategy.format_tool_result("not json")
        assert result == []

    def test_empty_matches_returns_empty(self):
        """Empty matches array returns empty list."""
        strategy = _make_strategy(
            core_names=["core_a"],
            deferred_names=["get_weather", "get_calendar"],
        )
        result = strategy.format_tool_result(
            '{"query":"x","matches":[],"total_found":0}'
        )
        assert result == []

    def test_missing_name_key_skipped(self):
        """Match missing 'name' key is skipped."""
        strategy = _make_strategy(
            core_names=["core_a"],
            deferred_names=["get_weather", "get_calendar"],
        )
        result = strategy.format_tool_result(
            '{"query":"x","matches":[{"description":"no name"}],"total_found":1}'
        )
        assert result == []

    def test_catalog_validation_filters_unknown_tools(self):
        """Match with name NOT in catalog deferred tools returns [] for that match."""
        strategy = _make_strategy(
            core_names=["core_a"],
            deferred_names=["get_weather", "get_calendar"],
        )
        result = strategy.format_tool_result(
            '{"query":"x","matches":[{"name":"nonexistent_tool","description":"...","score":1.0}],"total_found":1}'
        )
        assert result == []


# ===========================================================================
# CLN-03: build_tool_dicts returns identical list every call
# ===========================================================================


class TestToolDictsStability:
    """CLN-03: build_tool_dicts() returns the same list object on every call."""

    def test_identity(self):
        """build_tool_dicts() returns the same object (identity check)."""
        strategy = _make_strategy(
            core_names=["core_a", "core_b"],
            deferred_names=["plugin_weather"],
        )
        dicts1 = strategy.build_tool_dicts()
        dicts2 = strategy.build_tool_dicts()
        assert dicts1 is dicts2

    def test_content_unchanged_after_discovery(self):
        """Discovery does NOT change build_tool_dicts() output."""
        strategy = _make_strategy(
            core_names=["core_a"],
            deferred_names=["plugin_weather", "plugin_email"],
        )
        dicts_before = strategy.build_tool_dicts()
        len_before = len(dicts_before)

        # Manually add discovery
        tool_search = strategy.get_tool_search_tool()
        tool_search._discovery_state.add("plugin_weather")

        dicts_after = strategy.build_tool_dicts()
        assert dicts_after is dicts_before
        assert len(dicts_after) == len_before

    def test_list_length_unchanged(self):
        """len(build_tool_dicts()) is the same before and after discovery."""
        strategy = _make_strategy(
            core_names=["core_a"],
            deferred_names=["plugin_weather"],
        )
        len_before = len(strategy.build_tool_dicts())

        # Discover a tool
        tool_search = strategy.get_tool_search_tool()
        tool_search._discovery_state.add("plugin_weather")

        len_after = len(strategy.build_tool_dicts())
        assert len_before == len_after


# ===========================================================================
# CLN-04: server tool block handling
# ===========================================================================


class TestServerToolBlocks:
    """CLN-04: is_server_tool_block() recognizes server-side block types."""

    def test_is_static_method(self):
        """is_server_tool_block is a @staticmethod."""
        assert isinstance(
            ClaudeToolSearchStrategy.__dict__["is_server_tool_block"],
            staticmethod,
        )

    def test_server_tool_use_returns_true(self):
        assert ClaudeToolSearchStrategy.is_server_tool_block("server_tool_use") is True

    def test_tool_search_tool_result_returns_true(self):
        assert (
            ClaudeToolSearchStrategy.is_server_tool_block("tool_search_tool_result")
            is True
        )

    def test_tool_use_returns_false(self):
        assert ClaudeToolSearchStrategy.is_server_tool_block("tool_use") is False

    def test_text_returns_false(self):
        assert ClaudeToolSearchStrategy.is_server_tool_block("text") is False

    def test_thinking_returns_false(self):
        assert ClaudeToolSearchStrategy.is_server_tool_block("thinking") is False

    def test_empty_string_returns_false(self):
        assert ClaudeToolSearchStrategy.is_server_tool_block("") is False


# ===========================================================================
# ABC compliance
# ===========================================================================


class TestABCCompliance:
    """ClaudeToolSearchStrategy satisfies ToolSearchStrategy ABC contract."""

    def test_is_subclass(self):
        """ClaudeToolSearchStrategy is a subclass of ToolSearchStrategy."""
        assert issubclass(ClaudeToolSearchStrategy, ToolSearchStrategy)

    def test_build_tool_set_returns_toolset(self):
        """build_tool_set() returns a ToolSet instance."""
        strategy = _make_strategy(
            core_names=["core_a", "core_b"],
            deferred_names=["plugin_weather"],
        )
        result = strategy.build_tool_set()
        assert isinstance(result, ToolSet)

    def test_build_tool_set_contains_all_tools(self):
        """build_tool_set().tools contains all core, deferred, and tool_search tools."""
        strategy = _make_strategy(
            core_names=["core_a", "core_b"],
            deferred_names=["plugin_weather", "plugin_email"],
        )
        result = strategy.build_tool_set()
        names = [t.name for t in result.tools]
        assert "core_a" in names
        assert "core_b" in names
        assert "plugin_weather" in names
        assert "plugin_email" in names
        assert "tool_search" in names

    def test_build_tool_set_overrides_anthropic_schema(self):
        """build_tool_set().anthropic_schema() uses deferred-loading tool dicts."""
        strategy = _make_strategy(
            core_names=["core_a"],
            deferred_names=["plugin_weather"],
        )
        result = strategy.build_tool_set()
        tool_defs = result.anthropic_schema()

        weather_tool = next(d for d in tool_defs if d["name"] == "plugin_weather")
        assert weather_tool["defer_loading"] is True

    def test_get_tool_search_tool_returns_tool_search_tool(self):
        """get_tool_search_tool() returns a ToolSearchTool instance."""
        strategy = _make_strategy(
            core_names=["core_a"],
            deferred_names=["plugin_weather"],
        )
        result = strategy.get_tool_search_tool()
        assert isinstance(result, ToolSearchTool)

    def test_get_tool_search_tool_identity(self):
        """get_tool_search_tool() returns the same object every call."""
        strategy = _make_strategy(
            core_names=["core_a"],
            deferred_names=["plugin_weather"],
        )
        tool1 = strategy.get_tool_search_tool()
        tool2 = strategy.get_tool_search_tool()
        assert tool1 is tool2
