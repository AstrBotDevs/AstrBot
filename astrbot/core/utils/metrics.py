import aiohttp
import sys
import logging
from core.config import VERSION

logger = logging.getLogger("astrbot")

class Metric():
    @staticmethod
    async def upload(**kwargs):
        '''
        上传相关非敏感的指标以更好地了解 AstrBot 的使用情况。上传的指标不会包含任何有关消息文本、用户信息等敏感信息。
        
        Powered by TickStats.
        '''
        base_url = "https://tickstats.soulter.top/api/metric/90a6c2a1"
        kwargs["v"] = VERSION
        kwargs["os"] = sys.platform
        payload = {
            "metrics_data": kwargs
        }
        try:
            async with aiohttp.ClientSession() as session:
                logger.debug(f"Uploading metric: {kwargs}")
                async with session.post(base_url, json=payload, timeout=3) as response:
                    if response.status != 200:
                        logger.error(f"Failed to upload metric: {response.status} {response.reason}")
        except Exception as e:
            logger.error(f"Failed to upload metric: {e}")