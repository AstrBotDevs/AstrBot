import asyncio
import os
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
from quart import request
from sqlmodel import select

from astrbot.core import DEMO_MODE, logger
from astrbot.core.config import VERSION
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.db.migration.helper import check_migration_needed_v4
from astrbot.core.db.po import ProviderStat
from astrbot.core.utils.astrbot_path import get_astrbot_path
from astrbot.core.utils.io import get_dashboard_version
from astrbot.core.utils.storage_cleaner import StorageCleaner
from astrbot.core.utils.version_comparator import VersionComparator

from .route import Response, Route, RouteContext


class StatRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        db_helper: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/stat/get": ("GET", self.get_stat),
            "/stat/provider-tokens": ("GET", self.get_provider_token_stats),
            "/stat/version": ("GET", self.get_version),
            "/stat/start-time": ("GET", self.get_start_time),
            "/stat/restart-core": ("POST", self.restart_core),
            "/stat/test-ghproxy-connection": ("POST", self.test_ghproxy_connection),
            "/stat/changelog": ("GET", self.get_changelog),
            "/stat/changelog/list": ("GET", self.list_changelog_versions),
            "/stat/first-notice": ("GET", self.get_first_notice),
            "/stat/storage": ("GET", self.get_storage_status),
            "/stat/storage/cleanup": ("POST", self.cleanup_storage),
        }
        self.db_helper = db_helper
        self.register_routes()
        self.core_lifecycle = core_lifecycle
        self.storage_cleaner = StorageCleaner(self.config)

    async def restart_core(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        await self.core_lifecycle.restart()
        return Response().ok().__dict__

    def _get_running_time_components(self, total_seconds: int):
        """将总秒数转换为时分秒组件"""
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return {"hours": hours, "minutes": minutes, "seconds": seconds}

    def is_default_cred(self):
        username = self.config["dashboard"]["username"]
        password = self.config["dashboard"]["password"]
        return (
            username == "astrbot"
            and password == "77b90590a8945a7d36c963981a307dc9"
            and not DEMO_MODE
        )

    async def get_version(self):
        need_migration = await check_migration_needed_v4(self.core_lifecycle.db)

        return (
            Response()
            .ok(
                {
                    "version": VERSION,
                    "dashboard_version": await get_dashboard_version(),
                    "change_pwd_hint": self.is_default_cred(),
                    "need_migration": need_migration,
                },
            )
            .__dict__
        )

    async def get_start_time(self):
        return Response().ok({"start_time": self.core_lifecycle.start_time}).__dict__

    async def get_storage_status(self):
        try:
            status = await asyncio.to_thread(self.storage_cleaner.get_status)
            return Response().ok(status).__dict__
        except Exception:
            logger.error("获取存储占用失败", exc_info=True)
            return (
                Response().error("获取存储占用失败，请查看后端日志了解详情。").__dict__
            )

    async def cleanup_storage(self):
        try:
            data = await request.get_json(silent=True)
            target = "all"
            if isinstance(data, dict):
                target = str(data.get("target", "all"))

            result = await asyncio.to_thread(self.storage_cleaner.cleanup, target)
            return Response().ok(result).__dict__
        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception:
            logger.error("清理存储失败", exc_info=True)
            return Response().error("清理存储失败，请查看后端日志了解详情。").__dict__

    async def get_stat(self):
        offset_sec = request.args.get("offset_sec", 86400)
        offset_sec = int(offset_sec)
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

            # 获取插件信息
            plugins = self.core_lifecycle.star_context.get_all_stars()
            plugin_info = []
            for plugin in plugins:
                info = {
                    "name": getattr(plugin, "name", plugin.__class__.__name__),
                    "version": getattr(plugin, "version", "1.0.0"),
                    "is_enabled": True,
                }
                plugin_info.append(info)

            # 计算运行时长组件
            running_time = self._get_running_time_components(
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
                    "running": running_time,  # 现在返回时间组件而不是格式化的字符串
                    "memory": {
                        "process": psutil.Process().memory_info().rss >> 20,
                        "system": psutil.virtual_memory().total >> 20,
                    },
                    "cpu_percent": round(cpu_percent, 1),
                    "thread_count": thread_count,
                    "start_time": self.core_lifecycle.start_time,
                },
            )

            return Response().ok(stat_dict).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(e.__str__()).__dict__

    @staticmethod
    def _ensure_aware_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    async def get_provider_token_stats(self):
        try:
            try:
                days = int(request.args.get("days", 1))
            except (TypeError, ValueError):
                days = 1
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
                    .order_by(ProviderStat.created_at.asc())
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

            return (
                Response()
                .ok(
                    {
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
                            range_total_tokens / (range_duration_total_ms / 1000 / 60)
                            if range_duration_total_ms > 0
                            else 0
                        ),
                        "range_success_rate": (
                            range_success_calls / range_total_calls
                            if range_total_calls
                            else 0
                        ),
                        "range_by_provider": range_by_provider_data,
                        "range_by_umo": range_by_umo_data,
                        "today_total_tokens": today_total_tokens,
                        "today_total_calls": today_total_calls,
                        "today_by_model": today_by_model_data,
                        "today_by_provider": today_by_provider_data,
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Error: {e!s}").__dict__

    async def test_ghproxy_connection(self):
        """测试 GitHub 代理连接是否可用。"""
        try:
            data = await request.get_json()
            proxy_url: str = data.get("proxy_url")

            if not proxy_url:
                return Response().error("proxy_url is required").__dict__

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
                    ret = {
                        "latency": round((end_time - start_time) * 1000, 2),
                    }
                    return Response().ok(data=ret).__dict__
                return (
                    Response().error(f"Failed. Status code: {response.status}").__dict__
                )
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Error: {e!s}").__dict__

    async def get_changelog(self):
        """获取指定版本的更新日志"""
        try:
            version = request.args.get("version")
            if not version:
                return Response().error("version parameter is required").__dict__

            version = version.lstrip("v")

            # 防止路径遍历攻击
            if not re.match(r"^[a-zA-Z0-9._-]+$", version):
                return Response().error("Invalid version format").__dict__
            if ".." in version or "/" in version or "\\" in version:
                return Response().error("Invalid version format").__dict__

            filename = f"v{version}.md"
            project_path = get_astrbot_path()
            changelogs_dir = os.path.join(project_path, "changelogs")
            changelog_path = os.path.join(changelogs_dir, filename)

            # 规范化路径，防止符号链接攻击
            changelog_path = os.path.realpath(changelog_path)
            changelogs_dir = os.path.realpath(changelogs_dir)

            # 验证最终路径在预期的 changelogs 目录内（防止路径遍历）
            # 确保规范化后的路径以 changelogs_dir 开头，且是目录内的文件
            changelog_path_normalized = os.path.normpath(changelog_path)
            changelogs_dir_normalized = os.path.normpath(changelogs_dir)

            # 检查路径是否在预期目录内（必须是目录的子文件，不能是目录本身）
            expected_prefix = changelogs_dir_normalized + os.sep
            if not changelog_path_normalized.startswith(expected_prefix):
                logger.warning(
                    f"Path traversal attempt detected: {version} -> {changelog_path}",
                )
                return Response().error("Invalid version format").__dict__

            if not os.path.exists(changelog_path):
                return (
                    Response()
                    .error(f"Changelog for version {version} not found")
                    .__dict__
                )
            if not os.path.isfile(changelog_path):
                return (
                    Response()
                    .error(f"Changelog for version {version} not found")
                    .__dict__
                )

            with open(changelog_path, encoding="utf-8") as f:
                content = f.read()

            return Response().ok({"content": content, "version": version}).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Error: {e!s}").__dict__

    async def list_changelog_versions(self):
        """获取所有可用的更新日志版本列表"""
        try:
            project_path = get_astrbot_path()
            changelogs_dir = os.path.join(project_path, "changelogs")

            if not os.path.exists(changelogs_dir):
                return Response().ok({"versions": []}).__dict__

            versions = []
            for filename in os.listdir(changelogs_dir):
                if filename.endswith(".md") and filename.startswith("v"):
                    # 提取版本号（去除 v 前缀和 .md 后缀）
                    version = filename[1:-3]  # 去掉 "v" 和 ".md"
                    # 验证版本号格式
                    if re.match(r"^[a-zA-Z0-9._-]+$", version):
                        versions.append(version)

            # 按版本号排序（降序，最新的在前）
            # 使用项目中的 VersionComparator 进行语义化版本号排序
            versions.sort(
                key=cmp_to_key(
                    lambda v1, v2: VersionComparator.compare_version(v2, v1),
                ),
            )

            return Response().ok({"versions": versions}).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Error: {e!s}").__dict__

    async def get_first_notice(self):
        """读取项目根目录 FIRST_NOTICE.md 内容。"""
        try:
            locale = (request.args.get("locale") or "").strip()
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
                    return Response().ok({"content": content}).__dict__

            return Response().ok({"content": None}).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Error: {e!s}").__dict__
