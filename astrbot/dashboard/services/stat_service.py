import ast
import asyncio
import re
import threading
import time
import traceback
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from functools import cmp_to_key
from pathlib import Path
from typing import Any, Literal

import psutil
from sqlmodel import col, func, select

from astrbot import logger
from astrbot.core.config import VERSION
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.core_runtime import CoreControl
from astrbot.core.db.po import PlatformStat, ProviderStat
from astrbot.core.db.protocols import StatisticsSessionStore
from astrbot.core.desktop_runtime import (
    DESKTOP_MANAGED_RESTART_MESSAGE,
    is_desktop_managed_backend,
)
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.star.star import PluginRegistry
from astrbot.core.umo_alias import build_umo_alias_map, serialize_umo_alias
from astrbot.core.utils.astrbot_path import get_astrbot_path
from astrbot.core.utils.auth_password import (
    is_default_dashboard_password,
    is_md5_dashboard_password,
)
from astrbot.core.utils.io import get_dashboard_dist_version, get_dashboard_version
from astrbot.core.utils.storage_cleaner import StorageCleaner
from astrbot.core.utils.t2i.renderer import HtmlRenderer
from astrbot.dashboard.password_state import (
    get_dashboard_password_hash,
    is_password_change_required,
    is_password_storage_upgraded,
)
from astrbot.utils.version_comparator import VersionComparator


class StatServiceError(Exception):
    pass


class StatService:
    def __init__(
        self,
        db_helper: StatisticsSessionStore,
        core_control: CoreControl,
        config: AstrBotConfig,
        *,
        demo_mode: bool,
        start_time: int,
        html_renderer: HtmlRenderer,
        plugin_catalog: PluginRegistry,
        platform_manager: PlatformManager,
    ) -> None:
        self.db_helper = db_helper
        self.core_control = core_control
        self.config = config
        self.demo_mode = demo_mode
        self.start_time = start_time
        self.html_renderer = html_renderer
        self.plugin_catalog = plugin_catalog
        self.platform_manager = platform_manager
        self.storage_cleaner = StorageCleaner(config)

    async def restart_core(self) -> None:
        if self.demo_mode:
            raise StatServiceError(
                "You are not permitted to do this operation in demo mode"
            )
        if is_desktop_managed_backend():
            raise StatServiceError(DESKTOP_MANAGED_RESTART_MESSAGE)

        await self.core_control.restart()

    @staticmethod
    def get_running_time_components(total_seconds: int):
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return {"hours": hours, "minutes": minutes, "seconds": seconds}

    async def is_default_cred(self):
        password_change_required = await is_password_change_required(
            self.config,
        )
        if password_change_required:
            return not self.demo_mode

        storage_upgraded = await is_password_storage_upgraded(
            self.config,
        )
        if not storage_upgraded:
            return False

        username = self.config["dashboard"]["username"]
        password = get_dashboard_password_hash(self.config, upgraded=True)
        return (
            username == "astrbot" and is_default_dashboard_password(password)
        ) and not self.demo_mode

    async def get_version(self) -> dict:
        storage_upgraded = await is_password_storage_upgraded(
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
        }

    async def get_public_versions(
        self,
        dashboard_static_folder: str | None = None,
    ) -> dict:
        """Return version details that are safe to expose before login.

        Args:
            dashboard_static_folder: Current dashboard static folder, when known.

        Returns:
            Public WebUI and AstrBot version information.
        """

        def read_code_version() -> str | None:
            """Read the packaged AstrBot code version from disk.

            Returns:
                The `__version__` value when available, otherwise `None`.
            """

            version_file = Path(get_astrbot_path()) / "astrbot" / "__init__.py"
            module = ast.parse(version_file.read_text(encoding="utf-8"))
            for statement in module.body:
                if not isinstance(statement, ast.Assign):
                    continue
                if not any(
                    isinstance(target, ast.Name) and target.id == "__version__"
                    for target in statement.targets
                ):
                    continue
                if isinstance(statement.value, ast.Constant) and isinstance(
                    statement.value.value,
                    str,
                ):
                    return statement.value.value.strip()
                return None
            return None

        dashboard_version = None
        try:
            if dashboard_static_folder:
                dashboard_version = get_dashboard_dist_version(
                    Path(dashboard_static_folder)
                )
            if dashboard_version is None:
                dashboard_version = await get_dashboard_version()
        except Exception as exc:
            logger.warning("Failed to read public WebUI version: %s", exc)

        code_version = None
        try:
            code_version = await asyncio.to_thread(read_code_version)
        except Exception as exc:
            logger.warning("Failed to read AstrBot code version from disk: %s", exc)

        return {
            "webui_version": dashboard_version,
            "astrbot_version": VERSION,
            "astrbot_code_version": code_version,
        }

    def get_start_time(self) -> dict:
        return {"start_time": self.start_time}

    def get_t2i_runtime_stats(self) -> dict[str, int | float | bool]:
        """Return the current non-sensitive local T2I renderer statistics."""
        return self.html_renderer.get_runtime_stats()

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
            stat = await self.db_helper.get_platform_stats(offset_sec)
            async with self.db_helper.get_db() as session:
                total_messages = (
                    await session.execute(
                        select(func.coalesce(func.sum(PlatformStat.count), 0)),
                    )
                ).scalar_one()
            now = int(time.time())
            start_time = now - offset_sec
            message_time_based_stats = []
            platform_stats: list[tuple[Any, int]] = []
            for item in stat:
                if not hasattr(item, "platform_id") or not hasattr(item, "count"):
                    logger.warning("Skipping invalid platform stat row: %r", item)
                    continue
                try:
                    timestamp = int(
                        self._coerce_platform_stat_timestamp(
                            getattr(item, "timestamp", None)
                        ).timestamp()
                    )
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "Skipping platform stat row with invalid timestamp %r: %s",
                        getattr(item, "timestamp", None),
                        exc,
                    )
                    continue
                platform_stats.append((item, timestamp))

            platform_stats.sort(key=lambda entry: entry[1])

            idx = 0
            for bucket_end in range(start_time, now, 3600):
                cnt = 0
                while idx < len(platform_stats) and platform_stats[idx][1] < bucket_end:
                    cnt += platform_stats[idx][0].count
                    idx += 1
                message_time_based_stats.append([bucket_end, cnt])

            grouped_platform = []
            grouped_counts: dict[str, int] = defaultdict(int)
            grouped_timestamps: dict[str, int] = {}
            for item, timestamp in platform_stats:
                grouped_counts[item.platform_id] += item.count
                grouped_timestamps[item.platform_id] = max(
                    grouped_timestamps.get(item.platform_id, 0),
                    timestamp,
                )
            for platform_id, count in grouped_counts.items():
                grouped_platform.append(
                    {
                        "name": platform_id,
                        "count": count,
                        "timestamp": grouped_timestamps[platform_id],
                    }
                )

            stat_dict: dict[str, Any] = {"platform": grouped_platform}

            process = psutil.Process()
            process_cpu = await asyncio.to_thread(process.cpu_percent, 0.5)
            cpu_percent = process_cpu / (psutil.cpu_count() or 1)
            thread_count = threading.active_count()

            plugins = self.plugin_catalog.all()
            plugin_info = []
            for plugin in plugins:
                info = {
                    "name": getattr(plugin, "name", plugin.__class__.__name__),
                    "version": getattr(plugin, "version", "1.0.0"),
                    "is_enabled": True,
                }
                plugin_info.append(info)

            running_time = self.get_running_time_components(
                int(time.time()) - self.start_time,
            )
            stat_dict.update(
                {
                    "message_count": total_messages,
                    "platform_count": self.platform_manager.get_platform_count(),
                    "plugin_count": len(plugins),
                    "plugins": plugin_info,
                    "message_time_series": message_time_based_stats,
                    "running": running_time,
                    "memory": {
                        "process": process.memory_info().rss >> 20,
                        "system": psutil.virtual_memory().total >> 20,
                    },
                    "cpu_percent": round(cpu_percent, 1),
                    "thread_count": thread_count,
                    "start_time": self.start_time,
                },
            )
            return stat_dict
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise StatServiceError(str(exc)) from exc

    @staticmethod
    def _ensure_aware_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @classmethod
    def _coerce_platform_stat_timestamp(cls, value: Any) -> datetime:
        if isinstance(value, datetime):
            return cls._ensure_aware_utc(value)

        if isinstance(value, int | float):
            timestamp = float(value)
            if timestamp > 10_000_000_000:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp, UTC)

        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("timestamp is empty")
            try:
                numeric_timestamp = float(normalized)
            except ValueError:
                iso_timestamp = normalized.replace("Z", "+00:00")
                return cls._ensure_aware_utc(datetime.fromisoformat(iso_timestamp))
            if numeric_timestamp > 10_000_000_000:
                numeric_timestamp /= 1000
            return datetime.fromtimestamp(numeric_timestamp, UTC)

        raise TypeError(f"Unsupported timestamp type: {type(value).__name__}")

    async def get_provider_token_stats(self, days: int) -> dict:
        try:
            if days not in (1, 3, 7):
                days = 1

            local_tz = datetime.now().astimezone().tzinfo or UTC
            now_local = datetime.now(local_tz)
            range_start_local = (now_local - timedelta(days=days)).replace(
                minute=0, second=0, microsecond=0
            )
            today_start_local = now_local.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            query_start_local = min(range_start_local, today_start_local)
            query_start_utc = query_start_local.astimezone(UTC)

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
            platform_type_by_id = {"webchat": "webchat"}
            for platform_config in self.config.get("platform", []):
                platform_id = platform_config.get("id")
                platform_type = platform_config.get("type")
                if platform_id and platform_type:
                    platform_type_by_id[str(platform_id)] = str(platform_type)
            alias_map = build_umo_alias_map(
                await self.db_helper.get_umo_aliases(list(total_by_umo)),
            )
            range_by_umo_data = []
            for umo, tokens in sorted(
                total_by_umo.items(),
                key=lambda item: item[1],
                reverse=True,
            ):
                alias_info = serialize_umo_alias(alias_map.get(umo), umo)
                range_by_umo_data.append(
                    {
                        "umo": umo,
                        "display_name": alias_info["display_name"],
                        "platform_type": platform_type_by_id.get(
                            umo.split(":", 1)[0],
                            umo.split(":", 1)[0],
                        ),
                        "tokens": tokens,
                    },
                )

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

            from astrbot.core.utils.outbound_http import (
                GITHUB_MIRROR_TEST,
                OutboundRequestError,
                compose_github_mirror_url,
                fetch_text,
                validate_github_mirror_origin,
            )

            try:
                validate_github_mirror_origin(proxy_url)
                test_url = compose_github_mirror_url(
                    proxy_url,
                    "https://github.com/AstrBotDevs/AstrBot/raw/refs/heads/master/.python-version",
                )
            except OutboundRequestError as exc:
                raise StatServiceError("镜像测试失败") from exc

            start_time = time.time()
            try:
                status, _body, _headers = await fetch_text(test_url, GITHUB_MIRROR_TEST)
            except OutboundRequestError as exc:
                raise StatServiceError("镜像测试失败") from exc
            if status == 200:
                end_time = time.time()
                return {
                    "latency": round((end_time - start_time) * 1000, 2),
                }
            raise StatServiceError("镜像测试失败")
        except StatServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise StatServiceError("镜像测试失败") from exc

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

    def get_first_notice(self, locale: Literal["zh-CN", "en-US"] | None) -> dict:
        try:
            base_path = Path(get_astrbot_path())
            candidates = (
                [base_path / "FIRST_NOTICE.en-US.md", base_path / "FIRST_NOTICE.md"]
                if locale == "en-US"
                else [
                    base_path / "FIRST_NOTICE.md",
                    base_path / "FIRST_NOTICE.en-US.md",
                ]
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
