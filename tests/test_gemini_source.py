import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import httpx
import pytest
from google.genai import types as google_types
from google.genai.errors import APIError

import astrbot.core.provider.sources.gemini_source as gemini_source_module
import astrbot.core.provider.sources.request_retry as request_retry
from astrbot.core.agent.llm_types import LLMResponse
from astrbot.core.agent.message import AudioURLPart, ImageURLPart, TextPart
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI


class FakeToolSet:
    def google_schema(self):
        return {
            "function_declarations": [
                {"name": "lookup", "description": "Lookup data", "parameters": {}}
            ]
        }


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


def test_gemini_extract_reasoning_content_ignores_missing_parts():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    assert provider._extract_reasoning_content(SimpleNamespace(content=None)) == ""
    assert (
        provider._extract_reasoning_content(
            SimpleNamespace(content=SimpleNamespace(parts=[]))
        )
        == ""
    )


def test_gemini_extract_usage_defaults_missing_counts_to_zero():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    usage = provider._extract_usage(
        SimpleNamespace(
            prompt_token_count=None,
            cached_content_token_count=None,
            candidates_token_count=None,
        )
    )

    assert usage.input_other == 0
    assert usage.input_cached == 0
    assert usage.output == 0
    assert usage.total == 0


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


def test_gemini_prepare_conversation_handles_tool_calls_and_multimodal_content():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    thought_signature = base64.b64encode(b"sig-bytes").decode("utf-8")

    conversation = provider._prepare_conversation(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64,"
                                + base64.b64encode(b"img").decode("utf-8")
                            },
                        },
                    ],
                },
                {
                    "role": "assistant",
                    "content": [{"type": "think", "encrypted": thought_signature}],
                    "tool_calls": [
                        {
                            "function": {
                                "name": "lookup",
                                "arguments": '{"x": 1}',
                            },
                            "extra_content": {
                                "google": {"thought_signature": thought_signature}
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "lookup",
                    "content": "done",
                },
            ]
        }
    )

    assert len(conversation) == 3
    assert isinstance(conversation[0], google_types.UserContent)
    assert conversation[0].parts[0].text == "hello"
    assert conversation[0].parts[1].inline_data.mime_type == "image/png"

    assert isinstance(conversation[1], google_types.ModelContent)
    assert len(conversation[1].parts) == 1
    assert conversation[1].parts[0].function_call.name == "lookup"
    assert conversation[1].parts[0].thought_signature == b"sig-bytes"

    assert isinstance(conversation[2], google_types.UserContent)
    assert conversation[2].parts[0].function_response.name == "lookup"


def test_gemini_prepare_conversation_drops_leading_assistant_and_uses_placeholders(
    monkeypatch,
):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    logger_warning = call  # placeholder for type checkers
    from unittest.mock import MagicMock

    logger_warning = MagicMock()
    monkeypatch.setattr(gemini_source_module.logger, "warning", logger_warning)

    conversation = provider._prepare_conversation(
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [{"type": "think", "encrypted": "not-base64"}],
                },
                {
                    "role": "assistant",
                    "content": [],
                },
                {
                    "role": "user",
                    "content": "",
                },
            ]
        }
    )

    assert len(conversation) == 1
    assert isinstance(conversation[0], google_types.ModelContent)
    assert [part.text for part in conversation[0].parts] == ["", ""]
    assert logger_warning.call_count == 2
    assert (
        "Failed to decode google gemini thinking signature"
        in logger_warning.call_args_list[0].args[0]
    )
    assert (
        "Text content is empty, added a space as placeholder."
        in logger_warning.call_args_list[1].args[0]
    )


@pytest.mark.asyncio
async def test_gemini_assemble_context_uses_placeholder_and_skips_failed_audio(
    monkeypatch,
):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    async def fake_resolve_media_ref_to_base64_data(
        ref: str, media_type: str, **kwargs
    ):
        if media_type == "audio":
            raise RuntimeError("bad audio")
        return SimpleNamespace(
            to_data_url=lambda: f"data:{media_type}/png;base64,resolved-{ref}"
        )

    monkeypatch.setattr(
        gemini_source_module,
        "resolve_media_ref_to_base64_data",
        fake_resolve_media_ref_to_base64_data,
    )

    assembled = await provider.assemble_context(
        "",
        extra_user_content_parts=[
            TextPart(text="extra text"),
            ImageURLPart(
                image_url=ImageURLPart.ImageURL(url="image-ref"),
            ),
            AudioURLPart(
                audio_url=AudioURLPart.AudioURL(url="audio-ref"),
            ),
        ],
    )

    assert assembled == {
        "role": "user",
        "content": [
            {"type": "text", "text": " "},
            {"type": "text", "text": "extra text"},
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,resolved-image-ref"},
            },
        ],
    }


@pytest.mark.asyncio
async def test_gemini_assemble_context_keeps_placeholder_when_all_media_resolution_returns_none(
    monkeypatch,
):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    async def fake_resolve_media_ref_to_base64_data(
        ref: str, media_type: str, **kwargs
    ):
        return None

    monkeypatch.setattr(
        gemini_source_module,
        "resolve_media_ref_to_base64_data",
        fake_resolve_media_ref_to_base64_data,
    )

    assembled = await provider.assemble_context(
        "",
        image_urls=["image-ref"],
        audio_urls=["audio-ref"],
    )

    assert assembled == {
        "role": "user",
        "content": [{"type": "text", "text": "[Image]"}],
    }


@pytest.mark.asyncio
async def test_gemini_assemble_context_rejects_unsupported_extra_part_type():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    with pytest.raises(ValueError, match="Unsupported extra content part type"):
        await provider.assemble_context(
            "",
            extra_user_content_parts=[object()],
        )


def test_gemini_process_content_parts_collects_reasoning_tool_calls_and_images():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    llm_response = LLMResponse(role="assistant")
    thought_signature = base64.b64encode(b"tool-signature").decode("utf-8")
    function_part = google_types.Part.from_function_call(
        name="lookup",
        args={"value": 1},
    )
    function_part.thought_signature = b"tool-signature"
    candidate = SimpleNamespace(
        content=SimpleNamespace(
            parts=[
                google_types.Part(text="think", thought=True),
                google_types.Part(text="visible"),
                function_part,
                google_types.Part.from_bytes(data=b"img", mime_type="image/png"),
            ]
        ),
        finish_reason=google_types.FinishReason.STOP,
    )

    chain = provider._process_content_parts(candidate, llm_response)

    assert chain.get_plain_text() == "visible"
    assert llm_response.reasoning_content == "think"
    assert llm_response.role == "tool"
    assert llm_response.tools_call_name == ["lookup"]
    assert llm_response.tools_call_args == [{"value": 1}]
    assert llm_response.tools_call_ids == ["lookup"]
    assert llm_response.tools_call_extra_content == {
        "lookup": {"google": {"thought_signature": thought_signature}}
    }
    assert llm_response.reasoning_signature == thought_signature
    assert any(
        getattr(component.type, "value", None) == "Image" for component in chain.chain
    )


@pytest.mark.parametrize(
    ("finish_reason", "error_message"),
    [
        (google_types.FinishReason.SAFETY, "safety checks"),
        (google_types.FinishReason.PROHIBITED_CONTENT, "platform policy"),
    ],
)
def test_gemini_process_content_parts_rejects_safety_and_policy_blocks(
    finish_reason,
    error_message,
):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    llm_response = LLMResponse(role="assistant")
    candidate = SimpleNamespace(
        content=SimpleNamespace(parts=[google_types.Part(text="blocked")]),
        finish_reason=finish_reason,
    )

    with pytest.raises(Exception, match=error_message):
        provider._process_content_parts(candidate, llm_response)


def test_gemini_process_content_parts_allows_empty_candidate_when_validation_disabled():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    llm_response = LLMResponse(role="assistant")
    candidate = SimpleNamespace(
        content=None, finish_reason=google_types.FinishReason.STOP
    )

    chain = provider._process_content_parts(
        candidate,
        llm_response,
        validate_output=False,
    )

    assert chain.chain == []
    assert llm_response.result_chain.chain == []


def test_gemini_process_content_parts_allows_empty_parts_when_validation_disabled():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    llm_response = LLMResponse(role="assistant")
    candidate = SimpleNamespace(
        content=SimpleNamespace(parts=[]),
        finish_reason=google_types.FinishReason.STOP,
    )

    chain = provider._process_content_parts(
        candidate,
        llm_response,
        validate_output=False,
    )

    assert chain.chain == []
    assert llm_response.result_chain.chain == []


@pytest.mark.asyncio
async def test_gemini_query_stream_accumulates_text_and_reasoning(monkeypatch):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.provider_settings = {}
    provider.get_model = lambda: "gemini-test"
    provider._prepare_conversation = lambda payloads: ["conversation"]
    provider._prepare_query_config = AsyncMock(return_value="config")

    class FakeStream:
        def __init__(self, chunks):
            self._chunks = chunks

        def __aiter__(self):
            self._iterator = iter(self._chunks)
            return self

        async def __anext__(self):
            try:
                return next(self._iterator)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    chunks = [
        SimpleNamespace(
            candidates=[], text="", response_id="skip", usage_metadata=None
        ),
        SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(
                        parts=[google_types.Part(text="ponder", thought=True)]
                    ),
                    finish_reason=None,
                )
            ],
            text="Hel",
            response_id="resp-1",
            usage_metadata=None,
        ),
        SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(parts=[google_types.Part(text="lo")]),
                    finish_reason=google_types.FinishReason.STOP,
                )
            ],
            text="lo",
            response_id="resp-2",
            usage_metadata=SimpleNamespace(
                prompt_token_count=1,
                cached_content_token_count=2,
                candidates_token_count=3,
            ),
        ),
    ]

    async def fake_generate_content_stream(**kwargs):
        return FakeStream(chunks)

    provider.client = SimpleNamespace(
        models=SimpleNamespace(generate_content_stream=fake_generate_content_stream)
    )

    async def fake_retry_provider_request(name, factory, max_attempts=None):
        return await factory()

    monkeypatch.setattr(
        gemini_source_module,
        "retry_provider_request",
        fake_retry_provider_request,
    )

    responses = [
        response
        async for response in provider._query_stream(
            {
                "messages": [{"role": "user", "content": "hello"}],
                "model": "gemini-test",
            },
            tools=None,
        )
    ]

    assert [response.is_chunk for response in responses] == [True, True, False]
    assert responses[0].reasoning_content == "ponder"
    assert responses[0].completion_text == "Hel"
    assert responses[1].completion_text == "lo"
    assert responses[2].completion_text == "Hello"
    assert responses[2].reasoning_content == "ponder"
    assert responses[2].usage.total == 6


@pytest.mark.asyncio
async def test_gemini_query_stream_raises_when_all_chunks_are_empty(monkeypatch):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.provider_settings = {}
    provider.get_model = lambda: "gemini-test"
    provider._prepare_conversation = lambda payloads: ["conversation"]
    provider._prepare_query_config = AsyncMock(return_value="config")

    class FakeStream:
        def __init__(self, chunks):
            self._chunks = chunks

        def __aiter__(self):
            self._iterator = iter(self._chunks)
            return self

        async def __anext__(self):
            try:
                return next(self._iterator)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    chunks = [
        SimpleNamespace(
            candidates=[], text="", response_id="skip-1", usage_metadata=None
        ),
        SimpleNamespace(
            candidates=[SimpleNamespace(content=None, finish_reason=None)],
            text="",
            response_id="skip-2",
            usage_metadata=None,
        ),
    ]

    async def fake_generate_content_stream(**kwargs):
        return FakeStream(chunks)

    provider.client = SimpleNamespace(
        models=SimpleNamespace(generate_content_stream=fake_generate_content_stream)
    )

    async def fake_retry_provider_request(name, factory, max_attempts=None):
        return await factory()

    monkeypatch.setattr(
        gemini_source_module,
        "retry_provider_request",
        fake_retry_provider_request,
    )

    with pytest.raises(EmptyModelOutputError, match="no usable output"):
        _ = [
            response
            async for response in provider._query_stream(
                {
                    "messages": [{"role": "user", "content": "hello"}],
                    "model": "gemini-test",
                },
                tools=None,
            )
        ]


@pytest.mark.asyncio
async def test_gemini_handle_api_error_rotates_key_and_retries(monkeypatch):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.chosen_api_key = "bad-key"
    provider.provider_config = {}
    provider.set_key = lambda key: setattr(provider, "chosen_api_key", key)

    monkeypatch.setattr(gemini_source_module.random, "choice", lambda keys: keys[-1])
    monkeypatch.setattr(gemini_source_module.asyncio, "sleep", AsyncMock())

    should_retry = await provider._handle_api_error(
        APIError(429, {"message": "API key not valid"}),
        ["bad-key", "good-key"],
    )

    assert should_retry is True
    assert provider.chosen_api_key == "good-key"


def test_gemini_key_accessors_and_set_key_reinitialize_client(monkeypatch):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.api_keys = ["key-a", "key-b"]
    provider.chosen_api_key = "key-a"
    init_client = []

    monkeypatch.setattr(
        provider,
        "_init_client",
        lambda: init_client.append(provider.chosen_api_key),
    )

    assert provider.get_current_key() == "key-a"
    assert provider.get_keys() == ["key-a", "key-b"]

    provider.set_key("key-b")

    assert provider.chosen_api_key == "key-b"
    assert init_client == ["key-b"]


def test_gemini_init_client_tracks_previous_http_client_on_set_key(monkeypatch):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.timeout = 30
    provider.api_base = "https://gemini.example"
    provider.chosen_api_key = "key-a"
    provider._http_client = object()
    provider._stale_http_clients = []

    created_http_clients = []

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            created_http_clients.append(self)

    class FakeHttpOptions:
        def __init__(self, **kwargs):
            self.base_url = kwargs["base_url"]
            self.timeout = kwargs["timeout"]
            self.httpx_async_client = None

    class FakeGenAIClient:
        def __init__(self, *, api_key, http_options):
            self.aio = SimpleNamespace(api_key=api_key, http_options=http_options)

    monkeypatch.setattr(gemini_source_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(gemini_source_module.types, "HttpOptions", FakeHttpOptions)
    monkeypatch.setattr(gemini_source_module.genai, "Client", FakeGenAIClient)

    provider.set_key("key-b")

    assert provider.chosen_api_key == "key-b"
    assert (
        provider._stale_http_clients == [provider._http_client]
        or len(created_http_clients) == 1
    )
    assert created_http_clients[0].kwargs == {
        "base_url": "https://gemini.example",
        "timeout": 30,
        "trust_env": False,
        "follow_redirects": False,
    }
    assert provider._stale_http_clients[0] is not provider._http_client
    assert provider.client.api_key == "key-b"
    assert provider.client.http_options.httpx_async_client is provider._http_client


@pytest.mark.asyncio
async def test_gemini_handle_api_error_raises_when_no_keys_remain():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.chosen_api_key = "last-key"
    provider.provider_config = {}

    with pytest.raises(
        Exception,
        match="Gemini API rate limit reached or API key issue detected.",
    ):
        await provider._handle_api_error(
            APIError(429, {"message": "API key not valid"}),
            ["last-key"],
        )


@pytest.mark.asyncio
async def test_gemini_handle_api_error_logs_connection_failure(monkeypatch):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.chosen_api_key = "key-a"
    provider.provider_config = {"proxy": "http://proxy.test"}
    connection_log = []

    monkeypatch.setattr(gemini_source_module, "is_connection_error", lambda e: True)
    monkeypatch.setattr(
        gemini_source_module,
        "log_connection_failure",
        lambda provider_name, error, proxy: connection_log.append(
            (provider_name, error, proxy)
        ),
    )

    with pytest.raises(APIError):
        await provider._handle_api_error(
            APIError(500, {"message": "upstream reset"}),
            ["key-a", "key-b"],
        )

    assert len(connection_log) == 1
    assert connection_log[0][0] == "Gemini"
    assert connection_log[0][2] == "http://proxy.test"
    assert isinstance(connection_log[0][1], APIError)


@pytest.mark.asyncio
async def test_gemini_handle_api_error_normalizes_none_message_before_reraising(
    monkeypatch,
):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.chosen_api_key = "key-a"
    provider.provider_config = {}
    error = APIError(500, {"message": None})

    monkeypatch.setattr(gemini_source_module, "is_connection_error", lambda e: False)

    with pytest.raises(APIError) as exc_info:
        await provider._handle_api_error(error, ["key-a", "key-b"])

    assert exc_info.value is error
    assert error.message == ""


def test_gemini_require_client_raises_when_not_initialized():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.client = None

    with pytest.raises(RuntimeError, match="Gemini client is not initialized"):
        provider._require_client()


@pytest.mark.asyncio
async def test_gemini_encode_image_bs64_raises_when_resolution_returns_none(
    monkeypatch,
):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)

    monkeypatch.setattr(
        gemini_source_module,
        "resolve_media_ref_to_base64_data",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        gemini_source_module,
        "describe_media_ref",
        lambda ref: f"desc:{ref}",
    )

    with pytest.raises(
        RuntimeError, match="Failed to encode image data: desc:image-ref"
    ):
        await provider.encode_image_bs64("image-ref")


@pytest.mark.asyncio
async def test_gemini_get_models_wraps_api_errors():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.client = SimpleNamespace(
        models=SimpleNamespace(
            list=AsyncMock(side_effect=APIError(500, {"message": "boom"}))
        )
    )

    with pytest.raises(Exception, match="Failed to fetch Gemini model list: boom"):
        await provider.get_models()


@pytest.mark.asyncio
async def test_gemini_text_chat_retries_after_api_error_and_strips_no_save_flag():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.api_keys = ["key-a", "key-b"]
    provider.get_model = lambda: "gemini-test"
    provider.assemble_context = AsyncMock(
        return_value={"role": "user", "content": "prompt"}
    )
    provider._ensure_message_to_dicts = lambda contexts: list(contexts)
    provider._handle_api_error = AsyncMock(side_effect=[True])
    expected = LLMResponse(role="assistant")
    query_calls: list[tuple[dict, object]] = []

    async def fake_query(payloads, func_tool, *, request_max_retries=None):
        query_calls.append((payloads, func_tool))
        if len(query_calls) == 1:
            raise APIError(429, {"message": "retry"})
        return expected

    provider._query = fake_query

    result = await provider.text_chat(
        prompt="hello",
        contexts=[{"role": "assistant", "content": "keep", "_no_save": True}],
        system_prompt="system",
        request_max_retries=4,
    )

    assert result is expected
    assert len(query_calls) == 2
    assert query_calls[0][0]["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "assistant", "content": "keep"},
        {"role": "user", "content": "prompt"},
    ]
    provider._handle_api_error.assert_awaited_once()
    assert provider._handle_api_error.await_args.args[1] == ["key-a", "key-b"]


@pytest.mark.asyncio
async def test_gemini_text_chat_raises_when_error_handler_declines_retry():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.api_keys = ["key-a"]
    provider.get_model = lambda: "gemini-test"
    provider.assemble_context = AsyncMock(
        return_value={"role": "user", "content": "prompt"}
    )
    provider._ensure_message_to_dicts = lambda contexts: list(contexts)
    provider._handle_api_error = AsyncMock(return_value=False)

    async def fake_query(payloads, func_tool, *, request_max_retries=None):
        raise APIError(500, {"message": "fatal"})

    provider._query = fake_query

    with pytest.raises(Exception, match="Gemini request failed."):
        await provider.text_chat(
            prompt="hello",
            contexts=[],
            request_max_retries=2,
        )

    provider._handle_api_error.assert_awaited_once()


@pytest.mark.asyncio
async def test_gemini_text_chat_expands_tool_call_result_lists():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.api_keys = ["key-a"]
    provider.get_model = lambda: "gemini-test"
    provider.assemble_context = AsyncMock(
        return_value={"role": "user", "content": "prompt"}
    )
    provider._ensure_message_to_dicts = lambda contexts: list(contexts)
    provider._handle_api_error = AsyncMock()
    expected = LLMResponse(role="assistant")
    payloads_seen: list[dict] = []

    class FakeToolCallResult:
        def __init__(self, name: str):
            self.name = name

        def to_messages(self):
            return [{"role": "tool", "content": f"result-{self.name}"}]

    async def fake_query(payloads, func_tool, *, request_max_retries=None):
        payloads_seen.append(payloads)
        return expected

    provider._query = fake_query

    result = await provider.text_chat(
        prompt="hello",
        contexts=[{"role": "assistant", "content": "keep"}],
        tool_calls_result=[FakeToolCallResult("a"), FakeToolCallResult("b")],
    )

    assert result is expected
    assert payloads_seen == [
        {
            "messages": [
                {"role": "assistant", "content": "keep"},
                {"role": "user", "content": "prompt"},
                {"role": "tool", "content": "result-a"},
                {"role": "tool", "content": "result-b"},
            ],
            "model": "gemini-test",
        }
    ]


@pytest.mark.asyncio
async def test_gemini_text_chat_stream_retries_after_api_error():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.api_keys = ["key-a", "key-b"]
    provider.get_model = lambda: "gemini-test"
    provider.assemble_context = AsyncMock(
        return_value={"role": "user", "content": "prompt"}
    )
    provider._ensure_message_to_dicts = lambda contexts: list(contexts)
    provider._handle_api_error = AsyncMock(side_effect=[True])
    yielded = [
        LLMResponse(role="assistant", is_chunk=True),
        LLMResponse(role="assistant", is_chunk=False),
    ]
    stream_calls: list[dict] = []

    async def fake_query_stream(payloads, func_tool, *, request_max_retries=None):
        stream_calls.append(payloads)
        if len(stream_calls) == 1:
            raise APIError(429, {"message": "retry"})
        for item in yielded:
            yield item

    provider._query_stream = fake_query_stream

    responses = [
        item
        async for item in provider.text_chat_stream(
            prompt="hello",
            contexts=[],
            system_prompt="system",
            request_max_retries=3,
        )
    ]

    assert responses == yielded
    assert len(stream_calls) == 2
    assert stream_calls[0]["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "prompt"},
    ]
    provider._handle_api_error.assert_awaited_once()
    assert provider._handle_api_error.await_args.args[1] == ["key-a", "key-b"]


@pytest.mark.asyncio
async def test_gemini_text_chat_stream_retries_with_tool_results_and_strips_no_save_flag():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.api_keys = ["key-a", "key-b"]
    provider.get_model = lambda: "gemini-test"
    provider.assemble_context = AsyncMock(
        return_value={"role": "user", "content": "prompt"}
    )
    provider._ensure_message_to_dicts = lambda contexts: list(contexts)
    provider._handle_api_error = AsyncMock(side_effect=[True])
    yielded = [LLMResponse(role="assistant", is_chunk=False)]
    stream_calls: list[dict] = []

    class FakeToolCallResult:
        def __init__(self, name: str) -> None:
            self.name = name

        def to_messages(self):
            return [{"role": "tool", "content": f"result-{self.name}"}]

    async def fake_query_stream(payloads, func_tool, *, request_max_retries=None):
        stream_calls.append(payloads)
        if len(stream_calls) == 1:
            raise APIError(429, {"message": "retry"})
        for item in yielded:
            yield item

    provider._query_stream = fake_query_stream

    responses = [
        item
        async for item in provider.text_chat_stream(
            prompt="hello",
            contexts=[{"role": "assistant", "content": "keep", "_no_save": True}],
            system_prompt="system",
            tool_calls_result=[FakeToolCallResult("a"), FakeToolCallResult("b")],
            request_max_retries=3,
        )
    ]

    assert responses == yielded
    assert len(stream_calls) == 2
    assert stream_calls[0]["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "assistant", "content": "keep"},
        {"role": "user", "content": "prompt"},
        {"role": "tool", "content": "result-a"},
        {"role": "tool", "content": "result-b"},
    ]
    assert stream_calls[1]["messages"] == stream_calls[0]["messages"]


@pytest.mark.asyncio
async def test_gemini_prepare_query_config_downgrades_stream_image_and_sets_tools():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {
        "gm_native_coderunner": True,
        "gm_native_search": True,
        "gm_url_context": True,
        "gm_thinking_config": {"budget": 32},
    }
    provider.provider_settings = {"streaming_response": True}
    provider.safety_settings = []
    provider.get_model = lambda: "gemini-2.5-flash"

    config = await provider._prepare_query_config(
        {"model": "gemini-2.5-flash", "max_tokens": 128},
        tools=FakeToolSet(),
        tool_choice="required",
        system_instruction="system",
        modalities=["TEXT", "IMAGE"],
        temperature=1.2,
    )

    assert config.system_instruction == "system"
    assert config.temperature == 1.2
    assert config.max_output_tokens == 128
    assert config.response_modalities == ["TEXT"]
    assert config.tools is not None
    assert len(config.tools) == 4
    assert (
        config.tool_config.function_calling_config.mode
        is google_types.FunctionCallingConfigMode.ANY
    )
    assert config.thinking_config.thinking_budget == 32
    assert config.automatic_function_calling.disable is True


@pytest.mark.asyncio
async def test_gemini_prepare_query_config_ignores_native_tools_for_gemini_2_lite():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {
        "gm_native_coderunner": True,
        "gm_native_search": True,
        "gm_url_context": True,
    }
    provider.provider_settings = {"streaming_response": False}
    provider.safety_settings = []
    provider.get_model = lambda: "gemini-2.0-lite"

    config = await provider._prepare_query_config({"model": "gemini-2.0-lite"})

    assert config.tools is None
    assert config.tool_config is None
    assert config.response_modalities == ["TEXT"]


@pytest.mark.asyncio
async def test_gemini_prepare_query_config_normalizes_invalid_thinking_level(caplog):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {
        "gm_thinking_config": {"level": "invalid"},
    }
    provider.provider_settings = {"streaming_response": False}
    provider.safety_settings = []
    provider.get_model = lambda: "gemini-3.1-pro"

    config = await provider._prepare_query_config({"model": "gemini-3.1-pro"})

    assert config.thinking_config is not None
    assert "Invalid thinking level: INVALID, using HIGH" in caplog.text


def test_gemini_process_content_parts_rejects_empty_candidate_content():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    llm_response = LLMResponse(role="assistant")
    candidate = SimpleNamespace(
        content=None, finish_reason=google_types.FinishReason.STOP
    )

    with pytest.raises(
        EmptyModelOutputError,
        match="Gemini candidate content is empty",
    ):
        provider._process_content_parts(candidate, llm_response)


def test_gemini_process_content_parts_rejects_empty_candidate_parts():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    llm_response = LLMResponse(role="assistant")
    candidate = SimpleNamespace(
        content=SimpleNamespace(parts=[]),
        finish_reason=google_types.FinishReason.STOP,
    )

    with pytest.raises(
        EmptyModelOutputError,
        match="Gemini candidate content parts are empty",
    ):
        provider._process_content_parts(candidate, llm_response)


@pytest.mark.asyncio
async def test_gemini_query_stream_returns_function_call_response_immediately(
    monkeypatch,
):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.provider_settings = {}
    provider.get_model = lambda: "gemini-test"
    provider._prepare_conversation = lambda payloads: ["conversation"]
    provider._prepare_query_config = AsyncMock(return_value="config")

    class FakeStream:
        def __init__(self, chunks):
            self._chunks = chunks

        def __aiter__(self):
            self._iterator = iter(self._chunks)
            return self

        async def __anext__(self):
            try:
                return next(self._iterator)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    function_part = google_types.Part.from_function_call(
        name="lookup",
        args={"value": 1},
    )
    chunks = [
        SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(parts=[function_part]),
                    finish_reason=None,
                )
            ],
            text="",
            response_id="resp-tool",
            usage_metadata=SimpleNamespace(
                prompt_token_count=4,
                cached_content_token_count=0,
                candidates_token_count=2,
            ),
        )
    ]

    async def fake_generate_content_stream(**kwargs):
        return FakeStream(chunks)

    provider.client = SimpleNamespace(
        models=SimpleNamespace(generate_content_stream=fake_generate_content_stream)
    )

    async def fake_retry_provider_request(name, factory, max_attempts=None):
        return await factory()

    monkeypatch.setattr(
        gemini_source_module,
        "retry_provider_request",
        fake_retry_provider_request,
    )

    responses = [
        response
        async for response in provider._query_stream(
            {
                "messages": [{"role": "user", "content": "hello"}],
                "model": "gemini-test",
            },
            tools=None,
        )
    ]

    assert len(responses) == 1
    assert responses[0].is_chunk is False
    assert responses[0].role == "tool"
    assert responses[0].tools_call_name == ["lookup"]
    assert responses[0].tools_call_args == [{"value": 1}]
    assert responses[0].tools_call_ids == ["lookup"]
    assert responses[0].usage.total == 6


@pytest.mark.asyncio
async def test_gemini_query_retries_capability_fallbacks_before_success(monkeypatch):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {"gm_resp_image_modal": True}
    provider.provider_settings = {}
    provider.get_model = lambda: "gemini-test"
    provider._prepare_conversation = lambda payloads: ["conversation"]
    provider._prepare_query_config = AsyncMock(return_value="config")

    result = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(parts=[google_types.Part(text="final answer")]),
                finish_reason=google_types.FinishReason.STOP,
            )
        ],
        response_id="resp-final",
        usage_metadata=SimpleNamespace(
            prompt_token_count=1,
            cached_content_token_count=2,
            candidates_token_count=3,
        ),
    )
    outcomes = [
        APIError(400, {"message": "Developer instruction is not enabled"}),
        APIError(400, {"message": "Function calling is not enabled"}),
        APIError(400, {"message": "Multi-modal output is not supported"}),
        result,
    ]

    async def fake_generate_content(**kwargs):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    provider.client = SimpleNamespace(
        models=SimpleNamespace(generate_content=fake_generate_content)
    )

    async def fake_retry_provider_request(name, factory, max_attempts=None):
        return await factory()

    monkeypatch.setattr(
        gemini_source_module,
        "retry_provider_request",
        fake_retry_provider_request,
    )

    response = await provider._query(
        {
            "messages": [
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "hello"},
            ],
            "model": "gemini-test",
            "tool_choice": "required",
        },
        tools=FakeToolSet(),
    )

    assert response.id == "resp-final"
    assert response.completion_text == "final answer"
    assert response.usage.total == 6
    assert provider._prepare_query_config.await_count == 4
    first_call, second_call, third_call, fourth_call = (
        provider._prepare_query_config.await_args_list
    )
    assert first_call.args[3] == "system prompt"
    assert first_call.args[4] == ["TEXT", "IMAGE"]
    assert second_call.args[3] is None
    assert second_call.args[1] is not None
    assert third_call.args[1] is None
    assert third_call.args[4] == ["TEXT", "IMAGE"]
    assert fourth_call.args[1] is None
    assert fourth_call.args[4] == ["TEXT"]


@pytest.mark.asyncio
async def test_gemini_query_raises_when_candidates_are_empty(monkeypatch):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.provider_settings = {}
    provider.get_model = lambda: "gemini-test"
    provider._prepare_conversation = lambda payloads: ["conversation"]
    provider._prepare_query_config = AsyncMock(return_value="config")
    provider.client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=AsyncMock(
                return_value=SimpleNamespace(
                    candidates=[],
                    response_id="resp-empty",
                    usage_metadata=None,
                )
            )
        )
    )

    async def fake_retry_provider_request(name, factory, max_attempts=None):
        return await factory()

    monkeypatch.setattr(
        gemini_source_module,
        "retry_provider_request",
        fake_retry_provider_request,
    )

    with pytest.raises(Exception, match="Gemini request failed: candidates is empty."):
        await provider._query(
            {
                "messages": [{"role": "user", "content": "hello"}],
                "model": "gemini-test",
            },
            tools=None,
        )


@pytest.mark.asyncio
async def test_gemini_query_reraises_unrecognized_api_error(monkeypatch):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.provider_settings = {}
    provider.get_model = lambda: "gemini-test"
    provider._prepare_conversation = lambda payloads: ["conversation"]
    provider._prepare_query_config = AsyncMock(return_value="config")
    provider.client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=AsyncMock(
                side_effect=APIError(500, {"message": "unhandled provider failure"})
            )
        )
    )

    async def fake_retry_provider_request(name, factory, max_attempts=None):
        return await factory()

    monkeypatch.setattr(
        gemini_source_module,
        "retry_provider_request",
        fake_retry_provider_request,
    )

    with pytest.raises(APIError, match="unhandled provider failure"):
        await provider._query(
            {
                "messages": [{"role": "user", "content": "hello"}],
                "model": "gemini-test",
            },
            tools=None,
        )

    provider._prepare_query_config.assert_awaited_once()


@pytest.mark.asyncio
async def test_gemini_query_recitation_retries_with_higher_temperature(monkeypatch):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.provider_settings = {}
    provider.get_model = lambda: "gemini-test"
    provider._prepare_conversation = lambda payloads: ["conversation"]
    provider._prepare_query_config = AsyncMock(return_value="config")

    recitation = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(parts=[google_types.Part(text="retry")]),
                finish_reason=google_types.FinishReason.RECITATION,
            )
        ],
        response_id="resp-retry",
        usage_metadata=None,
    )
    success = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(parts=[google_types.Part(text="done")]),
                finish_reason=google_types.FinishReason.STOP,
            )
        ],
        response_id="resp-ok",
        usage_metadata=None,
    )
    outcomes = [recitation, success]

    async def fake_generate_content(**kwargs):
        return outcomes.pop(0)

    provider.client = SimpleNamespace(
        models=SimpleNamespace(generate_content=fake_generate_content)
    )

    async def fake_retry_provider_request(name, factory, max_attempts=None):
        return await factory()

    monkeypatch.setattr(
        gemini_source_module,
        "retry_provider_request",
        fake_retry_provider_request,
    )

    response = await provider._query(
        {"messages": [{"role": "user", "content": "hello"}], "model": "gemini-test"},
        tools=None,
    )

    assert response.id == "resp-ok"
    assert response.completion_text == "done"
    assert provider._prepare_query_config.await_count == 2
    assert provider._prepare_query_config.await_args_list[0].args[5] == pytest.approx(
        0.7
    )
    assert provider._prepare_query_config.await_args_list[1].args[5] == pytest.approx(
        0.9
    )


@pytest.mark.asyncio
async def test_gemini_query_recitation_raises_after_temperature_exceeds_limit(
    monkeypatch,
):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.provider_settings = {}
    provider.get_model = lambda: "gemini-test"
    provider._prepare_conversation = lambda payloads: ["conversation"]
    provider._prepare_query_config = AsyncMock(return_value="config")

    recitation = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(parts=[google_types.Part(text="retry")]),
                finish_reason=google_types.FinishReason.RECITATION,
            )
        ],
        response_id="resp-retry",
        usage_metadata=None,
    )
    provider.client = SimpleNamespace(
        models=SimpleNamespace(generate_content=AsyncMock(return_value=recitation))
    )

    async def fake_retry_provider_request(name, factory, max_attempts=None):
        return await factory()

    monkeypatch.setattr(
        gemini_source_module,
        "retry_provider_request",
        fake_retry_provider_request,
    )

    with pytest.raises(
        Exception,
        match="Temperature exceeded the maximum value of 2",
    ):
        await provider._query(
            {
                "messages": [{"role": "user", "content": "hello"}],
                "model": "gemini-test",
                "temperature": 2.1,
            },
            tools=None,
        )


@pytest.mark.asyncio
async def test_gemini_query_stream_retries_after_capability_fallbacks(monkeypatch):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.provider_settings = {}
    provider.get_model = lambda: "gemini-test"
    provider._prepare_conversation = lambda payloads: ["conversation"]
    provider._prepare_query_config = AsyncMock(return_value="config")

    class FakeStream:
        def __init__(self, chunks):
            self._chunks = chunks

        def __aiter__(self):
            self._iterator = iter(self._chunks)
            return self

        async def __anext__(self):
            try:
                return next(self._iterator)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    outcomes = [
        APIError(400, {"message": "Developer instruction is not enabled"}),
        APIError(400, {"message": "Function calling is not enabled"}),
        FakeStream(
            [
                SimpleNamespace(
                    candidates=[
                        SimpleNamespace(
                            content=SimpleNamespace(
                                parts=[google_types.Part(text="ok")]
                            ),
                            finish_reason=google_types.FinishReason.STOP,
                        )
                    ],
                    text="ok",
                    response_id="resp-stream",
                    usage_metadata=None,
                )
            ]
        ),
    ]

    async def fake_generate_content_stream(**kwargs):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    provider.client = SimpleNamespace(
        models=SimpleNamespace(generate_content_stream=fake_generate_content_stream)
    )

    async def fake_retry_provider_request(name, factory, max_attempts=None):
        return await factory()

    monkeypatch.setattr(
        gemini_source_module,
        "retry_provider_request",
        fake_retry_provider_request,
    )

    responses = [
        response
        async for response in provider._query_stream(
            {
                "messages": [
                    {"role": "system", "content": "system prompt"},
                    {"role": "user", "content": "hello"},
                ],
                "model": "gemini-test",
                "tool_choice": "required",
            },
            tools=FakeToolSet(),
        )
    ]

    assert [response.is_chunk for response in responses] == [True, False]
    assert responses[-1].completion_text == "ok"
    assert provider._prepare_query_config.await_count == 3
    first_call, second_call, third_call = provider._prepare_query_config.await_args_list
    assert first_call.args[3] == "system prompt"
    assert second_call.args[3] is None
    assert second_call.args[1] is not None
    assert third_call.args[1] is None


@pytest.mark.asyncio
async def test_gemini_query_stream_final_tool_only_response_is_usable(monkeypatch):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.provider_settings = {}
    provider.get_model = lambda: "gemini-test"
    provider._prepare_conversation = lambda payloads: ["conversation"]
    provider._prepare_query_config = AsyncMock(return_value="config")

    class FakeStream:
        def __init__(self, chunks):
            self._chunks = chunks

        def __aiter__(self):
            self._iterator = iter(self._chunks)
            return self

        async def __anext__(self):
            try:
                return next(self._iterator)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    function_part = google_types.Part.from_function_call(
        name="lookup",
        args={"value": 1},
    )
    chunks = [
        SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(
                        parts=[google_types.Part(text="ponder", thought=True)]
                    ),
                    finish_reason=None,
                )
            ],
            text="",
            response_id="resp-think",
            usage_metadata=None,
        ),
        SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(parts=[function_part]),
                    finish_reason=google_types.FinishReason.STOP,
                )
            ],
            text="",
            response_id="resp-final-tool",
            usage_metadata=SimpleNamespace(
                prompt_token_count=2,
                cached_content_token_count=0,
                candidates_token_count=1,
            ),
        ),
    ]

    async def fake_generate_content_stream(**kwargs):
        return FakeStream(chunks)

    provider.client = SimpleNamespace(
        models=SimpleNamespace(generate_content_stream=fake_generate_content_stream)
    )

    async def fake_retry_provider_request(name, factory, max_attempts=None):
        return await factory()

    monkeypatch.setattr(
        gemini_source_module,
        "retry_provider_request",
        fake_retry_provider_request,
    )

    responses = [
        response
        async for response in provider._query_stream(
            {
                "messages": [{"role": "user", "content": "hello"}],
                "model": "gemini-test",
            },
            tools=None,
        )
    ]

    assert [response.is_chunk for response in responses] == [True, False]
    assert responses[0].reasoning_content == "ponder"
    assert responses[1].role == "tool"
    assert responses[1].tools_call_name == ["lookup"]
    assert responses[1].tools_call_args == [{"value": 1}]
    assert responses[1].usage.total == 3


@pytest.mark.asyncio
async def test_gemini_query_stream_reraises_unrecognized_api_error(monkeypatch):
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.provider_settings = {}
    provider.get_model = lambda: "gemini-test"
    provider._prepare_conversation = lambda payloads: ["conversation"]
    provider._prepare_query_config = AsyncMock(return_value="config")
    provider.client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content_stream=AsyncMock(
                side_effect=APIError(500, {"message": "unhandled stream failure"})
            )
        )
    )

    async def fake_retry_provider_request(name, factory, max_attempts=None):
        return await factory()

    monkeypatch.setattr(
        gemini_source_module,
        "retry_provider_request",
        fake_retry_provider_request,
    )

    with pytest.raises(APIError, match="unhandled stream failure"):
        _ = [
            response
            async for response in provider._query_stream(
                {
                    "messages": [{"role": "user", "content": "hello"}],
                    "model": "gemini-test",
                },
                tools=None,
            )
        ]

    provider._prepare_query_config.assert_awaited_once()


@pytest.mark.asyncio
async def test_gemini_text_chat_stream_stops_when_error_handler_declines_retry():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.api_keys = ["key-a", "key-b"]
    provider.get_model = lambda: "gemini-test"
    provider.assemble_context = AsyncMock(
        return_value={"role": "user", "content": "prompt"}
    )
    provider._ensure_message_to_dicts = lambda contexts: list(contexts)
    provider._handle_api_error = AsyncMock(return_value=False)
    stream_calls: list[dict] = []

    async def fake_query_stream(payloads, func_tool, *, request_max_retries=None):
        stream_calls.append(payloads)
        raise APIError(500, {"message": "fatal"})
        yield

    provider._query_stream = fake_query_stream

    responses = [
        item
        async for item in provider.text_chat_stream(
            prompt="hello",
            contexts=[{"role": "assistant", "content": "keep", "_no_save": True}],
            system_prompt="system",
            request_max_retries=2,
        )
    ]

    assert responses == []
    assert stream_calls == [
        {
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "assistant", "content": "keep"},
                {"role": "user", "content": "prompt"},
            ],
            "model": "gemini-test",
        }
    ]
    provider._handle_api_error.assert_awaited_once()
    assert provider._handle_api_error.await_args.args[1] == ["key-a", "key-b"]


@pytest.mark.asyncio
async def test_gemini_terminate_closes_clients_and_clears_references():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.client = AsyncMock()
    current_client = SimpleNamespace(name="current")
    stale_clients = [
        SimpleNamespace(name="stale-1"),
        SimpleNamespace(name="stale-2"),
    ]
    provider._http_client = current_client
    provider._stale_http_clients = list(stale_clients)
    provider._close_httpx_client = AsyncMock()

    await provider.terminate()

    provider._close_httpx_client.assert_has_awaits(
        [call(stale_clients[0]), call(stale_clients[1]), call(current_client)]
    )
    assert provider._close_httpx_client.await_count == 3
    assert provider.client is None
    assert provider._stale_http_clients == []
    assert provider._http_client is None


@pytest.mark.asyncio
async def test_gemini_terminate_swallows_client_aclose_errors():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    client = AsyncMock()
    client.aclose.side_effect = RuntimeError("close failed")
    provider.client = client
    provider._http_client = None
    provider._stale_http_clients = []
    provider._close_httpx_client = AsyncMock()

    await provider.terminate()

    client.aclose.assert_awaited_once()
    provider._close_httpx_client.assert_awaited_once_with(None)
    assert provider.client is None


@pytest.mark.asyncio
async def test_gemini_close_httpx_client_swallows_aclose_errors():
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    client = AsyncMock()
    client.aclose.side_effect = RuntimeError("close failed")

    await provider._close_httpx_client(client)

    client.aclose.assert_awaited_once()
