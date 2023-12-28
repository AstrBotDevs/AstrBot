'''
监测机器性能
- Bot 内存使用量
- CPU 占用率
'''

import psutil
from cores.qqbot.global_object import GlobalObject
import time

def run_monitor(global_object: GlobalObject):
    '''运行监测'''
    start_time = time.time()
    while True:
        stat = global_object.dashboard_data.stats
        # 程序占用的内存大小
        mem = psutil.Process().memory_info().rss / 1024 / 1024 # MB
        stat['sys_perf'] = {
            'memory': mem,
            'cpu': psutil.cpu_percent()
        }
        stat['sys_start_time'] = start_time
        time.sleep(30)