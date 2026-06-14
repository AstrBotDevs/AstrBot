from __future__ import annotations

import asyncio
import re
import threading
import time
import traceback
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import cmp_to_key
from pathlib import Path

import aiohttp
import psutil
from sqlmodel import col, select

from astrbot.core import DEMO_MODE, logger
from astrbot.core.config import VERSION
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.db.migration.helper import check_migration_needed_v4
from astrbot.core.db.po import ProviderStat
from astrbot.core.utils.astrbot_path import get_astrbot_path
from astrbot.core.utils.auth_password import (
    is_default_dashboard_password,
    is_md5_dashboard_password,
)
from astrbot.core.utils.io import get_dashboard_version
from astrbot.core.utils.storage_cleaner import StorageCleaner
from astrbot.core.utils.version_comparator import VersionComparator
from astrbot.dashboard.password_state import (
    get_dashboard_password_hash,
    is_password_change_required,
    is_password_storage_upgraded,
)


class StatServiceError(Exception):
    pass


class StatService:
    def __init__(
        self,
        db_helper: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
        config: AstrBotConfig,
    ) -> None:
        self.db_helper = db_helper
        self.core_lifecycle = core_lifecycle
        self.config = config
        self.storage_cleaner = StorageCleaner(config)

    async def restart_core(self) -> None:
        if DEMO_MODE:
            raise StatServiceError(
                "You are not permitted to do this operation in demo mode"
            )
        await self.core_lifecycle.restart()

    @staticmethod
    def get_running_time_components(total_seconds: int):
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return {"hours": hours, "minutes": minutes, "seconds": seconds}

    async def is_default_cred(self):
        password_change_required = await is_password_change_required(
            self.db_helper,
            self.config,
        )
        if password_change_required:
            return not DEMO_MODE

        storage_upgraded = await is_password_storage_upgraded(
            self.db_helper,
            self.config,
        )
        if not storage_upgraded:
            return False

        username = self.config["dashboard"]["username"]
        password = get_dashboard_password_hash(self.config, upgraded=True)
        return (
            username == "astrbot" and is_default_dashboard_password(password)
        ) and not DEMO_MODE

    async def get_version(self) -> dict:
        need_migration = await check_migration_needed_v4(self.core_lifecycle.db)
        storage_upgraded = await is_password_storage_upgraded(
            self.db_helper,
            self.config,
        )
        password = get_dashboard_password_hash(
            self.config,
            upgraded=storage_upgraded,
        )

        md5_pwd_hint = is_md5_dashboard_password(password)
        return {
            "version": VERSION,
            "dashboard_version": await get_dashboard_version(),
            "change_pwd_hint": await self.is_default_cred(),
            "md5_pwd_hint": md5_pwd_hint,
            "password_upgrade_required": not storage_upgraded,
            "need_migration": need_migration,
        }

    def get_start_time(self) -> dict:
        return {"start_time": self.core_lifecycle.start_time}

    async def get_storage_status(self) -> dict:
        try:
            return await asyncio.to_thread(self.storage_cleaner.get_status)
        except Exception as exc:
            logger.error("获取存储占用失败", exc_info=True)
            raise StatServiceError(
                "获取存储占用失败，请查看后端日志了解详情。"
            ) from exc

    async def cleanup_storage(self, target: str) -> dict:
        try:
            return await asyncio.to_thread(self.storage_cleaner.cleanup, target)
        except ValueError as exc:
            raise StatServiceError(str(exc)) from exc
        except Exception as exc:
            logger.error("清理存储失败", exc_info=True)
            raise StatServiceError("清理存储失败，请查看后端日志了解详情。") from exc

    async def get_stat(self, offset_sec: int) -> dict:
        try:
            stat = self.db_helper.get_base_stats(offset_sec)
            now = int(time.time())
            start_time = now - offset_sec
            message_time_based_stats = []

            idx = 0
            for bucket_end in range(start_time, now, 3600):
                cnt = 0
                while (
                    idx < len(stat.platform)
                    and stat.platform[idx].timestamp < bucket_end
                ):
                    cnt += stat.platform[idx].count
                    idx += 1
                message_time_based_stats.append([bucket_end, cnt])

            stat_dict = stat.__dict__

            cpu_percent = psutil.cpu_percent(interval=0.5)
            thread_count = threading.active_count()

            plugins = self.core_lifecycle.star_context.get_all_stars()
            plugin_info = []
            for plugin in plugins:
                info = {
                    "name": getattr(plugin, "name", plugin.__class__.__name__),
                    "version": getattr(plugin, "version", "1.0.0"),
                    "is_enabled": True,
                }
                plugin_info.append(info)

            running_time = self.get_running_time_components(
                int(time.time()) - self.core_lifecycle.start_time,
            )

            stat_dict.update(
                {
                    "platform": self.db_helper.get_grouped_base_stats(
                        offset_sec,
                    ).platform,
                    "message_count": self.db_helper.get_total_message_count() or 0,
                    "platform_count": len(
                        self.core_lifecycle.platform_manager.get_insts(),
                    ),
                    "plugin_count": len(plugins),
                    "plugins": plugin_info,
                    "message_time_series": message_time_based_stats,
                    "running": running_time,
                    "memory": {
                        "process": psutil.Process().memory_info().rss >> 20,
                        "system": psutil.virtual_memory().total >> 20,
                    },
                    "cpu_percent": round(cpu_percent, 1),
                    "thread_count": thread_count,
                    "start_time": self.core_lifecycle.start_time,
                },
            )
            return stat_dict
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise StatServiceError(str(exc)) from exc

    @staticmethod
    def _ensure_aware_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    async def get_provider_token_stats(self, days: int) -> dict:
        try:
            if days not in (1, 3, 7):
                days = 1

            local_tz = datetime.now().astimezone().tzinfo or timezone.utc
            now_local = datetime.now(local_tz)
            range_start_local = (now_local - timedelta(days=days)).replace(
                minute=0, second=0, microsecond=0
            )
            today_start_local = now_local.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            query_start_local = min(range_start_local, today_start_local)
            query_start_utc = query_start_local.astimezone(timezone.utc)

            async with self.db_helper.get_db() as session:
                result = await session.execute(
                    select(ProviderStat)
                    .where(
                        ProviderStat.agent_type == "internal",
                        ProviderStat.created_at >= query_start_utc,
                    )
                    .order_by(col(ProviderStat.created_at).asc())
                )
                records = result.scalars().all()

            bucket_timestamps: list[int] = []
            bucket_cursor = range_start_local
            while bucket_cursor <= now_local:
                bucket_timestamps.append(int(bucket_cursor.timestamp() * 1000))
                bucket_cursor += timedelta(hours=1)

            trend_by_provider: dict[str, dict[int, int]] = defaultdict(
                lambda: defaultdict(int)
            )
            total_by_provider: dict[str, int] = defaultdict(int)
            total_by_umo: dict[str, int] = defaultdict(int)
            total_by_bucket: dict[int, int] = defaultdict(int)
            range_total_tokens = 0
            range_total_output_tokens = 0
            range_total_calls = 0
            range_success_calls = 0
            range_ttft_total_ms = 0.0
            range_ttft_samples = 0
            range_duration_total_ms = 0.0
            range_duration_samples = 0
            today_by_model: dict[str, int] = defaultdict(int)
            today_by_provider: dict[str, int] = defaultdict(int)
            today_total_tokens = 0
            today_total_calls = 0

            for record in records:
                created_at_utc = self._ensure_aware_utc(record.created_at)
                created_at_local = created_at_utc.astimezone(local_tz)
                token_total = (
                    record.token_input_other
                    + record.token_input_cached
                    + record.token_output
                )
                provider_id = record.provider_id or "unknown"
                provider_model = record.provider_model or "Unknown"

                if created_at_local >= range_start_local:
                    bucket_local = created_at_local.replace(
                        minute=0, second=0, microsecond=0
                    )
                    bucket_ts = int(bucket_local.timestamp() * 1000)
                    trend_by_provider[provider_id][bucket_ts] += token_total
                    total_by_provider[provider_id] += token_total
                    total_by_umo[record.umo or "unknown"] += token_total
                    total_by_bucket[bucket_ts] += token_total
                    range_total_tokens += token_total
                    range_total_calls += 1
                    if record.status != "error":
                        range_success_calls += 1
                    if record.time_to_first_token > 0:
                        range_ttft_total_ms += record.time_to_first_token * 1000
                        range_ttft_samples += 1
                    if record.end_time > record.start_time:
                        range_duration_total_ms += (
                            record.end_time - record.start_time
                        ) * 1000
                        range_duration_samples += 1
                        range_total_output_tokens += record.token_output

                if created_at_local >= today_start_local:
                    today_total_calls += 1
                    today_total_tokens += token_total
                    today_by_model[provider_model] += token_total
                    today_by_provider[provider_id] += token_total

            sorted_provider_ids = sorted(
                total_by_provider.keys(),
                key=lambda item: total_by_provider[item],
                reverse=True,
            )

            series = [
                {
                    "name": provider_id,
                    "data": [
                        [bucket_ts, trend_by_provider[provider_id].get(bucket_ts, 0)]
                        for bucket_ts in bucket_timestamps
                    ],
                    "total_tokens": total_by_provider[provider_id],
                }
                for provider_id in sorted_provider_ids
            ]

            total_series = [
                [bucket_ts, total_by_bucket.get(bucket_ts, 0)]
                for bucket_ts in bucket_timestamps
            ]

            today_by_model_data = [
                {"provider_model": model_name, "tokens": tokens}
                for model_name, tokens in sorted(
                    today_by_model.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            ]
            today_by_provider_data = [
                {"provider_id": provider_id, "tokens": tokens}
                for provider_id, tokens in sorted(
                    today_by_provider.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            ]
            range_by_provider_data = [
                {"provider_id": provider_id, "tokens": tokens}
                for provider_id, tokens in sorted(
                    total_by_provider.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            ]
            range_by_umo_data = [
                {"umo": umo, "tokens": tokens}
                for umo, tokens in sorted(
                    total_by_umo.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            ]

            return {
                "days": days,
                "trend": {
                    "series": series,
                    "total_series": total_series,
                },
                "range_total_tokens": range_total_tokens,
                "range_total_calls": range_total_calls,
                "range_avg_ttft_ms": (
                    range_ttft_total_ms / range_ttft_samples
                    if range_ttft_samples
                    else 0
                ),
                "range_avg_duration_ms": (
                    range_duration_total_ms / range_duration_samples
                    if range_duration_samples
                    else 0
                ),
                "range_avg_tpm": (
                    range_total_output_tokens / (range_duration_total_ms / 1000 / 60)
                    if range_duration_total_ms > 0
                    else 0
                ),
                "range_success_rate": (
                    range_success_calls / range_total_calls if range_total_calls else 0
                ),
                "range_by_provider": range_by_provider_data,
                "range_by_umo": range_by_umo_data,
                "today_total_tokens": today_total_tokens,
                "today_total_calls": today_total_calls,
                "today_by_model": today_by_model_data,
                "today_by_provider": today_by_provider_data,
            }
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise StatServiceError(f"Error: {exc!s}") from exc

    async def test_ghproxy_connection(self, proxy_url: str | None) -> dict:
        try:
            if not proxy_url:
                raise StatServiceError("proxy_url is required")

            proxy_url = proxy_url.rstrip("/")
            test_url = f"{proxy_url}/https://github.com/AstrBotDevs/AstrBot/raw/refs/heads/master/.python-version"
            start_time = time.time()

            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    test_url,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response,
            ):
                if response.status == 200:
                    end_time = time.time()
                    _ = await response.text()
                    return {
                        "latency": round((end_time - start_time) * 1000, 2),
                    }
                raise StatServiceError(f"Failed. Status code: {response.status}")
        except StatServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise StatServiceError(f"Error: {exc!s}") from exc

    def get_changelog(self, version: str | None) -> dict:
        try:
            if not version:
                raise StatServiceError("version parameter is required")

            version = version.lstrip("v")
            if not re.match(r"^[a-zA-Z0-9._-]+$", version):
                raise StatServiceError("Invalid version format")
            if ".." in version or "/" in version or "\\" in version:
                raise StatServiceError("Invalid version format")

            changelogs_dir = (Path(get_astrbot_path()) / "changelogs").resolve()
            changelog_path = (changelogs_dir / f"v{version}.md").resolve(strict=False)
            if not changelog_path.is_relative_to(changelogs_dir):
                logger.warning(
                    "Path traversal attempt detected: %s -> %s",
                    version,
                    changelog_path,
                )
                raise StatServiceError("Invalid version format")

            if not changelog_path.is_file():
                raise StatServiceError(f"Changelog for version {version} not found")

            content = changelog_path.read_text(encoding="utf-8")
            return {"content": content, "version": version}
        except StatServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise StatServiceError(f"Error: {exc!s}") from exc

    def list_changelog_versions(self) -> dict:
        try:
            changelogs_dir = Path(get_astrbot_path()) / "changelogs"
            if not changelogs_dir.exists():
                return {"versions": []}

            versions = []
            for path in changelogs_dir.iterdir():
                filename = path.name
                if filename.endswith(".md") and filename.startswith("v"):
                    version = filename[1:-3]
                    if re.match(r"^[a-zA-Z0-9._-]+$", version):
                        versions.append(version)

            versions.sort(
                key=cmp_to_key(
                    lambda v1, v2: VersionComparator.compare_version(v2, v1),
                ),
            )

            return {"versions": versions}
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise StatServiceError(f"Error: {exc!s}") from exc

    def get_first_notice(self, locale: str | None) -> dict:
        try:
            locale = (locale or "").strip()
            if not re.match(r"^[A-Za-z0-9_-]*$", locale):
                locale = ""

            base_path = Path(get_astrbot_path())
            candidates: list[Path] = []

            if locale:
                candidates.append(base_path / f"FIRST_NOTICE.{locale}.md")
                if locale.lower().startswith("zh"):
                    candidates.append(base_path / "FIRST_NOTICE.md")
                    candidates.append(base_path / "FIRST_NOTICE.zh-CN.md")
                elif locale.lower().startswith("en"):
                    candidates.append(base_path / "FIRST_NOTICE.en-US.md")

            candidates.extend(
                [
                    base_path / "FIRST_NOTICE.md",
                    base_path / "FIRST_NOTICE.en-US.md",
                ],
            )

            for notice_path in candidates:
                if not notice_path.is_file():
                    continue
                content = notice_path.read_text(encoding="utf-8")
                if content.strip():
                    return {"content": content}

            return {"content": None}
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise StatServiceError(f"Error: {exc!s}") from exc
