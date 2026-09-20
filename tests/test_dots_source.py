import json
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from mcp.types import CallToolResult, TextContent
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.provider.sources.dots_source import ProviderDots
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial


@pytest.mark.asyncio
async def test_dots_authentication_follows_request_key_rotation(monkeypatch):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {
                        "id": "dots3-note-prev",
                        "object": "model",
                        "created": 0,
                        "owned_by": "dots",
                    }
                ],
            },
        )

    monkeypatch.setattr(
        ProviderOpenAIOfficial,
        "_create_http_client",
        lambda self, config: httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    template = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]["Dots"]
    config = {
        **template,
        "key": ["first-key", "second-key"],
        "custom_headers": {"X-Test": "preserved"},
    }
    provider = ProviderDots(config, {})
    try:
        assert provider.get_model() == "dots3-note-prev"
        assert await provider.get_models() == ["dots3-note-prev"]
        # Chat retries also assign client.api_key directly rather than calling set_key.
        provider.client.api_key = "second-key"
        assert await provider.get_models() == ["dots3-note-prev"]
        assert [request.headers["api-key"] for request in requests] == [
            "first-key",
            "second-key",
        ]
        assert [request.headers["authorization"] for request in requests] == [
            "Bearer first-key",
            "Bearer second-key",
        ]
        assert all(request.headers["X-Test"] == "preserved" for request in requests)
        assert all(
            str(request.url) == "https://note3-prev-api.askdiandian.com/v1/models"
            for request in requests
        )
        assert "model" not in config
    finally:
        await provider.terminate()


@pytest_asyncio.fixture
async def provider():
    instance = ProviderDots({"id": "dots-test", "key": ["test-key"]}, {})
    try:
        yield instance
    finally:
        await instance.terminate()


@pytest.fixture
def tools():
    return ToolSet(
        tools=[
            FunctionTool(
                name="web_search_tavily",
                description="Search the web",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer", "minimum": 1},
                        "enabled": {"type": "boolean"},
                        "filters": {"type": "object"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "optional": {"type": ["string", "null"]},
                    },
                    "required": ["query", "max_results"],
                    "additionalProperties": False,
                },
            )
        ]
    )


def completion(content, finish_reason="tool_calls", tool_calls=None):
    return ChatCompletion.model_validate(
        {
            "id": "dots-response",
            "object": "chat.completion",
            "created": 0,
            "model": "dots3-note-prev",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": finish_reason,
                    "message": {
                        "role": "assistant",
                        "content": content,
                        "tool_calls": tool_calls,
                    },
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }
    )


NATIVE_CALL = (
    '<dots_function_call><invoke name="web_search_tavily">'
    '<parameter name="query">123 & weather</parameter>'
    '<parameter name="max_results">5</parameter>'
    "</invoke></dots_function_call>"
)


@pytest.mark.asyncio
async def test_issue_10094_native_call_is_normalized(provider, tools):
    original = completion("Searching.\n" + NATIVE_CALL + "\nPlease wait.")
    result = await provider._parse_openai_completion(original, tools)
    assert result.role == "tool"
    assert result.tools_call_name == ["web_search_tavily"]
    assert result.tools_call_args == [{"query": "123 & weather", "max_results": 5}]
    assert result.completion_text == "Searching.\n\nPlease wait."
    assert len(result.tools_call_ids) == 1
    assert (
        result.raw_completion.choices[0].message.tool_calls[0].id
        == result.tools_call_ids[0]
    )
    assert original.choices[0].message.tool_calls is None
    assert NATIVE_CALL in original.choices[0].message.content
    assert result.usage.total == 30


@pytest.mark.asyncio
async def test_native_parameter_types_and_multiple_invocations(provider, tools):
    block = NATIVE_CALL.replace(
        "</invoke>",
        '<parameter name="enabled">true</parameter>'
        '<parameter name="filters">{"year": 2026}</parameter>'
        '<parameter name="tags">["news"]</parameter>'
        '<parameter name="optional">null</parameter></invoke>',
    )
    # Exercise multiple invokes in one block, plus multiple blocks.
    block = block.replace("</dots_function_call>", NATIVE_CALL.split(">", 1)[1])
    result = await provider._parse_openai_completion(
        completion(block + NATIVE_CALL), tools
    )
    assert len(result.tools_call_ids) == len(set(result.tools_call_ids)) == 3
    assert result.tools_call_args[0] == {
        "query": "123 & weather",
        "max_results": 5,
        "enabled": True,
        "filters": {"year": 2026},
        "tags": ["news"],
        "optional": None,
    }
    assert not result.completion_text


@pytest.mark.asyncio
async def test_json_fallback_and_standard_call_precedence(provider, tools):
    body = {
        "name": "web_search_tavily",
        "arguments": {"query": "weather", "max_results": 2},
    }
    result = await provider._parse_openai_completion(
        completion(f"<dots_function_call>{json.dumps(body)}</dots_function_call>"),
        tools,
    )
    assert result.tools_call_args == [body["arguments"]]
    standard = [
        {
            "id": "original-id",
            "type": "function",
            "function": {
                "name": body["name"],
                "arguments": json.dumps(body["arguments"]),
            },
        }
    ]
    for content in ("Searching", NATIVE_CALL):
        result = await provider._parse_openai_completion(
            completion(content, tool_calls=standard), tools
        )
        assert result.tools_call_ids == ["original-id"]
        assert result.tools_call_args == [body["arguments"]]
        assert "dots_function_call" not in (result.completion_text or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content", [NATIVE_CALL, f"Example:\n```xml\n{NATIVE_CALL}\n```"]
)
async def test_ordinary_xml_answers_are_not_executed(provider, tools, content):
    result = await provider._parse_openai_completion(completion(content, "stop"), tools)
    assert not result.tools_call_name
    assert result.completion_text == content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        NATIVE_CALL[:-10],
        NATIVE_CALL.replace("web_search_tavily", "unavailable"),
        NATIVE_CALL.replace(">5<", ">invalid<"),
        NATIVE_CALL.replace(">5<", ">0<"),
        NATIVE_CALL.replace('<parameter name="max_results">5</parameter>', ""),
        NATIVE_CALL.replace(
            "</invoke>", '<parameter name="max_results">2</parameter></invoke>'
        ),
        NATIVE_CALL.replace(
            "</invoke>", '<parameter name="unknown">test</parameter></invoke>'
        ),
        "<dots_function_call>{broken}</dots_function_call>",
        "<dots_function_call></dots_function_call>",
        "Searching without any call",
    ],
)
async def test_invalid_native_calls_fail_without_becoming_answers(
    provider, tools, content
):
    with pytest.raises(ValueError):
        await provider._parse_openai_completion(completion(content), tools)


@pytest.mark.asyncio
@pytest.mark.parametrize("available_tools", [None, ToolSet()])
async def test_native_calls_require_available_tools(provider, available_tools):
    with pytest.raises(ValueError):
        await provider._parse_openai_completion(
            completion(NATIVE_CALL), available_tools
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_native_call_round_trip_through_agent(monkeypatch, tools, streaming):
    requests = []
    executed = []

    def handle(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert request.headers["api-key"] == "test-key"
        result = (
            completion(NATIVE_CALL)
            if len(requests) == 1
            else completion("The result is ready.", "stop")
        )
        if not payload["stream"]:
            return httpx.Response(200, json=result.model_dump())
        content = result.choices[0].message.content
        chunks = (
            [{"role": "assistant"}] + [{"content": char} for char in content] + [{}]
        )
        events = []
        for index, delta in enumerate(chunks):
            chunk = {
                "id": result.id,
                "object": "chat.completion.chunk",
                "created": 0,
                "model": result.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": delta,
                        "finish_reason": result.choices[0].finish_reason
                        if index == len(chunks) - 1
                        else None,
                    }
                ],
            }
            if index == len(chunks) - 1:
                chunk["usage"] = result.usage.model_dump()
            events.append("data: " + json.dumps(chunk) + "\n\n")
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text="".join(events) + "data: [DONE]\n\n",
        )

    class Executor:
        async def execute(self, tool, run_context, **kwargs):
            executed.append(kwargs)
            yield CallToolResult(
                content=[
                    TextContent(type="text", text="A deterministic search result.")
                ]
            )

    monkeypatch.setattr(
        ProviderOpenAIOfficial,
        "_create_http_client",
        lambda self, config: httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    instance = ProviderDots({"id": "dots-test", "key": ["test-key"]}, {})
    runner = ToolLoopAgentRunner()
    try:
        await runner.reset(
            provider=instance,
            request=ProviderRequest(prompt="Search", func_tool=tools),
            run_context=ContextWrapper(context=None),
            tool_executor=Executor(),
            agent_hooks=BaseAgentRunHooks(),
            streaming=streaming,
        )
        responses = [response async for response in runner.step_until_done(3)]
        assert runner.done()
        assert len(requests) == 2
        assert executed == [{"query": "123 & weather", "max_results": 5}]
        history = requests[1]["messages"]
        assistant = next(message for message in history if message.get("tool_calls"))
        tool_result = next(message for message in history if message["role"] == "tool")
        assert tool_result["tool_call_id"] == assistant["tool_calls"][0]["id"]
        assert "deterministic search result" in tool_result["content"]
        assert "dots_function_call" not in json.dumps(history)
        assert "dots_function_call" not in str(responses)
        assert runner.get_final_llm_resp().completion_text == "The result is ready."
        if streaming:
            text = "".join(
                r.data["chain"].get_plain_text()
                for r in responses
                if r.type == "streaming_delta" and r.data.get("chain")
            )
            assert text == "The result is ready."
    finally:
        await instance.terminate()


@pytest.mark.asyncio
async def test_native_parameters_resolve_references_and_unions(provider, tools):
    schema = tools.tools[0].parameters
    schema["$defs"] = {"count": {"type": "integer", "minimum": 1}}
    schema["properties"]["max_results"] = {"$ref": "#/$defs/count"}
    schema["properties"]["optional"] = {
        "anyOf": [{"type": "integer"}, {"type": "null"}]
    }
    raw = NATIVE_CALL.replace(
        "</invoke>", '<parameter name="optional">3</parameter></invoke>'
    )
    result = await provider._parse_openai_completion(completion(raw), tools)
    assert result.tools_call_args == [
        {"query": "123 & weather", "max_results": 5, "optional": 3}
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_enabled,finish_reason",
    [(False, "stop"), (True, "stop"), (True, "tool_calls"), (True, "length")],
)
async def test_stream_output_and_parse_failure(
    provider, tools, tool_enabled, finish_reason
):
    malformed = finish_reason != "stop"
    content = NATIVE_CALL[:-10] if malformed else "Hello world"

    async def chunks():
        for index, text in enumerate([content[:5], content[5:], None]):
            yield ChatCompletionChunk.model_validate(
                {
                    "id": "stream-test",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": "dots3-note-prev",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": text},
                            "finish_reason": finish_reason if index == 2 else None,
                        }
                    ],
                }
            )

    provider.client.chat.completions.create = AsyncMock(return_value=chunks())
    responses = provider._query_stream(
        {"model": "dots3-note-prev", "messages": []}, tools if tool_enabled else None
    )
    if malformed:
        with pytest.raises(ValueError, match="without a valid final response"):
            await anext(responses)
    else:
        text_chunks = []
        finals = []
        async for response in responses:
            if response.is_chunk:
                text_chunks.append(response.completion_text)
            else:
                finals.append(response)
        assert text_chunks == (["Hello world"] if tool_enabled else ["Hello", " world"])
        assert len(finals) == 1
        assert finals[0].completion_text == "Hello world"
