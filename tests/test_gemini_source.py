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
@pytest.mark.parametrize(
    ("model", "gm_thinking_config", "expected"),
    [
        # Gemini 4 and relay-decorated ids must use thinkingLevel, never budget.
        (
            "gemini-4-argon",
            {"level": "HIGH"},
            {"thinking_level": types.ThinkingLevel.HIGH},
        ),
        (
            "［抗截断］gemini-4-argon",
            {"budget": 0, "level": "HIGH"},
            {"thinking_level": types.ThinkingLevel.HIGH},
        ),
        (
            "［抗截断］gemini-4-argon",
            {"level": "low"},
            {"thinking_level": types.ThinkingLevel.LOW},
        ),
        # Gemini 3.7+ generations reject MINIMAL, so it falls back to MEDIUM.
        (
            "gemini-4.1-pro",
            {"level": "MINIMAL"},
            {"thinking_level": types.ThinkingLevel.MEDIUM},
        ),
        (
            "gemini-3.8-flash",
            {"level": "MINIMAL"},
            {"thinking_level": types.ThinkingLevel.MEDIUM},
        ),
        (
            "［抗截断］gemini-3.8-flash",
            {},
            {"thinking_level": types.ThinkingLevel.HIGH},
        ),
        # Gemini 3.0-3.6 still accept MINIMAL.
        (
            "gemini-3.1-pro",
            {"level": "MINIMAL"},
            {"thinking_level": types.ThinkingLevel.MINIMAL},
        ),
        (
            "gemini-3.7-flash",
            {"level": "MINIMAL"},
            {"thinking_level": types.ThinkingLevel.MEDIUM},
        ),
        # Gemini 2.5 behavior is unchanged, including decorated ids.
        (
            "gemini-2.5-flash",
            {"budget": 0},
            {"thinking_budget": 0},
        ),
        (
            "［抗截断］gemini-2.5-flash",
            {"budget": 0},
            {"thinking_budget": 0},
        ),
        # Dated and experimental 2.5 thinking variants stay covered.
        (
            "gemini-2.5-flash-preview-09-2025",
            {"budget": 2048},
            {"thinking_budget": 2048},
        ),
        (
            "gemini-2.5-flash-lite-preview",
            {"budget": 0},
            {"thinking_budget": 0},
        ),
        (
            "gemini-2.5-pro-preview-05-06",
            {"budget": 1024},
            {"thinking_budget": 1024},
        ),
        # Old and non-Gemini models keep sending no thinking config.
        ("gemini-2.0-flash", {}, None),
        ("gpt-4o", {}, None),
    ],
    ids=[
        "gemini-4-argon-level",
        "relay-gemini-4-argon-budget-and-level",
        "relay-gemini-4-argon-lowercase-level",
        "gemini-4.1-pro-minimal",
        "gemini-3.8-flash-minimal",
        "relay-gemini-3.8-flash-default",
        "gemini-3.1-pro-minimal",
        "gemini-3.7-flash-minimal",
        "gemini-2.5-flash-budget",
        "relay-gemini-2.5-flash-budget",
        "gemini-2.5-flash-preview-09-2025-budget",
        "gemini-2.5-flash-lite-preview-budget",
        "gemini-2.5-pro-preview-05-06-budget",
        "gemini-2.0-flash-none",
        "gpt-4o-none",
    ],
)
async def test_gemini_thinking_config_matrix(model, gm_thinking_config, expected):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {"gm_thinking_config": gm_thinking_config}
    provider.provider_settings = {}
    provider.model_name = model
    provider.safety_settings = []

    config = await provider._prepare_query_config({"model": model})

    if expected is None:
        assert config.thinking_config is None
        return
    assert config.thinking_config is not None
    assert config.thinking_config.model_dump(exclude_none=True) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "gm_thinking_config"),
    [
        # Gemini 2.5 image models reject any thinkingConfig with
        # 400 INVALID_ARGUMENT ("Thinking is not enabled for this model"), so
        # even the default budget of 0 must not be sent to them.
        ("gemini-2.5-flash-image", {"budget": 0, "level": "HIGH"}),
        ("gemini-2.5-flash-image", {"budget": 2048}),
        ("gemini-2.5-flash-image-preview", {"budget": 0, "level": "HIGH"}),
        ("gemini-2.5-flash-image-preview-09-2025", {"budget": 2048}),
        ("gemini-2.5-flash-image-generation", {"budget": 0, "level": "HIGH"}),
        ("gemini-2.5-pro-image", {"budget": 0, "level": "HIGH"}),
        # Relay-decorated aliases of the image ids must be excluded as well.
        ("［抗截断］gemini-2.5-flash-image", {"budget": 0, "level": "HIGH"}),
        ("image-relay:gemini-2.5-flash-image", {"budget": 2048}),
        # Other 2.5 modalities that reject thinkingConfig: TTS, native audio
        # and computer use.
        ("gemini-2.5-flash-preview-tts", {"budget": 0, "level": "HIGH"}),
        ("gemini-2.5-pro-preview-tts", {"budget": 2048}),
        ("gemini-2.5-flash-native-audio-preview-09-2025", {"budget": 0}),
        ("gemini-2.5-computer-use-preview-10-2025", {"budget": 0, "level": "HIGH"}),
        # Older image generation models keep sending nothing.
        ("gemini-2.0-flash-exp-image-generation", {"budget": 0, "level": "HIGH"}),
    ],
    ids=[
        "flash-image-default-budget",
        "flash-image-positive-budget",
        "flash-image-preview-default-budget",
        "flash-image-preview-09-2025-positive-budget",
        "flash-image-generation-default-budget",
        "pro-image-default-budget",
        "relay-flash-image-default-budget",
        "image-relay-flash-image-positive-budget",
        "flash-preview-tts-default-budget",
        "pro-preview-tts-positive-budget",
        "flash-native-audio-preview-budget",
        "computer-use-preview-default-budget",
        "gemini-2.0-image-generation-default-budget",
    ],
)
async def test_gemini_25_non_thinking_models_get_no_thinking_config(
    model, gm_thinking_config
):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {"gm_thinking_config": gm_thinking_config}
    provider.provider_settings = {}
    provider.model_name = model
    provider.safety_settings = []

    config = await provider._prepare_query_config({"model": model})

    assert config.thinking_config is None


@pytest.mark.asyncio
async def test_gemini_25_image_generation_request_gets_no_thinking_config():
    model = "gemini-2.5-flash-image"
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {"gm_thinking_config": {"budget": 0, "level": "HIGH"}}
    provider.provider_settings = {}
    provider.model_name = model
    provider.safety_settings = []

    config = await provider._prepare_query_config(
        {"model": model}, modalities=["IMAGE"]
    )

    assert config.response_modalities == ["IMAGE"]
    assert config.thinking_config is None


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
