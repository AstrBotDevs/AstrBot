import os
import re
import threading
import time
import traceback
from functools import cmp_to_key

import aiohttp
import psutil
from quart import request

from astrbot.core import DEMO_MODE, logger
from astrbot.core.config import VERSION
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.db.migration.helper import check_migration_needed_v4
from astrbot.core.utils.astrbot_path import get_astrbot_path
from astrbot.core.utils.io import get_dashboard_version
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
            "/stat/version": ("GET", self.get_version),
            "/stat/start-time": ("GET", self.get_start_time),
            "/stat/restart-core": ("POST", self.restart_core),
            "/stat/test-ghproxy-connection": ("POST", self.test_ghproxy_connection),
            "/stat/changelog": ("GET", self.get_changelog),
            "/stat/changelog/list": ("GET", self.list_changelog_versions),
        }
        self.db_helper = db_helper
        self.register_routes()
        self.core_lifecycle = core_lifecycle

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
