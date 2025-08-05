import asyncio
import json
from quart import make_response
from astrbot.core import logger, LogBroker
from .route import Route, RouteContext, Response


class LogRoute(Route):
    def __init__(self, context: RouteContext, log_broker: LogBroker) -> None:
        super().__init__(context)
        self.log_broker = log_broker
        self.app.add_url_rule("/api/live-log", view_func=self.log, methods=["GET"])
        self.app.add_url_rule("/api/log-history", view_func=self.log_history, methods=["GET"])

    async def log(self):
        async def stream():
            queue = None
            try:
                queue = self.log_broker.register()
                while True:
                    message = await queue.get()
                    payload = {
                        "type": "log",
                        **message,  # see astrbot/core/log.py
                    }
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except asyncio.CancelledError:
                pass
            except BaseException as e:
                logger.error(f"Log SSE 连接错误: {e}")
            finally:
                if queue:
                    self.log_broker.unregister(queue)

        response = await make_response(
            stream(),
            {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Transfer-Encoding": "chunked",
            },
        )
        response.timeout = None
        return response

    async def log_history(self):
        """获取日志历史"""
        try:
            logs = list(self.log_broker.log_cache)
            return Response().ok(data={
                "logs": logs,
            }).__dict__
        except BaseException as e:
            logger.error(f"获取日志历史失败: {e}")
            return Response().error(f"获取日志历史失败: {e}").__dict__
