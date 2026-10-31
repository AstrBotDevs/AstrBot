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
    provider.vertexai = False
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


@pytest.fixture
def genai_client_calls(monkeypatch) -> list[dict]:
    """Replace genai.Client with a stub that records its init kwargs.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        A list that receives the kwargs of every client construction.
    """
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)

            async def aclose():
                return None

            self.aio = SimpleNamespace(
                _api_client=SimpleNamespace(_http_options=SimpleNamespace(headers={})),
                aclose=aclose,
            )

    monkeypatch.setattr(gemini_source.genai, "Client", FakeClient)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("project", "expected_scope"),
    [
        ("", {}),
        ("bound-project", {"project": "bound-project", "location": "us-central1"}),
    ],
)
async def test_vertex_with_api_key(genai_client_calls, project, expected_scope):
    calls = genai_client_calls
    provider = ProviderGoogleGenAI(
        {
            "id": "vertex",
            "model": "gemini-x",
            "key": ["vertex-key"],
            "api_base": "",
            "gm_vertexai": True,
            "gm_vertex_project": project,
            "gm_vertex_location": "us-central1",
        },
        {},
    )
    try:
        kwargs = dict(calls[-1])
        assert kwargs.pop("http_options").base_url is None
        assert kwargs == {"vertexai": True, "api_key": "vertex-key", **expected_scope}
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_vertex_without_api_key_uses_service_account(
    genai_client_calls, monkeypatch, tmp_path
):
    calls = genai_client_calls
    credentials = SimpleNamespace(project_id="sa-project")
    loaded = []

    def fake_from_file(path, scopes):
        loaded.append((path, scopes))
        return credentials

    monkeypatch.setattr(
        gemini_source.service_account.Credentials,
        "from_service_account_file",
        fake_from_file,
    )
    key_file = tmp_path / "sa.json"
    provider = ProviderGoogleGenAI(
        {
            "id": "vertex",
            "model": "gemini-x",
            "key": [],
            "api_base": "",
            "gm_vertexai": True,
            "gm_vertex_project": "",
            "gm_vertex_location": "",
            "gm_vertex_credentials_file": str(key_file),
        },
        {},
    )
    try:
        assert loaded == [
            (str(key_file), ["https://www.googleapis.com/auth/cloud-platform"])
        ]
        assert calls[-1]["vertexai"] is True
        assert calls[-1]["credentials"] is credentials
        assert calls[-1]["project"] == "sa-project"
        assert calls[-1]["location"] == "global"
        assert "api_key" not in calls[-1]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_vertex_get_models_strips_publisher_prefix():
    async def list_models():
        return [
            SimpleNamespace(
                name="publishers/google/models/gemini-a", supported_actions=None
            ),
            SimpleNamespace(name=None, supported_actions=None),
        ]

    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.vertexai = True
    provider.client = SimpleNamespace(models=SimpleNamespace(list=list_models))

    assert await provider.get_models() == ["gemini-a"]


@pytest.mark.asyncio
async def test_vertex_get_models_with_api_key_explains_manual_model_entry():
    async def list_models():
        raise gemini_source.APIError(
            401, {"error": {"message": "API keys are not supported by this API."}}
        )

    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.vertexai = True
    provider.chosen_api_key = "vertex-key"
    provider.client = SimpleNamespace(models=SimpleNamespace(list=list_models))

    with pytest.raises(Exception, match="Add the model ID manually"):
        await provider.get_models()
