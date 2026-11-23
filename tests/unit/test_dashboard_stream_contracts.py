import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from quart import Quart, Response

from astrbot.dashboard.routes.log import LogRoute
from astrbot.dashboard.routes.route import RouteContext


@pytest.mark.asyncio
async def test_log_stream_preserves_response_factory_and_cancellation_cleanup():
    class CustomResponse(Response):
        pass

    class ObservedQueue(asyncio.Queue):
        def __init__(self):
            super().__init__()
            self.waiting = asyncio.Event()

        async def get(self):
            self.waiting.set()
            return await super().get()

    app = Quart(__name__)
    app.response_class = CustomResponse
    queue = ObservedQueue()
    broker = SimpleNamespace(
        log_cache=[], register=Mock(return_value=queue), unregister=Mock()
    )
    route = LogRoute(RouteContext(config={}, app=app), broker)

    async with app.test_request_context("/api/live-log"):
        response = await route.log()
        assert isinstance(response, CustomResponse)
        assert response.timeout is None
        assert response.headers["Content-Type"] == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"
        async with response.response as body:
            iterator = body.__aiter__()
            first = asyncio.create_task(anext(iterator))
            await asyncio.wait_for(queue.waiting.wait(), timeout=1)
            queue.put_nowait({"time": 123, "message": "ready"})
            chunk = await asyncio.wait_for(first, timeout=1)
            assert "id: 123.0\n" in chunk
            assert '"message": "ready"' in chunk

            queue.waiting.clear()
            pending = asyncio.create_task(anext(iterator))
            await asyncio.wait_for(queue.waiting.wait(), timeout=1)
            pending.cancel()
            with pytest.raises(StopAsyncIteration):
                await pending

    broker.register.assert_called_once_with()
    broker.unregister.assert_called_once_with(queue)
