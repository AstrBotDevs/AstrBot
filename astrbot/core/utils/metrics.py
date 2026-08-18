"""Runtime-owned best-effort telemetry."""

from __future__ import annotations

import asyncio
import os
import socket
import sys
import uuid
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any, Protocol

import aiohttp

from astrbot import logger
from astrbot.core.config import VERSION
from astrbot.core.db.protocols import StatisticsStore
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


class MetricsSink(Protocol):
    """Minimal telemetry capability needed by runtime collaborators."""

    async def upload(self, **kwargs: Any) -> None:
        """Record a best-effort telemetry event."""


class MetricsRuntime:
    """Aggregate and upload telemetry for one AstrBot runtime instance.

    The object deliberately owns all mutable telemetry state.  In particular,
    two runtimes never share pending batches, flush tasks, configuration, or
    database statistics writes.
    """

    UPLOAD_INTERVAL_SECONDS = 10 * 60
    MAX_PENDING_METRIC_GROUPS = 64
    COUNTER_FIELDS = frozenset({"llm_tick", "msg_event_tick"})

    def __init__(
        self,
        config: Mapping[str, Any],
        db: StatisticsStore | None,
        *,
        installation_id_path: Path | None = None,
    ) -> None:
        self._config = config
        self._db = db
        self._installation_id_path = installation_id_path or (
            Path(get_astrbot_data_path()) / ".installation_id"
        )
        self._iid_cache: str | None = None
        self._has_uploaded_once = False
        self._pending_metrics: dict[tuple[tuple[str, str], ...], dict[str, Any]] = {}
        self._flush_task: asyncio.Task[None] | None = None
        self._lock: asyncio.Lock | None = None
        self._lock_loop: asyncio.AbstractEventLoop | None = None
        self._stopped = False
        self._upload_interval_seconds = self.UPLOAD_INTERVAL_SECONDS
        self._max_pending_metric_groups = self.MAX_PENDING_METRIC_GROUPS

    def _is_disabled(self) -> bool:
        """Return whether telemetry is disabled for this runtime."""
        if self._stopped:
            return True
        if os.environ.get("ASTRBOT_TEST_MODE", "").lower() == "true":
            return True
        if os.environ.get("ASTRBOT_DISABLE_METRICS", "0") == "1":
            return True
        return bool(self._config.get("disable_metrics", False))

    async def shutdown(self) -> None:
        """Stop this runtime's periodic telemetry task without flushing.

        Telemetry is best-effort, so shutdown discards queued batches instead
        of extending application termination with network I/O.
        """
        lock = self._get_lock()
        async with lock:
            self._stopped = True
            flush_task = self._flush_task
            self._flush_task = None
            self._pending_metrics.clear()
            self._has_uploaded_once = False

        if flush_task is not None and not flush_task.done():
            flush_task.cancel()
            await asyncio.gather(flush_task, return_exceptions=True)

    def get_installation_id(self) -> str:
        """Return the stable installation identifier for this runtime root."""
        if self._iid_cache is not None:
            return self._iid_cache

        try:
            if self._installation_id_path.exists():
                self._iid_cache = self._installation_id_path.read_text(
                    encoding="utf-8"
                ).strip()
                return self._iid_cache
            self._installation_id_path.parent.mkdir(parents=True, exist_ok=True)
            installation_id = str(uuid.uuid4())
            self._installation_id_path.write_text(installation_id, encoding="utf-8")
            self._iid_cache = installation_id
            return installation_id
        except OSError:
            self._iid_cache = "null"
            return self._iid_cache

    def _get_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    @staticmethod
    def _format_group_value(value: Any) -> str:
        return repr(value)

    def _get_metric_group_key(
        self, kwargs: dict[str, Any]
    ) -> tuple[tuple[str, str], ...]:
        return tuple(
            sorted(
                (key, self._format_group_value(value))
                for key, value in kwargs.items()
                if key not in self.COUNTER_FIELDS
            )
        )

    def _get_metric_group_fields(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in kwargs.items()
            if key not in self.COUNTER_FIELDS
        }

    @staticmethod
    def _coerce_counter(value: Any) -> int:
        try:
            return int(value)
        except TypeError, ValueError:
            return 0

    def _ensure_flush_task_locked(self) -> None:
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._flush_periodically())

    async def _save_platform_stats(self, kwargs: dict[str, Any]) -> None:
        try:
            if "adapter_name" in kwargs and self._db is not None:
                await self._db.insert_platform_stats(
                    platform_id=kwargs["adapter_name"],
                    platform_type=kwargs.get("adapter_type", "unknown"),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("保存指标到数据库失败: %s", exc)

    async def _add_pending_metrics(self, kwargs: dict[str, Any]) -> None:
        key = self._get_metric_group_key(kwargs)
        immediate_metrics = None
        should_flush = False
        lock = self._get_lock()
        async with lock:
            if self._stopped:
                return
            if not self._has_uploaded_once:
                self._has_uploaded_once = True
                immediate_metrics = dict(kwargs)
            else:
                pending = self._pending_metrics.setdefault(
                    key,
                    self._get_metric_group_fields(kwargs),
                )
                for counter_field in self.COUNTER_FIELDS:
                    if counter_field in kwargs:
                        pending[counter_field] = pending.get(
                            counter_field,
                            0,
                        ) + self._coerce_counter(kwargs[counter_field])
                self._ensure_flush_task_locked()
                should_flush = (
                    len(self._pending_metrics) > self._max_pending_metric_groups
                )

        if immediate_metrics is not None:
            await self._post_metrics(immediate_metrics)
            return
        if should_flush:
            await self.flush()

    async def _flush_periodically(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._upload_interval_seconds)
                await self.flush()

                lock = self._get_lock()
                async with lock:
                    if not self._pending_metrics:
                        self._flush_task = None
                        return
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            current_task = asyncio.current_task()
            with suppress(RuntimeError):
                lock = self._get_lock()
                async with lock:
                    if self._flush_task is current_task:
                        self._flush_task = None

    async def flush(self) -> None:
        """Flush this runtime's pending telemetry immediately."""
        lock = self._get_lock()
        async with lock:
            if self._stopped:
                return
            pending_metrics = list(self._pending_metrics.values())
            self._pending_metrics.clear()

        for metrics_data in pending_metrics:
            await self._post_metrics(metrics_data)
            await asyncio.sleep(0.25)

    async def _post_metrics(self, metrics_data: dict[str, Any]) -> None:
        if self._is_disabled():
            return

        base_url = "https://tickstats.soulter.top/api/metric/90a6c2a1"
        payload_metrics = dict(metrics_data)
        payload_metrics["v"] = VERSION
        payload_metrics["os"] = sys.platform
        try:
            payload_metrics["hn"] = socket.gethostname()
        except OSError:
            pass
        try:
            payload_metrics["iid"] = self.get_installation_id()
        except OSError:
            pass
        payload = {"metrics_data": payload_metrics}

        try:
            from astrbot.core.utils.proxy_route import (
                create_aiohttp_session,
                current_aiohttp_proxy,
            )

            async with create_aiohttp_session() as session:
                async with session.post(
                    base_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=3),
                    proxy=current_aiohttp_proxy(),
                ) as response:
                    if response.status != 200:
                        return
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def upload(self, **kwargs: Any) -> None:
        """Upload non-sensitive telemetry for this runtime.

        The payload never includes message text or user identity.  Platform
        statistics are persisted before the batch is aggregated.
        """
        if self._is_disabled():
            return

        await self._save_platform_stats(kwargs)
        await self._add_pending_metrics(dict(kwargs))
