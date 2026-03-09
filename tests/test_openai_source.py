import asyncio
from types import SimpleNamespace

import pytest
from openai.types.responses.response import Response as OpenAIResponse

from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial


class _ErrorWithBody(Exception):
    def __init__(self, message: str, body: dict):
        super().__init__(message)
        self.body = body


class _ErrorWithResponse(Exception):
    def __init__(self, message: str, response_text: str):
        super().__init__(message)
        self.response = SimpleNamespace(text=response_text)


def _make_provider(overrides: dict | None = None) -> ProviderOpenAIOfficial:
    provider_config = {
        "id": "test-openai",
        "type": "openai_chat_completion",
        "model": "gpt-4o-mini",
        "key": ["test-key"],
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderOpenAIOfficial(
        provider_config=provider_config,
        provider_settings={},
    )


@pytest.mark.asyncio
async def test_handle_api_error_content_moderated_removes_images():
    provider = _make_provider(
        {"image_moderation_error_patterns": ["file:content-moderated"]}
    )
    try:
        payloads = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64,abcd"},
                        },
                    ],
                }
            ]
        }
        context_query = payloads["messages"]

        success, *_rest = await provider._handle_api_error(
            Exception("Content is moderated [WKE=file:content-moderated]"),
            payloads=payloads,
            context_query=context_query,
            func_tool=None,
            chosen_key="test-key",
            available_api_keys=["test-key"],
            retry_cnt=0,
            max_retries=10,
        )

        assert success is False
        updated_context = payloads["messages"]
        assert isinstance(updated_context, list)
        assert updated_context[0]["content"] == [{"type": "text", "text": "hello"}]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_handle_api_error_model_not_vlm_removes_images_and_retries_text_only():
    provider = _make_provider()
    try:
        payloads = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64,abcd"},
                        },
                    ],
                }
            ]
        }
        context_query = payloads["messages"]

        success, *_rest = await provider._handle_api_error(
            Exception("The model is not a VLM and cannot process images"),
            payloads=payloads,
            context_query=context_query,
            func_tool=None,
            chosen_key="test-key",
            available_api_keys=["test-key"],
            retry_cnt=0,
            max_retries=10,
        )

        assert success is False
        updated_context = payloads["messages"]
        assert isinstance(updated_context, list)
        assert updated_context[0]["content"] == [{"type": "text", "text": "hello"}]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_handle_api_error_model_not_vlm_after_fallback_raises():
    provider = _make_provider()
    try:
        payloads = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64,abcd"},
                        },
                    ],
                }
            ]
        }
        context_query = payloads["messages"]

        with pytest.raises(Exception, match="not a VLM"):
            await provider._handle_api_error(
                Exception("The model is not a VLM and cannot process images"),
                payloads=payloads,
                context_query=context_query,
                func_tool=None,
                chosen_key="test-key",
                available_api_keys=["test-key"],
                retry_cnt=1,
                max_retries=10,
                image_fallback_used=True,
            )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_handle_api_error_content_moderated_with_unserializable_body():
    provider = _make_provider({"image_moderation_error_patterns": ["blocked"]})
    try:
        payloads = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64,abcd"},
                        },
                    ],
                }
            ]
        }
        context_query = payloads["messages"]
        err = _ErrorWithBody(
            "upstream error",
            {"error": {"message": "blocked"}, "raw": object()},
        )

        success, *_rest = await provider._handle_api_error(
            err,
            payloads=payloads,
            context_query=context_query,
            func_tool=None,
            chosen_key="test-key",
            available_api_keys=["test-key"],
            retry_cnt=0,
            max_retries=10,
        )
        assert success is False
        assert payloads["messages"][0]["content"] == [{"type": "text", "text": "hello"}]
    finally:
        await provider.terminate()


def test_extract_error_text_candidates_truncates_long_response_text():
    long_text = "x" * 20000
    err = _ErrorWithResponse("upstream error", long_text)
    candidates = ProviderOpenAIOfficial._extract_error_text_candidates(err)
    assert candidates
    assert max(len(candidate) for candidate in candidates) <= (
        ProviderOpenAIOfficial._ERROR_TEXT_CANDIDATE_MAX_CHARS
    )


def test_build_responses_payload_converts_messages_and_tools():
    provider = _make_provider({"use_responses_api": True})
    try:
        payload = provider._build_responses_payload(
            {
                "model": "gpt-4.1-mini",
                "messages": [
                    {"role": "system", "content": "You are helpful."},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "look at this"},
                            {
                                "type": "image_url",
                                "image_url": {"url": "data:image/jpeg;base64,abcd"},
                            },
                        ],
                    },
                    {
                        "role": "assistant",
                        "content": "Calling a tool",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "weather",
                                    "arguments": '{"city":"Tokyo"}',
                                },
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "call_1",
                        "content": "sunny",
                    },
                ],
            },
            tools=SimpleNamespace(
                func_list=[
                    SimpleNamespace(
                        name="weather",
                        description="Get weather",
                        parameters={
                            "type": "object",
                            "properties": {
                                "city": {"type": "string"},
                            },
                        },
                    )
                ]
            ),
        )

        assert payload["model"] == "gpt-4.1-mini"
        assert payload["tools"][0]["type"] == "function"
        assert payload["tools"][0]["name"] == "weather"
        assert payload["input"][0]["role"] == "developer"
        assert payload["input"][1]["content"][0]["type"] == "input_text"
        assert payload["input"][1]["content"][1]["type"] == "input_image"
        assert payload["input"][2]["role"] == "assistant"
        assert payload["input"][3]["type"] == "function_call"
        assert payload["input"][4]["type"] == "function_call_output"
    finally:
        asyncio.run(provider.terminate())


def test_native_tools_force_responses_mode_and_override_function_tools():
    provider = _make_provider(
        {
            "oa_native_web_search": True,
            "oa_native_code_interpreter": True,
        }
    )
    try:
        payload = provider._build_responses_payload(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "search and calculate"}],
            },
            tools=SimpleNamespace(
                func_list=[
                    SimpleNamespace(
                        name="weather",
                        description="Get weather",
                        parameters={"type": "object", "properties": {}},
                    )
                ]
            ),
        )

        assert provider._should_use_responses_api() is True
        assert payload["tools"] == [
            {"type": "web_search"},
            {"type": "code_interpreter", "container": {"type": "auto"}},
        ]
    finally:
        asyncio.run(provider.terminate())


@pytest.mark.asyncio
async def test_parse_responses_completion_extracts_text_reasoning_and_tool_calls():
    provider = _make_provider({"use_responses_api": True})
    try:
        response = OpenAIResponse.model_validate(
            {
                "id": "resp_1",
                "object": "response",
                "created_at": 1,
                "model": "gpt-4.1-mini",
                "output": [
                    {
                        "id": "rs_1",
                        "type": "reasoning",
                        "summary": [],
                        "content": [{"type": "reasoning_text", "text": "thinking..."}],
                        "status": "completed",
                    },
                    {
                        "id": "msg_1",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Hello world",
                                "annotations": [],
                            }
                        ],
                    },
                    {
                        "id": "fc_1",
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "weather",
                        "arguments": '{"city":"Tokyo"}',
                        "status": "completed",
                    },
                ],
                "parallel_tool_calls": True,
                "tool_choice": "auto",
                "tools": [],
                "usage": {
                    "input_tokens": 12,
                    "input_tokens_details": {"cached_tokens": 2},
                    "output_tokens": 5,
                    "output_tokens_details": {"reasoning_tokens": 1},
                    "total_tokens": 17,
                },
            }
        )

        parsed = await provider._parse_responses_completion(
            response,
            tools=SimpleNamespace(func_list=[SimpleNamespace(name="weather")]),
        )

        assert parsed.completion_text == "Hello world"
        assert parsed.reasoning_content == "thinking..."
        assert parsed.role == "tool"
        assert parsed.tools_call_name == ["weather"]
        assert parsed.tools_call_args == [{"city": "Tokyo"}]
        assert parsed.tools_call_ids == ["call_1"]
        assert parsed.usage is not None
        assert parsed.usage.input_cached == 2
        assert parsed.usage.input_other == 10
        assert parsed.usage.output == 5
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_parse_responses_completion_raises_on_invalid_tool_arguments():
    provider = _make_provider({"use_responses_api": True})
    try:
        response = OpenAIResponse.model_validate(
            {
                "id": "resp_invalid_args",
                "object": "response",
                "created_at": 1,
                "model": "gpt-4.1-mini",
                "output": [
                    {
                        "id": "fc_1",
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "weather",
                        "arguments": '{"city":"Tokyo"',
                        "status": "completed",
                    }
                ],
                "parallel_tool_calls": False,
                "tool_choice": "auto",
                "tools": [],
            }
        )

        with pytest.raises(Exception, match="not valid JSON"):
            await provider._parse_responses_completion(
                response,
                tools=SimpleNamespace(func_list=[SimpleNamespace(name="weather")]),
            )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_parse_responses_completion_handles_missing_input_token_details():
    provider = _make_provider({"use_responses_api": True})
    try:
        usage = SimpleNamespace(
            input_tokens=12,
            input_tokens_details=None,
            output_tokens=5,
        )

        parsed = provider._extract_responses_usage(usage)

        assert parsed.input_cached == 0
        assert parsed.input_other == 12
        assert parsed.output == 5
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_query_stream_responses_yields_distinct_text_and_reasoning_chunks():
    provider = _make_provider({"use_responses_api": True})

    class _FakeStream:
        def __init__(self, events):
            self._events = iter(events)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._events)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    final_response = OpenAIResponse.model_validate(
        {
            "id": "resp_stream",
            "object": "response",
            "created_at": 1,
            "model": "gpt-4.1-mini",
            "output": [
                {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Hello",
                            "annotations": [],
                        }
                    ],
                }
            ],
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
        }
    )

    events = [
        SimpleNamespace(type="response.output_text.delta", delta="Hel"),
        SimpleNamespace(type="response.reasoning_text.delta", delta="thinking"),
        SimpleNamespace(
            type="response.completed",
            response=final_response,
        ),
    ]

    async def _fake_create(**kwargs):
        assert kwargs["stream"] is True
        return _FakeStream(events)

    provider.client.responses.create = _fake_create

    try:
        chunks = []
        async for item in provider._query_stream_responses(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hello"}],
            },
            tools=None,
        ):
            chunks.append(item)

        assert len(chunks) == 3
        assert chunks[0].is_chunk is True
        assert chunks[0].completion_text == "Hel"
        assert chunks[0].reasoning_content == ""
        assert chunks[1].is_chunk is True
        assert chunks[1].completion_text == ""
        assert chunks[1].reasoning_content == "thinking"
        assert chunks[2].is_chunk is False
        assert chunks[2].completion_text == "Hello"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_handle_api_error_content_moderated_without_images_raises():
    provider = _make_provider(
        {"image_moderation_error_patterns": ["file:content-moderated"]}
    )
    try:
        payloads = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "hello"}],
                }
            ]
        }
        context_query = payloads["messages"]
        err = Exception("Content is moderated [WKE=file:content-moderated]")

        with pytest.raises(Exception, match="content-moderated"):
            await provider._handle_api_error(
                err,
                payloads=payloads,
                context_query=context_query,
                func_tool=None,
                chosen_key="test-key",
                available_api_keys=["test-key"],
                retry_cnt=0,
                max_retries=10,
            )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_handle_api_error_content_moderated_detects_structured_body():
    provider = _make_provider(
        {"image_moderation_error_patterns": ["content_moderated"]}
    )
    try:
        payloads = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64,abcd"},
                        },
                    ],
                }
            ]
        }
        context_query = payloads["messages"]
        err = _ErrorWithBody(
            "upstream error",
            {"error": {"code": "content_moderated", "message": "blocked"}},
        )

        success, *_rest = await provider._handle_api_error(
            err,
            payloads=payloads,
            context_query=context_query,
            func_tool=None,
            chosen_key="test-key",
            available_api_keys=["test-key"],
            retry_cnt=0,
            max_retries=10,
        )
        assert success is False
        assert payloads["messages"][0]["content"] == [{"type": "text", "text": "hello"}]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_handle_api_error_content_moderated_supports_custom_patterns():
    provider = _make_provider(
        {"image_moderation_error_patterns": ["blocked_by_policy_code_123"]}
    )
    try:
        payloads = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64,abcd"},
                        },
                    ],
                }
            ]
        }
        context_query = payloads["messages"]
        err = Exception("upstream: blocked_by_policy_code_123")

        success, *_rest = await provider._handle_api_error(
            err,
            payloads=payloads,
            context_query=context_query,
            func_tool=None,
            chosen_key="test-key",
            available_api_keys=["test-key"],
            retry_cnt=0,
            max_retries=10,
        )
        assert success is False
        assert payloads["messages"][0]["content"] == [{"type": "text", "text": "hello"}]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_handle_api_error_content_moderated_without_patterns_raises():
    provider = _make_provider()
    try:
        payloads = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64,abcd"},
                        },
                    ],
                }
            ]
        }
        context_query = payloads["messages"]
        err = Exception("Content is moderated [WKE=file:content-moderated]")

        with pytest.raises(Exception, match="content-moderated"):
            await provider._handle_api_error(
                err,
                payloads=payloads,
                context_query=context_query,
                func_tool=None,
                chosen_key="test-key",
                available_api_keys=["test-key"],
                retry_cnt=0,
                max_retries=10,
            )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_handle_api_error_unknown_image_error_raises():
    provider = _make_provider()
    try:
        payloads = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64,abcd"},
                        },
                    ],
                }
            ]
        }
        context_query = payloads["messages"]

        with pytest.raises(Exception, match="unknown provider image upload error"):
            await provider._handle_api_error(
                Exception("some unknown provider image upload error"),
                payloads=payloads,
                context_query=context_query,
                func_tool=None,
                chosen_key="test-key",
                available_api_keys=["test-key"],
                retry_cnt=0,
                max_retries=10,
            )
    finally:
        await provider.terminate()
