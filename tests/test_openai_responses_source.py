import json
from types import SimpleNamespace

import pytest
from openai.types.responses import Response

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)
from tests.fixtures.fake_tool_call import make_fake_pair


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
    assert "xai_native_search" not in templates["xAI"]


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
async def test_responses_reorders_fake_pair_before_conversion():
    """插件注入的伪造对在 Responses 路径同样需要前置到用户消息之后。

    转换后的 input 应为 user → function_call → function_call_output，
    与 OpenAI Chat Completions / Anthropic / Gemini 对齐。
    """
    provider = _make_provider()
    payloads, context = await provider._prepare_chat_payload(
        prompt="帮我处理",
        contexts=[
            {"role": "user", "content": "hello"},
            *make_fake_pair(tool_call_id="fake_call_01"),
        ],
    )

    assert [m["role"] for m in context] == ["user", "user", "assistant", "tool"]
    assert [item["type"] for item in payloads["input"]] == [
        "message",
        "message",
        "function_call",
        "function_call_output",
    ]
    assert payloads["input"][2]["name"] == "recall_long_term_memory"
    assert payloads["input"][3]["call_id"] == "fake_call_01"


@pytest.mark.parametrize(
    "tail_user_content",
    [
        "请根据图片分析结果继续",  # cached_images 图片复核消息
        "Maximum tool call limit reached.",  # max_steps 收尾提示
        "下一个问题",  # 跨轮次历史后用户新消息
    ],
    ids=["cached_images", "max_steps", "cross_turn"],
)
@pytest.mark.asyncio
async def test_responses_reorder_skips_marked_real_pair(tail_user_content):
    """带 _from_real_tool_call 标记的真实工具对在 Responses 路径不被重排。"""
    provider = _make_provider()
    payloads, context = await provider._prepare_chat_payload(
        prompt=tail_user_content,
        contexts=[
            {"role": "user", "content": "帮我查一下"},
            *make_fake_pair(
                tool_call_id="real_call_01", content="real result", marked=True
            ),
        ],
    )

    assert [m["role"] for m in context] == ["user", "assistant", "tool", "user"]
    assert [item["type"] for item in payloads["input"]] == [
        "message",
        "function_call",
        "function_call_output",
        "message",
    ]


@pytest.mark.asyncio
async def test_responses_real_tool_calls_result_not_reordered_and_no_marker_leak():
    """经 ToolCallsResult 进入的真实工具结果带标记，不被重排，且标记不泄漏到 input。"""
    from astrbot.core.agent.message import (
        AssistantMessageSegment,
        ToolCallMessageSegment,
    )
    from astrbot.core.provider.entities import ToolCallsResult

    provider = _make_provider()
    tcr = ToolCallsResult(
        tool_calls_info=AssistantMessageSegment(
            content=None,
            tool_calls=[
                {
                    "id": "real_call_01",
                    "type": "function",
                    "function": {"name": "search_web", "arguments": "{}"},
                }
            ],
        ),
        tool_calls_result=[
            ToolCallMessageSegment(content="real result", tool_call_id="real_call_01")
        ],
    )
    payloads, context = await provider._prepare_chat_payload(
        prompt="请根据图片分析结果继续",
        contexts=[{"role": "user", "content": "帮我查一下"}],
        tool_calls_result=tcr,
    )

    # tool_calls_result 追加在 prompt 之后，尾部是 tool 消息，重排天然 no-op
    assert [m["role"] for m in context] == ["user", "user", "assistant", "tool"]
    assert [item["type"] for item in payloads["input"]] == [
        "message",
        "message",
        "function_call",
        "function_call_output",
    ]
    for item in payloads["input"]:
        assert "_from_real_tool_call" not in item


@pytest.mark.asyncio
async def test_responses_mixed_real_and_fake_only_fake_reordered():
    """真实对（标记）与伪造对（无标记）并存时，只重排尾部伪造对。"""
    provider = _make_provider()
    payloads, context = await provider._prepare_chat_payload(
        prompt="尾部问题",
        contexts=[
            {"role": "user", "content": "开始"},
            *make_fake_pair(
                tool_call_id="real_call_01", content="real result", marked=True
            ),
            {"role": "user", "content": "中间补充"},
            *make_fake_pair(tool_call_id="fake_call_02"),
        ],
    )

    assert [m["role"] for m in context] == [
        "user",
        "assistant",
        "tool",
        "user",
        "user",
        "assistant",
        "tool",
    ]
    assert [item["type"] for item in payloads["input"]] == [
        "message",
        "function_call",
        "function_call_output",
        "message",
        "message",
        "function_call",
        "function_call_output",
    ]
    # 真实对的 call_id 在重排后仍紧跟其 function_call
    assert payloads["input"][1]["call_id"] == "real_call_01"
    assert payloads["input"][2]["call_id"] == "real_call_01"
