import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
async def test_gemini_37_minimal_thinking_level_falls_back_to_medium():
    model = "gemini-3.7-flash"
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {"gm_thinking_config": {"level": "MINIMAL"}}
    provider.provider_settings = {}
    provider.model_name = model
    provider.safety_settings = []

    config = await provider._prepare_query_config({"model": model})

    assert config.thinking_config is not None
    assert config.thinking_config.model_dump(exclude_none=True) == {
        "thinking_level": types.ThinkingLevel.MEDIUM,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("naming", ["openai", "snake", "camel", "default", "zero"])
async def test_gemini_generation_parameters_reach_sdk(streaming, naming):
    parameters = {
        "temperature": 1.0,
        "max_output_tokens": 2048,
        "top_p": 0.9,
        "top_k": 40,
        "seed": 7,
        "frequency_penalty": 0.5,
        "presence_penalty": 0.5,
        "stop_sequences": ["END"],
        "logprobs": 3,
        "response_logprobs": True,
    }
    extra_body = parameters.copy()
    if naming == "openai":
        extra_body["max_tokens"] = extra_body.pop("max_output_tokens")
        extra_body["stop"] = extra_body.pop("stop_sequences")
    elif naming == "camel":
        extra_body = {
            "temperature": 1.0,
            "maxOutputTokens": 2048,
            "topP": 0.9,
            "topK": 40,
            "seed": 7,
            "frequencyPenalty": 0.5,
            "presencePenalty": 0.5,
            "stopSequences": ["END"],
            "logprobs": 3,
            "responseLogprobs": True,
        }
    elif naming == "default":
        extra_body = {}
        parameters = dict.fromkeys(parameters)
    elif naming == "zero":
        extra_body.update(
            temperature=0,
            top_p=0,
            top_k=0,
            seed=0,
            frequency_penalty=0,
            presence_penalty=0,
            response_logprobs=False,
        )
        parameters = extra_body.copy()

    provider = _gemini_stream_provider()
    provider.api_keys = ["test-key"]
    provider.provider_config = {"custom_extra_body": extra_body}
    original_body = extra_body.copy()
    response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(parts=[types.Part(text="ok")]),
                finish_reason=types.FinishReason.STOP,
            )
        ]
    )

    async def stream():
        yield response

    sdk_request = AsyncMock(return_value=stream() if streaming else response)
    if streaming:
        provider.client.models.generate_content_stream = sdk_request
        results = [
            result
            async for result in provider.text_chat_stream(
                prompt="hello", system_prompt="system", model="gemini-2.5-flash"
            )
        ]
        result = results[-1]
    else:
        provider.client.models.generate_content = sdk_request
        result = await provider.text_chat(
            prompt="hello", system_prompt="system", model="gemini-2.5-flash"
        )

    assert result.completion_text == "ok"
    sdk_request.assert_awaited_once()
    request = sdk_request.call_args.kwargs
    config = request["config"]
    for field, value in parameters.items():
        assert getattr(config, field) == value
    assert config.system_instruction == "system"
    assert request["model"] == "gemini-2.5-flash"
    assert request["contents"][0].parts[0].text == "hello"
    assert extra_body == original_body


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_gemini_generation_parameters_match_http_api(streaming):
    provider = _gemini_stream_provider()
    provider.api_keys = ["test-key"]
    provider.provider_config = {
        "custom_extra_body": {
            "temperature": 0,
            "max_tokens": 2048,
            "top_p": 0,
            "top_k": 40,
            "seed": 0,
            "frequency_penalty": 0,
            "presence_penalty": 0,
            "stop": ["END"],
            "response_logprobs": False,
            "logprobs": 3,
        }
    }
    requests = []

    def handle_request(request):
        requests.append(request)
        response = {
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"text": "ok"}]},
                    "finishReason": "STOP",
                }
            ]
        }
        if streaming:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=f"data: {json.dumps(response)}\n\n",
            )
        return httpx.Response(200, json=response)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as http_client:
        sdk = gemini_source.genai.Client(
            api_key="test-key",
            http_options=types.HttpOptions(httpx_async_client=http_client),
        )
        async with sdk.aio as provider.client:
            if streaming:
                results = [
                    result
                    async for result in provider.text_chat_stream(
                        prompt="hello", model="gemini-2.0-flash"
                    )
                ]
                result = results[-1]
            else:
                result = await provider.text_chat(
                    prompt="hello", model="gemini-2.0-flash"
                )

    assert result.completion_text == "ok"
    assert len(requests) == 1
    body = json.loads(requests[0].content)
    assert body["generationConfig"] == {
        "temperature": 0,
        "maxOutputTokens": 2048,
        "topP": 0,
        "topK": 40,
        "seed": 0,
        "frequencyPenalty": 0,
        "presencePenalty": 0,
        "stopSequences": ["END"],
        "responseLogprobs": False,
        "logprobs": 3,
        "responseModalities": ["TEXT"],
    }
    method = "streamGenerateContent" if streaming else "generateContent"
    assert requests[0].url.path.endswith(f"/models/gemini-2.0-flash:{method}")


@pytest.mark.asyncio
async def test_gemini_generation_alias_precedence_preserves_false_and_zero():
    provider = _gemini_stream_provider()
    provider.provider_config = {
        "custom_extra_body": {
            "top_p": 0,
            "topP": 0.9,
            "frequency_penalty": 0,
            "frequencyPenalty": 1,
            "presence_penalty": 0,
            "presencePenalty": 1,
            "response_logprobs": False,
            "responseLogprobs": True,
            "max_output_tokens": 100,
            "max_tokens": 200,
            "maxOutputTokens": 300,
            "stop_sequences": [],
            "stop": ["OPENAI"],
            "stopSequences": ["GEMINI"],
        }
    }
    config = await provider._prepare_query_config({})
    assert config.top_p == 0
    assert config.frequency_penalty == 0
    assert config.presence_penalty == 0
    assert config.response_logprobs is False
    assert config.max_output_tokens == 100
    assert config.stop_sequences == []

    config = await provider._prepare_query_config({"max_tokens": 400})
    assert config.max_output_tokens == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra_body, error",
    [
        ([], "must be a JSON object"),
        ({"temperature": "invalid"}, "temperature"),
        ({"unknown": 1}, "unknown"),
        ({"messages": []}, "messages"),
        ({"model": "another-model"}, "model"),
        ({"tools": []}, "tools"),
        ({"tool_choice": "required"}, "tool_choice"),
    ],
)
async def test_gemini_rejects_invalid_custom_parameters(extra_body, error):
    provider = _gemini_stream_provider()
    provider.provider_config = {"custom_extra_body": extra_body}
    with pytest.raises(ValueError, match=error):
        await provider._prepare_query_config({})


@pytest.mark.asyncio
@pytest.mark.parametrize("temperature", [None, 0, 1.0, 2.0])
@pytest.mark.parametrize("recovers", [False, True])
async def test_gemini_recitation_retries_are_bounded(temperature, recovers):
    provider = _gemini_stream_provider()
    provider.api_keys = ["test-key"]
    if temperature is not None:
        provider.provider_config = {"custom_extra_body": {"temperature": temperature}}
    recitation = types.GenerateContentResponse(
        candidates=[types.Candidate(finish_reason=types.FinishReason.RECITATION)]
    )
    success = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(parts=[types.Part(text="ok")]),
                finish_reason=types.FinishReason.STOP,
            )
        ]
    )
    sdk_request = AsyncMock(
        side_effect=[recitation, recitation, success if recovers else recitation]
    )
    provider.client.models.generate_content = sdk_request
    if recovers:
        result = await provider.text_chat(prompt="hello")
        assert result.completion_text == "ok"
    else:
        with pytest.raises(
            Exception, match="recitation still occurred after 2 retries"
        ):
            await provider.text_chat(prompt="hello")
    assert sdk_request.await_count == 3
    assert all(
        call.kwargs["config"].temperature == temperature
        for call in sdk_request.call_args_list
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_gemini_unsupported_generation_parameter_error_is_preserved(streaming):
    provider = _gemini_stream_provider()
    provider.api_keys = ["test-key"]
    provider.provider_config = {"custom_extra_body": {"top_k": 40}}
    error = APIError(400, {"error": {"message": "top_k is not supported"}})
    sdk_request = AsyncMock(side_effect=error)
    provider.client.models.generate_content = sdk_request
    provider.client.models.generate_content_stream = sdk_request
    with pytest.raises(APIError, match="top_k is not supported") as exc:
        if streaming:
            async for _ in provider.text_chat_stream(prompt="hello"):
                pass
        else:
            await provider.text_chat(prompt="hello")
    assert exc.value is error
    sdk_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_gemini_prepare_conversation_removes_leading_model_content():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    contents = await provider._prepare_conversation(
        {
            "messages": [
                {"role": "assistant", "content": "stale assistant turn"},
                {"role": "user", "content": "current user turn"},
            ]
        }
    )

    assert len(contents) == 1
    assert isinstance(contents[0], types.UserContent)
    assert contents[0].parts is not None
    assert contents[0].parts[-1].text == "current user turn"


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


def _gemini_part(*, text=None, thought=None, function_call=None):
    return SimpleNamespace(
        text=text,
        thought=thought,
        function_call=function_call,
        inline_data=None,
        thought_signature=None,
    )


def _gemini_stream_chunk(
    *,
    text=None,
    thought=None,
    function_call=None,
    finish_reason=None,
    response_id="resp-1",
):
    """Build a minimal stand-in for a google-genai streaming chunk."""
    parts = []
    if text is not None:
        parts.append(_gemini_part(text=text))
    if thought is not None:
        parts.append(_gemini_part(text=thought, thought=True))
    if function_call is not None:
        parts.append(_gemini_part(function_call=function_call))
    return SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(parts=parts),
                finish_reason=finish_reason,
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

    async def fake_retry(provider_name, request_factory, max_attempts=None):
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
