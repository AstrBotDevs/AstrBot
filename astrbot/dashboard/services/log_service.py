from __future__ import annotations

import asyncio
import contextlib
import json
import stat
import time
import uuid
import zipfile
from collections.abc import AsyncGenerator
from pathlib import Path

from astrbot.core import LogBroker, logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import VERSION
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
        the configured log and trace log files), the in-memory cache split into
        ``memory/logs.txt`` and ``memory/traces.jsonl``, and ``manifest.json``.
        Only regular files are packed. Symlinks, files reached through a
        symlinked directory, special files such as FIFOs and files that go away
        while packing are skipped and listed in the manifest. Archive names
        never contain absolute host paths.

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
        data_dir = Path(get_astrbot_data_path())
        export_dir = Path(get_astrbot_temp_path()) / "log_exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        # The response removes its archive, except when the download is cancelled.
        for stale in export_dir.glob("*.zip"):
            with contextlib.suppress(OSError):
                if time.time() - stale.stat().st_mtime > 3600:
                    stale.unlink()
        archive_path = export_dir / f"astrbot-logs-{uuid.uuid4().hex}.zip"
        manifest = {
            "astrbot_version": VERSION,
            "exported_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
            "files": [],
            "skipped": [],
            "memory_logs": len(logs),
            "memory_traces": len(traces),
        }
        used_names: set[str] = set()
        try:
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for file_path in sorted(
                    StorageCleaner(self.config).collect_log_files()
                ):
                    if file_path.is_relative_to(data_dir):
                        arcname = file_path.relative_to(data_dir).as_posix()
                    else:
                        arcname = f"external/{file_path.name}"
                        index = 2
                        while arcname in used_names:
                            arcname = f"external/{index}/{file_path.name}"
                            index += 1
                    used_names.add(arcname)
                    try:
                        # lstat() and the resolve() check keep symlinks from
                        # pulling in files outside the log locations.
                        if (
                            not stat.S_ISREG(file_path.lstat().st_mode)
                            or file_path.resolve() != file_path
                        ):
                            manifest["skipped"].append(
                                {"name": arcname, "reason": "not a regular file"}
                            )
                            continue
                        archive.write(file_path, arcname)
                        manifest["files"].append(arcname)
                    except OSError as exc:
                        # A log file can be rotated away while we are packing.
                        manifest["skipped"].append(
                            {
                                "name": arcname,
                                "reason": exc.strerror or type(exc).__name__,
                            }
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
                archive.writestr(
                    "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)
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
