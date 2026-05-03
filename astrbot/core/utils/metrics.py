import asyncio
import os
import socket
import sys
import uuid
from contextlib import suppress
from typing import Any

import aiohttp

from astrbot.core import db_helper, logger
from astrbot.core.config import VERSION


class Metric:
    _iid_cache = None
    _has_uploaded_once = False
    _upload_interval_seconds = 10 * 60
    _max_pending_metric_groups = 64
    _counter_fields = {"llm_tick", "msg_event_tick"}
    _pending_metrics: dict[tuple[tuple[str, str], ...], dict[str, Any]] = {}
    _flush_task: asyncio.Task | None = None
    _lock: asyncio.Lock | None = None
    _lock_loop: asyncio.AbstractEventLoop | None = None

    @staticmethod
    def get_installation_id():
        """获取或创建一个唯一的安装ID"""
        if Metric._iid_cache is not None:
            return Metric._iid_cache

        config_dir = os.path.join(os.path.expanduser("~"), ".astrbot")
        id_file = os.path.join(config_dir, ".installation_id")

        if os.path.exists(id_file):
            try:
                with open(id_file) as f:
                    Metric._iid_cache = f.read().strip()
                    return Metric._iid_cache
            except Exception:
                pass
        try:
            os.makedirs(config_dir, exist_ok=True)
            installation_id = str(uuid.uuid4())
            with open(id_file, "w") as f:
                f.write(installation_id)
            Metric._iid_cache = installation_id
            return installation_id
        except Exception:
            Metric._iid_cache = "null"
            return "null"

    @staticmethod
    def _get_lock() -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if Metric._lock is None or Metric._lock_loop is not loop:
            Metric._lock = asyncio.Lock()
            Metric._lock_loop = loop
        return Metric._lock

    @staticmethod
    def _format_group_value(value: Any) -> str:
        return repr(value)

    @staticmethod
    def _get_metric_group_key(kwargs: dict[str, Any]) -> tuple[tuple[str, str], ...]:
        return tuple(
            sorted(
                (key, Metric._format_group_value(value))
                for key, value in kwargs.items()
                if key not in Metric._counter_fields
            )
        )

    @staticmethod
    def _get_metric_group_fields(kwargs: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in kwargs.items()
            if key not in Metric._counter_fields
        }

    @staticmethod
    def _coerce_counter(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _ensure_flush_task_locked() -> None:
        if Metric._flush_task is None or Metric._flush_task.done():
            Metric._flush_task = asyncio.create_task(Metric._flush_periodically())

    @staticmethod
    async def _save_platform_stats(kwargs: dict[str, Any]) -> None:
        try:
            if "adapter_name" in kwargs:
                await db_helper.insert_platform_stats(
                    platform_id=kwargs["adapter_name"],
                    platform_type=kwargs.get("adapter_type", "unknown"),
                )
        except Exception as e:
            logger.error(f"保存指标到数据库失败: {e}")

    @staticmethod
    async def _add_pending_metrics(kwargs: dict[str, Any]) -> None:
        key = Metric._get_metric_group_key(kwargs)
        immediate_metrics = None
        should_flush = False
        lock = Metric._get_lock()
        async with lock:
            if not Metric._has_uploaded_once:
                Metric._has_uploaded_once = True
                immediate_metrics = dict(kwargs)
            else:
                pending = Metric._pending_metrics.setdefault(
                    key,
                    Metric._get_metric_group_fields(kwargs),
                )
                for counter_field in Metric._counter_fields:
                    if counter_field in kwargs:
                        pending[counter_field] = pending.get(
                            counter_field,
                            0,
                        ) + Metric._coerce_counter(kwargs[counter_field])
                Metric._ensure_flush_task_locked()
                should_flush = (
                    len(Metric._pending_metrics) > Metric._max_pending_metric_groups
                )

        if immediate_metrics is not None:
            await Metric._post_metrics(immediate_metrics)
            return
        if should_flush:
            await Metric.flush()

    @staticmethod
    async def _flush_periodically() -> None:
        try:
            while True:
                await asyncio.sleep(Metric._upload_interval_seconds)
                await Metric.flush()

                lock = Metric._get_lock()
                async with lock:
                    if not Metric._pending_metrics:
                        Metric._flush_task = None
                        return
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            current_task = asyncio.current_task()
            with suppress(RuntimeError):
                lock = Metric._get_lock()
                async with lock:
                    if Metric._flush_task is current_task:
                        Metric._flush_task = None

    @staticmethod
    async def flush() -> None:
        """Flush pending metrics immediately."""
        lock = Metric._get_lock()
        async with lock:
            pending_metrics = list(Metric._pending_metrics.values())
            Metric._pending_metrics = {}

        for metrics_data in pending_metrics:
            await Metric._post_metrics(metrics_data)
            await asyncio.sleep(0.25)

    @staticmethod
    async def _post_metrics(metrics_data: dict[str, Any]) -> None:
        if os.environ.get("ASTRBOT_DISABLE_METRICS", "0") == "1":
            return

        base_url = "https://tickstats.soulter.top/api/metric/90a6c2a1"
        payload_metrics = dict(metrics_data)
        payload_metrics["v"] = VERSION
        payload_metrics["os"] = sys.platform
        try:
            payload_metrics["hn"] = socket.gethostname()
        except Exception:
            pass
        try:
            payload_metrics["iid"] = Metric.get_installation_id()
        except Exception:
            pass
        payload = {"metrics_data": payload_metrics}

        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.post(base_url, json=payload, timeout=3) as response:
                    if response.status != 200:
                        pass
        except Exception:
            pass

    @staticmethod
    async def upload(**kwargs) -> None:
        """上传相关非敏感的指标以更好地了解 AstrBot 的使用情况。上传的指标不会包含任何有关消息文本、用户信息等敏感信息。

        Powered by TickStats.
        """
        if os.environ.get("ASTRBOT_DISABLE_METRICS", "0") == "1":
            return

        await Metric._save_platform_stats(kwargs)
        await Metric._add_pending_metrics(dict(kwargs))
