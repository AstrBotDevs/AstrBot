from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator

from astrbot.core import LogBroker, logger
from astrbot.core.config.astrbot_config import AstrBotConfig


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
        return f"id: {ts}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def replay_cached_logs(self, last_event_id: str) -> AsyncGenerator[str, None]:
        try:
            last_ts = float(last_event_id)
            cached_logs = list(self.log_broker.log_cache)

            for log_item in cached_logs:
                log_ts = float(log_item.get("time", 0))
                if log_ts > last_ts:
                    yield self.format_log_sse(log_item, log_ts)
        except ValueError:
            pass
        except Exception as exc:
            logger.error(f"Log SSE 补发历史错误: {exc}")

    async def stream_log_events(
        self, last_event_id: str | None
    ) -> AsyncGenerator[str, None]:
        queue = None
        try:
            if last_event_id:
                async for event in self.replay_cached_logs(last_event_id):
                    yield event

            queue = self.log_broker.register()
            while True:
                message = await queue.get()
                current_ts = message.get("time", time.time())
                yield self.format_log_sse(message, current_ts)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(f"Log SSE 连接错误: {exc}")
        finally:
            if queue:
                self.log_broker.unregister(queue)

    def get_log_history(self) -> dict:
        try:
            return {"logs": list(self.log_broker.log_cache)}
        except Exception as exc:
            logger.error(f"获取日志历史失败: {exc}")
            raise LogServiceError(f"获取日志历史失败: {exc}") from exc

    def get_trace_settings(self) -> dict:
        try:
            return {"trace_enable": self.config.get("trace_enable", True)}
        except Exception as exc:
            logger.error(f"获取 Trace 设置失败: {exc}")
            raise LogServiceError(f"获取 Trace 设置失败: {exc}") from exc

    def update_trace_settings(self, payload: dict | None) -> str:
        try:
            if payload is None:
                raise LogServiceError("请求数据为空")

            trace_enable = payload.get("trace_enable")
            if trace_enable is not None:
                self.config["trace_enable"] = bool(trace_enable)
                self.config.save_config()

            return "Trace 设置已更新"
        except LogServiceError:
            raise
        except Exception as exc:
            logger.error(f"更新 Trace 设置失败: {exc}")
            raise LogServiceError(f"更新 Trace 设置失败: {exc}") from exc
