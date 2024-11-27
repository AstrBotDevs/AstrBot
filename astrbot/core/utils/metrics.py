import asyncio
import aiohttp
import json
import sys
import logging

from core.db import BaseDatabase
from collections import defaultdict
from core.config import VERSION

logger = logging.getLogger("astrbot")

class MetricUploader():
    def __init__(self, db_helper: BaseDatabase) -> None:
        self.platform_stats = {}
        self.llm_stats = defaultdict(int)
        self.command_stats = defaultdict(int)
        self.db_helper = db_helper

    async def upload_metrics(self):
        '''
        上传相关非敏感的指标以更好地了解 AstrBot 的使用情况。上传的指标不会包含任何有关消息文本、用户信息等敏感信息。

        这些数据包含：
            - AstrBot 版本
            - OS 版本
            - 平台消息数量
            - LLM 模型名称、调用次数
        '''
        await asyncio.sleep(30)
        while True:
            res = {
                "stat_version": "moon",
                "version": VERSION,  # 版本号
                "platform_stats": self.platform_stats,  # 过去 30 分钟各消息平台交互消息数
                "llm_stats": self.llm_stats,
                "command_stats": self.command_stats,
                "sys": sys.platform,  # 系统版本
                "plugin_stats": None,
            }

            try:
                self.db_helper.insert_base_metrics(res)
            except BaseException as e:
                logger.debug("指标数据保存到数据库失败: " + str(e))
                await asyncio.sleep(30*60)
                continue

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post('https://api.soulter.top/upload', data=json.dumps(res), timeout=10) as _:
                        pass
            except BaseException as e:
                pass
            
            self.clear()
            await asyncio.sleep(30*60)

    def increment_platform_stat(self, platform_name: str):
        self.platform_stats[platform_name] = self.platform_stats.get(
            platform_name, 0) + 1

    def clear(self):
        self.platform_stats.clear()
        self.llm_stats.clear()
        self.command_stats.clear()
