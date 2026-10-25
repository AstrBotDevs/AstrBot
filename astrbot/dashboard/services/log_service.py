from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import stat
import threading
import time
import uuid
import zipfile
from collections.abc import AsyncGenerator
from pathlib import Path

from astrbot.core import LogBroker, logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import VERSION
from astrbot.core.dashboard_assets import get_dashboard_version
from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_temp_path
from astrbot.core.utils.storage_cleaner import StorageCleaner
from astrbot.core.utils.trace_store import get_trace_store
from astrbot.dashboard.services.diagnostic_service import collect_diagnostics


class LogServiceError(Exception):
    pass


class LogService:
    def __init__(
        self,
        log_broker: LogBroker,
        config: AstrBotConfig,
        *,
        core=None,
        dashboard_static_folder: str | None = None,
    ) -> None:
        self.log_broker = log_broker
        self.config = config
        self.core = core
        self.dashboard_static_folder = dashboard_static_folder
        self._export_lock = threading.Lock()

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
            # Flush response headers through gzip before waiting for log events.
            yield ": connected\n\n"
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

    def export_logs(
        self,
        *,
        redact: bool = True,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> Path:
        """Build one diagnostic ZIP in a worker thread.

        Args:
            redact: Mask credentials unless the administrator explicitly opts out.
            start_time: Inclusive minimum log or trace start time, in Unix seconds.
            end_time: Inclusive maximum log or trace start time, in Unix seconds.

        Returns:
            Private temporary archive; the response removes it after delivery.

        Raises:
            LogServiceError: If an export is running or safe export is unavailable.
        """
        if start_time is not None and end_time is not None and start_time > end_time:
            raise LogServiceError("Start time must not be after end time")
        if not self._export_lock.acquire(blocking=False):
            raise LogServiceError("Another log export is already running")
        archive_path = None
        try:
            sections, redactor = collect_diagnostics(
                self.config,
                self.core,
                redact=redact,
                webui_version=asyncio.run(
                    get_dashboard_version(self.dashboard_static_folder)
                ),
            )
            cached = list(self.log_broker.log_cache)
            if start_time is not None or end_time is not None:
                cached = [
                    item
                    for item in cached
                    if isinstance(item.get("time"), (int, float))
                    and (start_time is None or item["time"] >= start_time)
                    and (end_time is None or item["time"] <= end_time)
                ]
            logs = [
                str(item.get("data", ""))
                for item in cached
                if item.get("type") != "trace"
            ]
            traces = [item for item in cached if item.get("type") == "trace"]
            redactor.collect(traces)
            data_dir = Path(get_astrbot_data_path())
            export_dir = Path(get_astrbot_temp_path()) / "log_exports"
            export_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
            if export_dir.resolve() != export_dir or not stat.S_ISDIR(
                export_dir.lstat().st_mode
            ):
                raise LogServiceError("Unsafe diagnostic export directory")
            export_dir.chmod(0o700)
            archive_path = export_dir / f"astrbot-diagnostics-{uuid.uuid4().hex}.zip"
            for stale in export_dir.glob("astrbot-*.zip"):
                with contextlib.suppress(OSError):
                    if time.time() - stale.lstat().st_mtime > 3600:
                        stale.unlink()
            manifest = {
                "schema_version": 1,
                "astrbot_version": VERSION,
                "exported_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
                "redacted": redact,
                "time_range": {
                    "start_time": start_time,
                    "end_time": end_time,
                    "disk_log_timezone": list(time.tzname),
                    "undated_logs": "Only continuations of matching dated records are included when a range is selected.",
                    "trace_selection": "Trace start time; matching traces retain their complete details.",
                },
                "privacy_notice": (
                    "Known credentials are masked and public IP addresses use consistent aliases. Local addresses, conversations and personal data may remain; review before sharing."
                    if redact
                    else "Redaction is disabled. This bundle contains original credentials and personal data; do not share publicly."
                ),
                "files": [],
                "skipped": [],
                "truncated": [],
                "memory_logs": len(logs),
                "memory_traces": len(traces),
                "memory_log_range": {
                    "first_timestamp": cached[0].get("time") if cached else None,
                    "last_timestamp": cached[-1].get("time") if cached else None,
                    "cache_limit": self.log_broker.log_cache.maxlen,
                },
                "trace_enabled": bool(self.config.get("trace_enable", False)),
                "trace_history": {
                    "count": 0,
                    "limit": 50,
                    "byte_limit": 16 * 1024 * 1024,
                    "status": "no_history",
                },
            }
            try:
                log_files = sorted(StorageCleaner(self.config).collect_log_files())
            except (OSError, RuntimeError) as exc:
                log_files = []
                manifest["skipped"].append(
                    {"name": "disk_logs", "reason": type(exc).__name__}
                )
            history = []
            trace_path = Path(self.config.get("trace_db_path") or "logs/traces.db")
            if not trace_path.is_absolute():
                trace_path = data_dir / trace_path
            # Do not create a database, enable tracing, or change trace settings.
            if trace_path.is_file():
                try:
                    store = get_trace_store(self.config)
                    page = store.list_traces(
                        limit=50, start_time=start_time, end_time=end_time
                    )
                    history_bytes = 0
                    for summary in page["traces"]:
                        detail = store.get_trace(summary["trace_id"])
                        if detail is None:
                            continue
                        size = len(json.dumps(detail, ensure_ascii=False).encode())
                        if history_bytes + size > 16 * 1024 * 1024:
                            break
                        history_bytes += size
                        history.append(detail)
                        redactor.collect(detail)
                    manifest["trace_history"].update(
                        count=len(history),
                        status="available" if history else "no_history",
                        truncated=len(history) < page["total"],
                    )
                except Exception as exc:
                    manifest["trace_history"].update(
                        count=len(history),
                        status="partial" if history else "unavailable",
                    )
                    manifest["skipped"].append(
                        {"name": "traces/history.jsonl", "reason": type(exc).__name__}
                    )
            elif not manifest["trace_enabled"]:
                manifest["trace_history"]["status"] = "disabled_no_history"
            needed_bytes = 0
            for path in log_files:
                with contextlib.suppress(OSError):
                    needed_bytes += path.lstat().st_size
            # The limits apply to source bytes, including files growing during export.
            budget = 256 * 1024 * 1024
            if (
                shutil.disk_usage(export_dir).free
                < min(needed_bytes, budget) + 20 * 1024 * 1024
            ):
                raise LogServiceError(
                    "Not enough free disk space to export diagnostics"
                )
            flags = (
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0)
                | getattr(os, "O_BINARY", 0)
            )
            used_names = {
                "manifest.json",
                "logs/astrbot.in-memory.log",
                "traces/history.in-memory.jsonl",
                "traces/history.jsonl",
                *sections,
            }
            fd = os.open(
                archive_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                0o600,
            )
            with (
                os.fdopen(fd, "wb") as output,
                zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive,
            ):
                for path in log_files:
                    base_name = (
                        path.relative_to(data_dir).as_posix()
                        if path.is_relative_to(data_dir)
                        else f"external/{path.name}"
                    )
                    base_name = redactor.text(base_name)
                    arcname, index = base_name, 2
                    while arcname in used_names:
                        parent, _, name = base_name.rpartition("/")
                        arcname = (
                            f"{parent}/{index}/{name}" if parent else f"{index}/{name}"
                        )
                        index += 1
                    used_names.add(arcname)
                    try:
                        if (
                            not stat.S_ISREG(path.lstat().st_mode)
                            or path.resolve() != path
                        ):
                            manifest["skipped"].append(
                                {"name": arcname, "reason": "not a regular file"}
                            )
                            continue
                        if budget <= 0:
                            manifest["skipped"].append(
                                {"name": arcname, "reason": "export size limit"}
                            )
                            continue
                        with open(os.open(path, flags), "rb") as source:
                            info = os.fstat(source.fileno())
                            if (
                                not stat.S_ISREG(info.st_mode)
                                or path.resolve() != path
                                or not os.path.samestat(info, path.lstat())
                            ):
                                manifest["skipped"].append(
                                    {
                                        "name": arcname,
                                        "reason": "file changed during export",
                                    }
                                )
                                continue
                            header = source.read(1024)
                            source.seek(0)
                            if b"\x00" in header or header.startswith(
                                (b"PK\x03\x04", b"\x1f\x8b", b"SQLite format 3")
                            ):
                                manifest["skipped"].append(
                                    {
                                        "name": arcname,
                                        "reason": "binary file cannot be redacted",
                                    }
                                )
                                continue
                            limit = min(info.st_size, 64 * 1024 * 1024, budget)
                            if info.st_size > limit:
                                # Keep the same source limits in both export modes.
                                manifest["skipped"].append(
                                    {
                                        "name": arcname,
                                        "reason": "file exceeds export size limit",
                                    }
                                )
                                continue
                            with archive.open(arcname, "w", force_zip64=True) as target:
                                truncated = redactor.copy_log(
                                    source,
                                    target,
                                    limit,
                                    start_time=start_time,
                                    end_time=end_time,
                                )
                            budget -= min(info.st_size, 64 * 1024 * 1024, budget)
                            if truncated:
                                manifest["truncated"].append(arcname)
                        manifest["files"].append(arcname)
                    except OSError as exc:
                        manifest["skipped"].append(
                            {"name": arcname, "reason": type(exc).__name__}
                        )
                archive.writestr(
                    "logs/astrbot.in-memory.log",
                    redactor.text("".join(f"{line}\n" for line in logs)),
                )
                archive.writestr(
                    "traces/history.in-memory.jsonl",
                    "".join(
                        json.dumps(redactor.redact(trace), ensure_ascii=False) + "\n"
                        for trace in traces
                    ),
                )
                archive.writestr(
                    "traces/history.jsonl",
                    "".join(
                        json.dumps(redactor.redact(trace), ensure_ascii=False) + "\n"
                        for trace in history
                    ),
                )
                for name, section in sections.items():
                    archive.writestr(
                        name,
                        json.dumps(
                            redactor.redact(section), ensure_ascii=False, indent=2
                        ),
                    )
                archive.writestr(
                    "manifest.json",
                    json.dumps(redactor.redact(manifest), ensure_ascii=False, indent=2),
                )
            return archive_path
        except Exception as exc:
            if archive_path is not None:
                with contextlib.suppress(OSError):
                    archive_path.unlink(missing_ok=True)
            # Exception messages can include host paths or credentials.
            logger.error("Diagnostic export failed: %s", type(exc).__name__)
            if isinstance(exc, LogServiceError):
                raise
            raise LogServiceError("Unable to create a diagnostic bundle") from exc
        finally:
            self._export_lock.release()

    def get_trace_settings(self) -> dict:
        try:
            return {"trace_enable": self.config.get("trace_enable", True)}
        except Exception as exc:
            logger.error(f"获取 Trace 设置失败: {exc}")
            raise LogServiceError(f"获取 Trace 设置失败: {exc}") from exc

    async def get_trace_history(self, **filters) -> dict:
        """Read a bounded database page.

        Args:
            **filters: Validated page/cursor, keyword, and feature filters.

        Returns:
            Trace summaries and pagination metadata.

        Raises:
            LogServiceError: If the cursor or database is unavailable.
        """
        try:
            store = get_trace_store(self.config)
            return await asyncio.to_thread(store.list_traces, **filters)
        except Exception as exc:
            logger.error("Failed to query trace history: %s", exc)
            raise LogServiceError(str(exc)) from exc

    async def get_trace_detail(self, trace_id: str) -> dict | None:
        """Read the spans and events of a single trace.

        Args:
            trace_id: Validated trace identifier.

        Returns:
            Trace detail, or None if evicted.

        Raises:
            LogServiceError: If database access fails.
        """
        try:
            return await asyncio.to_thread(
                get_trace_store(self.config).get_trace, trace_id
            )
        except Exception as exc:
            logger.error("Failed to query trace detail: %s", exc)
            raise LogServiceError(str(exc)) from exc

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
