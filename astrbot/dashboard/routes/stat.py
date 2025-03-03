import traceback
import psutil
import time
from .route import Route, Response, RouteContext
from astrbot.core import logger
from quart import request
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.config import VERSION


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
        }
        self.db_helper = db_helper
        self.register_routes()
        self.core_lifecycle = core_lifecycle

    async def restart_core(self):
        self.core_lifecycle.restart()
        return Response().ok().__dict__

    def format_sec(self, sec: int):
        m, s = divmod(sec, 60)
        h, m = divmod(m, 60)
        return f"{h}小时{m}分{s}秒"

    async def get_version(self):
        return Response().ok({"version": VERSION}).__dict__

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
            for bucket_end in range(start_time, now, 1800):
                cnt = 0
                while (
                    idx < len(stat.platform)
                    and stat.platform[idx].timestamp < bucket_end
                ):
                    cnt += stat.platform[idx].count
                    idx += 1
                message_time_based_stats.append([bucket_end, cnt])

            stat_dict = stat.__dict__

            stat_dict.update(
                {
                    "platform": self.db_helper.get_grouped_base_stats(
                        offset_sec
                    ).platform,
                    "message_count": self.db_helper.get_total_message_count() or 0,
                    "platform_count": len(
                        self.core_lifecycle.platform_manager.get_insts()
                    ),
                    "plugin_count": len(
                        self.core_lifecycle.star_context.get_all_stars()
                    ),
                    "message_time_series": message_time_based_stats,
                    "running": self.format_sec(
                        int(time.time()) - self.core_lifecycle.start_time
                    ),
                    "memory": {
                        "process": psutil.Process().memory_info().rss >> 20,
                        "system": psutil.virtual_memory().total >> 20,
                    },
                }
            )

            return Response().ok(stat_dict).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(e.__str__()).__dict__
