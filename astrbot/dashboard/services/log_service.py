import asyncio
import json
import time
from collections.abc import AsyncGenerator

from astrbot import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.log import LogBroker


class LogServiceError(Exception):
    pass


class LogService:
    def __init__(self, log_broker: LogBroker, config: AstrBotConfig) -> None:
        self.log_broker = log_broker
        self.config = config

    @staticmethod
    def format_log_sse(log: dict, ts: float) -> str:
        payload = {
            "type": "log",
            **log,
        }
        event_id = str(log.get("event_id") or ts)
        return f"id: {event_id}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    @staticmethod
    def _matches(
        log: dict,
        categories: set[str] | None,
        privacy: set[str] | None,
    ) -> bool:
        if categories and str(log.get("category", "system")) not in categories:
            return False
        return not privacy or str(log.get("privacy", "internal")) in privacy

    async def replay_cached_logs(self, last_event_id: str) -> AsyncGenerator[str]:
        try:
            cached_logs = list(self.log_broker.log_cache)
            start = 0
            for index, log_item in enumerate(cached_logs):
                if str(log_item.get("event_id")) == last_event_id:
                    start = index + 1
                    break
            else:
                try:
                    last_ts = float(last_event_id)
                except ValueError:
                    last_ts = 0
                start = next(
                    (
                        index
                        for index, log_item in enumerate(cached_logs)
                        if float(log_item.get("time", 0)) > last_ts
                    ),
                    len(cached_logs),
                )
            for log_item in cached_logs[start:]:
                yield self.format_log_sse(
                    log_item, float(log_item.get("timestamp", log_item.get("time", 0)))
                )
        except Exception as exc:
            logger.error(f"Log SSE 补发历史错误: {exc}")

    async def stream_log_events(
        self,
        last_event_id: str | None,
        categories: set[str] | None = None,
        privacy: set[str] | None = None,
    ) -> AsyncGenerator[str]:
        queue = None
        try:
            queue = self.log_broker.register()
            if last_event_id:
                async for event in self.replay_cached_logs(last_event_id):
                    payload = json.loads(event.split("data: ", 1)[1])
                    if self._matches(payload, categories, privacy):
                        yield event

            while True:
                message = await queue.get()
                if self._matches(message, categories, privacy):
                    current_ts = message.get(
                        "timestamp", message.get("time", time.time())
                    )
                    yield self.format_log_sse(message, current_ts)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"Log SSE 连接错误: {exc}")
        finally:
            if queue:
                self.log_broker.unregister(queue)

    def get_log_history(
        self,
        categories: set[str] | None = None,
        privacy: set[str] | None = None,
    ) -> dict:
        try:
            return {
                "logs": [
                    log
                    for log in self.log_broker.log_cache
                    if self._matches(log, categories, privacy)
                ]
            }
        except Exception as exc:
            logger.error(f"获取日志历史失败: {exc}")
            raise LogServiceError(f"获取日志历史失败: {exc}") from exc

    def get_trace_settings(self) -> dict:
        try:
            return {"enabled": self.config.get("trace_enable", True)}
        except Exception as exc:
            logger.error(f"获取 Trace 设置失败: {exc}")
            raise LogServiceError(f"获取 Trace 设置失败: {exc}") from exc

    async def update_trace_settings(self, enabled: bool) -> str:
        try:
            committed = await self.config.save_config_async({"trace_enable": enabled})
            if not committed:
                raise LogServiceError(
                    "Trace configuration save was superseded by a newer update."
                )
            return "Trace 设置已更新"
        except LogServiceError:
            raise
        except Exception as exc:
            logger.error(f"更新 Trace 设置失败: {exc}")
            raise LogServiceError(f"更新 Trace 设置失败: {exc}") from exc
