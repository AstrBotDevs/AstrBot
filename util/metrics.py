import asyncio
import requests
import json
import sys

from type.types import Context
from collections import defaultdict

class MetricUploader():
    def __init__(self, context: Context) -> None:
        self.platform_stats = {}
        self.llm_stats = {}
        self.plugin_stats = {}
        self.command_stats = defaultdict(int)
        self.context = context
        
    async def upload_metrics(self):
        '''
        上传相关非敏感的指标以更好地了解 AstrBot 的使用情况。上传的指标不会包含任何有关消息文本、用户信息等敏感信息。
        
        这些数据包含：
            - AstrBot 版本
            - OS 版本
            - 平台消息上下行数量
            - LLM 模型名称、调用次数
            - 加载的插件的元数据
        '''
        await asyncio.sleep(10)
        context = self.context
        while True:
            for llm in context.llms:
                stat = llm.llm_instance.model_stat
                for k in stat:
                    self.llm_stats[llm.llm_name + "#" + k] = stat[k]
                llm.llm_instance.reset_model_stat()
                
            for plugin in context.cached_plugins:
                self.plugin_stats[plugin.metadata.plugin_name] = {
                    "metadata": {
                        "plugin_name": plugin.metadata.plugin_name,
                        "plugin_type": plugin.metadata.plugin_type.value,
                        "author": plugin.metadata.author,
                        "desc": plugin.metadata.desc,
                        "version": plugin.metadata.version,
                        "repo": plugin.metadata.repo,
                    }
                }
            
            try:
                res = {
                    "stat_version": "moon",
                    "version": context.version, # 版本号
                    "platform_stats": self.platform_stats, # 过去 30 分钟各消息平台交互消息数
                    "llm_stats": self.llm_stats,
                    "plugin_stats": self.plugin_stats,
                    "command_stats": self.command_stats,
                    "sys": sys.platform, # 系统版本
                }
                resp = requests.post(
                    'https://api.soulter.top/upload', data=json.dumps(res), timeout=5)
                if resp.status_code == 200:
                    ok = resp.json()
                    if ok['status'] == 'ok':
                        self.clear()
            except BaseException as e:
                pass
            await asyncio.sleep(30*60)
    
    def increment_platform_stat(self, platform_name: str):
        self.platform_stats[platform_name] = self.platform_stats.get(platform_name, 0) + 1

    def clear(self):
        self.platform_stats.clear()
        self.llm_stats.clear()
        self.plugin_stats.clear()
        self.command_stats.clear()