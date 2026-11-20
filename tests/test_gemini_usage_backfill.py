import gzip
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from google import genai
from google.genai import _common as genai_common
from google.genai import types

from astrbot.core.provider.sources import gemini_usage_backfill as usage_backfill
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI
from astrbot.core.provider.sources.gemini_usage_backfill import (
    GeminiUsageBackfillTransport,
    backfill_usage_metadata,
    backfill_usage_metadata_in_payload,
    wrap_httpx_client_for_usage_backfill,
)


def _relay_usage_metadata(
    *,
    cached_official: Any = 0,
    thoughts_official: Any = 0,
    cached_nested: Any = 10522,
    reasoning_nested: Any = 19,
    include_official_keys: bool = True,
) -> dict[str, Any]:
    usage: dict[str, Any] = {
        "promptTokenCount": 12572,
        "toolUsePromptTokenCount": 0,
        "candidatesTokenCount": 6,
        "totalTokenCount": 12597,
        "promptTokensDetails": None,
        "toolUsePromptTokensDetails": None,
        "candidatesTokensDetails": None,
        "billing_usage": {
            "source": "oai_chat",
            "semantic": "openai",
            "openai_usage": {
                "prompt_tokens": 12572,
                "completion_tokens": 6,
                "total_tokens": 12597,
                "prompt_tokens_details": {
                    "cached_tokens": cached_nested,
                    "text_tokens": 0,
                    "audio_tokens": 0,
                    "image_tokens": 0,
                },
                "completion_tokens_details": {
                    "text_tokens": 0,
                    "audio_tokens": 0,
                    "image_tokens": 0,
                    "reasoning_tokens": reasoning_nested,
                },
                "input_tokens": 0,
                "output_tokens": 0,
                "input_tokens_details": None,
            },
        },
    }
    if include_official_keys:
        usage["cachedContentTokenCount"] = cached_official
        usage["thoughtsTokenCount"] = thoughts_official
    return usage


def _gemini_payload(
    *,
    text: str = "你好世界",
    usage_metadata: dict[str, Any] | None = None,
    finish_reason: str | None = "STOP",
    response_id: str = "resp-relay-1",
) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "content": {
            "role": "model",
            "parts": [{"text": text}],
        }
    }
    if finish_reason is not None:
        candidate["finishReason"] = finish_reason
    payload: dict[str, Any] = {
        "candidates": [candidate],
        "responseId": response_id,
    }
    if usage_metadata is not None:
        payload["usageMetadata"] = usage_metadata
    return payload


class _ChunkedAsyncStream(httpx.AsyncByteStream):
    """Test helper stream yielding exact pre-sliced chunks and tracking aclose()."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


class _CountingAsyncTransport(httpx.AsyncBaseTransport):
    """Minimal transport that tracks enter/exit/aclose delegation."""

    def __init__(self, handler) -> None:
        self._handler = handler
        self.entered = False
        self.exited = False
        self.closed = False

    async def __aenter__(self) -> "_CountingAsyncTransport":
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        self.exited = True
        await self.aclose()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return self._handler(request)

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    ("cached_official", "thoughts_official", "include_keys"),
    [
        (0, 0, True),
        (None, None, True),
        (-1, -5, True),
        (None, None, False),
    ],
)
def test_backfill_usage_metadata_fills_missing_null_or_non_positive_fields(
    cached_official, thoughts_official, include_keys
):
    usage = _relay_usage_metadata(
        cached_official=cached_official,
        thoughts_official=thoughts_official,
        cached_nested=10522,
        reasoning_nested=19,
        include_official_keys=include_keys,
    )

    assert backfill_usage_metadata(usage) is True
    assert usage["cachedContentTokenCount"] == 10522
    assert usage["thoughtsTokenCount"] == 19


def test_backfill_usage_metadata_never_overwrites_positive_official_values():
    usage = _relay_usage_metadata(
        cached_official=4096,
        thoughts_official=77,
        cached_nested=10522,
        reasoning_nested=19,
    )

    assert backfill_usage_metadata(usage) is False
    assert usage["cachedContentTokenCount"] == 4096
    assert usage["thoughtsTokenCount"] == 77


def test_backfill_usage_metadata_only_fills_missing_side_when_other_is_positive():
    usage = _relay_usage_metadata(
        cached_official=4096,
        thoughts_official=0,
        cached_nested=10522,
        reasoning_nested=19,
    )

    assert backfill_usage_metadata(usage) is True
    assert usage["cachedContentTokenCount"] == 4096
    assert usage["thoughtsTokenCount"] == 19


@pytest.mark.parametrize(
    "billing_usage",
    [
        {
            "openai_usage": {
                "input_tokens_details": {"cached_tokens": 300},
                "output_tokens_details": {"reasoning_tokens": 12},
            }
        },
        {"openai_usage": {"cached_tokens": 300, "reasoning_tokens": 12}},
        {
            "prompt_tokens_details": {"cached_tokens": 300},
            "completion_tokens_details": {"reasoning_tokens": 12},
        },
        {"cached_tokens": 300, "reasoning_tokens": 12},
    ],
)
def test_backfill_usage_metadata_supports_fallback_nested_shapes(billing_usage):
    usage: dict[str, Any] = {
        "promptTokenCount": 500,
        "candidatesTokenCount": 20,
        "cachedContentTokenCount": 0,
        "thoughtsTokenCount": 0,
        "billing_usage": billing_usage,
    }

    assert backfill_usage_metadata(usage) is True
    assert usage["cachedContentTokenCount"] == 300
    assert usage["thoughtsTokenCount"] == 12


@pytest.mark.parametrize(
    "bad_usage",
    [
        None,
        "not-a-dict",
        [],
        {"cachedContentTokenCount": 0, "billing_usage": None},
        {"cachedContentTokenCount": 0, "billing_usage": "bad"},
        {"cachedContentTokenCount": 0, "billing_usage": []},
        {"cachedContentTokenCount": 0, "billing_usage": {"openai_usage": None}},
        {"cachedContentTokenCount": 0, "billing_usage": {"openai_usage": "bad"}},
        {
            "cachedContentTokenCount": 0,
            "billing_usage": {
                "openai_usage": {
                    "prompt_tokens_details": None,
                    "completion_tokens_details": ["bad"],
                }
            },
        },
        {
            "cachedContentTokenCount": 0,
            "thoughtsTokenCount": 0,
            "billing_usage": {
                "openai_usage": {
                    "prompt_tokens_details": {"cached_tokens": True},
                    "completion_tokens_details": {"reasoning_tokens": False},
                }
            },
        },
        {
            "cachedContentTokenCount": 0,
            "thoughtsTokenCount": 0,
            "billing_usage": {
                "openai_usage": {
                    "prompt_tokens_details": {"cached_tokens": -10},
                    "completion_tokens_details": {"reasoning_tokens": "19"},
                }
            },
        },
        {
            "cachedContentTokenCount": 0,
            "thoughtsTokenCount": 0,
            "billing_usage": {
                "openai_usage": {
                    "prompt_tokens_details": {"cached_tokens": 12.5},
                    "completion_tokens_details": {"reasoning_tokens": 0},
                }
            },
        },
    ],
)
def test_backfill_usage_metadata_is_fail_open_on_malformed_or_invalid_values(bad_usage):
    assert backfill_usage_metadata(bad_usage) is False
    if isinstance(bad_usage, dict) and "cachedContentTokenCount" in bad_usage:
        assert bad_usage["cachedContentTokenCount"] == 0


def test_backfill_payload_handles_chunk_list_and_response_wrapper_without_touching_tool_args():
    chunk_list = [
        _gemini_payload(text="part 1", finish_reason=None),
        _gemini_payload(text="part 2", usage_metadata=_relay_usage_metadata()),
    ]
    assert backfill_usage_metadata_in_payload(chunk_list) is True
    assert chunk_list[1]["usageMetadata"]["cachedContentTokenCount"] == 10522
    assert chunk_list[1]["usageMetadata"]["thoughtsTokenCount"] == 19

    wrapped = {"response": _gemini_payload(usage_metadata=_relay_usage_metadata())}
    assert backfill_usage_metadata_in_payload(wrapped) is True
    assert wrapped["response"]["usageMetadata"]["cachedContentTokenCount"] == 10522

    tool_call_payload = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {
                                "name": "inspect_payload",
                                "args": {
                                    "usageMetadata": _relay_usage_metadata(),
                                },
                            }
                        }
                    ],
                }
            }
        ]
    }
    assert backfill_usage_metadata_in_payload(tool_call_payload) is False
    args_usage = tool_call_payload["candidates"][0]["content"]["parts"][0][
        "functionCall"
    ]["args"]["usageMetadata"]
    assert args_usage["cachedContentTokenCount"] == 0
    assert args_usage["thoughtsTokenCount"] == 0


@pytest.mark.asyncio
async def test_transport_non_stream_json_backfill_and_content_length_consistency():
    payload = _gemini_payload(usage_metadata=_relay_usage_metadata())
    raw_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Content-Length": str(len(raw_bytes)),
            },
            stream=_ChunkedAsyncStream([raw_bytes]),
        )

    transport = GeminiUsageBackfillTransport(httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.post(
            "https://relay.example/v1beta/models/m:generateContent"
        )

    assert response.status_code == 200
    assert int(response.headers["content-length"]) == len(response.content)
    data = response.json()
    assert data["usageMetadata"]["cachedContentTokenCount"] == 10522
    assert data["usageMetadata"]["thoughtsTokenCount"] == 19


@pytest.mark.asyncio
async def test_transport_non_stream_json_preserves_official_nonzero_and_malformed_fail_open():
    official_payload = _gemini_payload(
        usage_metadata=_relay_usage_metadata(
            cached_official=8888,
            thoughts_official=44,
            cached_nested=10522,
            reasoning_nested=19,
        )
    )
    official_bytes = json.dumps(official_payload, ensure_ascii=False).encode("utf-8")
    malformed_json = b'{"usageMetadata":{"cachedContentTokenCount":0,"billing_usage":'
    bad_utf8 = b'\xff\xfe{"usageMetadata":{"billing_usage":{}}}'

    responses_by_path = {
        "/official": official_bytes,
        "/malformed": malformed_json,
        "/bad-utf8": bad_utf8,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = responses_by_path[request.url.path]
        return httpx.Response(
            200,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
            stream=_ChunkedAsyncStream([body]),
        )

    transport = GeminiUsageBackfillTransport(httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=transport) as client:
        r_official = await client.post("https://relay.example/official")
        r_malformed = await client.post("https://relay.example/malformed")
        r_bad_utf8 = await client.post("https://relay.example/bad-utf8")

    assert r_official.content == official_bytes
    assert r_official.json()["usageMetadata"]["cachedContentTokenCount"] == 8888
    assert r_official.json()["usageMetadata"]["thoughtsTokenCount"] == 44
    assert r_malformed.content == malformed_json
    assert int(r_malformed.headers["content-length"]) == len(malformed_json)
    assert r_bad_utf8.content == bad_utf8


@pytest.mark.asyncio
async def test_transport_fast_path_skips_json_parse_when_billing_usage_absent(
    monkeypatch,
):
    payload = _gemini_payload(
        usage_metadata={
            "promptTokenCount": 100,
            "candidatesTokenCount": 10,
            "cachedContentTokenCount": 30,
            "thoughtsTokenCount": 5,
        }
    )
    raw_bytes = json.dumps(payload).encode("utf-8")

    def fail_json_loads(*args, **kwargs):
        raise AssertionError(
            "json.loads must not be called when billing_usage is absent"
        )

    monkeypatch.setattr(usage_backfill.json, "loads", fail_json_loads)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/error":
            err = b'{"error":{"message":"billing_usage error"}}'
            return httpx.Response(
                500,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(err)),
                },
                content=err,
            )
        if request.url.path == "/binary":
            blob = b"PNG billing_usage binary"
            return httpx.Response(
                200,
                headers={"Content-Type": "image/png", "Content-Length": str(len(blob))},
                content=blob,
            )
        if request.url.path == "/head":
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": "999",
                },
                content=b"",
            )
        if request.url.path == "/no-content":
            return httpx.Response(
                204,
                headers={"Content-Type": "application/json"},
                content=b"",
            )
        if request.url.path == "/redirect":
            redir = b'{"billing_usage":{"cached_tokens":99}}'
            return httpx.Response(
                302,
                headers={
                    "Content-Type": "application/json",
                    "Location": "https://relay.example/ok",
                    "Content-Length": str(len(redir)),
                },
                content=redir,
            )
        if request.url.path == "/unknown-encoding":
            raw_enc = b'{"usageMetadata":{"cachedContentTokenCount":0,"billing_usage":{"cached_tokens":99}}}'
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "x-custom-codec",
                    "Content-Length": str(len(raw_enc)),
                },
                stream=_ChunkedAsyncStream([raw_enc]),
            )
        if request.url.path == "/sse":
            sse = f"data: {json.dumps(payload)}\n\n".encode()
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                stream=_ChunkedAsyncStream([sse]),
            )
        return httpx.Response(
            200,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(raw_bytes)),
            },
            stream=_ChunkedAsyncStream([raw_bytes]),
        )

    transport = GeminiUsageBackfillTransport(httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=transport) as client:
        r_json = await client.post("https://relay.example/ok")
        r_err = await client.post("https://relay.example/error")
        r_bin = await client.get("https://relay.example/binary")
        r_head = await client.head("https://relay.example/head")
        r_204 = await client.get("https://relay.example/no-content")
        r_302 = await client.get("https://relay.example/redirect")
        r_enc = await client.post("https://relay.example/unknown-encoding")
        async with client.stream("POST", "https://relay.example/sse") as r_sse:
            sse_body = await r_sse.aread()

    assert r_json.content == raw_bytes
    assert r_err.status_code == 500
    assert b"billing_usage" in r_err.content
    assert r_bin.content == b"PNG billing_usage binary"
    assert r_head.status_code == 200
    assert r_head.headers["content-length"] == "999"
    assert r_204.status_code == 204
    assert r_302.status_code == 302
    assert r_enc.headers["content-encoding"] == "x-custom-codec"
    assert b'"cachedContentTokenCount":0' in r_enc.content
    assert b'"cachedContentTokenCount": 30' in sse_body


@pytest.mark.asyncio
async def test_transport_json_array_and_chunked_without_content_length_and_read_error_cleanup():
    chunk_array = [
        _gemini_payload(text="段一", finish_reason=None),
        _gemini_payload(text="段二", usage_metadata=_relay_usage_metadata()),
    ]
    array_bytes = json.dumps(chunk_array, ensure_ascii=False).encode()
    single_bytes = json.dumps(
        _gemini_payload(usage_metadata=_relay_usage_metadata()), ensure_ascii=False
    ).encode()

    class _FailingStream(httpx.AsyncByteStream):
        def __init__(self) -> None:
            self.closed = False

        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b'{"partial":'
            raise httpx.ReadError("simulated socket failure")

        async def aclose(self) -> None:
            self.closed = True

    failing_stream = _FailingStream()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/array":
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(array_bytes)),
                },
                stream=_ChunkedAsyncStream([array_bytes]),
            )
        if request.url.path == "/chunked":
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/json",
                    "Transfer-Encoding": "chunked",
                },
                stream=_ChunkedAsyncStream([single_bytes]),
            )
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            stream=failing_stream,
        )

    transport = GeminiUsageBackfillTransport(httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=transport) as client:
        r_array = await client.post("https://relay.example/array")
        r_chunked = await client.post("https://relay.example/chunked")
        with pytest.raises(httpx.ReadError, match="simulated socket failure"):
            await client.post("https://relay.example/fail")

    assert int(r_array.headers["content-length"]) == len(r_array.content)
    parsed_array = r_array.json()
    assert parsed_array[1]["usageMetadata"]["cachedContentTokenCount"] == 10522
    assert parsed_array[1]["usageMetadata"]["thoughtsTokenCount"] == 19

    assert "content-length" not in r_chunked.headers
    assert r_chunked.json()["usageMetadata"]["cachedContentTokenCount"] == 10522

    assert failing_stream.closed is True


@pytest.mark.asyncio
async def test_transport_gzip_json_and_gzip_sse_responses():
    payload = _gemini_payload(
        text="压缩测试中文内容",
        usage_metadata=_relay_usage_metadata(cached_nested=7777, reasoning_nested=33),
    )
    plain_json = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    gz_json = gzip.compress(plain_json)

    plain_sse = (
        f"data: {json.dumps(_gemini_payload(text='第一段', finish_reason=None), ensure_ascii=False)}\n\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    ).encode()
    gz_sse = gzip.compress(plain_sse)
    gz_sse_stream = _ChunkedAsyncStream(
        [gz_sse[i : i + 7] for i in range(0, len(gz_sse), 7)]
    )

    plain_no_billing = json.dumps(
        _gemini_payload(text="无计费字段"), ensure_ascii=False
    ).encode("utf-8")
    gz_no_billing = gzip.compress(plain_no_billing)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/json":
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                    "Content-Length": str(len(gz_json)),
                },
                stream=_ChunkedAsyncStream([gz_json]),
            )
        if request.url.path == "/json-plain":
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                    "Content-Length": str(len(gz_no_billing)),
                },
                stream=_ChunkedAsyncStream([gz_no_billing]),
            )
        return httpx.Response(
            200,
            headers={
                "Content-Type": "text/event-stream",
                "Content-Encoding": "gzip",
                "Content-Length": str(len(gz_sse)),
            },
            stream=gz_sse_stream,
        )

    transport = GeminiUsageBackfillTransport(httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=transport) as client:
        r_json = await client.post("https://relay.example/json")
        r_plain = await client.post("https://relay.example/json-plain")
        async with client.stream("POST", "https://relay.example/sse") as r_sse:
            assert "content-length" not in r_sse.headers
            assert "content-encoding" not in r_sse.headers
            lines = [line async for line in r_sse.aiter_lines()]

    assert "content-encoding" not in r_json.headers
    assert int(r_json.headers["content-length"]) == len(r_json.content)
    assert r_json.json()["usageMetadata"]["cachedContentTokenCount"] == 7777
    assert r_json.json()["usageMetadata"]["thoughtsTokenCount"] == 33

    assert "content-encoding" not in r_plain.headers
    assert (
        r_plain.json()["candidates"][0]["content"]["parts"][0]["text"] == "无计费字段"
    )

    assert gz_sse_stream.closed is True
    data_lines = [line[6:] for line in lines if line.startswith("data: ")]
    assert len(data_lines) == 2
    parsed_final = json.loads(data_lines[1])
    assert parsed_final["usageMetadata"]["cachedContentTokenCount"] == 7777
    assert parsed_final["usageMetadata"]["thoughtsTokenCount"] == 33
    assert (
        parsed_final["candidates"][0]["content"]["parts"][0]["text"]
        == "压缩测试中文内容"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("chunk_size", [1, 2, 3, 5, 11])
@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
async def test_transport_sse_arbitrary_tiny_chunk_splits_preserve_utf8_and_backfill(
    chunk_size, newline
):
    chunk1 = _gemini_payload(text="你好，世界！🚀", finish_reason=None)
    chunk2 = _gemini_payload(
        text="继续输出中文\u2028段落\u2029换行\x85测试✨",
        usage_metadata=_relay_usage_metadata(cached_nested=10522, reasoning_nested=19),
    )
    sse_bytes = (
        b": keep-alive billing_usage"
        + newline
        + b"event: message"
        + newline
        + b"data: "
        + json.dumps(chunk1, ensure_ascii=False).encode("utf-8")
        + newline
        + newline
        + b"data: "
        + json.dumps(chunk2, ensure_ascii=False).encode("utf-8")
        + newline
        + newline
    )
    sliced = [
        sse_bytes[i : i + chunk_size] for i in range(0, len(sse_bytes), chunk_size)
    ]
    upstream_stream = _ChunkedAsyncStream(sliced)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "Content-Type": "text/event-stream; charset=utf-8",
                "Content-Length": str(len(sse_bytes)),
            },
            stream=upstream_stream,
        )

    transport = GeminiUsageBackfillTransport(httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=transport) as client:
        async with client.stream(
            "POST",
            "https://relay.example/v1beta/models/m:streamGenerateContent?alt=sse",
        ) as response:
            assert "content-length" not in response.headers
            raw_out = await response.aread()

    assert upstream_stream.closed is True
    assert newline in raw_out
    if newline == b"\r\n":
        assert b"\r\n\r\n" in raw_out

    # Verify httpx line splitting (the exact reader google-genai uses) keeps each
    # JSON payload intact even with U+2028/U+2029/U+0085 inside the text.
    check_resp = httpx.Response(200, content=raw_out)
    lines = list(check_resp.iter_lines())
    assert lines[0] == ": keep-alive billing_usage"
    assert lines[1] == "event: message"
    data_events = [json.loads(line[6:]) for line in lines if line.startswith("data: ")]
    assert len(data_events) == 2
    assert (
        data_events[0]["candidates"][0]["content"]["parts"][0]["text"]
        == "你好，世界！🚀"
    )
    assert (
        data_events[1]["candidates"][0]["content"]["parts"][0]["text"]
        == "继续输出中文\u2028段落\u2029换行\x85测试✨"
    )
    assert data_events[1]["usageMetadata"]["cachedContentTokenCount"] == 10522
    assert data_events[1]["usageMetadata"]["thoughtsTokenCount"] == 19


@pytest.mark.asyncio
async def test_transport_sse_flushes_eof_without_trailing_newline_and_handles_no_space_prefix():
    payload = _gemini_payload(
        text="无换行结尾",
        usage_metadata=_relay_usage_metadata(cached_nested=600, reasoning_nested=15),
    )
    raw = b"data:" + json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=_ChunkedAsyncStream([raw[:19], raw[19:]]),
        )

    transport = GeminiUsageBackfillTransport(httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=transport) as client:
        async with client.stream("POST", "https://relay.example/sse") as response:
            out = await response.aread()

    assert out.startswith(b"data:")
    parsed = json.loads(out[5:])
    assert parsed["candidates"][0]["content"]["parts"][0]["text"] == "无换行结尾"
    assert parsed["usageMetadata"]["cachedContentTokenCount"] == 600
    assert parsed["usageMetadata"]["thoughtsTokenCount"] == 15


@pytest.mark.asyncio
async def test_transport_sse_malformed_data_line_is_fail_open_and_early_break_closes_upstream():
    bad_line = b'data: {"usageMetadata":{"billing_usage":INVALID}\n\n'
    good_line = (
        b"data: "
        + json.dumps(_gemini_payload(text="after"), ensure_ascii=False).encode("utf-8")
        + b"\n\n"
    )
    upstream_malformed = _ChunkedAsyncStream([bad_line, good_line])
    upstream_early = _ChunkedAsyncStream([good_line, good_line, good_line])
    gz_early_bytes = gzip.compress(good_line * 4)
    upstream_gz_early = _ChunkedAsyncStream(
        [gz_early_bytes[i : i + 16] for i in range(0, len(gz_early_bytes), 16)]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/malformed":
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                stream=upstream_malformed,
            )
        if request.url.path == "/gz-early":
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "text/event-stream",
                    "Content-Encoding": "gzip",
                },
                stream=upstream_gz_early,
            )
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=upstream_early,
        )

    transport = GeminiUsageBackfillTransport(httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=transport) as client:
        async with client.stream("POST", "https://relay.example/malformed") as resp:
            content = await resp.aread()
        assert content == bad_line + good_line
        assert upstream_malformed.closed is True

        async with client.stream("POST", "https://relay.example/early") as resp:
            async for line in resp.aiter_lines():
                if line:
                    break
        assert upstream_early.closed is True

        async with client.stream("POST", "https://relay.example/gz-early") as resp:
            async for line in resp.aiter_lines():
                if line:
                    break
        assert upstream_gz_early.closed is True


@pytest.mark.asyncio
async def test_transport_sse_only_parses_json_on_lines_containing_billing_usage(
    monkeypatch,
):
    real_loads = json.loads
    loads_calls = 0

    def spy_loads(*args, **kwargs):
        nonlocal loads_calls
        loads_calls += 1
        return real_loads(*args, **kwargs)

    monkeypatch.setattr(usage_backfill.json, "loads", spy_loads)

    delta1 = _gemini_payload(text="delta-1", finish_reason=None)
    delta2 = _gemini_payload(text="delta-2", finish_reason=None)
    final = _gemini_payload(
        text="final",
        usage_metadata=_relay_usage_metadata(cached_nested=1234, reasoning_nested=56),
    )
    sse = (
        f"data: {json.dumps(delta1)}\n\n"
        f"data: {json.dumps(delta2)}\n\n"
        f"data: {json.dumps(final)}\n\n"
    ).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=_ChunkedAsyncStream([sse]),
        )

    transport = GeminiUsageBackfillTransport(httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=transport) as client:
        async with client.stream("POST", "https://relay.example/sse") as resp:
            lines = [line async for line in resp.aiter_lines()]

    assert loads_calls == 1
    data_events = [real_loads(line[6:]) for line in lines if line.startswith("data: ")]
    assert data_events[-1]["usageMetadata"]["cachedContentTokenCount"] == 1234
    assert data_events[-1]["usageMetadata"]["thoughtsTokenCount"] == 56


@pytest.mark.asyncio
async def test_wrap_httpx_client_wraps_proxy_mounts_is_idempotent_and_closes_cleanly(
    monkeypatch,
):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:18080")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")

    env_client = wrap_httpx_client_for_usage_backfill(httpx.AsyncClient(trust_env=True))
    try:
        assert isinstance(env_client._transport, GeminiUsageBackfillTransport)
        wrapped_mounts = [m for m in env_client._mounts.values() if m is not None]
        none_mounts = [m for m in env_client._mounts.values() if m is None]
        assert wrapped_mounts
        assert none_mounts
        assert all(isinstance(m, GeminiUsageBackfillTransport) for m in wrapped_mounts)
        # Idempotent wrapping does not double-wrap.
        first_transport = env_client._transport
        wrap_httpx_client_for_usage_backfill(env_client)
        assert env_client._transport is first_transport
    finally:
        await env_client.aclose()

    proxy_client = wrap_httpx_client_for_usage_backfill(
        httpx.AsyncClient(proxy="http://127.0.0.1:18080", trust_env=False)
    )
    try:
        assert isinstance(proxy_client._transport, GeminiUsageBackfillTransport)
        assert any(
            isinstance(m, GeminiUsageBackfillTransport)
            for m in proxy_client._mounts.values()
        )
    finally:
        await proxy_client.aclose()

    counting = _CountingAsyncTransport(lambda req: httpx.Response(200, content=b"ok"))
    wrapped_transport = GeminiUsageBackfillTransport(counting)
    async with wrapped_transport as active:
        assert active is wrapped_transport
        assert counting.entered is True
    assert counting.exited is True
    assert counting.closed is True


@pytest.mark.asyncio
async def test_provider_google_genai_wires_usage_backfill_transport_and_lifecycle():
    provider = ProviderGoogleGenAI(
        {
            "id": "gemini-test",
            "model": "gemini-2.5-flash",
            "key": ["key-1", "key-2"],
            "api_base": "https://relay.example",
            "proxy": "http://127.0.0.1:18080",
        },
        {},
    )
    try:
        assert provider._http_client is not None
        assert isinstance(
            provider._http_client._transport, GeminiUsageBackfillTransport
        )
        assert any(
            isinstance(m, GeminiUsageBackfillTransport)
            for m in provider._http_client._mounts.values()
        )
        first_client = provider._http_client
        provider.set_key("key-2")
        assert provider._http_client is not first_client
        assert provider._stale_http_clients == [first_client]
        assert isinstance(
            provider._http_client._transport, GeminiUsageBackfillTransport
        )
    finally:
        await provider.terminate()
    assert provider._http_client is None
    assert provider._stale_http_clients == []

    # Default official endpoint config (empty api_base, no explicit proxy)
    default_provider = ProviderGoogleGenAI(
        {
            "id": "gemini-default",
            "model": "gemini-2.5-flash",
            "key": ["key-default"],
            "api_base": "",
        },
        {},
    )
    try:
        assert default_provider._http_client is not None
        assert isinstance(
            default_provider._http_client._transport, GeminiUsageBackfillTransport
        )
    finally:
        await default_provider.terminate()


@pytest.mark.asyncio
async def test_e2e_google_genai_sdk_model_validate_and_provider_query_non_stream_and_stream():
    non_stream_payload = _gemini_payload(
        text="非流式回复",
        usage_metadata=_relay_usage_metadata(cached_nested=10523, reasoning_nested=20),
    )
    stream_chunk_1 = _gemini_payload(text="你好，", finish_reason=None)
    stream_chunk_2 = _gemini_payload(
        text="流式缓存回执！",
        usage_metadata=_relay_usage_metadata(cached_nested=10522, reasoning_nested=19),
        finish_reason="STOP",
    )
    sse_wire = (
        f"data: {json.dumps(stream_chunk_1, ensure_ascii=False)}\n\n"
        f"data: {json.dumps(stream_chunk_2, ensure_ascii=False)}\n\n"
    ).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        if "streamGenerateContent" in str(request.url):
            # Slice every 3 bytes to split Chinese UTF-8 characters and JSON lines.
            chunks = [sse_wire[i : i + 3] for i in range(0, len(sse_wire), 3)]
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "text/event-stream",
                    "Content-Length": str(len(sse_wire)),
                },
                stream=_ChunkedAsyncStream(chunks),
            )
        body = json.dumps(non_stream_payload, ensure_ascii=False).encode("utf-8")
        return httpx.Response(
            200,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
            stream=_ChunkedAsyncStream([body]),
        )

    # 1. Direct transport -> real google.genai.types.GenerateContentResponse validation
    raw_client = wrap_httpx_client_for_usage_backfill(
        httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    try:
        http_resp = await raw_client.post(
            "https://relay.example/v1beta/models/gemini-2.5-flash:generateContent"
        )
        normalized_dict = http_resp.json()
        # SDK's exact _from_response path (removes extra fields then calls model_validate)
        sdk_from_resp = types.GenerateContentResponse._from_response(
            response=json.loads(http_resp.content),
            kwargs={},
        )
        assert sdk_from_resp.usage_metadata is not None
        assert sdk_from_resp.usage_metadata.cached_content_token_count == 10523
        assert sdk_from_resp.usage_metadata.thoughts_token_count == 20

        # Direct Pydantic GenerateContentResponse.model_validate(...) check after
        # SDK extra-field stripping proves backfilled fields survive strict validation.
        genai_common._remove_extra_fields(
            types.GenerateContentResponse, normalized_dict
        )
        validated = types.GenerateContentResponse.model_validate(normalized_dict)
        assert validated.usage_metadata is not None
        assert validated.usage_metadata.cached_content_token_count == 10523
        assert validated.usage_metadata.thoughts_token_count == 20
    finally:
        await raw_client.aclose()

    # 2. Full end-to-end through real genai.Client + ProviderGoogleGenAI._query() / _query_stream()
    sdk_http_client = wrap_httpx_client_for_usage_backfill(
        httpx.AsyncClient(
            base_url="https://relay.example",
            transport=httpx.MockTransport(handler),
        )
    )
    try:
        provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
        provider.provider_config = {}
        provider.provider_settings = {}
        provider.model_name = "gemini-2.5-flash"
        provider.safety_settings = []
        provider._http_client = sdk_http_client
        provider._stale_http_clients = []
        provider.client = genai.Client(
            api_key="test-key",
            http_options=types.HttpOptions(
                api_version="v1beta",
                base_url="https://relay.example",
                httpx_async_client=sdk_http_client,
            ),
        ).aio

        non_stream_resp = await provider._query(
            payloads={
                "messages": [{"role": "user", "content": "hello"}],
                "model": "gemini-2.5-flash",
            },
            tools=None,
        )
        assert non_stream_resp.completion_text == "非流式回复"
        assert non_stream_resp.usage is not None
        assert non_stream_resp.usage.input_cached == 10523
        assert non_stream_resp.usage.input_other == 12572 - 10523
        assert non_stream_resp.usage.input == 12572
        assert non_stream_resp.usage.output == 6
        assert (
            non_stream_resp.raw_completion.usage_metadata.cached_content_token_count
            == 10523
        )
        assert non_stream_resp.raw_completion.usage_metadata.thoughts_token_count == 20

        stream_responses = [
            item
            async for item in provider._query_stream(
                payloads={
                    "messages": [{"role": "user", "content": "hello"}],
                    "model": "gemini-2.5-flash",
                },
                tools=None,
            )
        ]
        final_stream = stream_responses[-1]
        assert final_stream.is_chunk is False
        assert final_stream.completion_text == "你好，流式缓存回执！"
        assert final_stream.usage is not None
        assert final_stream.usage.input_cached == 10522
        assert final_stream.usage.input_other == 12572 - 10522
        assert final_stream.usage.input == 12572
        assert final_stream.usage.output == 6
        assert (
            final_stream.raw_completion.usage_metadata.cached_content_token_count
            == 10522
        )
        assert final_stream.raw_completion.usage_metadata.thoughts_token_count == 19
    finally:
        await sdk_http_client.aclose()
