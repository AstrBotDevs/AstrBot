import asyncio
from unittest.mock import AsyncMock

import pytest

import astrbot.core.provider.sources.openai_oauth_source as oauth_source
from tests.test_openai_oauth_source import _make_provider


class _FakeTools:
    def __init__(self, schemas):
        self.schemas = schemas

    def empty(self):
        return not self.schemas

    def get_func_desc_openai_style(self, omit_empty_parameter_field=False):
        assert omit_empty_parameter_field is False
        return self.schemas


@pytest.mark.asyncio
async def test_citations_preserve_message_text_without_top_level_output_text():
    provider = _make_provider()
    try:
        raw = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Actual answer",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://example.com",
                                    "title": "Source",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        result = await provider._parse_responses_completion(raw, None)
        assert result.completion_text.startswith("Actual answer")
        assert "[Source](https://example.com)" in result.completion_text
        assert result.raw_completion == raw
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_stream_delivers_citations_as_visible_delta_once():
    provider = _make_provider()

    async def events(_params):
        yield {"type": "response.output_text.delta", "delta": "Actual answer"}
        yield {
            "type": "response.completed",
            "response": {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Actual answer",
                                "annotations": [
                                    {
                                        "type": "url_citation",
                                        "url": "https://example.com",
                                        "title": "Source",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
        }

    provider._stream_backend_events = events
    try:
        responses = [
            response
            async for response in provider._query_stream({"messages": []}, None)
        ]
        visible = "".join(r.completion_text or "" for r in responses if r.is_chunk)
        assert visible == responses[-1].completion_text
        assert visible.count("Actual answer") == 1
        assert visible.count("[Source](https://example.com)") == 1
    finally:
        await provider.terminate()


def test_citation_urls_cannot_break_markdown_link_boundaries():
    raw = {
        "output": [
            {
                "content": [
                    {
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://example.com/)![x](bad",
                                "title": "x\ny",
                            },
                            {
                                "type": "url_citation",
                                "url": "https://example.com/\nattack",
                                "title": "bad",
                            },
                        ]
                    }
                ]
            }
        ]
    }
    citations = oauth_source.ProviderOpenAIOAuth._extract_url_citations(raw)
    assert len(citations) == 1
    assert citations[0][0] == "x y"
    assert ")" not in citations[0][1] and "[" not in citations[0][1]


@pytest.mark.asyncio
async def test_terminate_closes_active_stream_connections():
    provider = _make_provider()
    active = AsyncMock()
    provider._oauth_stream_clients = {active}
    await provider.terminate()
    active.aclose.assert_awaited_once()
    provider._ensure_fresh_oauth_token = AsyncMock()
    with pytest.raises(RuntimeError, match="closed"):
        await anext(provider._stream_backend_events({}))
    provider._ensure_fresh_oauth_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_nonstream_tool_choice_without_function_tools_reaches_backend():
    provider = _make_provider({"oauth_web_search": "live"})
    provider._record_provider_stat = AsyncMock()
    provider._request_backend = AsyncMock(
        return_value={"output_text": "answer", "output": []}
    )
    try:
        await provider.text_chat(prompt="search", tool_choice="required")
        sent = provider._request_backend.await_args.args[0]
        assert sent["tool_choice"] == "required"
        assert sent["tools"][0]["type"] == "web_search"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_type", ["error", "response.failed", "response.incomplete"]
)
async def test_terminal_stream_events_raise_without_replaying_and_preserve_usage(
    event_type,
):
    provider = _make_provider()
    try:
        event = {
            "type": event_type,
            "message": "private payload",
            "response": {"usage": {"input_tokens": 3, "output_tokens": 2}},
        }
        with pytest.raises(RuntimeError) as caught:
            provider._apply_stream_event(event, [], [], {})
        assert "private payload" not in str(caught.value)
        assert caught.value._astrbot_token_usage.output == 2
    finally:
        await provider.terminate()


class _FakeStreamResponse:
    def __init__(self, status_code, lines=(), body=b""):
        self.status_code = status_code
        self._lines = lines
        self._body = body
        self.exited = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        self.exited = True

    async def aread(self):
        return self._body

    async def aiter_lines(self):
        async for line in self._lines:
            yield line


class _FakeAsyncClient:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def stream(self, *_args, **_kwargs):
        return self.response


async def _lines(*values):
    for value in values:
        yield value


@pytest.mark.asyncio
async def test_stream_emits_incremental_text_reasoning_tool_args_and_complete_final():
    provider = _make_provider()
    provider._record_provider_stat = AsyncMock()
    events = [
        {"type": "response.reasoning_summary_text.delta", "delta": "checking"},
        {"type": "response.output_text.delta", "delta": "hel"},
        {
            "type": "response.output_item.added",
            "item": {
                "id": "item-1",
                "type": "function_call",
                "call_id": "call-1",
                "name": "weather",
                "arguments": "",
            },
        },
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "item-1",
            "delta": '{"city":',
        },
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "item-1",
            "delta": '"Shanghai"}',
        },
        {"type": "response.output_text.delta", "delta": "lo"},
        {
            "type": "response.output_item.done",
            "item": {
                "id": "item-1",
                "type": "function_call",
                "call_id": "call-1",
                "name": "weather",
                "arguments": '{"city":"Shanghai"}',
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-1",
                "status": "completed",
                "output": [],
                "usage": {
                    "input_tokens": 7,
                    "input_tokens_details": {"cached_tokens": 2},
                    "output_tokens": 3,
                },
            },
        },
    ]

    async def fake_events(_payload):
        for event in events:
            yield event

    provider._stream_backend_events = fake_events
    tools = _FakeTools(
        [
            {
                "type": "function",
                "function": {
                    "name": "weather",
                    "description": "Get weather",
                    "parameters": {"type": "object"},
                },
            }
        ]
    )
    try:
        responses = [
            item
            async for item in provider.text_chat_stream(
                prompt="hi",
                func_tool=tools,
                session_id="stream-session",
            )
        ]
    finally:
        await provider.terminate()

    assert [item.reasoning_content for item in responses if item.is_chunk] == [
        "checking",
        None,
        None,
        None,
        None,
    ]
    assert [item.completion_text for item in responses if item.is_chunk] == [
        None,
        "hel",
        None,
        None,
        "lo",
    ]
    tool_chunks = [item for item in responses if item.is_chunk and item.tools_call_ids]
    assert [item.tools_call_args for item in tool_chunks] == [
        [{"_arguments_delta": '{"city":'}],
        [{"_arguments_delta": '"Shanghai"}'}],
    ]
    final = responses[-1]
    assert final.is_chunk is False
    assert final.completion_text == "hello"
    assert final.reasoning_content == "checking"
    assert final.tools_call_ids == ["call-1"]
    assert final.tools_call_name == ["weather"]
    assert final.tools_call_args == [{"city": "Shanghai"}]
    assert final.usage.input_other == 5
    assert final.usage.input_cached == 2
    assert final.usage.output == 3
    provider._record_provider_stat.assert_awaited_once()
    assert provider._record_provider_stat.await_args.kwargs["status"] == "completed"


@pytest.mark.asyncio
async def test_stream_closes_backend_iterator_when_consumer_cancels():
    provider = _make_provider()
    provider._record_provider_stat = AsyncMock()
    closed = asyncio.Event()

    async def fake_events(_payload):
        try:
            yield {"type": "response.output_text.delta", "delta": "first"}
            await asyncio.Event().wait()
        finally:
            closed.set()

    provider._stream_backend_events = fake_events
    stream = provider.text_chat_stream(prompt="hi")
    try:
        first = await anext(stream)
        assert first.completion_text == "first"
        await stream.aclose()
        await asyncio.wait_for(closed.wait(), timeout=1)
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_backend_stream_refreshes_401_before_output_and_closes_both_responses(
    monkeypatch,
):
    unauthorized = _FakeStreamResponse(401, body=b'{"error":"expired"}')
    completed = _FakeStreamResponse(
        200,
        _lines(
            'data: {"type":"response.output_text.delta","delta":"ok"}',
            "",
            'data: {"type":"response.completed","response":{"output_text":"ok"}}',
            "",
        ),
    )
    provider = _make_provider()
    clients = iter([_FakeAsyncClient(unauthorized), _FakeAsyncClient(completed)])
    monkeypatch.setattr(
        oauth_source.httpx, "AsyncClient", lambda **_kwargs: next(clients)
    )
    provider._ensure_fresh_oauth_token = AsyncMock()
    provider._refresh_after_auth_failure = AsyncMock(return_value=True)
    try:
        events = [event async for event in provider._stream_backend_events({})]
    finally:
        await provider.terminate()

    assert [event["type"] for event in events] == [
        "response.output_text.delta",
        "response.completed",
    ]
    provider._refresh_after_auth_failure.assert_awaited_once()
    assert unauthorized.exited is True
    assert completed.exited is True


@pytest.mark.asyncio
async def test_backend_stream_connection_closes_when_consumer_stops(monkeypatch):
    continue_stream = asyncio.Event()

    async def blocking_lines():
        yield 'data: {"type":"response.output_text.delta","delta":"first"}'
        yield ""
        await continue_stream.wait()

    response = _FakeStreamResponse(200, blocking_lines())
    provider = _make_provider()
    monkeypatch.setattr(
        oauth_source.httpx,
        "AsyncClient",
        lambda **_kwargs: _FakeAsyncClient(response),
    )
    provider._ensure_fresh_oauth_token = AsyncMock()
    stream = provider._stream_backend_events({})
    try:
        event = await anext(stream)
        assert event["delta"] == "first"
        await stream.aclose()
    finally:
        continue_stream.set()
        await provider.terminate()

    assert response.exited is True


@pytest.mark.asyncio
async def test_backend_stream_does_not_refresh_403(monkeypatch):
    forbidden = _FakeStreamResponse(403, body=b'{"error":"forbidden"}')
    provider = _make_provider()
    monkeypatch.setattr(
        oauth_source.httpx,
        "AsyncClient",
        lambda **_kwargs: _FakeAsyncClient(forbidden),
    )
    provider._ensure_fresh_oauth_token = AsyncMock()
    provider._refresh_after_auth_failure = AsyncMock(return_value=True)
    try:
        with pytest.raises(Exception, match="status=403"):
            _ = [event async for event in provider._stream_backend_events({})]
    finally:
        await provider.terminate()

    provider._refresh_after_auth_failure.assert_not_awaited()
    assert forbidden.exited is True


@pytest.mark.asyncio
async def test_query_merges_function_and_custom_tools_and_forwards_tool_choice():
    captured = []
    provider = _make_provider(
        {
            "custom_extra_body": {
                "tools": [
                    {"type": "web_search", "external_web_access": False},
                ]
            }
        }
    )

    async def fake_request(payload):
        captured.append(payload)
        return {"id": "resp", "output_text": "ok"}

    provider._request_backend = fake_request
    tools = _FakeTools(
        [
            {
                "type": "function",
                "function": {
                    "name": "weather",
                    "description": "Get weather",
                    "parameters": {"type": "object"},
                },
            }
        ]
    )
    try:
        await provider._query(
            {
                "model": "gpt-5.4",
                "messages": [{"role": "user", "content": "hi"}],
                "tool_choice": "required",
            },
            tools,
        )
    finally:
        await provider.terminate()

    assert captured[0]["tool_choice"] == "required"
    assert captured[0]["tools"] == [
        {
            "type": "function",
            "name": "weather",
            "description": "Get weather",
            "parameters": {"type": "object"},
        },
        {"type": "web_search", "external_web_access": False},
    ]


@pytest.mark.asyncio
async def test_query_rejects_conflicting_duplicate_tools():
    provider = _make_provider(
        {
            "custom_extra_body": {
                "tools": [
                    {
                        "type": "function",
                        "name": "weather",
                        "description": "Different",
                        "parameters": {"type": "object"},
                    }
                ]
            }
        }
    )
    provider._request_backend = AsyncMock(return_value={"output_text": "unused"})
    tools = _FakeTools(
        [
            {
                "type": "function",
                "function": {
                    "name": "weather",
                    "description": "Original",
                    "parameters": {"type": "object"},
                },
            }
        ]
    )
    try:
        with pytest.raises(ValueError, match="weather"):
            await provider._query(
                {
                    "model": "gpt-5.4",
                    "messages": [{"role": "user", "content": "hi"}],
                },
                tools,
            )
        provider._request_backend.assert_not_awaited()
    finally:
        await provider.terminate()


def test_identical_duplicate_tools_are_deduplicated():
    provider = _make_provider()
    tool = {
        "type": "function",
        "name": "weather",
        "description": "Get weather",
        "parameters": {"type": "object"},
    }
    try:
        assert provider._merge_backend_tools([tool], [dict(tool)]) == [tool]
    finally:
        asyncio.run(provider.terminate())


@pytest.mark.asyncio
async def test_custom_function_call_is_preserved_without_astrbot_toolset():
    provider = _make_provider()
    raw = {
        "id": "resp",
        "output": [
            {
                "type": "function_call",
                "call_id": "custom-1",
                "name": "external_action",
                "arguments": '{"value":1}',
            }
        ],
    }
    try:
        response = await provider._parse_responses_completion(raw, None)
    finally:
        await provider.terminate()

    assert response.tools_call_ids == ["custom-1"]
    assert response.tools_call_name == ["external_action"]
    assert response.tools_call_args == [{"value": 1}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "external_access"),
    [("cached", False), ("live", True)],
)
async def test_native_web_search_configuration(mode, external_access):
    captured = []
    provider = _make_provider(
        {
            "oauth_web_search": mode,
            "oauth_web_search_domains": ["openai.com", "docs.python.org"],
        }
    )

    async def fake_request(payload):
        captured.append(payload)
        return {"id": "resp", "output_text": "ok"}

    provider._request_backend = fake_request
    try:
        await provider._query(
            {
                "model": "gpt-5.4",
                "messages": [{"role": "user", "content": "latest"}],
            },
            None,
        )
    finally:
        await provider.terminate()

    assert captured[0]["tools"] == [
        {
            "type": "web_search",
            "external_web_access": external_access,
            "filters": {"allowed_domains": ["openai.com", "docs.python.org"]},
        }
    ]


@pytest.mark.asyncio
async def test_disabled_web_search_does_not_add_tool():
    captured = []
    provider = _make_provider({"oauth_web_search": "disabled"})

    async def fake_request(payload):
        captured.append(payload)
        return {"id": "resp", "output_text": "ok"}

    provider._request_backend = fake_request
    try:
        await provider._query(
            {
                "model": "gpt-5.4",
                "messages": [{"role": "user", "content": "latest"}],
            },
            None,
        )
    finally:
        await provider.terminate()

    assert "tools" not in captured[0]


@pytest.mark.asyncio
async def test_real_url_annotations_are_rendered_and_raw_is_preserved():
    provider = _make_provider()
    raw = {
        "id": "resp",
        "output_text": "Answer",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Answer",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://example.com/source",
                                "title": "Example source",
                            },
                            {"type": "unknown", "title": "Do not invent"},
                        ],
                    }
                ],
            }
        ],
    }
    try:
        response = await provider._parse_responses_completion(raw, None)
    finally:
        await provider.terminate()

    assert response.raw_completion is raw
    assert response.completion_text == (
        "Answer\n\n来源：\n- [Example source](https://example.com/source)"
    )


@pytest.mark.asyncio
async def test_unsupported_audio_and_file_content_are_not_silently_dropped():
    provider = _make_provider()
    try:
        with pytest.raises(ValueError, match="audio"):
            provider._convert_message_content(
                [{"type": "input_audio", "input_audio": {"data": "..."}}]
            )
        with pytest.raises(ValueError, match="file"):
            provider._convert_message_content(
                [{"type": "file", "file": {"file_id": "file-1"}}]
            )
    finally:
        await provider.terminate()
