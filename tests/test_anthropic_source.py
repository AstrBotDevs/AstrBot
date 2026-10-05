import asyncio
from types import SimpleNamespace

import pytest
from anthropic.types import MessageDeltaUsage, Usage

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.provider.entities import TokenUsage
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic


def _provider() -> ProviderAnthropic:
    return ProviderAnthropic.__new__(ProviderAnthropic)


def test_anthropic_extract_usage_counts_cache_creation_input():
    provider = _provider()

    usage = provider._extract_usage(
        Usage(
            input_tokens=10,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=50,
            output_tokens=20,
        )
    )

    # Anthropic's input_tokens excludes cache writes, so cache_creation
    # must be folded into input_other to keep total input accurate.
    assert usage.input_other == 60
    assert usage.input_cached == 100
    assert usage.input == 160
    assert usage.output == 20


def test_anthropic_extract_usage_without_cache_breakpoints():
    provider = _provider()

    usage = provider._extract_usage(Usage(input_tokens=30, output_tokens=10))

    assert usage.input_other == 30
    assert usage.input_cached == 0
    assert usage.input == 30
    assert usage.output == 10


def test_anthropic_extract_usage_none_returns_empty():
    provider = _provider()

    assert provider._extract_usage(None) == TokenUsage()


def test_anthropic_update_usage_counts_cache_creation_input():
    provider = _provider()
    token_usage = TokenUsage(input_other=5, input_cached=0, output=0)

    provider._update_usage(
        token_usage,
        MessageDeltaUsage(
            input_tokens=10,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=50,
            output_tokens=20,
        ),
    )

    assert token_usage.input_other == 60
    assert token_usage.input_cached == 100
    assert token_usage.input == 160
    assert token_usage.output == 20


def test_anthropic_update_usage_omitted_fields_are_preserved():
    provider = _provider()
    token_usage = TokenUsage(input_other=5, input_cached=0, output=0)

    # message_delta usage only carries output tokens in practice.
    provider._update_usage(token_usage, MessageDeltaUsage(output_tokens=7))

    assert token_usage.input_other == 5
    assert token_usage.input_cached == 0
    assert token_usage.output == 7


def test_merge_request_tools_keeps_provider_and_function_tools():
    function_tools = [
        {"name": "reverse_image_search", "input_schema": {"type": "object"}},
    ]
    server_tool = {"type": "web_search_20250305", "name": "web_search"}

    merged = ProviderAnthropic._merge_request_tools([server_tool], function_tools)

    assert merged == [*function_tools, server_tool]


def test_merge_request_tools_prefers_user_declared_entry_on_name_conflict():
    function_tools = [{"name": "web_search", "input_schema": {"type": "object"}}]
    server_tool = {"type": "web_search_20250305", "name": "web_search"}

    merged = ProviderAnthropic._merge_request_tools([server_tool], function_tools)

    assert merged == [server_tool]


def test_merge_request_tools_ignores_non_list_value():
    function_tools = [{"name": "reverse_image_search"}]

    merged = ProviderAnthropic._merge_request_tools("not-a-list", function_tools)

    assert merged == function_tools


def test_merge_request_tools_collapses_duplicate_declared_entries():
    server_tool = {"type": "web_search_20250305", "name": "web_search"}

    merged = ProviderAnthropic._merge_request_tools(
        [server_tool, dict(server_tool)],
        [],
    )

    assert merged == [server_tool]


def test_merge_request_tools_keeps_duplicate_unnamed_entries():
    # Provider-side tools without a name cannot be deduplicated and must survive.
    unnamed = {"type": "computer_20250124"}

    merged = ProviderAnthropic._merge_request_tools([unnamed, dict(unnamed)], [])

    assert merged == [unnamed, unnamed]


def test_merge_request_tools_drops_non_object_entries(caplog):
    server_tool = {"type": "web_search_20250305", "name": "web_search"}

    with caplog.at_level("WARNING"):
        merged = ProviderAnthropic._merge_request_tools(
            [server_tool, "web_search", 42],
            [],
        )

    assert merged == [server_tool]
    assert any(
        "custom_extra_body.tools entry of type str" in record.getMessage()
        for record in caplog.records
    )


def test_prepare_request_tools_moves_custom_tools_out_of_extra_body():
    provider = _provider()
    # Custom body parameters must not carry "tools" into the SDK request, because
    # the SDK replaces the whole key and would drop the merged tool list.
    provider.provider_config = {
        "custom_extra_body": {
            "temperature": 0.4,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        },
    }
    payloads = {}

    extra_body = provider._prepare_request_tools(payloads, None)

    assert payloads["tools"] == [
        {"type": "web_search_20250305", "name": "web_search"},
    ]
    # A provider-side tool alone still needs the normalized tool_choice shape.
    assert payloads["tool_choice"] == {"type": "auto"}
    assert extra_body == {"temperature": 0.4}


def test_prepare_request_tools_keeps_function_tools_alongside_custom_tools():
    provider = _provider()
    provider.provider_config = {
        "custom_extra_body": {
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        },
    }
    tools = ToolSet()
    tools.add_tool(
        FunctionTool(
            name="reverse_image_search",
            description="Search by image",
            parameters={"type": "object", "properties": {}},
        )
    )
    payloads = {}

    extra_body = provider._prepare_request_tools(payloads, tools)

    # The regression this guards: a declared provider-side tool must not remove the
    # function tools AstrBot injects for the same request.
    assert payloads["tools"] == [
        {
            "name": "reverse_image_search",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
            "description": "Search by image",
        },
        {"type": "web_search_20250305", "name": "web_search"},
    ]
    assert payloads["tool_choice"] == {"type": "auto"}
    assert extra_body == {}


def test_prepare_request_tools_without_custom_tools_writes_nothing_extra():
    provider = _provider()
    provider.provider_config = {"custom_extra_body": {"temperature": 0.4}}
    payloads = {}

    extra_body = provider._prepare_request_tools(payloads, None)

    assert payloads == {}
    assert extra_body == {"temperature": 0.4}


def test_query_passes_merged_tools_and_no_tools_in_extra_body():
    """Guard the SDK merge boundary, where the original bug happened.

    The streaming path is skipped on purpose: it asserts the SDK stream type, so
    it cannot be exercised without a real client.
    """
    provider = _provider()
    provider.provider_config = {
        "custom_extra_body": {
            "temperature": 0.4,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        },
    }
    # _query() reaches _apply_thinking_config(), which needs this instance state
    # that __init__ would normally provide.
    provider.thinking_config = {}
    captured = {}

    async def _create(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop before the SDK is reached")

    provider.client = SimpleNamespace(
        messages=SimpleNamespace(create=_create),
    )

    with pytest.raises(RuntimeError, match="stop before the SDK"):
        asyncio.run(
            provider._query(
                {"messages": [], "model": "deepseek-flash"},
                None,
            )
        )

    assert captured["tools"] == [
        {"type": "web_search_20250305", "name": "web_search"},
    ]
    # extra_body must not carry "tools" any more, or the SDK merge would replace
    # the merged list with the raw value.
    assert captured["extra_body"] == {"temperature": 0.4}
