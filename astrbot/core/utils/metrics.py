import aiohttp
import sys
import os
import socket
import uuid
from astrbot.core.config import VERSION
from astrbot.core import db_helper, logger


class Metric:
    _iid_cache = None

    @staticmethod
    def get_installation_id():
        """获取或创建一个唯一的安装ID"""
        if Metric._iid_cache is not None:
            return Metric._iid_cache

        config_dir = os.path.join(os.path.expanduser("~"), ".astrbot")
        id_file = os.path.join(config_dir, ".installation_id")

        if os.path.exists(id_file):
            try:
                with open(id_file, "r") as f:
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
    async def upload(**kwargs):
        """
        上传相关非敏感的指标以更好地了解 AstrBot 的使用情况。上传的指标不会包含任何有关消息文本、用户信息等敏感信息。

        Powered by TickStats.
        """
        base_url = "https://tickstats.soulter.top/api/metric/90a6c2a1"
        kwargs["v"] = VERSION
        kwargs["os"] = sys.platform
        payload = {"metrics_data": kwargs}
        try:
            kwargs["hn"] = socket.gethostname()
        except Exception:
            pass
        try:
            kwargs["iid"] = Metric.get_installation_id()
        except Exception:
            pass
        try:
            if "adapter_name" in kwargs:
                db_helper.insert_platform_metrics({kwargs["adapter_name"]: 1})
            if "llm_name" in kwargs:
                db_helper.insert_llm_metrics({kwargs["llm_name"]: 1})
        except Exception as e:
            logger.error(f"保存指标到数据库失败: {e}")
            pass

        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.post(base_url, json=payload, timeout=3) as response:
                    if response.status != 200:
                        pass
        except Exception:
            pass
