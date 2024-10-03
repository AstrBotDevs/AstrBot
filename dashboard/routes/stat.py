import traceback, psutil, time, datetime
from .. import Route, Response, logger
from quart import Quart, request
from type.types import Context
from astrbot.db import BaseDatabase
from type.config import VERSION

class StatRoute(Route):
    def __init__(self, context: Context, app: Quart, db_helper: BaseDatabase) -> None:
        super().__init__(context, app)
        self.routes = {
            '/stat/get': ('GET', self.get_stat),
            '/stat/version': ('GET', self.get_version),
        }
        self.db_helper = db_helper
        self.register_routes()
        
    def format_sec(self, sec: int):
        m, s = divmod(sec, 60)
        h, m = divmod(m, 60)
        return f"{h}小时{m}分{s}秒"
        
    async def get_version(self):
        return Response().ok({
            "version": VERSION
        }).__dict__
    
    async def get_stat(self):
        offset_sec = request.args.get('offset_sec', 86400)
        offset_sec = int(offset_sec)
        try:
            stat = self.db_helper.get_base_stats(offset_sec)
            now = int(time.time())
            start_time = now - offset_sec
            message_time_based_stats = []
            
            idx = 0
            for bucket_end in range(start_time, now, 1800):
                cnt = 0
                while idx < len(stat.platform) and stat.platform[idx].timestamp < bucket_end:
                    cnt += stat.platform[idx].count
                    idx += 1
                message_time_based_stats.append([bucket_end, cnt])
            
            stat_dict = stat.__dict__
            
            stat_dict.update({
                "platform": self.db_helper.get_grouped_base_stats(offset_sec).platform,
                "message_count": self.db_helper.get_total_message_count() or 0,
                "platform_count": len(self.context.platforms),
                "message_time_series": message_time_based_stats,
                "running": self.format_sec(int(time.time() - self.context._start_running)),
                "memory": {
                    "process": psutil.Process().memory_info().rss >> 20,
                    "system": psutil.virtual_memory().total >> 20
                }
            })
            
            return Response().ok(stat_dict).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(e.__str__()).__dict__