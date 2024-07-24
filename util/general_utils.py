import time
import asyncio
import requests
import json
import sys
import psutil

from type.types import Context
from SparkleLogging.utils.core import LogManager
from logging import Logger

logger: Logger = LogManager.GetLogger(log_name='astrbot')

async def upload_metrics(_global_object: Context):
    '''
    上传相关非敏感统计数据
    '''
    await asyncio.sleep(10)
    while True:
        platform_stats = {}
        llm_stats = {}
        plugin_stats = {}
        for platform in _global_object.platforms:
            platform_stats[platform.platform_name] = {
                "cnt_receive": 0,
                "cnt_reply": 0
            }
            
        for llm in _global_object.llms:
            stat = llm.llm_instance.model_stat
            for k in stat:
                llm_stats[llm.llm_name + "#" + k] = stat[k]
            llm.llm_instance.reset_model_stat()
            
        for plugin in _global_object.cached_plugins:
            plugin_stats[plugin.metadata.plugin_name] = {
                "metadata": plugin.metadata,
                "trig_cnt": plugin.trig_cnt
            }
            plugin.reset_trig_cnt()
        
        try:
            res = {
                "stat_version": "moon",
                "version": _global_object.version, # 版本号
                "platform_stats": platform_stats, # 过去 30 分钟各消息平台交互消息数
                "llm_stats": llm_stats,
                "plugin_stats": plugin_stats,
                "sys": sys.platform, # 系统版本
            }
            resp = requests.post(
                'https://api.soulter.top/upload', data=json.dumps(res), timeout=5)
            if resp.status_code == 200:
                ok = resp.json()
                if ok['status'] == 'ok':
                    _global_object.cnt_total = 0
        except BaseException as e:
            pass
        await asyncio.sleep(30*60)

def retry(n: int = 3):
    '''
    重试装饰器
    '''
    def decorator(func):
        def wrapper(*args, **kwargs):
            for i in range(n):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if i == n-1: raise e
                    logger.warning(f"函数 {func.__name__} 第 {i+1} 次重试... {e}")
        return wrapper
    return decorator

def run_monitor(global_object: Context):
    '''
    监测机器性能
    - Bot 内存使用量
    - CPU 占用率
    '''
    start_time = time.time()
    while True:
        stat = global_object.dashboard_data.stats
        # 程序占用的内存大小
        mem = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        stat['sys_perf'] = {
            'memory': mem,
            'cpu': psutil.cpu_percent()
        }
        stat['sys_start_time'] = start_time
        time.sleep(30)
