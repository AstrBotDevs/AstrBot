import asyncio
import base64
import copy
import json
from contextlib import asynccontextmanager
from io import BytesIO
from types import SimpleNamespace

import aiohttp
import pytest
from aiohttp import ClientConnectionError
from anthropic import BadRequestError
from anthropic import _base_client as anthropic_base_client
from anthropic.types import Message, MessageDeltaUsage, TextBlock, Usage
from PIL import Image

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.provider.entities import LLMResponse, TokenUsage
from astrbot.core.provider.sources.anthropic_source import (
    ProviderAnthropic,
    _PublicImageResolver,
)

# The SDK bundles its own httpx (``httpx`` before 1.0.0, ``httpx2`` after).
sdk_httpx = getattr(
    anthropic_base_client, "httpx", getattr(anthropic_base_client, "httpx2", None)
)


def _provider() -> ProviderAnthropic:
    return ProviderAnthropic.__new__(ProviderAnthropic)


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize(
    "reference",
    [
        "http",
        "https",
        "path",
        "file",
        "base64",
        "data",
        "missing",
        "download_error",
        "invalid_data",
        "unsupported_format",
        "truncated_png",
        "oversize",
        "redirect",
        "ip_literal",
        "bare_base64",
    ],
)
async def test_history_images_survive_repeated_requests(
    monkeypatch, tmp_path, streaming, reference
):
    image = Image.new("RGB", (2, 2))
    png = BytesIO()
    image.save(png, format="PNG")
    image_bytes = png.getvalue()
    bmp = BytesIO()
    image.save(bmp, format="BMP")
    encoded = base64.b64encode(image_bytes).decode()
    source = tmp_path / "image.png"
    source.write_bytes(image_bytes)
    refs = {
        "http": "http://example.com/image.png",
        "https": "https://example.com/image.png",
        "path": str(source),
        "file": source.as_uri(),
        "base64": "base64://" + encoded,
        "bare_base64": encoded,
        "data": "data:image/png;base64," + encoded,
        "missing": str(tmp_path / "missing.png"),
        "invalid_data": "data:image/png;base64,!!!!",
        "download_error": "https://example.com/unavailable.png",
        "unsupported_format": "https://example.com/image.bmp",
        "truncated_png": "data:image/png;base64,"
        + base64.b64encode(image_bytes[:33]).decode(),
        "oversize": "https://example.com/large.png",
        "redirect": "https://example.com/moved.png",
        "ip_literal": "http://127.0.0.1/image.png",
    }
    remote_refs = {
        "http",
        "https",
        "download_error",
        "unsupported_format",
        "oversize",
        "redirect",
    }

    @asynccontextmanager
    async def get(session, url, *, allow_redirects, headers):
        assert reference in remote_refs
        assert str(url) == refs[reference]
        assert not allow_redirects
        assert not session.trust_env
        if reference == "download_error":
            raise ClientConnectionError("Image download failed")

        async def chunks(size):
            yield bmp.getvalue() if reference == "unsupported_format" else image_bytes

        yield SimpleNamespace(
            status=302 if reference == "redirect" else 200,
            content=SimpleNamespace(iter_chunked=chunks),
        )

    monkeypatch.setattr(aiohttp.ClientSession, "get", get)
    if reference == "oversize":
        monkeypatch.setattr(
            ProviderAnthropic, "_HISTORY_IMAGE_MAX_BYTES", len(image_bytes) - 1
        )
    provider = ProviderAnthropic({"model": "claude-test"}, {}, use_api_key=False)
    captured = []

    async def query(payloads, tools, **kwargs):
        provider._sanitize_assistant_messages(payloads)
        captured.append(payloads)
        return LLMResponse(role="assistant", completion_text="ok")

    async def query_stream(payloads, tools, **kwargs):
        yield await query(payloads, tools, **kwargs)

    monkeypatch.setattr(provider, "_query", query)
    monkeypatch.setattr(provider, "_query_stream", query_stream)
    history = [
        {
            "role": "user",
            "content": [{"type": "image_url", "image_url": {"url": refs[reference]}}],
        },
        {"role": "assistant", "content": "Previous answer"},
    ]
    for _ in range(3):
        original = copy.deepcopy(history)
        if streaming:
            responses = [
                response
                async for response in provider.text_chat_stream(
                    prompt="Look at the picture again", contexts=history
                )
            ]
            assert responses[-1].completion_text == "ok"
        else:
            response = await provider.text_chat(
                prompt="Look at the picture again", contexts=history
            )
            assert response.completion_text == "ok"
        assert history == original
        first_message = captured[-1]["messages"][0]
        assert first_message["role"] == "user"
        if reference not in {"http", "https", "data", "base64", "bare_base64"}:
            assert first_message["content"] == [
                {"type": "text", "text": "[Image unavailable]"}
            ]
        else:
            assert first_message["content"] == [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": encoded,
                    },
                }
            ]
        history.extend(
            [
                {"role": "user", "content": "Look at the picture again"},
                {"role": "assistant", "content": "ok"},
            ]
        )


@pytest.mark.asyncio
async def test_history_images_share_one_download_deadline(monkeypatch):
    requested = []

    @asynccontextmanager
    async def slow_get(session, url, **kwargs):
        requested.append(str(url))
        await asyncio.Event().wait()
        yield

    monkeypatch.setattr(aiohttp.ClientSession, "get", slow_get)
    monkeypatch.setattr(ProviderAnthropic, "_HISTORY_IMAGE_TIMEOUT", 0.05)
    refs = ["https://example.com/slow.png", "https://example.com/next.png"]
    _, messages = await _provider()._prepare_payload(
        [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": ref}} for ref in refs
                ],
            }
        ]
    )
    assert requested == refs[:1]
    assert messages[0]["content"] == [
        {"type": "text", "text": "[Image unavailable]"},
        {"type": "text", "text": "[Image unavailable]"},
    ]


@pytest.mark.asyncio
async def test_history_image_resolver_only_returns_public_destinations(monkeypatch):
    async def resolve(self, host, port, family):
        return [
            {"host": address}
            for address in (
                "127.0.0.1",
                "10.0.0.2",
                "224.0.0.1",
                "::1",
                "::ffff:127.0.0.1",
                "93.184.216.34",
            )
            if host == "example.com" or address != "93.184.216.34"
        ]

    monkeypatch.setattr(aiohttp.ThreadedResolver, "resolve", resolve)
    resolver = _PublicImageResolver()
    assert await resolver.resolve("example.com") == [{"host": "93.184.216.34"}]
    with pytest.raises(OSError, match="no public address"):
        await resolver.resolve("internal.example")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("custom_headers", "expected_key"),
    [({}, "test-key"), ({"x-api-key": "override-key"}, "override-key")],
)
async def test_anthropic_request_sends_single_api_key_header(
    monkeypatch, custom_headers, expected_key
):
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_CUSTOM_HEADERS", raising=False)

    def handle(request):
        assert request.headers.get_list("x-api-key") == [expected_key]
        return sdk_httpx.Response(200, json={})

    async with sdk_httpx.AsyncClient(
        transport=sdk_httpx.MockTransport(handle)
    ) as http_client:
        monkeypatch.setattr(
            ProviderAnthropic,
            "_create_http_client",
            lambda self, config: http_client,
        )
        provider = ProviderAnthropic(
            provider_config={
                "key": ["test-key"],
                "api_base": "https://opencode.ai/zen/go",
                "custom_headers": custom_headers,
            },
            provider_settings={},
        )
        provider.client.max_retries = 0
        await provider.client.messages.with_raw_response.create(
            model="claude-test",
            max_tokens=16,
            messages=[{"role": "user", "content": "hi"}],
        )


def test_anthropic_extract_usage_counts_cache_creation_input():
    provider = _provider()

    usage = provider._extract_usage(
        Usage(
            input_tokens=10,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=50,
            output_tokens=20,
        )
    )

    # Anthropic's input_tokens excludes cache writes, so cache_creation
    # must be folded into input_other to keep total input accurate.
    assert usage.input_other == 60
    assert usage.input_cached == 100
    assert usage.input == 160
    assert usage.output == 20


def test_anthropic_extract_usage_without_cache_breakpoints():
    provider = _provider()

    usage = provider._extract_usage(Usage(input_tokens=30, output_tokens=10))

    assert usage.input_other == 30
    assert usage.input_cached == 0
    assert usage.input == 30
    assert usage.output == 10


def test_anthropic_extract_usage_none_returns_empty():
    provider = _provider()

    assert provider._extract_usage(None) == TokenUsage()


def test_anthropic_update_usage_counts_cache_creation_input():
    provider = _provider()
    token_usage = TokenUsage(input_other=5, input_cached=0, output=0)

    provider._update_usage(
        token_usage,
        MessageDeltaUsage(
            input_tokens=10,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=50,
            output_tokens=20,
        ),
    )

    assert token_usage.input_other == 60
    assert token_usage.input_cached == 100
    assert token_usage.input == 160
    assert token_usage.output == 20


def test_anthropic_update_usage_omitted_fields_are_preserved():
    provider = _provider()
    token_usage = TokenUsage(input_other=5, input_cached=0, output=0)

    # message_delta usage only carries output tokens in practice.
    provider._update_usage(token_usage, MessageDeltaUsage(output_tokens=7))

    assert token_usage.input_other == 5
    assert token_usage.input_cached == 0
    assert token_usage.output == 7


@pytest.mark.asyncio
async def test_query_merges_custom_server_tools_with_registered_tools():
    provider = ProviderAnthropic(
        provider_config={
            "id": "anthropic-test",
            "type": "anthropic_chat_completion",
            "model": "claude-test",
            "key": ["test-key"],
            "custom_extra_body": {
                "tools": [{"type": "web_search_20250305", "name": "web_search"}],
                "custom_flag": True,
            },
        },
        provider_settings={},
    )

    captured: dict[str, object] = {}

    class FakeMessages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return Message(
                id="msg_1",
                content=[TextBlock(text="ok", type="text")],
                model="claude-test",
                role="assistant",
                stop_reason="end_turn",
                stop_sequence=None,
                type="message",
                usage=Usage(input_tokens=1, output_tokens=1),
            )

    provider.client = SimpleNamespace(messages=FakeMessages())

    tool_set = ToolSet(
        [
            FunctionTool(
                name="get_time",
                description="Get the current time.",
                parameters={"type": "object", "properties": {}},
            )
        ]
    )

    await provider._query({"model": "claude-test", "messages": []}, tool_set)

    # Server-side tools from the custom body must coexist with the
    # registered function tools instead of replacing them.
    assert [tool["name"] for tool in captured["tools"]] == ["get_time", "web_search"]
    assert "tools" not in captured["extra_body"]
    assert captured["extra_body"]["custom_flag"] is True


@pytest.mark.asyncio
async def test_query_custom_tools_without_registered_tools_pass_through():
    provider = ProviderAnthropic(
        provider_config={
            "id": "anthropic-test",
            "type": "anthropic_chat_completion",
            "model": "claude-test",
            "key": ["test-key"],
            "custom_extra_body": {
                "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            },
        },
        provider_settings={},
    )

    captured: dict[str, object] = {}

    class FakeMessages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return Message(
                id="msg_1",
                content=[TextBlock(text="ok", type="text")],
                model="claude-test",
                role="assistant",
                stop_reason="end_turn",
                stop_sequence=None,
                type="message",
                usage=Usage(input_tokens=1, output_tokens=1),
            )

    provider.client = SimpleNamespace(messages=FakeMessages())

    await provider._query({"model": "claude-test", "messages": []}, None)

    # No registered tools: the custom body keeps its previous override
    # semantics and goes out via extra_body untouched.
    assert "tools" not in captured
    assert captured["extra_body"]["tools"] == [
        {"type": "web_search_20250305", "name": "web_search"}
    ]


@pytest.mark.asyncio
async def test_query_custom_tool_overrides_registered_tool_with_same_name():
    provider = ProviderAnthropic(
        provider_config={
            "id": "anthropic-test",
            "type": "anthropic_chat_completion",
            "model": "claude-test",
            "key": ["test-key"],
            "custom_extra_body": {
                "tools": [
                    {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}
                ],
            },
        },
        provider_settings={},
    )

    captured: dict[str, object] = {}

    class FakeMessages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return Message(
                id="msg_1",
                content=[TextBlock(text="ok", type="text")],
                model="claude-test",
                role="assistant",
                stop_reason="end_turn",
                stop_sequence=None,
                type="message",
                usage=Usage(input_tokens=1, output_tokens=1),
            )

    provider.client = SimpleNamespace(messages=FakeMessages())

    tool_set = ToolSet(
        [
            FunctionTool(
                name="web_search",
                description="Client-side web search.",
                parameters={"type": "object", "properties": {}},
            )
        ]
    )

    await provider._query({"model": "claude-test", "messages": []}, tool_set)

    # A name collision must not duplicate the tool (the API rejects
    # duplicates); the custom body keeps its override authority.
    assert captured["tools"] == [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}
    ]


@pytest.mark.asyncio
async def test_query_null_custom_extra_body_does_not_break_request():
    provider = ProviderAnthropic(
        provider_config={
            "id": "anthropic-test",
            "type": "anthropic_chat_completion",
            "model": "claude-test",
            "key": ["test-key"],
            "custom_extra_body": None,
        },
        provider_settings={},
    )

    captured: dict[str, object] = {}

    class FakeMessages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return Message(
                id="msg_1",
                content=[TextBlock(text="ok", type="text")],
                model="claude-test",
                role="assistant",
                stop_reason="end_turn",
                stop_sequence=None,
                type="message",
                usage=Usage(input_tokens=1, output_tokens=1),
            )

    provider.client = SimpleNamespace(messages=FakeMessages())

    tool_set = ToolSet(
        [
            FunctionTool(
                name="get_time",
                description="Get the current time.",
                parameters={"type": "object", "properties": {}},
            )
        ]
    )

    await provider._query({"model": "claude-test", "messages": []}, tool_set)

    assert [tool["name"] for tool in captured["tools"]] == ["get_time"]
    assert captured["extra_body"] == {}


def _tool_use_stream(
    partial_json_chunks: list[str], start_input: dict | None = None
) -> bytes:
    events = [
        {
            "type": "message_start",
            "message": {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-test",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 1},
            },
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {
                "type": "tool_use",
                "id": "toolu_01",
                "name": "get_time",
                "input": start_input or {},
            },
        },
        *(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": chunk},
            }
            for chunk in partial_json_chunks
        ),
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use", "stop_sequence": None},
            "usage": {"output_tokens": 5},
        },
        {"type": "message_stop"},
    ]
    return "".join(
        f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events
    ).encode()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chunks", "start_input", "expected_args"),
    [
        ([""], None, {}),
        ([], None, {}),
        (["", '{"tz": "UTC"}'], None, {"tz": "UTC"}),
        ([], {"tz": "UTC"}, {"tz": "UTC"}),
    ],
)
async def test_anthropic_stream_keeps_tool_call_with_empty_input(
    monkeypatch, chunks, start_input, expected_args
):
    body = _tool_use_stream(chunks, start_input)
    transport = sdk_httpx.MockTransport(
        lambda request: sdk_httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=body
        )
    )
    monkeypatch.setattr(
        ProviderAnthropic,
        "_create_http_client",
        lambda self, provider_config: sdk_httpx.AsyncClient(transport=transport),
    )
    provider = ProviderAnthropic(
        {
            "id": "test",
            "type": "anthropic_chat_completion",
            "key": ["sk-test"],
            "model": "claude-test",
            "api_base": "https://api.anthropic.test",
        },
        {},
    )
    tools = ToolSet(
        [
            FunctionTool(
                name="get_time",
                description="Return the current time.",
                parameters={"type": "object", "properties": {}},
            )
        ]
    )
    payloads = {
        "messages": [{"role": "user", "content": "what time is it?"}],
        "model": "claude-test",
    }

    try:
        responses = [r async for r in provider._query_stream(payloads, tools)]
    finally:
        await provider.terminate()

    tool_chunks = [r for r in responses if r.role == "tool"]
    assert len(tool_chunks) == 1
    final = responses[-1]
    assert not final.is_chunk
    for response in (tool_chunks[0], final):
        assert response.tools_call_name == ["get_time"]
        assert response.tools_call_args == [expected_args]
        assert response.tools_call_ids == ["toolu_01"]


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True], ids=["standard", "stream"])
@pytest.mark.parametrize(
    "custom_tool",
    [{}, {"name": ""}, {"name": None}, None, "invalid", 0, False],
    ids=["missing-name", "empty-name", "null-name", "null", "string", "zero", "false"],
)
async def test_malformed_custom_tools_reach_api_validation(
    monkeypatch, streaming, custom_tool
):
    captured = []

    def handle(request):
        captured.append(json.loads(request.content))
        return sdk_httpx.Response(
            400,
            json={
                "type": "error",
                "error": {"type": "invalid_request_error", "message": "Invalid tool"},
            },
        )

    monkeypatch.setattr(
        ProviderAnthropic,
        "_create_http_client",
        lambda self, config: sdk_httpx.AsyncClient(
            transport=sdk_httpx.MockTransport(handle)
        ),
    )
    custom_tools = [custom_tool, {"type": "unnamed"}]
    provider = ProviderAnthropic(
        {
            "id": "test",
            "type": "anthropic_chat_completion",
            "key": ["test-key"],
            "model": "claude-test",
            "api_base": "https://offline.invalid",
            "custom_extra_body": {"tools": custom_tools},
        },
        {},
    )
    tools = ToolSet(
        [
            FunctionTool(
                name="get_time",
                description="Offline tool schema.",
                parameters={"type": "object", "properties": {}},
            )
        ]
    )
    payload = {"model": "claude-test", "messages": [{"role": "user", "content": "hi"}]}
    try:
        for _ in range(2):
            with pytest.raises(BadRequestError):
                if streaming:
                    async for _ in provider._query_stream(
                        payload, tools, request_max_retries=1
                    ):
                        pass
                else:
                    await provider._query(payload, tools, request_max_retries=1)
    finally:
        await provider.terminate()

    assert len(captured) == 2
    assert captured[0] == captured[1]
    assert captured[0]["tools"][0]["name"] == "get_time"
    assert captured[0]["tools"][1:] == custom_tools
    assert provider.provider_config["custom_extra_body"]["tools"] == custom_tools


@pytest.mark.asyncio
async def test_query_concatenates_multiple_text_blocks():
    provider = ProviderAnthropic(
        provider_config={
            "id": "anthropic-test",
            "type": "anthropic_chat_completion",
            "model": "claude-test",
            "key": ["test-key"],
        },
        provider_settings={},
    )

    class FakeMessages:
        async def create(self, **kwargs):
            return Message(
                id="msg_1",
                content=[
                    TextBlock(text="Let me search. ", type="text"),
                    TextBlock(text="The answer is ", type="text"),
                    TextBlock(text="42.", type="text"),
                ],
                model="claude-test",
                role="assistant",
                stop_reason="end_turn",
                stop_sequence=None,
                type="message",
                usage=Usage(input_tokens=1, output_tokens=1),
            )

    provider.client = SimpleNamespace(messages=FakeMessages())

    response = await provider._query({"model": "claude-test", "messages": []}, None)

    assert response.completion_text == "Let me search. The answer is 42."
