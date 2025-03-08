import logging
import colorlog
import asyncio
import os
from collections import deque
from asyncio import Queue
from typing import List

CACHED_SIZE = 200
log_color_config = {
    "DEBUG": "green",
    "INFO": "bold_cyan",
    "WARNING": "bold_yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
    "RESET": "reset",
    "asctime": "green",
}


def is_plugin_path(pathname):
    """
    检查文件路径是否来自插件目录
    """
    if not pathname:
        return False

    norm_path = os.path.normpath(pathname)
    return ("data/plugins" in norm_path) or ("packages/" in norm_path)


def get_short_level_name(level_name):
    """
    将日志级别名称转换为四个字母的缩写
    """
    level_map = {
        "DEBUG": "DBUG",
        "INFO": "INFO",
        "WARNING": "WARN",
        "ERROR": "ERRO",
        "CRITICAL": "CRIT",
    }
    return level_map.get(level_name, level_name[:4].upper())


class LogBroker:
    def __init__(self):
        self.log_cache = deque(maxlen=CACHED_SIZE)
        self.subscribers: List[Queue] = []

    def register(self) -> Queue:
        """给每个订阅者返回一个带有日志缓存的队列"""
        q = Queue(maxsize=CACHED_SIZE + 10)
        for log in self.log_cache:
            q.put_nowait(log)
        self.subscribers.append(q)
        return q

    def unregister(self, q: Queue):
        """取消订阅"""
        self.subscribers.remove(q)

    def publish(self, log_entry: str):
        """发布消息"""
        self.log_cache.append(log_entry)
        for q in self.subscribers:
            try:
                q.put_nowait(log_entry)
            except asyncio.QueueFull:
                pass


class LogQueueHandler(logging.Handler):
    def __init__(self, log_broker: LogBroker):
        super().__init__()
        self.log_broker = log_broker

    def emit(self, record):
        log_entry = self.format(record)
        self.log_broker.publish(log_entry)


class LogManager:
    @classmethod
    def GetLogger(cls, log_name: str = "default"):
        logger = logging.getLogger(log_name)
        if logger.hasHandlers():
            return logger
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)

        console_formatter = colorlog.ColoredFormatter(
            fmt="%(log_color)s [%(asctime)s] %(plugin_tag)s [%(short_levelname)-4s] [%(filename)s:%(lineno)d]: %(message)s %(reset)s",
            datefmt="%H:%M:%S",
            log_colors=log_color_config,
        )

        class PluginFilter(logging.Filter):
            def filter(self, record):
                record.plugin_tag = (
                    "[Plug]" if is_plugin_path(record.pathname) else "[Core]"
                )
                return True

        class FileNameFilter(logging.Filter):
            # 获取这个文件和父文件夹的名字：<folder>.<file> 并且去除 .py
            def filter(self, record):
                dirname = os.path.dirname(record.pathname)
                record.filename = (
                    os.path.basename(dirname)
                    + "."
                    + os.path.basename(record.pathname).replace(".py", "")
                )
                return True

        class LevelNameFilter(logging.Filter):
            # 添加短日志级别名称
            def filter(self, record):
                record.short_levelname = get_short_level_name(record.levelname)
                return True

        console_handler.setFormatter(console_formatter)
        logger.addFilter(PluginFilter())
        logger.addFilter(FileNameFilter())
        logger.addFilter(LevelNameFilter())  # 添加级别名称过滤器
        logger.setLevel(logging.DEBUG)
        logger.addHandler(console_handler)

        return logger

    @classmethod
    def set_queue_handler(cls, logger: logging.Logger, log_broker: LogBroker):
        handler = LogQueueHandler(log_broker)
        handler.setLevel(logging.DEBUG)
        if logger.handlers:
            handler.setFormatter(logger.handlers[0].formatter)
        else:
            # 为队列处理器设置相同格式的formatter
            handler.setFormatter(
                logging.Formatter(
                    "[%(asctime)s] [%(short_levelname)s] %(plugin_tag)s[%(filename)s:%(lineno)d]: %(message)s"
                )
            )
        logger.addHandler(handler)
