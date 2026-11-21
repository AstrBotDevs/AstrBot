import json
import math
from collections.abc import AsyncIterator
from types import TracebackType
from typing import Any

import httpx

try:
    from httpx._decoders import SUPPORTED_DECODERS as _HTTPX_SUPPORTED_DECODERS
except ImportError:  # pragma: no cover
    _HTTPX_SUPPORTED_DECODERS = {"identity", "gzip", "deflate"}

_BILLING_USAGE_MARKER = b"billing_usage"

_CACHED_TOKEN_PATHS: tuple[tuple[str, ...], ...] = (
    ("openai_usage", "prompt_tokens_details", "cached_tokens"),
    ("openai_usage", "input_tokens_details", "cached_tokens"),
    ("openai_usage", "cached_tokens"),
    ("prompt_tokens_details", "cached_tokens"),
    ("input_tokens_details", "cached_tokens"),
    ("cached_tokens",),
)

_REASONING_TOKEN_PATHS: tuple[tuple[str, ...], ...] = (
    ("openai_usage", "completion_tokens_details", "reasoning_tokens"),
    ("openai_usage", "output_tokens_details", "reasoning_tokens"),
    ("openai_usage", "reasoning_tokens"),
    ("completion_tokens_details", "reasoning_tokens"),
    ("output_tokens_details", "reasoning_tokens"),
    ("reasoning_tokens",),
)


def _as_positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _needs_backfill(usage_metadata: dict[str, Any], key: str) -> bool:
    if key not in usage_metadata:
        return True
    current = usage_metadata[key]
    if current is None:
        return True
    if isinstance(current, bool):
        return False
    if isinstance(current, int):
        return current <= 0
    if isinstance(current, float):
        return math.isfinite(current) and current <= 0.0
    return False


def _nested_positive_int(mapping: dict[str, Any], *path: str) -> int | None:
    current: Any = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return _as_positive_int(current)


def _extract_first_positive_int(
    mapping: dict[str, Any],
    paths: tuple[tuple[str, ...], ...],
) -> int | None:
    for path in paths:
        value = _nested_positive_int(mapping, *path)
        if value is not None:
            return value
    return None


def backfill_usage_metadata(usage_metadata: Any) -> bool:
    """Backfill official Gemini usageMetadata counts from relay billing_usage.

    Some OneAPI / New-API compatible Gemini relays leave the official
    ``cachedContentTokenCount`` and ``thoughtsTokenCount`` fields unset or zero
    while placing the actual token counts under a non-standard
    ``usageMetadata.billing_usage`` object. Because ``google-genai`` strips
    unknown fields before validating ``GenerateContentResponseUsageMetadata``,
    backfilling the official fields before SDK deserialization preserves cache
    and reasoning token telemetry without overwriting positive official counts.

    Args:
        usage_metadata: Candidate ``usageMetadata`` mapping from a Gemini JSON
            response payload.

    Returns:
        ``True`` if at least one official usage field was backfilled.
    """
    if not isinstance(usage_metadata, dict):
        return False
    billing_usage = usage_metadata.get("billing_usage")
    if not isinstance(billing_usage, dict):
        return False

    changed = False
    if _needs_backfill(usage_metadata, "cachedContentTokenCount"):
        cached_tokens = _extract_first_positive_int(billing_usage, _CACHED_TOKEN_PATHS)
        if cached_tokens is not None:
            prompt_tokens = usage_metadata.get("promptTokenCount")
            if (
                not isinstance(prompt_tokens, bool)
                and isinstance(prompt_tokens, (int, float))
                and math.isfinite(prompt_tokens)
            ):
                max_cached = int(prompt_tokens)
                if max_cached <= 0:
                    cached_tokens = None
                elif cached_tokens > max_cached:
                    cached_tokens = max_cached
            if cached_tokens is not None:
                usage_metadata["cachedContentTokenCount"] = cached_tokens
                changed = True

    if _needs_backfill(usage_metadata, "thoughtsTokenCount"):
        reasoning_tokens = _extract_first_positive_int(
            billing_usage, _REASONING_TOKEN_PATHS
        )
        if reasoning_tokens is not None:
            usage_metadata["thoughtsTokenCount"] = reasoning_tokens
            changed = True

    return changed


def _backfill_response_object(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    changed = backfill_usage_metadata(obj.get("usageMetadata"))
    nested_response = obj.get("response")
    if isinstance(nested_response, dict):
        changed = (
            backfill_usage_metadata(nested_response.get("usageMetadata")) or changed
        )
    return changed


def backfill_usage_metadata_in_payload(payload: Any) -> bool:
    """Normalize ``usageMetadata`` in a decoded Gemini JSON response payload.

    Handles both single response objects (including ``{"response": {...}}``
    wrappers) and JSON arrays of response chunks, without descending into
    candidate text or tool call arguments.

    Args:
        payload: Parsed JSON payload from a Gemini HTTP response or SSE event.

    Returns:
        ``True`` if any ``usageMetadata`` object was modified.
    """
    if isinstance(payload, dict):
        return _backfill_response_object(payload)
    if isinstance(payload, list):
        changed = False
        for item in payload:
            if _backfill_response_object(item):
                changed = True
        return changed
    return False


def _dump_compact_json_bytes(payload: Any) -> bytes:
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # httpx.Response.aiter_lines() uses str.splitlines() semantics, which split
    # on NEL/LS/PS characters. Keep them JSON-escaped so SSE data lines stay intact.
    if "\u2028" in serialized:
        serialized = serialized.replace("\u2028", "\\u2028")
    if "\u2029" in serialized:
        serialized = serialized.replace("\u2029", "\\u2029")
    if "\x85" in serialized:
        serialized = serialized.replace("\x85", "\\u0085")
    return serialized.encode("utf-8")


def _backfill_json_bytes(raw_bytes: bytes) -> bytes | None:
    if _BILLING_USAGE_MARKER not in raw_bytes:
        return None
    try:
        payload = json.loads(raw_bytes)
    except (ValueError, TypeError):
        return None
    if not backfill_usage_metadata_in_payload(payload):
        return None
    try:
        return _dump_compact_json_bytes(payload)
    except (TypeError, ValueError):
        return None


def _split_sse_line_ending(raw_line: bytes) -> tuple[bytes, bytes]:
    """Split a raw SSE line into its payload bytes and trailing line ending.

    Args:
        raw_line: Raw SSE line bytes, optionally ending in CRLF, LF, or CR.

    Returns:
        Tuple of ``(body_bytes, line_ending)``.
    """
    if raw_line.endswith(b"\r\n"):
        return raw_line[:-2], b"\r\n"
    if raw_line.endswith(b"\n"):
        return raw_line[:-1], b"\n"
    if raw_line.endswith(b"\r"):
        return raw_line[:-1], b"\r"
    return raw_line, b""


def _rewrite_sse_event(event_lines: list[bytes]) -> bytes:
    """Backfill usageMetadata inside a buffered SSE event (single or multi-line).

    Args:
        event_lines: Non-empty SSE lines belonging to one event, excluding the
            trailing blank event-delimiter line.

    Returns:
        Rewritten event bytes if a valid JSON payload was backfilled, otherwise
        the original event bytes untouched.
    """
    if not event_lines:
        return b""

    data_entries: list[tuple[int, bytes, bytes, bytes]] = []
    for idx, raw_line in enumerate(event_lines):
        body_bytes, line_ending = _split_sse_line_ending(raw_line)
        if body_bytes.startswith(b"data: "):
            data_entries.append((idx, b"data: ", body_bytes[6:], line_ending))
        elif body_bytes.startswith(b"data:"):
            data_entries.append((idx, b"data:", body_bytes[5:], line_ending))

    if not data_entries:
        return b"".join(event_lines)

    if len(data_entries) == 1:
        combined_payload = data_entries[0][2]
    else:
        combined_payload = b"\n".join(entry[2] for entry in data_entries)

    if _BILLING_USAGE_MARKER not in combined_payload:
        return b"".join(event_lines)

    rewritten = _backfill_json_bytes(combined_payload)
    if rewritten is None:
        return b"".join(event_lines)

    data_index_set = {entry[0] for entry in data_entries}
    first_prefix = data_entries[0][1]
    last_idx = data_entries[-1][0]
    last_ending = data_entries[-1][3]

    out_parts: list[bytes] = []
    for idx, raw_line in enumerate(event_lines):
        if idx not in data_index_set:
            out_parts.append(raw_line)
        elif idx == last_idx:
            out_parts.append(first_prefix + rewritten + last_ending)
    return b"".join(out_parts)


def _pop_complete_sse_lines(buffer: bytearray) -> list[bytes]:
    """Extract complete SSE lines terminated by CRLF, LF, or bare CR.

    A lone trailing CR at the end of ``buffer`` is kept until the next chunk
    or EOF so a CRLF sequence split across chunk boundaries stays intact.

    Args:
        buffer: Mutable raw byte buffer receiving incoming stream chunks.

    Returns:
        List of complete raw SSE lines (including their line terminators).
    """
    lines: list[bytes] = []
    start = 0
    buf_len = len(buffer)
    while start < buf_len:
        nl = buffer.find(b"\n", start)
        cr = buffer.find(b"\r", start)
        if nl == -1 and cr == -1:
            break
        if nl != -1 and (cr == -1 or nl < cr):
            lines.append(bytes(buffer[start : nl + 1]))
            start = nl + 1
            continue
        # CR precedes LF (or no LF found).
        if cr + 1 == buf_len:
            # Hold trailing CR until the next byte shows whether LF follows.
            break
        if buffer[cr + 1] == 0x0A:
            lines.append(bytes(buffer[start : cr + 2]))
            start = cr + 2
        else:
            lines.append(bytes(buffer[start : cr + 1]))
            start = cr + 1
    if start:
        del buffer[:start]
    return lines


def _parse_media_type(headers: httpx.Headers) -> str:
    content_type = headers.get("content-type", "")
    return content_type.split(";", 1)[0].strip().lower()


def _classify_content_encoding(headers: httpx.Headers) -> tuple[bool, bool]:
    """Classify response Content-Encoding into ``(supported, needs_decode)``."""
    encodings = [
        enc.strip().lower()
        for enc in headers.get_list("content-encoding", split_commas=True)
        if enc.strip()
    ]
    non_identity = [enc for enc in encodings if enc != "identity"]
    if not non_identity:
        return True, False
    if all(enc in _HTTPX_SUPPORTED_DECODERS for enc in non_identity):
        return True, True
    return False, False


class _BytesAsyncStream(httpx.AsyncByteStream):
    """Single-buffer async byte stream for a buffered HTTP response body."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    async def __aiter__(self) -> AsyncIterator[bytes]:
        if self._data:
            yield self._data

    async def aclose(self) -> None:
        return None


class _UsageBackfillSSEStream(httpx.AsyncByteStream):
    """Event-buffered SSE stream that backfills relay ``usageMetadata`` fields.

    Buffers incomplete lines at the raw byte level across CRLF, LF, and bare CR
    line endings, and joins multi-line ``data:`` fields within each SSE event
    before backfilling so multi-byte UTF-8 sequences and split JSON payloads
    are never corrupted.
    """

    def __init__(
        self,
        *,
        raw_stream: httpx.AsyncByteStream | None = None,
        decoded_response: httpx.Response | None = None,
    ) -> None:
        if (raw_stream is None) == (decoded_response is None):
            raise ValueError(
                "Exactly one of raw_stream or decoded_response must be provided."
            )
        self._raw_stream = raw_stream
        self._decoded_response = decoded_response
        self._closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        if self._decoded_response is not None:
            source = self._decoded_response.aiter_bytes()
        else:
            assert self._raw_stream is not None
            source = self._raw_stream.__aiter__()

        buffer = bytearray()
        event_lines: list[bytes] = []
        async for chunk in source:
            if not chunk:
                continue
            buffer.extend(chunk)
            complete_lines = _pop_complete_sse_lines(buffer)
            if not complete_lines:
                continue
            out_parts: list[bytes] = []
            for raw_line in complete_lines:
                body_bytes, _ = _split_sse_line_ending(raw_line)
                if not body_bytes:
                    if event_lines:
                        out_parts.append(_rewrite_sse_event(event_lines))
                        event_lines.clear()
                    out_parts.append(raw_line)
                else:
                    event_lines.append(raw_line)
            if out_parts:
                yield b"".join(out_parts) if len(out_parts) > 1 else out_parts[0]

        if buffer:
            raw_tail = bytes(buffer)
            body_bytes, _ = _split_sse_line_ending(raw_tail)
            if not body_bytes:
                tail_parts: list[bytes] = []
                if event_lines:
                    tail_parts.append(_rewrite_sse_event(event_lines))
                    event_lines.clear()
                tail_parts.append(raw_tail)
                yield b"".join(tail_parts)
            else:
                event_lines.append(raw_tail)

        if event_lines:
            yield _rewrite_sse_event(event_lines)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._decoded_response is not None:
            await self._decoded_response.aclose()
        elif self._raw_stream is not None:
            await self._raw_stream.aclose()


class GeminiUsageBackfillTransport(httpx.AsyncBaseTransport):
    """Async httpx transport wrapper that backfills Gemini relay usageMetadata."""

    def __init__(self, transport: httpx.AsyncBaseTransport) -> None:
        self._transport = transport

    async def __aenter__(self) -> "GeminiUsageBackfillTransport":
        await self._transport.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self._transport.__aexit__(exc_type, exc_value, traceback)

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._transport.handle_async_request(request)

        if (
            request.method.upper() == "HEAD"
            or response.status_code < 200
            or response.status_code >= 300
            or response.status_code == 204
        ):
            return response

        media_type = _parse_media_type(response.headers)
        if media_type not in {"application/json", "text/event-stream"}:
            return response

        supported_encoding, needs_decode = _classify_content_encoding(response.headers)
        if not supported_encoding:
            return response

        if media_type == "application/json":
            return await self._handle_json_response(request, response, needs_decode)

        return self._handle_sse_response(request, response, needs_decode)

    async def _handle_json_response(
        self,
        request: httpx.Request,
        response: httpx.Response,
        needs_decode: bool,
    ) -> httpx.Response:
        response.request = request
        try:
            body = await response.aread()
        except BaseException:
            try:
                await response.aclose()
            except Exception:
                pass
            raise
        await response.aclose()

        rewritten = _backfill_json_bytes(body)
        if rewritten is None and not needs_decode:
            return httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                stream=_BytesAsyncStream(body),
                extensions=response.extensions,
                default_encoding=response.default_encoding,
            )

        final_body = rewritten if rewritten is not None else body
        headers = response.headers.copy()
        if needs_decode:
            headers.pop("content-encoding", None)
        if "content-length" in headers:
            headers["content-length"] = str(len(final_body))
        return httpx.Response(
            status_code=response.status_code,
            headers=headers,
            stream=_BytesAsyncStream(final_body),
            extensions=response.extensions,
            default_encoding=response.default_encoding,
        )

    def _handle_sse_response(
        self,
        request: httpx.Request,
        response: httpx.Response,
        needs_decode: bool,
    ) -> httpx.Response:
        headers = response.headers.copy()
        headers.pop("content-length", None)
        if needs_decode:
            response.request = request
            headers.pop("content-encoding", None)
            stream: httpx.AsyncByteStream = _UsageBackfillSSEStream(
                decoded_response=response
            )
        else:
            if not isinstance(response.stream, httpx.AsyncByteStream):
                return response
            stream = _UsageBackfillSSEStream(raw_stream=response.stream)
        return httpx.Response(
            status_code=response.status_code,
            headers=headers,
            stream=stream,
            extensions=response.extensions,
            default_encoding=response.default_encoding,
        )


def wrap_httpx_client_for_usage_backfill(
    client: httpx.AsyncClient,
) -> httpx.AsyncClient:
    """Wrap all transports on an ``httpx.AsyncClient`` for Gemini usage backfill.

    Wraps both the default transport and any configured proxy/mounted
    transports so explicit proxies, ``trust_env`` environment proxies, SSL
    verification, timeouts, and ``aclose()`` lifecycles remain preserved.

    Args:
        client: Async httpx client whose transports should be wrapped.

    Returns:
        The same ``httpx.AsyncClient`` instance with wrapped transports.
    """
    wrapped_by_id: dict[int, GeminiUsageBackfillTransport] = {}

    def _wrap(transport: httpx.AsyncBaseTransport) -> GeminiUsageBackfillTransport:
        if isinstance(transport, GeminiUsageBackfillTransport):
            return transport
        existing = wrapped_by_id.get(id(transport))
        if existing is not None:
            return existing
        wrapped = GeminiUsageBackfillTransport(transport)
        wrapped_by_id[id(transport)] = wrapped
        return wrapped

    default_transport = getattr(client, "_transport", None)
    if isinstance(default_transport, httpx.AsyncBaseTransport):
        client._transport = _wrap(default_transport)

    mounts = getattr(client, "_mounts", None)
    if isinstance(mounts, dict):
        for pattern, mounted in list(mounts.items()):
            if isinstance(mounted, httpx.AsyncBaseTransport):
                mounts[pattern] = _wrap(mounted)

    return client
