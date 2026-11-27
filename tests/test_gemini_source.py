from types import SimpleNamespace

import httpx
import pytest
from google.genai import types

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
async def test_gemini_omits_unset_or_unsupported_thinking_config(
    model, provider_config
):
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


def test_gemini_extract_usage_counts_thoughts_and_tool_input_without_double_counting_cache():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    usage_metadata = SimpleNamespace(
        prompt_token_count=100,
        cached_content_token_count=30,
        candidates_token_count=50,
        thoughts_token_count=8,
        tool_use_prompt_token_count=2,
    )

    usage = provider._extract_usage(usage_metadata)

    # Prompt tokens include cache reads; tool prompts are reported separately.
    assert usage.input_other == 72
    assert usage.input_cached == 30
    assert usage.input == 102
    assert usage.output == 58


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
                grounding_metadata=None,
                url_context_metadata=None,
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

    async def generate_content_stream(**kwargs):
        return fake_stream()

    monkeypatch.setattr(
        provider.client.models, "generate_content_stream", generate_content_stream
    )
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

    async def generate_content_stream(**kwargs):
        return fake_stream()

    monkeypatch.setattr(
        provider.client.models, "generate_content_stream", generate_content_stream
    )
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
async def test_gemini_query_extracts_grounding_and_url_context_sources(monkeypatch):
    """Non-streaming responses expose deduplicated grounding and URL context sources."""
    provider = _gemini_stream_provider()
    candidate = types.Candidate(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text="AstrBot release summary")],
        ),
        finish_reason=types.FinishReason.STOP,
        grounding_metadata=types.GroundingMetadata(
            grounding_chunks=[
                types.GroundingChunk(
                    web=types.GroundingChunkWeb(
                        uri="https://vertexaisearch.cloud.google.com/grounding-api-redirect/a",
                        title="AstrBot Docs",
                    )
                ),
                types.GroundingChunk(
                    web=types.GroundingChunkWeb(
                        uri="https://vertexaisearch.cloud.google.com/grounding-api-redirect/a",
                        title="Duplicate",
                    )
                ),
            ]
        ),
        url_context_metadata=types.UrlContextMetadata(
            url_metadata=[
                types.UrlMetadata(
                    retrieved_url="https://docs.astrbot.app/guide",
                    url_retrieval_status=types.UrlRetrievalStatus.URL_RETRIEVAL_STATUS_SUCCESS,
                ),
                types.UrlMetadata(
                    retrieved_url="https://docs.astrbot.app/failed",
                    url_retrieval_status=types.UrlRetrievalStatus.URL_RETRIEVAL_STATUS_ERROR,
                ),
            ]
        ),
    )
    response = types.GenerateContentResponse(
        candidates=[candidate],
        response_id="resp-grounding",
    )

    async def generate_content(**kwargs):
        return response

    monkeypatch.setattr(
        provider.client.models,
        "generate_content",
        generate_content,
        raising=False,
    )
    llm_response = await provider._query(
        payloads={
            "messages": [{"role": "user", "content": "check AstrBot docs"}],
            "model": "gemini-3.7-flash",
        },
        tools=None,
    )

    assert llm_response.web_search_sources == [
        {
            "index": "1",
            "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/a",
            "title": "AstrBot Docs",
        },
        {
            "index": "2",
            "url": "https://docs.astrbot.app/guide",
            "title": "https://docs.astrbot.app/guide",
        },
    ]


@pytest.mark.asyncio
async def test_gemini_stream_collects_grounding_sources_across_chunks(monkeypatch):
    """Streaming responses aggregate incremental grounding chunks including contentless tail chunks."""
    provider = _gemini_stream_provider()
    first_chunk = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text="Part 1. ")],
                ),
                finish_reason=types.FinishReason.STOP,
                grounding_metadata=types.GroundingMetadata(
                    grounding_chunks=[
                        types.GroundingChunk(
                            web=types.GroundingChunkWeb(
                                uri="https://vertexaisearch.cloud.google.com/grounding-api-redirect/1",
                                title="Source 1",
                            )
                        )
                    ]
                ),
            )
        ],
        response_id="resp-stream",
    )
    tail_chunk = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=None,
                finish_reason=types.FinishReason.STOP,
                grounding_metadata=types.GroundingMetadata(
                    grounding_chunks=[
                        types.GroundingChunk(
                            web=types.GroundingChunkWeb(
                                uri="https://vertexaisearch.cloud.google.com/grounding-api-redirect/2",
                                title="Source 2",
                            )
                        )
                    ]
                ),
            )
        ],
        response_id="resp-stream",
    )

    responses = await _drain_gemini_stream(
        provider,
        monkeypatch,
        [first_chunk, tail_chunk],
    )

    final = responses[-1]
    assert final.is_chunk is False
    assert final.web_search_sources == [
        {
            "index": "1",
            "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/1",
            "title": "Source 1",
        },
        {
            "index": "2",
            "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/2",
            "title": "Source 2",
        },
    ]
