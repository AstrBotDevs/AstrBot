from __future__ import annotations

import asyncio
import json
import math
import os
import time
from collections.abc import AsyncGenerator

from astrbot.core import LogBroker, logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


class LogServiceError(Exception):
    pass


def _format_size(size_bytes: int) -> str:
    """Format a byte count into a human-readable string."""
    if size_bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"


class LogService:
    def __init__(
        self,
        log_broker: LogBroker,
        config: AstrBotConfig,
        db: BaseDatabase | None = None,
    ) -> None:
        self.log_broker = log_broker
        self.config = config
        self.db = db

    @staticmethod
    def format_log_sse(log: dict, ts: float) -> str:
        payload = {
            "type": "log",
            **log,
        }
        return f"id: {ts}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def replay_cached_logs(self, last_event_id: str) -> AsyncGenerator[str]:
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

    async def stream_log_events(self, last_event_id: str | None) -> AsyncGenerator[str]:
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
            return {"trace_enable": self.config.get("trace_enable", False)}
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

    def get_trace_history(self) -> dict:
        """Return the realtime trace cache (dedicated queue, unaffected by log volume)."""
        try:
            return {"traces": list(self.log_broker.trace_cache)}
        except Exception as exc:
            logger.error(f"获取 Trace 历史失败: {exc}")
            raise LogServiceError(f"获取 Trace 历史失败: {exc}") from exc

    async def list_traces(
        self,
        page: int = 1,
        page_size: int = 20,
        umo: str | None = None,
        search: str | None = None,
        sender: str | None = None,
    ) -> dict:
        """Query persisted traces with pagination."""
        try:
            page = max(1, page)
            page_size = max(1, min(page_size, 100))

            if self.db is None:
                raise LogServiceError("数据库未初始化")

            entries, total = await self.db.get_traces(
                page=page,
                page_size=page_size,
                umo=umo,
                search=search,
                sender=sender,
            )

            def _entry_to_dict(e):
                return {
                    "trace_id": e.trace_id,
                    "umo": e.umo,
                    "sender_name": e.sender_name,
                    "message_outline": e.message_outline,
                    "started_at": e.started_at,
                    "finished_at": e.finished_at,
                    "duration_ms": e.duration_ms,
                    "status": e.status,
                    "input_text": e.input_text,
                    "output_text": e.output_text,
                    "total_input_tokens": e.total_input_tokens,
                    "total_output_tokens": e.total_output_tokens,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }

            # Compute disk usage of trace-related files
            trace_size = 0
            data_path = get_astrbot_data_path()
            trace_log_dir = os.path.join(data_path, "logs")
            if os.path.exists(trace_log_dir):
                for f in os.listdir(trace_log_dir):
                    if "astrbot.trace.log" in f:
                        trace_size += os.path.getsize(os.path.join(trace_log_dir, f))

            # Database file size (includes other data, but traces are often dominant)
            db_size = 0
            if hasattr(self.db, "db_path") and os.path.exists(self.db.db_path):  # type: ignore[attr-defined]
                db_size = os.path.getsize(self.db.db_path)  # type: ignore[attr-defined]

            return {
                "traces": [_entry_to_dict(e) for e in entries],
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                },
                "trace_disk_usage": _format_size(trace_size),
                "db_disk_usage": _format_size(db_size),
            }
        except LogServiceError:
            raise
        except Exception as exc:
            logger.error(f"查询 Trace 列表失败: {exc}")
            raise LogServiceError(f"查询 Trace 列表失败: {exc}") from exc

    async def get_trace_sources(self) -> dict:
        """Return distinct sender_name values for the source filter dropdown."""
        try:
            if self.db is None:
                raise LogServiceError("数据库未初始化")
            sources = await self.db.get_trace_sources()
            return {"sources": sources}
        except LogServiceError:
            raise
        except Exception as exc:
            logger.error(f"查询 Trace 来源失败: {exc}")
            raise LogServiceError(f"查询 Trace 来源失败: {exc}") from exc

    async def get_trace_detail(self, trace_id: str | None) -> dict:
        """Return the full span tree of a single trace."""
        try:
            if not trace_id:
                raise LogServiceError("缺少 trace_id 参数")
            if self.db is None:
                raise LogServiceError("数据库未初始化")

            entry = await self.db.get_trace_detail(trace_id)
            if entry is None:
                raise LogServiceError("Trace 不存在")

            return {
                "trace_id": entry.trace_id,
                "umo": entry.umo,
                "sender_name": entry.sender_name,
                "message_outline": entry.message_outline,
                "started_at": entry.started_at,
                "finished_at": entry.finished_at,
                "duration_ms": entry.duration_ms,
                "status": entry.status,
                "spans": entry.spans,
                "input_text": entry.input_text,
                "output_text": entry.output_text,
                "total_input_tokens": entry.total_input_tokens,
                "total_output_tokens": entry.total_output_tokens,
            }
        except LogServiceError:
            raise
        except Exception as exc:
            logger.error(f"获取 Trace 详情失败: {exc}")
            raise LogServiceError(f"获取 Trace 详情失败: {exc}") from exc

    async def clear_traces(self, before_ts: float | None = None) -> dict:
        """Delete trace records; when before_ts is omitted, delete everything."""
        try:
            if self.db is None:
                raise LogServiceError("数据库未初始化")

            clear_all = before_ts is None
            if before_ts is None:
                before_ts = time.time()  # delete all

            deleted = await self.db.delete_traces_before(before_ts)

            # When clearing all records, also truncate trace log files so that
            # the reported disk usage reflects the actual state.
            if clear_all:
                data_path = get_astrbot_data_path()
                trace_log_dir = os.path.join(data_path, "logs")
                if os.path.exists(trace_log_dir):
                    for fname in os.listdir(trace_log_dir):
                        if "astrbot.trace.log" in fname:
                            fpath = os.path.join(trace_log_dir, fname)
                            try:
                                # Truncate in-place so open file handles remain valid
                                with open(fpath, "w"):
                                    pass
                            except OSError:
                                try:
                                    os.remove(fpath)
                                except OSError:
                                    pass

            return {"deleted": deleted}
        except LogServiceError:
            raise
        except Exception as exc:
            logger.error(f"清除 Trace 失败: {exc}")
            raise LogServiceError(f"清除 Trace 失败: {exc}") from exc
