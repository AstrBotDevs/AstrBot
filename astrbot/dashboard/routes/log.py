from typing import cast

from astrbot.core import LogBroker
from astrbot.dashboard.fastapi_compat import Response as CompatResponse
from astrbot.dashboard.fastapi_compat import make_response, request
from astrbot.dashboard.services.log_service import LogService, LogServiceError

from .route import Response, Route, RouteContext


class LogRoute(Route):
    def __init__(self, context: RouteContext, log_broker: LogBroker) -> None:
        super().__init__(context)
        self.log_broker = log_broker
        self.service = LogService(log_broker, self.config)
        self.app.add_url_rule("/api/live-log", view_func=self.log, methods=["GET"])
        self.app.add_url_rule(
            "/api/log-history",
            view_func=self.log_history,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/trace/settings",
            view_func=self.get_trace_settings,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/trace/settings",
            view_func=self.update_trace_settings,
            methods=["POST"],
        )

    @staticmethod
    def _ok(data=None, message: str | None = None):
        return Response().ok(data=data, message=message).__dict__

    @staticmethod
    def _error(message: str):
        return Response().error(message).__dict__

    @staticmethod
    async def _json_body() -> dict:
        data = await request.get_json()
        return data if isinstance(data, dict) else {}

    async def _run(self, operation, *, result_as_message: bool = False):
        try:
            result = operation() if callable(operation) else operation
            while hasattr(result, "__await__"):
                result = await result
            if result_as_message:
                return self._ok(message=str(result))
            return self._ok(result)
        except LogServiceError as exc:
            return self._error(str(exc))

    async def _run_json(self, operation, *, result_as_message: bool = False):
        async def invoke():
            data = await self._json_body()
            return operation(data)

        return await self._run(invoke, result_as_message=result_as_message)

    async def log(self) -> CompatResponse:
        last_event_id = request.headers.get("Last-Event-ID")

        async def stream():
            async for event in self.service.stream_log_events(last_event_id):
                yield event

        response = cast(
            CompatResponse,
            await make_response(
                stream(),
                {
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Transfer-Encoding": "chunked",
                },
            ),
        )
        response.timeout = None  # type: ignore
        return response

    async def log_history(self):
        """获取日志历史"""
        return await self._run(self.service.get_log_history)

    async def get_trace_settings(self):
        """获取 Trace 设置"""
        return await self._run(self.service.get_trace_settings)

    async def update_trace_settings(self):
        """更新 Trace 设置"""
        return await self._run_json(
            self.service.update_trace_settings_from_legacy_payload,
            result_as_message=True,
        )
