import asyncio
from types import SimpleNamespace

import pytest

import astrbot.core.provider.sources.openai_responses_source as openai_responses_module
from astrbot.core.agent.history_sanitizer import IMAGE_HISTORY_PLACEHOLDER
from astrbot.core.agent.message import ProviderMessageState
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.exceptions import ProviderResponseError
from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)


def _provider() -> ProviderOpenAIResponses:
    provider = ProviderOpenAIResponses.__new__(ProviderOpenAIResponses)
    provider.provider_config = {
        "id": "responses",
        "responses_state_mode": "stateless",
        "store": False,
    }
    provider.model_name = "gpt-test"
    return provider


def test_responses_provider_is_direct_provider_subclass():
    from astrbot.core.provider.provider import Provider

    assert ProviderOpenAIResponses.__bases__ == (Provider,)


@pytest.mark.asyncio
async def test_responses_history_keeps_omitted_images_as_text() -> None:
    provider = _provider()

    items, instructions = await provider._input_items_from_history(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": IMAGE_HISTORY_PLACEHOLDER},
                    },
                ],
            },
        ],
        "gpt-test",
    )

    assert instructions == ""
    assert items == [
        {
            "role": "user",
            "content": [{"type": "input_text", "text": IMAGE_HISTORY_PLACEHOLDER}],
        },
    ]


@pytest.mark.asyncio
async def test_responses_history_uses_output_text_for_assistant_messages() -> None:
    provider = _provider()

    items, instructions = await provider._input_items_from_history(
        [
            {"role": "assistant", "content": "previous answer"},
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "another answer"}],
            },
        ],
        "gpt-test",
    )

    assert instructions == ""
    assert items == [
        {
            "role": "assistant",
            "content": [{"type": "output_text", "text": "previous answer"}],
        },
        {
            "role": "assistant",
            "content": [{"type": "output_text", "text": "another answer"}],
        },
    ]


def test_null_api_version_uses_regular_openai_client(monkeypatch):
    created = []

    def regular_client(**kwargs):
        created.append(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(openai_responses_module, "AsyncOpenAI", regular_client)
    monkeypatch.setattr(
        openai_responses_module,
        "AsyncAzureOpenAI",
        lambda **_kwargs: pytest.fail("null api_version must not select Azure"),
    )
    monkeypatch.setattr(
        openai_responses_module,
        "create_proxy_client",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )

    ProviderOpenAIResponses(
        {
            "id": "responses",
            "type": "openai_responses",
            "model": "gpt-test",
            "key": ["test-key"],
            "api_version": None,
        },
        {},
    )

    assert created[0]["base_url"] is None


def test_responses_tools_preserve_plugin_schema():
    tool = FunctionTool(
        name="weather",
        description="Weather",
        parameters={"type": "object", "properties": {"city": {"type": "string"}}},
        handler=None,
    )
    schema = ToolSet([tool]).openai_responses_schema()
    assert schema == [
        {
            "type": "function",
            "name": "weather",
            "description": "Weather",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
            },
        }
    ]


def test_responses_schema_preserves_nested_optional_fields():
    tool = FunctionTool(
        name="send_message_to_user",
        description="Send messages",
        parameters={
            "type": "object",
            "properties": {
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "channel": {"type": "string"},
                        },
                    },
                }
            },
        },
        handler=None,
    )

    schema = ToolSet([tool]).openai_responses_schema()[0]

    assert schema["parameters"] == {
        "type": "object",
        "properties": {
            "messages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "channel": {"type": "string"},
                    },
                },
            }
        },
    }


def test_responses_schema_keeps_free_form_object_schema():
    tool = FunctionTool(
        name="shell",
        description="Run shell",
        parameters={
            "type": "object",
            "properties": {
                "environment": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                }
            },
        },
        handler=None,
    )

    schema = ToolSet([tool]).openai_responses_schema()[0]

    assert "strict" not in schema
    assert "required" not in schema["parameters"]
    assert schema["parameters"]["properties"]["environment"][
        "additionalProperties"
    ] == {"type": "string"}


def test_native_web_search_uses_only_current_responses_tool_fields():
    provider = _provider()
    provider.provider_config["web_search"] = {
        "enable": True,
        "search_context_size": "high",
        "allowed_domains": ["example.com"],
        "user_location": {"type": "approximate", "country": "US"},
        "include_sources": True,
        "include_raw_results": True,
    }

    tools = provider._tools(None)
    options = provider._request_options(
        model="gpt-test",
        items=[],
        instructions="",
        func_tool=None,
        tool_choice="auto",
        extra={},
    )

    assert tools == [
        {
            "type": "web_search",
            "search_context_size": "high",
            "filters": {"allowed_domains": ["example.com"]},
            "user_location": {"type": "approximate", "country": "US"},
        }
    ]
    assert options["include"] == [
        "reasoning.encrypted_content",
        "web_search_call.action.sources",
        "web_search_call.results",
    ]


def test_responses_omits_boolean_reasoning_capability_but_keeps_reasoning_object():
    provider = _provider()
    provider.provider_config["reasoning"] = True

    options = provider._request_options(
        model="gpt-test",
        items=[],
        instructions="",
        func_tool=None,
        tool_choice="auto",
        extra={},
    )

    assert "reasoning" not in options

    provider.provider_config["reasoning"] = {"effort": "medium"}
    options = provider._request_options(
        model="gpt-test",
        items=[],
        instructions="",
        func_tool=None,
        tool_choice="auto",
        extra={},
    )

    assert options["reasoning"] == {"effort": "medium"}


def test_parse_responses_output_tools_usage_and_citations():
    provider = _provider()
    response = SimpleNamespace(
        id="resp_1",
        model="gpt-test",
        status="completed",
        incomplete_details=None,
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=4,
            input_tokens_details=SimpleNamespace(cached_tokens=3),
        ),
        output=[
            SimpleNamespace(
                type="message",
                content=[
                    SimpleNamespace(
                        type="output_text",
                        text="hello",
                        annotations=[
                            SimpleNamespace(
                                type="url_citation",
                                url="https://example.com",
                                title="Example",
                                start_index=0,
                                end_index=5,
                            )
                        ],
                    )
                ],
            ),
            SimpleNamespace(
                type="function_call",
                call_id="call_1",
                name="weather",
                arguments='{"city":"Paris"}',
                content=[],
            ),
            SimpleNamespace(
                type="web_search_call",
                action=SimpleNamespace(
                    sources=[
                        SimpleNamespace(
                            url="https://source.example",
                            title="Source",
                            snippet="Source snippet",
                        )
                    ]
                ),
                content=[],
            ),
        ],
    )

    result = provider._parse(response)

    assert result.completion_text == "hello"
    assert result.tools_call_args == [{"city": "Paris"}]
    assert result.usage.input_other == 7
    assert result.citations[0].url == "https://example.com"
    assert result.sources[0].url == "https://source.example"
    assert result.provider_state.data["response_id"] == "resp_1"


@pytest.mark.asyncio
async def test_responses_reject_audio_input():
    provider = _provider()
    with pytest.raises(Exception, match="audio input"):
        await provider.text_chat(audio_urls=["x.wav"])


def _completed_response(*, response_id: str = "resp_1"):
    return SimpleNamespace(
        id=response_id,
        model="gpt-test",
        status="completed",
        incomplete_details=None,
        usage=SimpleNamespace(
            input_tokens=2,
            output_tokens=1,
            input_tokens_details=SimpleNamespace(cached_tokens=0),
        ),
        output=[
            SimpleNamespace(
                type="message",
                content=[
                    SimpleNamespace(type="output_text", text="done", annotations=[])
                ],
            )
        ],
    )


class _ResponsesClient:
    def __init__(self, response):
        self.response = response
        self.create_calls = []
        self.retrieve_calls = []
        self.cancel_calls = []
        self.conversation_creations = 0

    async def create(self, **options):
        self.create_calls.append(options)
        return self.response

    async def retrieve(self, response_id, **options):
        self.retrieve_calls.append((response_id, options))
        return self.response

    async def cancel(self, response_id):
        self.cancel_calls.append(response_id)
        return self.response


def _configured_provider(config: dict, client: _ResponsesClient):
    provider = _provider()
    provider.provider_config = {"id": "responses", **config}
    provider.api_keys = ["key"]
    provider._client_for = lambda _key: SimpleNamespace(
        responses=client,
        conversations=SimpleNamespace(create=provider_conversation_create(client)),
    )
    return provider


def provider_conversation_create(client: _ResponsesClient):
    async def create():
        client.conversation_creations += 1
        return SimpleNamespace(id="conv_1")

    return create


@pytest.mark.asyncio
async def test_stateless_state_replays_input_safe_output_items():
    provider = _provider()
    replayed = [
        {
            "type": "reasoning",
            "id": "rs_1",
            "encrypted_content": "ciphertext",
            "summary": [],
            "status": "completed",
        },
        {
            "type": "message",
            "id": "msg_1",
            "role": "assistant",
            "content": [],
            "status": "completed",
        },
    ]
    state = ProviderMessageState(
        provider_type="openai_responses",
        provider_id="responses",
        model="gpt-test",
        data={"output_items": replayed},
    )

    items, _ = await provider._input_items(
        [{"role": "assistant", "content": "ignored", "provider_state": state}],
        "next",
        None,
        None,
        "gpt-test",
    )

    assert items[:2] == [
        {
            "type": "reasoning",
            "id": "rs_1",
            "encrypted_content": "ciphertext",
            "summary": [],
        },
        {"type": "message", "id": "msg_1", "role": "assistant", "content": []},
    ]
    assert replayed[0]["status"] == "completed"
    assert items[2] == {
        "role": "user",
        "content": [{"type": "input_text", "text": "next"}],
    }


@pytest.mark.asyncio
async def test_previous_response_id_sends_only_incremental_input():
    client = _ResponsesClient(_completed_response(response_id="resp_2"))
    provider = _configured_provider(
        {"responses_state_mode": "previous_response_id", "store": True}, client
    )
    previous_user = {"role": "user", "content": "first"}
    state = ProviderMessageState(
        provider_type="openai_responses",
        provider_id="responses",
        model="gpt-test",
        data={
            "response_id": "resp_1",
            "context_fingerprint": provider._fingerprint([previous_user]),
        },
    )

    await provider.text_chat(
        prompt="second",
        contexts=[
            previous_user,
            {"role": "assistant", "content": "first answer", "provider_state": state},
        ],
    )

    options = client.create_calls[0]
    assert options["previous_response_id"] == "resp_1"
    assert options["input"] == [
        {"role": "user", "content": [{"type": "input_text", "text": "second"}]}
    ]
    assert options["store"] is True


@pytest.mark.asyncio
async def test_conversation_state_creates_and_attaches_conversation():
    client = _ResponsesClient(_completed_response())
    provider = _configured_provider(
        {"responses_state_mode": "conversation", "store": True}, client
    )

    result = await provider.text_chat(prompt="hello")

    assert client.conversation_creations == 1
    assert client.create_calls[0]["conversation"] == "conv_1"
    assert result.provider_state.data["conversation_id"] == "conv_1"


@pytest.mark.asyncio
async def test_background_polling_is_abortable_and_cancels_remote_response():
    queued = SimpleNamespace(id="resp_background", status="queued")
    client = _ResponsesClient(queued)
    provider = _provider()
    provider.provider_config.update(
        {
            "responses_background_timeout": 60,
            "responses_background_poll_interval": 60,
        }
    )
    signal = asyncio.Event()
    task = asyncio.create_task(
        provider._poll_background(SimpleNamespace(responses=client), queued, signal)
    )
    await asyncio.sleep(0)
    signal.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.cancel_calls == ["resp_background"]


@pytest.mark.asyncio
async def test_background_timeout_cancels_remote_response():
    queued = SimpleNamespace(id="resp_background", status="queued")
    client = _ResponsesClient(queued)
    provider = _provider()
    provider.provider_config.update(
        {
            "responses_background_timeout": 0,
            "responses_background_poll_interval": 1,
        }
    )

    with pytest.raises(ProviderResponseError, match="timed out"):
        await provider._poll_background(SimpleNamespace(responses=client), queued, None)
    assert client.cancel_calls == ["resp_background"]


class _EventStream:
    def __init__(self, events):
        self.events = iter(events)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            event = next(self.events)
        except StopIteration as exc:
            raise StopAsyncIteration from exc
        if isinstance(event, BaseException):
            raise event
        return event


class _BlockingEventStream:
    def __init__(self, first_event):
        self.first_event = first_event
        self.first_sent = False
        self.waiting = asyncio.Event()
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.first_sent:
            self.first_sent = True
            return self.first_event
        self.waiting.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_stream_uses_call_id_for_function_argument_deltas_and_final_response():
    final = _completed_response()
    final.output.append(
        SimpleNamespace(
            type="function_call",
            id="item_1",
            call_id="call_1",
            name="weather",
            arguments='{"city":"Paris"}',
            content=[],
        )
    )
    stream = _EventStream(
        [
            SimpleNamespace(
                type="response.output_item.added",
                response_id="resp_1",
                sequence_number=1,
                item=SimpleNamespace(
                    type="function_call",
                    id="item_1",
                    call_id="call_1",
                    name="weather",
                ),
            ),
            SimpleNamespace(
                type="response.function_call_arguments.delta",
                response_id="resp_1",
                sequence_number=2,
                item_id="item_1",
                delta='{"city":',
            ),
            SimpleNamespace(
                type="response.function_call_arguments.done",
                response_id="resp_1",
                sequence_number=3,
                item_id="item_1",
                output_index=0,
                name="weather",
                arguments='{"city":"Paris"}',
            ),
            SimpleNamespace(
                type="response.completed",
                response=final,
                sequence_number=4,
            ),
        ]
    )
    client = _ResponsesClient(stream)
    provider = _configured_provider({}, client)

    responses = [item async for item in provider.text_chat_stream(prompt="weather")]

    assert responses[0].tools_call_ids == ["call_1"]
    assert responses[0].tools_call_name == ["weather"]
    assert responses[0].tools_call_extra_content == {
        "call_1": {"arguments_delta": '{"city":'}
    }
    assert responses[-1].tools_call_ids == ["call_1"]
    assert responses[-1].tools_call_args == [{"city": "Paris"}]


@pytest.mark.asyncio
async def test_stream_abort_waiting_for_event_cancels_response_and_closes_stream():
    signal = asyncio.Event()
    stream = _BlockingEventStream(
        SimpleNamespace(
            type="response.output_text.delta",
            response_id="resp_abort",
            sequence_number=1,
            delta="visible",
        )
    )
    client = _ResponsesClient(stream)
    provider = _configured_provider({"responses_background": True}, client)
    responses = provider.text_chat_stream(prompt="hello", abort_signal=signal)

    first = await anext(responses)
    assert first.completion_text == "visible"
    waiting = asyncio.create_task(anext(responses))
    await stream.waiting.wait()
    signal.set()

    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert client.cancel_calls == ["resp_abort"]
    assert stream.closed is True


@pytest.mark.asyncio
async def test_background_stream_recovers_from_last_sequence_without_replaying_delta():
    final = _completed_response(response_id="resp_recover")
    initial = _EventStream(
        [
            SimpleNamespace(
                type="response.output_text.delta",
                response_id="resp_recover",
                sequence_number=7,
                delta="once",
            ),
            RuntimeError("connection lost"),
        ]
    )
    recovered = _EventStream(
        [SimpleNamespace(type="response.completed", response=final, sequence_number=8)]
    )

    class Client(_ResponsesClient):
        async def retrieve(self, response_id, **options):
            self.retrieve_calls.append((response_id, options))
            return recovered

    client = Client(initial)
    provider = _configured_provider({"responses_background": True}, client)

    responses = [item async for item in provider.text_chat_stream(prompt="hello")]

    assert [item.completion_text for item in responses[:-1]] == ["once"]
    assert client.retrieve_calls == [
        ("resp_recover", {"stream": True, "starting_after": 7})
    ]


@pytest.mark.asyncio
async def test_non_background_interruption_is_not_replayed():
    stream = _EventStream(
        [
            SimpleNamespace(
                type="response.output_text.delta",
                response_id="resp_no_replay",
                sequence_number=1,
                delta="once",
            ),
            RuntimeError("connection lost"),
        ]
    )
    client = _ResponsesClient(stream)
    provider = _configured_provider({}, client)

    with pytest.raises(ProviderResponseError, match="not replayed"):
        _ = [item async for item in provider.text_chat_stream(prompt="hello")]
    assert client.retrieve_calls == []


@pytest.mark.asyncio
async def test_stream_context_fingerprint_mismatch_uses_full_history():
    final = _completed_response()
    stream = _EventStream([SimpleNamespace(type="response.completed", response=final)])
    client = _ResponsesClient(stream)
    provider = _configured_provider(
        {"responses_state_mode": "previous_response_id", "store": True}, client
    )
    previous_user = {"role": "user", "content": "original"}
    stale_state = ProviderMessageState(
        provider_type="openai_responses",
        provider_id="responses",
        model="gpt-test",
        data={"response_id": "resp_stale", "context_fingerprint": "mismatch"},
    )

    _ = [
        item
        async for item in provider.text_chat_stream(
            prompt="next",
            contexts=[
                previous_user,
                {"role": "assistant", "content": "old", "provider_state": stale_state},
            ],
        )
    ]

    options = client.create_calls[0]
    assert "previous_response_id" not in options
    assert len(options["input"]) == 3


@pytest.mark.asyncio
async def test_stream_conversation_creates_then_reuses_and_persists_state():
    first = _completed_response(response_id="resp_first")
    second = _completed_response(response_id="resp_second")
    client = _ResponsesClient(
        _EventStream([SimpleNamespace(type="response.completed", response=first)])
    )
    provider = _configured_provider(
        {"responses_state_mode": "conversation", "store": True}, client
    )

    first_result = [item async for item in provider.text_chat_stream(prompt="first")][
        -1
    ]
    client.response = _EventStream(
        [SimpleNamespace(type="response.completed", response=second)]
    )
    second_result = [
        item
        async for item in provider.text_chat_stream(
            prompt="second",
            contexts=[
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "first"}],
                },
                {
                    "role": "assistant",
                    "content": "first",
                    "provider_state": first_result.provider_state,
                },
            ],
        )
    ][-1]

    assert client.conversation_creations == 1
    assert (
        client.create_calls[0]["conversation"] == client.create_calls[1]["conversation"]
    )
    assert second_result.provider_state.data["conversation_id"] == "conv_1"


@pytest.mark.asyncio
async def test_stream_requires_completed_event_and_preserves_cancellation():
    client = _ResponsesClient(_EventStream([]))
    provider = _configured_provider({}, client)

    with pytest.raises(ProviderResponseError, match="without response.completed"):
        _ = [item async for item in provider.text_chat_stream(prompt="hello")]

    signal = asyncio.Event()
    signal.set()
    provider = _configured_provider({}, _ResponsesClient(_EventStream([])))
    with pytest.raises(asyncio.CancelledError):
        _ = [
            item
            async for item in provider.text_chat_stream(
                prompt="hello", abort_signal=signal
            )
        ]
