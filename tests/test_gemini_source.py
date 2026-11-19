from types import SimpleNamespace

import httpx
import pytest
from google.genai import types
from google.genai.errors import APIError

import astrbot.core.message.components as Comp
import astrbot.core.provider.sources.gemini_source as gemini_source
import astrbot.core.provider.sources.request_retry as request_retry
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI


def _make_function_call_candidate(*function_calls):
    return types.Candidate(
        content=types.Content(
            parts=[
                types.Part(function_call=types.FunctionCall(**function_call))
                for function_call in function_calls
            ]
        )
    )


@pytest.mark.asyncio
async def test_gemini_thinking_level_is_serialized_on_every_request():
    model = "gemini-3.7-flash"
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {"gm_thinking_config": {"level": "HIGH"}}
    provider.provider_settings = {}
    provider.model_name = model
    provider.safety_settings = []

    first_config = await provider._prepare_query_config({"model": model})
    second_config = await provider._prepare_query_config({"model": model})

    assert first_config.thinking_config is not None
    assert second_config.thinking_config is not None
    assert first_config.thinking_config.model_dump(exclude_none=True) == {
        "thinking_level": types.ThinkingLevel.HIGH,
    }
    assert second_config.thinking_config.model_dump(exclude_none=True) == {
        "thinking_level": types.ThinkingLevel.HIGH,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "provider_config"),
    [
        ("gemini-4-argon", {}),
        ("gemini-4-argon", {"gm_thinking_config": {"level": "HIGH"}}),
        (
            "gemini-4-argon",
            {
                "gm_thinking_config": {"level": "HIGH"},
                "custom_extra_body": {"reasoning_effort": "auto"},
            },
        ),
        ("gemini-4-argon", {"custom_extra_body": {"reasoning_effort": "xhigh"}}),
        ("gemini-3.8-flash", {"gm_thinking_config": {"level": "MINIMAL"}}),
    ],
)
async def test_gemini_omits_unset_or_unsupported_thinking_config(model, provider_config):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = provider_config
    provider.provider_settings = {}
    provider.model_name = "gemini-2.5-flash"
    provider.safety_settings = []

    config = await provider._prepare_query_config({"model": model})

    assert "thinking_config" not in config.model_dump(exclude_none=True)


@pytest.mark.asyncio
async def test_gemini_prepare_conversation_keeps_normal_user_first_history():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    contents = await provider._prepare_conversation(
        {
            "messages": [
                {"role": "user", "content": "first user turn"},
                {"role": "assistant", "content": "assistant turn"},
                {"role": "user", "content": "current user turn"},
            ]
        }
    )

    assert [type(content) for content in contents] == [
        types.UserContent,
        types.ModelContent,
        types.UserContent,
    ]
    assert contents[-1].parts is not None
    assert contents[-1].parts[-1].text == "current user turn"


@pytest.mark.asyncio
async def test_gemini_prepare_conversation_preserves_user_model_history():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    contents = await provider._prepare_conversation(
        {
            "messages": [
                {"role": "user", "content": "user turn"},
                {"role": "assistant", "content": "assistant turn"},
            ]
        }
    )

    assert [type(content) for content in contents] == [
        types.UserContent,
        types.ModelContent,
    ]
    assert contents[-1].parts is not None
    assert contents[-1].parts[-1].text == "assistant turn"


@pytest.mark.asyncio
async def test_gemini_prepare_conversation_resolves_local_history_image(tmp_path):
    image_path = tmp_path / "history.webp"
    image_bytes = (
        b"RIFF\x16\x00\x00\x00WEBPVP8L\x0a\x00\x00\x00"
        b"/\x00\x00\x00\x10\x07\x10\x11\x11\x88\x88\xfe\x07"
    )
    image_path.write_bytes(image_bytes)
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    contents = await provider._prepare_conversation(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "historical image"},
                        {
                            "type": "image_url",
                            "image_url": {"url": str(image_path)},
                        },
                    ],
                }
            ]
        }
    )

    assert contents[0].parts is not None
    image_part = contents[0].parts[1]
    assert image_part.inline_data is not None
    assert image_part.inline_data.mime_type == "image/webp"
    assert image_part.inline_data.data == image_bytes


@pytest.mark.asyncio
async def test_gemini_prepare_conversation_resolves_url_history_audio(monkeypatch):
    audio_url = "https://example.com/history.mp3"

    async def fake_resolve_media_ref(media_ref, *, media_type, strict):
        assert media_ref == audio_url
        assert media_type == "audio"
        assert strict is True
        return SimpleNamespace(base64_data="YXVkaW8=", mime_type="audio/mpeg")

    monkeypatch.setattr(
        gemini_source,
        "resolve_media_ref_to_base64_data",
        fake_resolve_media_ref,
    )
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    contents = await provider._prepare_conversation(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "[Audio]"},
                        {"type": "audio_url", "audio_url": {"url": audio_url}},
                    ],
                },
                {"role": "assistant", "content": "Received."},
                {"role": "user", "content": "Reply in text."},
            ]
        }
    )

    assert contents[0].parts is not None
    audio_part = contents[0].parts[1]
    assert audio_part.inline_data is not None
    assert audio_part.inline_data.mime_type == "audio/mpeg"
    assert audio_part.inline_data.data == b"audio"
    assert contents[-1].parts is not None
    assert contents[-1].parts[-1].text == "Reply in text."


def test_gemini_empty_output_raises_empty_model_output_error():
    llm_response = LLMResponse(role="assistant")

    with pytest.raises(EmptyModelOutputError):
        ProviderGoogleGenAI._ensure_usable_response(
            llm_response,
            response_id="resp_empty",
            finish_reason="STOP",
        )


def test_gemini_reasoning_only_output_is_allowed():
    llm_response = LLMResponse(
        role="assistant",
        reasoning_content="chain of thought placeholder",
    )

    ProviderGoogleGenAI._ensure_usable_response(
        llm_response,
        response_id="resp_reasoning",
        finish_reason="STOP",
    )


def test_gemini_extract_usage_excludes_cached_tokens_from_input_other():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    usage_metadata = SimpleNamespace(
        prompt_token_count=100,
        cached_content_token_count=30,
        candidates_token_count=50,
    )

    usage = provider._extract_usage(usage_metadata)

    # prompt_token_count already includes cached tokens; input_other must
    # exclude them so input (input_other + input_cached) is not inflated.
    assert usage.input_other == 70
    assert usage.input_cached == 30
    assert usage.input == 100
    assert usage.output == 50


def test_gemini_extract_usage_without_cache_keeps_full_prompt_tokens():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    usage_metadata = SimpleNamespace(
        prompt_token_count=100,
        cached_content_token_count=0,
        candidates_token_count=20,
    )

    usage = provider._extract_usage(usage_metadata)

    assert usage.input_other == 100
    assert usage.input_cached == 0
    assert usage.input == 100
    assert usage.output == 20


@pytest.mark.asyncio
async def test_gemini_get_models_retries_transient_request_error(monkeypatch):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)

    class FakeModels:
        def __init__(self):
            self.calls = 0

        async def list(self):
            self.calls += 1
            if self.calls == 1:
                raise httpx.ConnectError("temporary connection failure")
            return [
                SimpleNamespace(
                    name="models/gemini-a",
                    supported_actions=["generateContent"],
                ),
                SimpleNamespace(
                    name="models/gemini-b",
                    supported_actions=["embedContent"],
                ),
            ]

    models = FakeModels()
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.client = SimpleNamespace(models=models)

    assert await provider.get_models() == ["gemini-a"]
    assert models.calls == 2


def _gemini_stream_chunk(
    *,
    text=None,
    thought=None,
    function_call=None,
    finish_reason=None,
    response_id="resp-1",
):
    """Build a streaming chunk with Google SDK candidate and part types."""
    parts = []
    if text is not None:
        parts.append(types.Part(text=text))
    if thought is not None:
        parts.append(types.Part(text=thought, thought=True))
    if function_call is not None:
        parts.append(
            types.Part(
                function_call=types.FunctionCall(
                    name=function_call.name,
                    args=function_call.args,
                    id=function_call.id,
                )
            )
        )
    return SimpleNamespace(
        candidates=[
            types.Candidate(
                content=types.Content(parts=parts), finish_reason=finish_reason
            )
        ],
        text=text,
        response_id=response_id,
        usage_metadata=None,
    )


def _gemini_stream_provider():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.provider_settings = {}
    provider.model_name = "gemini-3.7-flash"
    provider.safety_settings = []
    provider.client = SimpleNamespace(
        models=SimpleNamespace(generate_content_stream=lambda **kwargs: None)
    )
    return provider


async def _drain_gemini_stream(provider, monkeypatch, chunks):
    async def fake_stream():
        for chunk in chunks:
            yield chunk

    async def fake_retry(
        provider_name,
        request_factory,
        max_attempts=None,
    ):
        return fake_stream()

    monkeypatch.setattr(gemini_source, "retry_provider_request", fake_retry)
    return [
        response
        async for response in provider._query_stream(
            payloads={
                "messages": [{"role": "user", "content": "what's the weather?"}],
                "model": "gemini-3.7-flash",
            },
            tools=None,
        )
    ]


@pytest.mark.asyncio
async def test_gemini_stream_keeps_narration_emitted_before_tool_call(monkeypatch):
    """Narration streamed before a tool call must reach the final response.

    Regression test for the tool-call branch that used to build the final
    LLMResponse from the tool-call chunk alone and return immediately, leaving
    text the user had already seen out of the conversation history.
    """
    provider = _gemini_stream_provider()
    tool_call = SimpleNamespace(
        name="get_weather",
        args={"city": "Shenyang"},
        id="call-1",
        thought_signature=None,
    )

    responses = await _drain_gemini_stream(
        provider,
        monkeypatch,
        [
            _gemini_stream_chunk(text="Sure, let me check that for you."),
            _gemini_stream_chunk(function_call=tool_call),
        ],
    )

    final = responses[-1]
    assert final.is_chunk is False
    assert final.tools_call_name == ["get_weather"]
    plain_text = "".join(
        part.text
        for part in (final.result_chain.chain or [])
        if isinstance(part, Comp.Plain)
    )
    assert "Sure, let me check that for you." in plain_text


@pytest.mark.asyncio
async def test_gemini_stream_keeps_conversation_header_until_consumed(
    monkeypatch,
):
    """The conversation header must be present while the stream is consumed."""
    provider = _gemini_stream_provider()
    headers: dict[str, str] = {}
    provider.client._api_client = SimpleNamespace(
        _http_options=SimpleNamespace(headers=headers),
    )
    observed_headers: list[str | None] = []

    async def fake_stream():
        observed_headers.append(headers.get("x-astrbot-conversation-id"))
        yield _gemini_stream_chunk(text="ok")

    async def fake_retry(provider_name, request_factory, max_attempts=None):
        return fake_stream()

    monkeypatch.setattr(gemini_source, "retry_provider_request", fake_retry)
    responses = [
        response
        async for response in provider._query_stream(
            payloads={
                "messages": [{"role": "user", "content": "hello"}],
                "model": "gemini-3.7-flash",
            },
            tools=None,
            conversation_id="conversation-1",
        )
    ]

    assert responses[-1].completion_text == "ok"
    assert observed_headers == ["conversation-1"]
    assert "x-astrbot-conversation-id" not in headers


@pytest.mark.asyncio
async def test_gemini_stream_keeps_reasoning_from_tool_call_chunk(monkeypatch):
    """Reasoning on the tool-call chunk itself must not be overwritten."""
    provider = _gemini_stream_provider()
    tool_call = SimpleNamespace(
        name="get_weather",
        args={"city": "Shenyang"},
        id="call-1",
        thought_signature=None,
    )

    responses = await _drain_gemini_stream(
        provider,
        monkeypatch,
        [
            _gemini_stream_chunk(thought="weighing options"),
            _gemini_stream_chunk(function_call=tool_call, thought="deciding to call"),
        ],
    )

    final = responses[-1]
    assert final.reasoning_content == "weighing optionsdeciding to call"


@pytest.mark.asyncio
async def test_gemini_prepare_conversation_preserves_tool_call_ids_and_responses():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    contents = await provider._prepare_conversation(
        {
            "messages": [
                {"role": "user", "content": "start"},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_same_id",
                            "function": {"name": "first_tool", "arguments": "{}"},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_same_id",
                    "name": "stale_name",
                    "content": "first result",
                },
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_same_id",
                            "function": {"name": "second_tool", "arguments": "{}"},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_same_id",
                    "name": "stale_name",
                    "content": "second result",
                },
                {"role": "user", "content": "continue"},
            ]
        }
    )

    first_call = contents[1].parts[0].function_call
    first_response = contents[2].parts[0].function_response
    second_call = contents[3].parts[0].function_call
    second_response = contents[4].parts[0].function_response
    assert first_call.id == "call_same_id"
    assert first_response.id == "call_same_id"
    assert first_response.name == "first_tool"
    assert second_call.id == "call_same_id"
    assert second_response.id == "call_same_id"
    assert second_response.name == "second_tool"


def test_gemini_missing_tool_call_ids_are_unique_and_request_scoped():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    candidate = _make_function_call_candidate(
        {"name": "publish", "args": {"status": "draft"}},
        {"name": "publish", "args": {"status": "draft"}},
    )

    response = LLMResponse("assistant")
    provider._process_content_parts(candidate, response, tool_call_scope="request-1")
    replay = LLMResponse("assistant")
    provider._process_content_parts(candidate, replay, tool_call_scope="request-1")
    next_response = LLMResponse("assistant")
    provider._process_content_parts(
        candidate, next_response, tool_call_scope="request-2"
    )
    fallback_response = LLMResponse("assistant")
    provider._process_content_parts(candidate, fallback_response)
    next_fallback_response = LLMResponse("assistant")
    provider._process_content_parts(candidate, next_fallback_response)

    assert len(set(response.tools_call_ids)) == 2
    assert all(
        call_id.startswith("gemini_call_") for call_id in response.tools_call_ids
    )
    assert replay.tools_call_ids == response.tools_call_ids
    assert set(next_response.tools_call_ids).isdisjoint(response.tools_call_ids)
    assert set(next_fallback_response.tools_call_ids).isdisjoint(
        fallback_response.tools_call_ids
    )


def test_gemini_explicit_tool_call_scope_wins_over_response_id():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    candidate = _make_function_call_candidate({"name": "publish", "args": {}})

    first = LLMResponse("assistant")
    provider._process_content_parts(
        candidate,
        first,
        response_id="provider-response-1",
        tool_call_scope="replayed-request",
    )
    second = LLMResponse("assistant")
    provider._process_content_parts(
        candidate,
        second,
        response_id="provider-response-2",
        tool_call_scope="replayed-request",
    )

    assert first.tools_call_ids == second.tools_call_ids


@pytest.mark.asyncio
async def test_gemini_non_streaming_retries_reuse_tool_call_scope(monkeypatch):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.api_keys = ["key-1", "key-2"]
    scopes = []

    async def fake_query(
        payloads,
        tools,
        *,
        request_max_retries=None,
        tool_call_scope=None,
    ):
        scopes.append(tool_call_scope)
        if len(scopes) == 1:
            raise APIError(503, {"error": {"message": "temporary failure"}})
        return LLMResponse("assistant")

    async def fake_handle_api_error(error, keys):
        return len(scopes) == 1

    monkeypatch.setattr(provider, "_query", fake_query)
    monkeypatch.setattr(provider, "_handle_api_error", fake_handle_api_error)

    await provider.text_chat(model="gemini-test", contexts=[])

    assert len(scopes) == 2
    assert scopes[0]
    assert scopes[0] == scopes[1]


def test_gemini_preserves_provider_tool_call_ids_and_thought_signatures():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    candidate = types.Candidate(
        content=types.Content(
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        id="provider-call-id",
                        name="publish",
                        args={"status": "draft"},
                    ),
                    thought_signature=b"signed-call",
                )
            ]
        )
    )
    response = LLMResponse("assistant")

    provider._process_content_parts(
        candidate,
        response,
        response_id="provider-response",
    )

    assert response.tools_call_ids == ["provider-call-id"]
    assert response.tools_call_extra_content == {
        "provider-call-id": {"google": {"thought_signature": "c2lnbmVkLWNhbGw="}}
    }


@pytest.mark.asyncio
async def test_gemini_non_streaming_requests_get_distinct_fallback_tool_ids(
    monkeypatch,
):
    import astrbot.core.provider.sources.gemini_source as gemini_source

    candidate = _make_function_call_candidate(
        {"name": "publish", "args": {"status": "draft"}},
        {"name": "publish", "args": {"status": "draft"}},
    )
    result = types.GenerateContentResponse(
        candidates=[candidate],
        response_id=None,
    )

    class FakeModels:
        async def generate_content(self, **kwargs):
            return result

    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.model_name = "gemini-test"
    provider.client = SimpleNamespace(models=FakeModels())

    async def fake_prepare_conversation(payloads):
        return []

    async def fake_prepare_query_config(*args, **kwargs):
        return None

    monkeypatch.setattr(provider, "_prepare_conversation", fake_prepare_conversation)
    monkeypatch.setattr(provider, "_prepare_query_config", fake_prepare_query_config)

    async def run_request(provider_name, request_factory, **kwargs):
        return await request_factory()

    monkeypatch.setattr(gemini_source, "retry_provider_request", run_request)
    payloads = {"messages": [], "model": "gemini-test"}
    first_response = await provider._query(payloads, tools=None)
    second_response = await provider._query(payloads, tools=None)
    replay_response = await provider._query(
        payloads,
        tools=None,
        tool_call_scope="replayed-invocation",
    )
    replay_response_again = await provider._query(
        payloads,
        tools=None,
        tool_call_scope="replayed-invocation",
    )

    assert first_response.id is None
    assert second_response.id is None
    assert set(first_response.tools_call_ids).isdisjoint(second_response.tools_call_ids)
    assert replay_response.tools_call_ids == replay_response_again.tools_call_ids


@pytest.mark.asyncio
async def test_gemini_streaming_requests_generate_tool_call_ids_without_response_id(
    monkeypatch,
):
    import astrbot.core.provider.sources.gemini_source as gemini_source

    candidate = _make_function_call_candidate(
        {"name": "publish", "args": {"status": "draft"}},
        {"name": "publish", "args": {"status": "draft"}},
    )
    chunk = types.GenerateContentResponse(
        candidates=[candidate],
        response_id=None,
    )

    class FakeModels:
        async def generate_content_stream(self, **kwargs):
            async def chunks():
                yield chunk

            return chunks()

    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.model_name = "gemini-test"
    provider.client = SimpleNamespace(models=FakeModels())

    async def fake_prepare_conversation(payloads):
        return []

    async def fake_prepare_query_config(*args, **kwargs):
        return None

    monkeypatch.setattr(provider, "_prepare_conversation", fake_prepare_conversation)
    monkeypatch.setattr(provider, "_prepare_query_config", fake_prepare_query_config)

    async def run_request(provider_name, request_factory, **kwargs):
        return await request_factory()

    monkeypatch.setattr(gemini_source, "retry_provider_request", run_request)
    payloads = {"messages": [], "model": "gemini-test"}
    first_responses = [
        response async for response in provider._query_stream(payloads, None)
    ]
    second_responses = [
        response async for response in provider._query_stream(payloads, None)
    ]
    replay_responses = [
        response
        async for response in provider._query_stream(
            payloads,
            None,
            tool_call_scope="replayed-stream-invocation",
        )
    ]
    replay_responses_again = [
        response
        async for response in provider._query_stream(
            payloads,
            None,
            tool_call_scope="replayed-stream-invocation",
        )
    ]

    assert len(first_responses) == 1
    assert len(second_responses) == 1
    assert first_responses[0].id is None
    assert len(set(first_responses[0].tools_call_ids)) == 2
    assert set(first_responses[0].tools_call_ids).isdisjoint(
        second_responses[0].tools_call_ids
    )
    assert (
        replay_responses[0].tools_call_ids == replay_responses_again[0].tools_call_ids
    )


@pytest.mark.asyncio
async def test_gemini_streaming_retries_reuse_tool_call_scope(monkeypatch):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.api_keys = ["key-1", "key-2"]
    scopes = []

    async def fake_query_stream(
        payloads,
        tools,
        *,
        request_max_retries=None,
        tool_call_scope=None,
    ):
        scopes.append(tool_call_scope)
        if len(scopes) == 1:
            raise APIError(503, {"error": {"message": "temporary failure"}})
        yield LLMResponse("assistant")

    async def fake_handle_api_error(error, keys):
        return len(scopes) == 1

    monkeypatch.setattr(provider, "_query_stream", fake_query_stream)
    monkeypatch.setattr(provider, "_handle_api_error", fake_handle_api_error)

    responses = [
        response
        async for response in provider.text_chat_stream(
            model="gemini-test",
            contexts=[],
        )
    ]

    assert len(responses) == 1
    assert len(scopes) == 2
    assert scopes[0]
    assert scopes[0] == scopes[1]


@pytest.mark.asyncio
async def test_gemini_streaming_collects_tool_calls_across_chunks(monkeypatch):
    import astrbot.core.provider.sources.gemini_source as gemini_source

    chunks = [
        types.GenerateContentResponse(
            response_id="stream-response",
            candidates=[
                types.Candidate(
                    content=types.Content(
                        parts=[
                            types.Part(text="Preparing"),
                            types.Part(text="Plan", thought=True),
                        ]
                    )
                )
            ],
        ),
        types.GenerateContentResponse(
            response_id="stream-response",
            candidates=[
                types.Candidate(
                    content=types.Content(
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(
                                    name="lookup", args={"item": 1}
                                ),
                                thought_signature=b"first-signature",
                            )
                        ]
                    )
                )
            ],
        ),
        types.GenerateContentResponse(
            response_id="stream-response",
            candidates=[
                types.Candidate(
                    content=types.Content(
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(
                                    name="lookup", args={"item": 2}
                                ),
                                thought_signature=b"second-signature",
                            )
                        ]
                    ),
                    finish_reason=types.FinishReason.STOP,
                )
            ],
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=10, candidates_token_count=5
            ),
        ),
    ]

    class FakeModels:
        async def generate_content_stream(self, **kwargs):
            async def responses():
                for chunk in chunks:
                    yield chunk

            return responses()

    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.model_name = "gemini-test"
    provider.client = SimpleNamespace(models=FakeModels())

    async def fake_prepare_conversation(payloads):
        return []

    async def fake_prepare_query_config(*args, **kwargs):
        return None

    async def run_request(provider_name, request_factory, **kwargs):
        return await request_factory()

    monkeypatch.setattr(provider, "_prepare_conversation", fake_prepare_conversation)
    monkeypatch.setattr(provider, "_prepare_query_config", fake_prepare_query_config)
    monkeypatch.setattr(gemini_source, "retry_provider_request", run_request)

    responses = [
        response async for response in provider._query_stream({"messages": []}, None)
    ]

    final = responses[-1]
    assert [response.is_chunk for response in responses] == [True, False]
    assert final.tools_call_name == ["lookup", "lookup"]
    assert final.tools_call_args == [{"item": 1}, {"item": 2}]
    assert len(set(final.tools_call_ids)) == 2
    assert final.completion_text == "Preparing"
    assert final.reasoning_content == "Plan"
    assert final.usage.total == 15
    assert set(final.tools_call_extra_content) == set(final.tools_call_ids)
    assert (
        final.tools_call_extra_content[final.tools_call_ids[0]]["google"][
            "thought_signature"
        ]
        == "Zmlyc3Qtc2lnbmF0dXJl"
    )
    assert (
        final.tools_call_extra_content[final.tools_call_ids[1]]["google"][
            "thought_signature"
        ]
        == "c2Vjb25kLXNpZ25hdHVyZQ=="
    )
