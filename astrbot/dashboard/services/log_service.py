from __future__ import annotations

import asyncio
import json
import time
import uuid
import zipfile
from collections.abc import AsyncGenerator
from pathlib import Path

from astrbot.core import LogBroker, logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_temp_path
from astrbot.core.utils.storage_cleaner import StorageCleaner


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

    def export_logs(self) -> Path:
        """Pack the log files and the in-memory logs into a zip archive.

        The archive holds the files found by ``StorageCleaner`` (data/logs plus
        the configured log and trace log files) and the in-memory cache, split
        into ``memory/logs.txt`` and ``memory/traces.jsonl``.

        Returns:
            Path of the archive in the temp directory. The caller removes it
            once it has been sent.

        Raises:
            LogServiceError: If the archive cannot be written.
        """
        cached = list(self.log_broker.log_cache)
        logs = [
            str(item.get("data", "")) for item in cached if item.get("type") != "trace"
        ]
        traces = [item for item in cached if item.get("type") == "trace"]
        data_dir = Path(get_astrbot_data_path()).resolve()
        export_dir = Path(get_astrbot_temp_path()) / "log_exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        archive_path = export_dir / f"astrbot-logs-{uuid.uuid4().hex}.zip"
        log_files = {
            path.resolve() for path in StorageCleaner(self.config).collect_log_files()
        }
        try:
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for file_path in sorted(log_files):
                    if file_path.is_relative_to(data_dir):
                        arcname = file_path.relative_to(data_dir).as_posix()
                    else:
                        arcname = f"external/{file_path.name}"
                    try:
                        archive.write(file_path, arcname)
                    except OSError as exc:
                        # A log file can be rotated away while we are packing.
                        logger.warning(
                            f"Skipped unreadable log file {file_path}: {exc}"
                        )
                archive.writestr(
                    "memory/logs.txt", "".join(f"{line}\n" for line in logs)
                )
                archive.writestr(
                    "memory/traces.jsonl",
                    "".join(
                        json.dumps(trace, ensure_ascii=False, default=str) + "\n"
                        for trace in traces
                    ),
                )
        except Exception as exc:
            archive_path.unlink(missing_ok=True)
            logger.error(f"Failed to export logs: {exc}")
            raise LogServiceError(f"Failed to export logs: {exc}") from exc
        return archive_path

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
