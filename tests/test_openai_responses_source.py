import json
from types import SimpleNamespace

import pytest
from openai import _base_client
from openai.types.responses import Response

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)


def _make_provider(overrides: dict | None = None) -> ProviderOpenAIResponses:
    provider_config = {
        "id": "test-responses",
        "provider": "openai",
        "type": "openai_responses",
        "model": "gpt-test",
        "key": ["test-key"],
        "api_base": "https://api.openai.com/v1",
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderOpenAIResponses(provider_config, {})


def _make_response(output: list[dict], **overrides) -> Response:
    payload = {
        "id": "resp_1",
        "object": "response",
        "created_at": 1,
        "status": "completed",
        "model": "gpt-test",
        "output": output,
        "usage": {
            "input_tokens": 10,
            "input_tokens_details": {
                "cached_tokens": 3,
                "cache_write_tokens": 0,
            },
            "output_tokens": 4,
            "output_tokens_details": {"reasoning_tokens": 2},
            "total_tokens": 14,
        },
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
    }
    payload.update(overrides)
    return Response.model_validate(payload)


def test_responses_provider_templates_are_independent_and_stateless():
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]

    assert templates["OpenAI Responses"]["type"] == "openai_responses"
    assert templates["OpenAI Responses"]["api_base"] == "https://api.openai.com/v1"
    assert templates["DeepSeek Responses"]["type"] == "openai_responses"
    assert templates["DeepSeek Responses"]["api_base"] == "https://api.deepseek.com/v1"
    assert templates["xAI"]["type"] == "openai_responses"
    assert templates["xAI"]["api_base"] == "https://api.x.ai/v1"
    assert templates["xAI"]["xai_native_search"] is False


def test_convert_chat_history_preserves_response_items_and_function_calls():
    provider = _make_provider()
    reasoning_item = {
        "id": "rs_1",
        "type": "reasoning",
        "status": "completed",
        "summary": [],
        "encrypted_content": "encrypted-reasoning",
    }
    reasoning_state = json.dumps(
        {
            "type": provider._REASONING_STATE_TYPE,
            "items": [reasoning_item],
        }
    )

    response_input = provider._convert_chat_messages_to_response_input(
        [
            {"role": "system", "content": "system context"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "look"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,AAAA",
                            "detail": "high",
                        },
                    },
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "think",
                        "think": "hidden",
                        "encrypted": reasoning_state,
                    },
                    {"type": "text", "text": "calling"},
                ],
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "weather", "arguments": '{"city":"SZ"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "sunny"},
        ]
    )

    assert response_input == [
        {"type": "message", "role": "system", "content": "system context"},
        {
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_text", "text": "look"},
                {
                    "type": "input_image",
                    "detail": "high",
                    "image_url": "data:image/png;base64,AAAA",
                },
            ],
        },
        reasoning_item,
        {"type": "message", "role": "assistant", "content": "calling"},
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "weather",
            "arguments": '{"city":"SZ"}',
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "sunny",
        },
    ]


def test_deepseek_converts_plain_reasoning_history_to_reasoning_item():
    provider = _make_provider(
        {
            "provider": "deepseek",
            "api_base": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
        }
    )

    response_input = provider._convert_chat_messages_to_response_input(
        [
            {
                "role": "assistant",
                "content": [
                    {"type": "think", "think": "prior thought"},
                    {"type": "text", "text": "prior answer"},
                ],
            }
        ]
    )

    assert response_input == [
        {
            "type": "reasoning",
            "content": [
                {"type": "reasoning_text", "text": "prior thought"},
            ],
            "summary": [],
        },
        {"type": "message", "role": "assistant", "content": "prior answer"},
    ]


@pytest.mark.asyncio
async def test_prepare_payload_replays_full_history_without_server_state():
    provider = _make_provider()

    payloads, context = await provider._prepare_chat_payload(
        prompt="current",
        contexts=[{"role": "user", "content": "previous"}],
        system_prompt="follow instructions",
    )

    assert context == [
        {"role": "user", "content": "previous"},
        {"role": "user", "content": "current"},
    ]
    assert payloads == {
        "model": "gpt-test",
        "store": False,
        "instructions": "follow instructions",
        "input": [
            {"type": "message", "role": "user", "content": "previous"},
            {"type": "message", "role": "user", "content": "current"},
        ],
    }
    assert "previous_response_id" not in payloads
    assert "conversation" not in payloads


@pytest.mark.asyncio
async def test_query_flattens_tools_and_enforces_stateless_body(monkeypatch):
    provider = _make_provider(
        {
            "custom_extra_body": {
                "max_tokens": 321,
                "reasoning_effort": "low",
                "previous_response_id": "resp_previous",
                "conversation": "conv_1",
                "store": True,
            }
        }
    )
    captured: dict = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _make_response(
            [
                {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_1",
                    "name": "weather",
                    "arguments": '{"city":"SZ"}',
                    "status": "completed",
                }
            ]
        )

    monkeypatch.setattr(provider.client.responses, "create", fake_create)
    tools = SimpleNamespace(
        openai_schema=lambda: [
            {
                "type": "function",
                "function": {
                    "name": "weather",
                    "description": "Get weather",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                    },
                },
            }
        ]
    )

    result = await provider._query(
        {
            "model": "gpt-test",
            "input": "weather",
            "store": True,
            "previous_response_id": "resp_direct",
            "conversation": "conv_direct",
        },
        tools,
    )

    assert captured["store"] is False
    assert captured["stream"] is False
    assert "previous_response_id" not in captured
    assert "conversation" not in captured
    assert captured["tools"] == [
        {
            "type": "function",
            "name": "weather",
            "description": "Get weather",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
            },
        }
    ]
    assert captured["extra_body"] == {
        "max_output_tokens": 321,
        "reasoning": {"effort": "low"},
    }
    assert result.role == "tool"
    assert result.tools_call_name == ["weather"]
    assert result.tools_call_args == [{"city": "SZ"}]
    assert result.tools_call_ids == ["call_1"]


@pytest.mark.asyncio
async def test_parse_response_extracts_text_reasoning_usage_and_replay_state():
    provider = _make_provider()
    response = _make_response(
        [
            {
                "type": "reasoning",
                "id": "rs_1",
                "status": "completed",
                "summary": [],
                "content": [
                    {"type": "reasoning_text", "text": "thinking"},
                ],
            },
            {
                "type": "message",
                "id": "msg_1",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "answer", "annotations": []},
                ],
            },
        ]
    )

    result = await provider._parse_response(response, tools=None)

    assert result.completion_text == "answer"
    assert result.reasoning_content == "thinking"
    assert result.usage.input_other == 7
    assert result.usage.input_cached == 3
    assert result.usage.output == 4
    assert result.raw_completion is response
    state = json.loads(result.reasoning_signature)
    assert state["type"] == provider._REASONING_STATE_TYPE
    assert state["items"][0]["id"] == "rs_1"
    assert state["items"][0]["content"] == [
        {"text": "thinking", "type": "reasoning_text"}
    ]


@pytest.mark.asyncio
async def test_query_stream_yields_semantic_deltas_and_final_response(monkeypatch):
    provider = _make_provider()
    final_response = _make_response(
        [
            {
                "type": "message",
                "id": "msg_1",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "hello", "annotations": []},
                ],
            }
        ]
    )
    captured: dict = {}

    async def fake_stream():
        yield SimpleNamespace(
            type="response.created",
            response=SimpleNamespace(id="resp_1"),
        )
        yield SimpleNamespace(type="response.reasoning_text.delta", delta="think")
        yield SimpleNamespace(type="response.output_text.delta", delta="hello")
        yield SimpleNamespace(type="response.completed", response=final_response)

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return fake_stream()

    monkeypatch.setattr(provider.client.responses, "create", fake_create)

    results = [
        result
        async for result in provider._query_stream(
            {"model": "gpt-test", "input": "hi", "store": False},
            tools=None,
        )
    ]

    assert captured["stream"] is True
    assert captured["store"] is False
    assert len(results) == 3
    assert results[0].is_chunk is True
    assert results[0].reasoning_content == "think"
    assert results[1].is_chunk is True
    assert results[1].completion_text == "hello"
    assert results[2].is_chunk is False
    assert results[2].completion_text == "hello"


@pytest.mark.asyncio
async def test_parse_failed_response_raises_provider_error():
    provider = _make_provider()
    response = _make_response(
        [],
        status="failed",
        error={"code": "server_error", "message": "failed"},
        usage=None,
    )

    with pytest.raises(RuntimeError, match="server_error: failed"):
        await provider._parse_response(response, tools=None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "enabled", "streaming"),
    [
        ("xai", True, False),
        ("xai", True, True),
        ("xai", False, False),
        ("openai", True, False),
    ],
)
async def test_native_xai_tools_in_serialized_request(
    source, enabled, streaming, monkeypatch
):
    httpx = (
        _base_client.httpx2 if hasattr(_base_client, "httpx2") else _base_client.httpx
    )
    configured = [{"type": "x_search"}]
    if streaming:
        configured.append(
            {"type": "web_search", "filters": {"allowed_domains": ["example.com"]}}
        )
    response = _make_response(
        [
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {"type": "output_text", "text": "Answer", "annotations": []}
                ],
            }
        ]
    ).model_dump(mode="json")

    def handle(request):
        body = json.loads(request.content)
        assert body["stream"] == streaming
        if source == "xai" and enabled:
            assert [(tool["type"], tool.get("name")) for tool in body["tools"]] == [
                ("function", "get_weather"),
                ("x_search", None),
                ("web_search", None),
            ]
            if streaming:
                assert body["tools"][-1] == configured[-1]
        else:
            assert body["tools"] == configured
        if streaming:
            event = json.dumps(
                {
                    "type": "response.completed",
                    "sequence_number": 1,
                    "response": response,
                }
            )
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=f"data: {event}\n\n",
            )
        return httpx.Response(200, json=response)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        monkeypatch.setattr(
            ProviderOpenAIResponses, "_create_http_client", lambda self, config: client
        )
        provider = _make_provider(
            {
                "provider": source,
                "xai_native_search": enabled,
                "custom_extra_body": {"tools": configured},
            }
        )
        tools = ToolSet(
            [
                FunctionTool(
                    name="get_weather",
                    description="Weather",
                    parameters={"type": "object", "properties": {}},
                )
            ]
        )
        if streaming:
            responses = [
                item
                async for item in provider.text_chat_stream(
                    prompt="hello", func_tool=tools
                )
            ]
            result = responses[-1]
        else:
            result = await provider.text_chat(prompt="hello", func_tool=tools)
        assert result.completion_text == "Answer"
        assert provider.provider_config["custom_extra_body"]["tools"] == configured


@pytest.mark.asyncio
async def test_parse_response_extracts_deduplicated_xai_url_and_top_level_citations():
    provider = _make_provider({"provider": "xai", "xai_native_search": True})
    annotated = _make_response(
        [
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": "xAI update [[1]](https://x.ai/news) [[1]](https://x.ai/news)",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://x.ai/news",
                                "title": "xAI News",
                                "start_index": 11,
                                "end_index": 34,
                            },
                            {
                                "type": "url_citation",
                                "url": "https://x.ai/news",
                                "title": "xAI News",
                                "start_index": 35,
                                "end_index": 58,
                            },
                            {
                                "type": "url_citation",
                                "url": "https://docs.x.ai/",
                                "title": "",
                                "start_index": 0,
                                "end_index": 1,
                            },
                        ],
                    }
                ],
            }
        ]
    )
    parsed = await provider._parse_response(annotated, tools=None)
    assert parsed.web_search_sources == [
        {"index": "1", "url": "https://x.ai/news", "title": "xAI News"},
        {"index": "2", "url": "https://docs.x.ai/", "title": "https://docs.x.ai/"},
    ]

    top_level = _make_response(
        [
            {
                "id": "msg_2",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {"type": "output_text", "text": "Summary", "annotations": []}
                ],
            }
        ],
        citations=["https://x.ai/company", "https://x.ai/company", "https://x.ai/"],
    )
    parsed_fallback = await provider._parse_response(top_level, tools=None)
    assert parsed_fallback.web_search_sources == [
        {"index": "1", "url": "https://x.ai/company", "title": "https://x.ai/company"},
        {"index": "2", "url": "https://x.ai/", "title": "https://x.ai/"},
    ]
    other = _make_provider()
    for response in (annotated, top_level):
        assert not (
            await other._parse_response(response, tools=None)
        ).web_search_sources


@pytest.mark.asyncio
async def test_prepare_payload_sanitizes_legacy_tool_call_history():
    provider = _make_provider()
    contexts = [
        {"role": "user", "content": "turn 1"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "search",
                    "type": "function",
                    "function": {"name": "search", "arguments": '{"q":"a"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "search", "content": "first"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                "malformed",
                {
                    "id": "unanswered",
                    "type": "function",
                    "function": {"name": "skip", "arguments": "{}"},
                },
                {
                    "id": "search",
                    "type": "function",
                    "function": {"name": "search", "arguments": '{"q":"b"}'},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "search", "content": "second"},
        {"role": "tool", "tool_call_id": "orphan_call", "content": "stale"},
    ]

    payloads, _ = await provider._prepare_chat_payload(
        prompt="follow up",
        contexts=contexts,
    )

    function_calls = [
        item for item in payloads["input"] if item.get("type") == "function_call"
    ]
    function_outputs = [
        item for item in payloads["input"] if item.get("type") == "function_call_output"
    ]
    assert len(function_calls) == 2
    assert len(function_outputs) == 2
    assert function_calls[0]["call_id"] == "search"
    assert function_calls[1]["call_id"] != "search"
    assert [item["call_id"] for item in function_outputs] == [
        function_calls[0]["call_id"],
        function_calls[1]["call_id"],
    ]
    assert [item["output"] for item in function_outputs] == ["first", "second"]
    # Caller-owned context list must remain untouched.
    assert contexts[3]["tool_calls"][2]["id"] == "search"
