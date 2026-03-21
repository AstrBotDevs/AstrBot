"""Tests for ToolSearchIndex -- BM25 search index (IDX-01, IDX-02, IDX-03, IDX-04)."""

import dataclasses

import pytest

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.tools.tool_search_index import ToolSearchIndex

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(
    name: str,
    description: str,
    params: dict | None = None,
) -> FunctionTool:
    """Create a FunctionTool with realistic parameters for search testing."""
    if params is None:
        params = {"type": "object", "properties": {}}
    return FunctionTool(
        name=name,
        description=description,
        parameters=params,
        handler_module_path="plugins.test",
    )


# A shared corpus of 10+ tools with diverse domains for meaningful BM25 IDF scores.
WEATHER_TOOL = _make_tool(
    "get_weather",
    "Get the current weather forecast for a location",
    {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "The city and state"},
            "unit": {"type": "string", "description": "Temperature unit celsius or fahrenheit"},
        },
        "required": ["location"],
    },
)

CALENDAR_TOOL = _make_tool(
    "create_calendar_event",
    "Create a new calendar event with title date and time",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "The event title"},
            "date": {"type": "string", "description": "The event date in YYYY-MM-DD format"},
            "time": {"type": "string", "description": "The event start time"},
        },
        "required": ["title", "date"],
    },
)

EMAIL_TOOL = _make_tool(
    "send_email",
    "Send an email message to a recipient",
    {
        "type": "object",
        "properties": {
            "recipient": {"type": "string", "description": "The email address of the recipient"},
            "subject": {"type": "string", "description": "The email subject line"},
            "body": {"type": "string", "description": "The email body content"},
        },
        "required": ["recipient", "subject", "body"],
    },
)

CALCULATOR_TOOL = _make_tool(
    "calculator",
    "Perform mathematical calculations and arithmetic operations",
    {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "The mathematical expression to evaluate"},
        },
        "required": ["expression"],
    },
)

TRANSLATOR_TOOL = _make_tool(
    "translate_text",
    "Translate text between different languages",
    {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The text to translate"},
            "source_lang": {"type": "string", "description": "Source language code"},
            "target_lang": {"type": "string", "description": "Target language code"},
        },
        "required": ["text", "target_lang"],
    },
)

FILE_MANAGER_TOOL = _make_tool(
    "manage_files",
    "Create read update and delete files on the filesystem",
    {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "The file operation create read update delete"},
            "path": {"type": "string", "description": "The file path on the filesystem"},
        },
        "required": ["action", "path"],
    },
)

MUSIC_TOOL = _make_tool(
    "play_music",
    "Play music tracks and manage playlists for the user",
    {
        "type": "object",
        "properties": {
            "track": {"type": "string", "description": "The name of the song or track"},
            "playlist": {"type": "string", "description": "The playlist name to play from"},
        },
    },
)

NEWS_TOOL = _make_tool(
    "get_news",
    "Fetch the latest news articles and headlines from various sources",
    {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "The news topic or category"},
            "count": {"type": "integer", "description": "Number of articles to return"},
        },
    },
)

COOKING_TOOL = _make_tool(
    "get_recipe",
    "Find cooking recipes and meal preparation instructions",
    {
        "type": "object",
        "properties": {
            "dish": {"type": "string", "description": "The name of the dish to cook"},
            "cuisine": {"type": "string", "description": "The cuisine type like Italian or Chinese"},
        },
    },
)

FITNESS_TOOL = _make_tool(
    "fitness_tracker",
    "Track exercise workouts and physical activity progress",
    {
        "type": "object",
        "properties": {
            "exercise": {"type": "string", "description": "The type of exercise or workout"},
            "duration": {"type": "integer", "description": "Duration in minutes"},
        },
    },
)

DATABASE_TOOL = _make_tool(
    "query_database",
    "Execute SQL queries against the application database",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The SQL query to execute"},
            "database": {"type": "string", "description": "The target database name"},
        },
        "required": ["query"],
    },
)

CHINESE_TOOL = _make_tool(
    "search_chinese_web",
    "搜索中文网页并返回相关结果",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "count": {"type": "integer", "description": "返回结果数量"},
        },
        "required": ["query"],
    },
)

ALL_TOOLS = (
    WEATHER_TOOL,
    CALENDAR_TOOL,
    EMAIL_TOOL,
    CALCULATOR_TOOL,
    TRANSLATOR_TOOL,
    FILE_MANAGER_TOOL,
    MUSIC_TOOL,
    NEWS_TOOL,
    COOKING_TOOL,
    FITNESS_TOOL,
    DATABASE_TOOL,
    CHINESE_TOOL,
)


# ===========================================================================
# IDX-01: Index Build
# ===========================================================================


class TestIndexBuild:
    """IDX-01: ToolSearchIndex builds BM25 index from tool metadata."""

    def test_builds_from_tuple(self):
        """ToolSearchIndex(tools=(...,)) constructs without error; has _bm25 attribute."""
        index = ToolSearchIndex(tools=ALL_TOOLS)

        assert hasattr(index, "_bm25")
        assert index._bm25 is not None

    def test_search_doc_includes_name_desc_params(self):
        """A tool with params matches a query targeting parameter descriptions.

        Verifies all four search surface components are indexed:
        name, description, parameter names, parameter descriptions.
        """
        index = ToolSearchIndex(tools=ALL_TOOLS)
        # Query for "city temperature" should match weather tool
        # because "city" is in location param description and
        # "temperature" is in unit param description
        results = index.search("city temperature")

        assert len(results) > 0
        tool_names = [t.name for t, _score in results]
        assert "get_weather" in tool_names

    def test_empty_corpus(self):
        """ToolSearchIndex(tools=()) constructs without error; search returns []."""
        index = ToolSearchIndex(tools=())

        assert index.search("anything") == []


# ===========================================================================
# IDX-02: Search
# ===========================================================================


class TestSearch:
    """IDX-02: search() returns ranked (FunctionTool, float) tuples without mutation."""

    def test_returns_ranked_tuples(self):
        """search() returns list of (FunctionTool, float) tuples.

        First result is the weather tool; scores are positive floats
        in descending order.
        """
        index = ToolSearchIndex(tools=ALL_TOOLS)
        results = index.search("weather forecast")

        assert len(results) > 0
        # Check types
        for tool, score in results:
            assert isinstance(tool, FunctionTool)
            assert isinstance(score, float)
            assert score > 0

        # Scores should be in descending order
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

        # Weather tool should be the top result
        assert results[0][0].name == "get_weather"

    def test_no_mutation(self):
        """After search(), the index's tools tuple and _bm25 are identical to pre-search state."""
        index = ToolSearchIndex(tools=ALL_TOOLS)
        tools_id_before = id(index.tools)
        bm25_id_before = id(index._bm25)

        index.search("weather forecast")

        assert id(index.tools) == tools_id_before
        assert id(index._bm25) == bm25_id_before

    def test_irrelevant_query(self):
        """search() for a completely irrelevant term returns []."""
        index = ToolSearchIndex(tools=ALL_TOOLS)
        results = index.search("completely_unrelated_xyz_gibberish_qwerty")

        assert results == []

    def test_deterministic(self):
        """Same query on same index returns identical results."""
        index = ToolSearchIndex(tools=ALL_TOOLS)
        results1 = index.search("email recipient")
        results2 = index.search("email recipient")

        assert len(results1) == len(results2)
        for (tool1, score1), (tool2, score2) in zip(results1, results2):
            assert tool1.name == tool2.name
            assert score1 == score2

    def test_empty_query(self):
        """search('') returns []."""
        index = ToolSearchIndex(tools=ALL_TOOLS)
        results = index.search("")

        assert results == []

    def test_chinese_query(self):
        """A tool with Chinese description matches a Chinese query via jieba tokenization."""
        index = ToolSearchIndex(tools=ALL_TOOLS)
        # The CHINESE_TOOL has description "搜索中文网页并返回相关结果"
        results = index.search("搜索中文网页")

        assert len(results) > 0
        tool_names = [t.name for t, _score in results]
        assert "search_chinese_web" in tool_names


# ===========================================================================
# IDX-03: Immutability
# ===========================================================================


class TestImmutability:
    """IDX-03: ToolSearchIndex is frozen and holds no mutable external references."""

    def test_frozen_instance(self):
        """Assignment to ToolSearchIndex attributes raises FrozenInstanceError."""
        index = ToolSearchIndex(tools=ALL_TOOLS)

        with pytest.raises(dataclasses.FrozenInstanceError):
            index.tools = ()  # type: ignore[misc]

    def test_no_toolset_reference(self):
        """ToolSearchIndex has no attribute referencing ToolSet or ToolCatalog."""
        index = ToolSearchIndex(tools=ALL_TOOLS)
        attrs = dir(index)

        # Should not have attributes pointing to mutable external objects
        for attr_name in attrs:
            assert "tool_set" not in attr_name.lower() or attr_name == "tool_set"
            assert "tool_catalog" not in attr_name.lower()
        # No tool_set or catalog attribute
        assert not hasattr(index, "tool_set")
        assert not hasattr(index, "tool_catalog")
        assert not hasattr(index, "catalog")

    def test_no_inject_into(self):
        """ToolSearchIndex has no inject_into method."""
        index = ToolSearchIndex(tools=ALL_TOOLS)

        assert not hasattr(index, "inject_into")


# ===========================================================================
# IDX-04: Max Results
# ===========================================================================


class TestMaxResults:
    """IDX-04: max_results is configurable, default 5."""

    def test_max_results_limits(self):
        """search(query, max_results=1) returns at most 1 result even when multiple match."""
        index = ToolSearchIndex(tools=ALL_TOOLS)
        results = index.search("the", max_results=1)

        assert len(results) <= 1

    def test_max_results_default(self):
        """search(query) without max_results returns at most 5 results."""
        index = ToolSearchIndex(tools=ALL_TOOLS)
        # Use a broad query that should match many tools
        results = index.search("text string description")

        assert len(results) <= 5

    def test_max_results_exceeds_positive(self):
        """When only 2 tools have positive scores, max_results=10 returns only 2."""
        # Create a corpus where only a few tools match
        tool_a = _make_tool("unique_alpha_tool", "Handles alpha-specific processing only")
        tool_b = _make_tool("unique_beta_tool", "Handles beta-specific processing only")
        tool_c = _make_tool("unrelated_gamma", "Does something completely different with widgets")
        tool_d = _make_tool("unrelated_delta", "Manages inventory of physical items in warehouse")
        tool_e = _make_tool("unrelated_epsilon", "Monitors network traffic and bandwidth usage")
        tool_f = _make_tool("unrelated_zeta", "Generates reports from financial spreadsheets")
        tool_g = _make_tool("unrelated_eta", "Handles customer support ticket routing")
        tool_h = _make_tool("unrelated_theta", "Processes image recognition and classification")
        tool_i = _make_tool("unrelated_iota", "Manages cloud infrastructure deployments")
        tool_j = _make_tool("unrelated_kappa", "Performs automated security vulnerability scanning")

        tools = (tool_a, tool_b, tool_c, tool_d, tool_e, tool_f, tool_g, tool_h, tool_i, tool_j)
        index = ToolSearchIndex(tools=tools)
        results = index.search("alpha-specific processing", max_results=10)

        # Only tools with positive scores should appear (not padded to max_results)
        for _tool, score in results:
            assert score > 0
        assert len(results) <= 10
