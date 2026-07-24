import asyncio

import pytest

from astrbot.core.agent.stream_controller import StreamController, StreamSignal


@pytest.mark.asyncio
async def test_stream_controller_emits_one_terminal_event() -> None:
    async def source():
        yield "one"

    frames = [
        frame async for frame in StreamController(idle_timeout=0.01).run(source())
    ]

    assert [frame.signal for frame in frames] == [
        StreamSignal.START,
        StreamSignal.DELTA,
        StreamSignal.END,
    ]


@pytest.mark.asyncio
async def test_stream_controller_emits_heartbeat_for_idle_source() -> None:
    async def source():
        await asyncio.sleep(0.03)
        yield "done"

    frames = [
        frame async for frame in StreamController(idle_timeout=0.01).run(source())
    ]

    signals = [frame.signal for frame in frames]
    assert StreamSignal.HEARTBEAT in signals
    assert signals[-1] == StreamSignal.END


@pytest.mark.asyncio
async def test_stream_controller_restarts_terminal_lifecycle_when_reused() -> None:
    async def source():
        yield "again"

    controller = StreamController(idle_timeout=0.01)
    first = [frame async for frame in controller.run(source())]
    second = [frame async for frame in controller.run(source())]

    assert first[-1].signal == StreamSignal.END
    assert second[-1].signal == StreamSignal.END
    assert [frame.signal for frame in second] == [
        StreamSignal.START,
        StreamSignal.DELTA,
        StreamSignal.END,
    ]
