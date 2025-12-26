import asyncio
import json
import time
from collections.abc import AsyncGenerator
from typing import cast

from quart import Response as QuartResponse
from quart import make_response, request

from astrbot.core import LogBroker, logger

from .route import Response, Route, RouteContext


def _format_log_sse(log: dict, ts: float) -> str:
    """辅助函数：格式化 SSE 消息"""
    payload = {
        "type": "log",
        **log,
    }
    return f"id: {ts}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


class LogRoute(Route):
    def __init__(self, context: RouteContext, log_broker: LogBroker) -> None:
        super().__init__(context)
        self.log_broker = log_broker
        self.app.add_url_rule("/api/live-log", view_func=self.log, methods=["GET"])
        self.app.add_url_rule(
            "/api/log-history",
            view_func=self.log_history,
            methods=["GET"],
        )

    async def _replay_cached_logs(
        self, last_event_id: str
    ) -> AsyncGenerator[str, None]:
        """辅助生成器：重放缓存的日志"""
        try:
            last_ts = float(last_event_id)
            cached_logs = list(self.log_broker.log_cache)

            for log_item in cached_logs:
                log_ts = float(log_item.get("time", 0))

                if log_ts > last_ts:
                    yield _format_log_sse(log_item, log_ts)

        except ValueError:
            pass
        except Exception as e:
            logger.error(f"Log SSE 补发历史错误: {e}")

    async def log(self) -> QuartResponse:
        last_event_id = request.headers.get("Last-Event-ID")

        async def stream():
            queue = None
            try:
                if last_event_id:
                    async for event in self._replay_cached_logs(last_event_id):
                        yield event

                queue = self.log_broker.register()
                while True:
                    message = await queue.get()
                    current_ts = message.get("time", time.time())
                    yield _format_log_sse(message, current_ts)

            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Log SSE 连接错误: {e}")
            finally:
                if queue:
                    self.log_broker.unregister(queue)

        response = cast(
            QuartResponse,
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
        try:
            logs = list(self.log_broker.log_cache)
            return (
                Response()
                .ok(
                    data={
                        "logs": logs,
                    },
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取日志历史失败: {e}")
            return Response().error(f"获取日志历史失败: {e}").__dict__
