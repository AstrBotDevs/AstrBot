"""Small, bounded parser for JSON Server-Sent Events."""

import json
from collections.abc import AsyncIterator
from typing import Any

DEFAULT_MAX_EVENT_BYTES = 4 * 1024 * 1024


async def iter_json_sse_events(
    lines: AsyncIterator[str],
    *,
    max_event_bytes: int = DEFAULT_MAX_EVENT_BYTES,
) -> AsyncIterator[dict[str, Any]]:
    """Yield JSON objects from an asynchronous stream of SSE lines.

    Args:
        lines: SSE lines with or without trailing newline characters.
        max_event_bytes: Maximum UTF-8 byte size of one joined ``data`` event.

    Yields:
        Each decoded JSON object, in stream order.

    Raises:
        ValueError: If the size limit is invalid, an event is too large, or an
            event does not contain a valid JSON object.
    """
    if max_event_bytes <= 0:
        raise ValueError("SSE 事件大小上限必须大于零。")

    iterator = lines.__aiter__()
    data_lines: list[str] = []
    data_bytes = 0
    first_line = True

    while True:
        try:
            line = await anext(iterator)
            reached_eof = False
        except StopAsyncIteration:
            line = ""
            reached_eof = True

        if first_line:
            line = line.removeprefix("\ufeff")
            first_line = False
        line = line.removesuffix("\n").removesuffix("\r")

        if line == "":
            if data_lines:
                payload = "\n".join(data_lines)
                data_lines = []
                data_bytes = 0

                if payload.strip() == "[DONE]":
                    return

                try:
                    event = json.loads(payload)
                except (json.JSONDecodeError, UnicodeError) as exc:
                    raise ValueError("OpenAI OAuth SSE 事件包含无效 JSON。") from exc
                if not isinstance(event, dict):
                    raise ValueError("OpenAI OAuth SSE 事件必须是 JSON 对象。")
                yield event

            if reached_eof:
                return
            continue

        if line.startswith(":"):
            continue

        field, separator, value = line.partition(":")
        if not separator:
            value = ""
        elif value.startswith(" "):
            value = value[1:]
        if field != "data":
            continue

        encoded_size = len(value.encode("utf-8"))
        if data_lines:
            encoded_size += 1
        data_bytes += encoded_size
        if data_bytes > max_event_bytes:
            raise ValueError("OpenAI OAuth SSE 事件超过大小上限。")
        data_lines.append(value)
