import asyncio
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock

from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import StreamingResponse

from astrbot.dashboard.services.log_service import LogService


class LogSSEStreamTests(IsolatedAsyncioTestCase):
    async def test_idle_stream_starts_with_comment(self):
        broker = Mock()
        service = LogService(broker, {})
        stream = service.stream_log_events(None)
        try:
            first = await asyncio.wait_for(anext(stream), timeout=1)
            self.assertEqual(first, ": connected\n\n")
        finally:
            await stream.aclose()

    async def test_comment_preserves_cached_and_live_events(self):
        queue = asyncio.Queue()
        cached = {"time": 11, "level": "INFO", "data": "cached"}
        live = {"time": 12, "level": "INFO", "data": "live"}
        queue.put_nowait(live)
        broker = Mock(log_cache=[{"time": 9, "data": "old"}, cached])
        broker.register.return_value = queue
        service = LogService(broker, {})
        stream = service.stream_log_events("10")
        try:
            self.assertEqual(await anext(stream), ": connected\n\n")
            self.assertEqual(await anext(stream), service.format_log_sse(cached, 11.0))
            self.assertEqual(await anext(stream), service.format_log_sse(live, 12))
        finally:
            await stream.aclose()
        broker.unregister.assert_called_once_with(queue)

    async def test_cancelled_idle_stream_unregisters_subscription(self):
        queue = asyncio.Queue()
        registered = asyncio.Event()

        def register():
            registered.set()
            return queue

        broker = Mock()
        broker.register.side_effect = register
        stream = LogService(broker, {}).stream_log_events(None)
        try:
            self.assertEqual(await anext(stream), ": connected\n\n")
            pending = asyncio.create_task(anext(stream))
            await asyncio.wait_for(registered.wait(), timeout=1)
            pending.cancel()
            with self.assertRaises(StopAsyncIteration):
                await pending
        finally:
            await stream.aclose()
        broker.unregister.assert_called_once_with(queue)

    async def test_idle_disconnect_with_gzip_and_two_http_middlewares(self):
        for accept_encoding in (b"gzip", b"identity"):
            with self.subTest(accept_encoding=accept_encoding):
                queue = asyncio.Queue()
                registered = asyncio.Event()

                def register():
                    registered.set()
                    return queue

                broker = Mock()
                broker.register.side_effect = register
                service = LogService(broker, {})
                app = FastAPI()
                app.add_middleware(GZipMiddleware, minimum_size=1024)

                @app.middleware("http")
                async def auth(request, call_next):
                    return await call_next(request)

                @app.middleware("http")
                async def body_limit(request, call_next):
                    return await call_next(request)

                @app.get("/logs/live")
                async def live_logs():
                    return StreamingResponse(
                        service.stream_log_events(None), media_type="text/event-stream"
                    )

                scope = {
                    "type": "http",
                    "asgi": {"version": "3.0", "spec_version": "2.1"},
                    "http_version": "1.1",
                    "method": "GET",
                    "scheme": "http",
                    "path": "/logs/live",
                    "raw_path": b"/logs/live",
                    "query_string": b"",
                    "headers": [(b"accept-encoding", accept_encoding)],
                    "server": ("testserver", 80),
                    "client": ("testclient", 1234),
                    "root_path": "",
                }
                state = SimpleNamespace(first_request=True)
                sent = []

                async def receive():
                    if state.first_request:
                        state.first_request = False
                        return {"type": "http.request", "body": b"", "more_body": False}
                    await registered.wait()
                    return {"type": "http.disconnect"}

                async def send(message):
                    sent.append(message)

                await asyncio.wait_for(app(scope, receive, send), timeout=2)
                start = next(m for m in sent if m["type"] == "http.response.start")
                self.assertEqual(start["status"], 200)
                self.assertNotIn(b"content-encoding", dict(start["headers"]))
                body = b"".join(
                    m.get("body", b"")
                    for m in sent
                    if m["type"] == "http.response.body"
                )
                self.assertEqual(body, b": connected\n\n")
                broker.unregister.assert_called_once_with(queue)
