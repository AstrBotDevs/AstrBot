import asyncio
import json
import time
from typing import cast

from quart import request, Response as QuartResponse
from quart import make_response

from astrbot.core import LogBroker, logger

from .route import Response, Route, RouteContext


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

    async def log(self):
        last_event_id = request.headers.get("Last-Event-ID")

        async def stream():
            queue = None
            try:
                if last_event_id:
                    try:
                        last_ts = float(last_event_id)

                        cached_logs = list(self.log_broker.log_cache)

                        for log_item in cached_logs:
                            log_ts = float(log_item.get("time", 0))

                            if log_ts > last_ts:
                                payload = {
                                    "type": "log",
                                    **log_item,
                                }

                                yield f"id: {log_ts}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    except ValueError:
                        pass
                    except Exception as e:
                        logger.error(f"Log SSE 历史错误: {e}")

                queue = self.log_broker.register()
                while True:
                    message = await queue.get()

                    current_ts = message.get("time", time.time())

                    payload = {
                        "type": "log",
                        **message,  # see astrbot/core/log.py
                    }

                    yield f"id: {current_ts}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

            except asyncio.CancelledError:
                pass
            except BaseException as e:
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
        response.timeout = None
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
        except BaseException as e:
            logger.error(f"获取日志历史失败: {e}")
            return Response().error(f"获取日志历史失败: {e}").__dict__
