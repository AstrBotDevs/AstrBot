import pytest

from astrbot.core.provider.oauth.openai_oauth_sse import iter_json_sse_events


async def _lines(values: list[str]):
    for value in values:
        yield value


@pytest.mark.asyncio
async def test_multiline_data_is_joined_before_json_parsing():
    events = [
        event
        async for event in iter_json_sse_events(
            _lines(
                [
                    'data: {"type":"response.output_text.delta",',
                    'data: "delta":"hello"}',
                    "",
                ]
            )
        )
    ]

    assert events == [{"type": "response.output_text.delta", "delta": "hello"}]


@pytest.mark.asyncio
async def test_multiple_events_comments_metadata_and_bom_are_supported():
    events = [
        event
        async for event in iter_json_sse_events(
            _lines(
                [
                    "\ufeff: keepalive",
                    "event: response",
                    "id: one",
                    'data: {"type":"one"}',
                    "",
                    ": another comment",
                    'data:{"type":"two"}',
                    "",
                ]
            )
        )
    ]

    assert events == [{"type": "one"}, {"type": "two"}]


@pytest.mark.asyncio
async def test_done_stops_without_consuming_later_events():
    consumed: list[str] = []

    async def source():
        for value in ["data: [DONE]", "", 'data: {"type":"late"}', ""]:
            consumed.append(value)
            yield value

    events = [event async for event in iter_json_sse_events(source())]

    assert events == []
    assert consumed == ["data: [DONE]", ""]


@pytest.mark.asyncio
async def test_complete_final_frame_is_emitted_at_eof():
    events = [
        event
        async for event in iter_json_sse_events(
            _lines(['data: {"type":"response.completed"}'])
        )
    ]

    assert events == [{"type": "response.completed"}]


@pytest.mark.asyncio
async def test_oversized_event_is_rejected_before_json_decode():
    with pytest.raises(ValueError, match="超过大小上限"):
        _ = [
            event
            async for event in iter_json_sse_events(
                _lines(['data: {"payload":"123456789"}', ""]),
                max_event_bytes=8,
            )
        ]


@pytest.mark.asyncio
async def test_malformed_json_raises_safe_error_without_raw_payload():
    secret = "secret-payload-value"

    with pytest.raises(ValueError) as exc_info:
        _ = [
            event
            async for event in iter_json_sse_events(
                _lines([f'data: {{"value":"{secret}"', ""])
            )
        ]

    assert "JSON" in str(exc_info.value)
    assert secret not in str(exc_info.value)


@pytest.mark.asyncio
async def test_non_object_json_is_rejected_explicitly():
    with pytest.raises(ValueError, match="JSON 对象"):
        _ = [event async for event in iter_json_sse_events(_lines(["data: []", ""]))]
