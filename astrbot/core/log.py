"""日志系统, 用于支持核心组件和插件的日志记录, 提供了日志订阅功能

const:
    CACHED_SIZE: 日志缓存大小, 用于限制缓存的日志数量
    log_color_config: 日志颜色配置, 定义了不同日志级别的颜色

class:
    LogBroker: 日志代理类, 用于缓存和分发日志消息
    LogQueueHandler: 日志处理器, 用于将日志消息发送到 LogBroker
    LogManager: 日志管理器, 用于创建和配置日志记录器

function:
    is_plugin_path: 检查文件路径是否来自插件目录
    get_short_level_name: 将日志级别名称转换为四个字母的缩写

工作流程:
1. 通过 LogManager.GetLogger() 获取日志器, 配置了控制台输出和多个格式化过滤器
2. 通过 set_queue_handler() 设置日志处理器, 将日志消息发送到 LogBroker
3. logBroker 维护一个订阅者列表, 负责将日志分发给所有订阅者
4. 订阅者可以使用 register() 方法注册到 LogBroker, 订阅日志流
"""

import asyncio
import logging
import os
import sys
import time
from asyncio import Queue
from collections import deque
from logging.handlers import RotatingFileHandler

import colorlog

from astrbot.core.config.default import VERSION
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

# 日志缓存大小
CACHED_SIZE = 500
# 日志颜色配置
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
    """检查文件路径是否来自插件目录

    Args:
        pathname (str): 文件路径

    Returns:
        bool: 如果路径来自插件目录，则返回 True，否则返回 False

    """
    if not pathname:
        return False

    norm_path = os.path.normpath(pathname)
    return ("data/plugins" in norm_path) or ("astrbot/builtin_stars/" in norm_path)


def get_short_level_name(level_name):
    """将日志级别名称转换为四个字母的缩写

    Args:
        level_name (str): 日志级别名称, 如 "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"

    Returns:
        str: 四个字母的日志级别缩写

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
    """日志代理类, 用于缓存和分发日志消息

    发布-订阅模式
    """

    def __init__(self):
        self.log_cache = deque(maxlen=CACHED_SIZE)  # 环形缓冲区, 保存最近的日志
        self.subscribers: list[Queue] = []  # 订阅者列表

    def register(self) -> Queue:
        """注册新的订阅者, 并给每个订阅者返回一个带有日志缓存的队列

        Returns:
            Queue: 订阅者的队列, 可用于接收日志消息

        """
        q = Queue(maxsize=CACHED_SIZE + 10)
        self.subscribers.append(q)
        return q

    def unregister(self, q: Queue):
        """取消订阅

        Args:
            q (Queue): 需要取消订阅的队列

        """
        self.subscribers.remove(q)

    def publish(self, log_entry: dict):
        """发布新日志到所有订阅者, 使用非阻塞方式投递, 避免一个订阅者阻塞整个系统

        Args:
            log_entry (dict): 日志消息, 包含日志级别和日志内容.
                example: {"level": "INFO", "data": "This is a log message.", "time": "2023-10-01 12:00:00"}

        """
        self.log_cache.append(log_entry)
        for q in self.subscribers:
            try:
                q.put_nowait(log_entry)
            except asyncio.QueueFull:
                pass


class LogQueueHandler(logging.Handler):
    """日志处理器, 用于将日志消息发送到 LogBroker

    继承自 logging.Handler
    """

    def __init__(self, log_broker: LogBroker):
        super().__init__()
        self.log_broker = log_broker

    def emit(self, record):
        """日志处理的入口方法, 接受一个日志记录, 转换为字符串后由 LogBroker 发布
        这个方法会在每次日志记录时被调用

        Args:
            record (logging.LogRecord): 日志记录对象, 包含日志信息

        """
        log_entry = self.format(record)
        self.log_broker.publish(
            {
                "level": record.levelname,
                "time": time.time(),
                "data": log_entry,
            },
        )


class LogManager:
    """日志管理器, 用于创建和配置日志记录器

    提供了获取默认日志记录器logger和设置队列处理器的方法
    """

    _FILE_HANDLER_FLAG = "_astrbot_file_handler"
    _TRACE_FILE_HANDLER_FLAG = "_astrbot_trace_file_handler"

    @classmethod
    def GetLogger(cls, log_name: str = "default"):
        """获取指定名称的日志记录器logger

        Args:
            log_name (str): 日志记录器的名称, 默认为 "default"

        Returns:
            logging.Logger: 返回配置好的日志记录器

        """
        logger = logging.getLogger(log_name)
        # 检查该logger或父级logger是否已经有处理器, 如果已经有处理器, 直接返回该logger, 避免重复配置
        if logger.hasHandlers():
            return logger
        # 如果logger没有处理器
        console_handler = logging.StreamHandler(
            sys.stdout,
        )  # 创建一个StreamHandler用于控制台输出
        console_handler.setLevel(
            logging.DEBUG,
        )  # 将日志级别设置为DEBUG(最低级别, 显示所有日志), *如果插件没有设置级别, 默认为DEBUG

        # 创建彩色日志格式化器, 输出日志格式为: [时间] [插件标签] [日志级别] [文件名:行号]: 日志消息
        console_formatter = colorlog.ColoredFormatter(
            fmt="%(log_color)s [%(asctime)s] %(plugin_tag)s [%(short_levelname)-4s]%(astrbot_version_tag)s [%(filename)s:%(lineno)d]: %(message)s %(reset)s",
            datefmt="%H:%M:%S",
            log_colors=log_color_config,
        )

        class PluginFilter(logging.Filter):
            """插件过滤器类, 用于标记日志来源是插件还是核心组件"""

            def filter(self, record):
                record.plugin_tag = (
                    "[Plug]" if is_plugin_path(record.pathname) else "[Core]"
                )
                return True

        class FileNameFilter(logging.Filter):
            """文件名过滤器类, 用于修改日志记录的文件名格式
            例如: 将文件路径 /path/to/file.py 转换为 file.<file> 格式
            """

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
            """短日志级别名称过滤器类, 用于将日志级别名称转换为四个字母的缩写"""

            # 添加短日志级别名称
            def filter(self, record):
                record.short_levelname = get_short_level_name(record.levelname)
                return True

        class AstrBotVersionTagFilter(logging.Filter):
            """在 WARNING 及以上级别日志后追加当前 AstrBot 版本号。"""

            def filter(self, record):
                if record.levelno >= logging.WARNING:
                    record.astrbot_version_tag = f" [v{VERSION}]"
                else:
                    record.astrbot_version_tag = ""
                return True

        console_handler.setFormatter(console_formatter)  # 设置处理器的格式化器
        logger.addFilter(PluginFilter())  # 添加插件过滤器
        logger.addFilter(FileNameFilter())  # 添加文件名过滤器
        logger.addFilter(LevelNameFilter())  # 添加级别名称过滤器
        logger.addFilter(AstrBotVersionTagFilter())  # 追加版本号（WARNING 及以上）
        logger.setLevel(logging.DEBUG)  # 设置日志级别为DEBUG
        logger.addHandler(console_handler)  # 添加处理器到logger

        return logger

    @classmethod
    def set_queue_handler(cls, logger: logging.Logger, log_broker: LogBroker):
        """设置队列处理器, 用于将日志消息发送到 LogBroker

        Args:
            logger (logging.Logger): 日志记录器
            log_broker (LogBroker): 日志代理类, 用于缓存和分发日志消息

        """
        handler = LogQueueHandler(log_broker)
        handler.setLevel(logging.DEBUG)
        if logger.handlers:
            handler.setFormatter(logger.handlers[0].formatter)
        else:
            # 为队列处理器设置相同格式的formatter
            handler.setFormatter(
                logging.Formatter(
                    "[%(asctime)s] [%(short_levelname)s] %(plugin_tag)s[%(filename)s:%(lineno)d]: %(message)s",
                ),
            )
        logger.addHandler(handler)

    @classmethod
    def _default_log_path(cls) -> str:
        return os.path.join(get_astrbot_data_path(), "logs", "astrbot.log")

    @classmethod
    def _resolve_log_path(cls, configured_path: str | None) -> str:
        if not configured_path:
            return cls._default_log_path()
        if os.path.isabs(configured_path):
            return configured_path
        return os.path.join(get_astrbot_data_path(), configured_path)

    @classmethod
    def _get_file_handlers(cls, logger: logging.Logger) -> list[logging.Handler]:
        return [
            handler
            for handler in logger.handlers
            if getattr(handler, cls._FILE_HANDLER_FLAG, False)
        ]

    @classmethod
    def _get_trace_file_handlers(cls, logger: logging.Logger) -> list[logging.Handler]:
        return [
            handler
            for handler in logger.handlers
            if getattr(handler, cls._TRACE_FILE_HANDLER_FLAG, False)
        ]

    @classmethod
    def _remove_file_handlers(cls, logger: logging.Logger):
        for handler in cls._get_file_handlers(logger):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

    @classmethod
    def _remove_trace_file_handlers(cls, logger: logging.Logger):
        for handler in cls._get_trace_file_handlers(logger):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

    @classmethod
    def _add_file_handler(
        cls,
        logger: logging.Logger,
        file_path: str,
        max_mb: int | None = None,
        backup_count: int = 3,
        trace: bool = False,
    ):
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        max_bytes = 0
        if max_mb and max_mb > 0:
            max_bytes = max_mb * 1024 * 1024
        if max_bytes > 0:
            file_handler = RotatingFileHandler(
                file_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
        else:
            file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setLevel(logger.level)
        if trace:
            formatter = logging.Formatter(
                "[%(asctime)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        else:
            formatter = logging.Formatter(
                "[%(asctime)s] %(plugin_tag)s [%(short_levelname)s]%(astrbot_version_tag)s [%(filename)s:%(lineno)d]: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        file_handler.setFormatter(formatter)
        setattr(
            file_handler,
            cls._TRACE_FILE_HANDLER_FLAG if trace else cls._FILE_HANDLER_FLAG,
            True,
        )
        logger.addHandler(file_handler)

    @classmethod
    def configure_logger(
        cls,
        logger: logging.Logger,
        config: dict | None,
        override_level: str | None = None,
    ):
        """根据配置设置日志级别和文件日志。

        Args:
            logger: 需要配置的 logger
            config: 配置字典
            override_level: 若提供，将覆盖配置中的日志级别
        """
        if not config:
            return

        level = override_level or config.get("log_level")
        if level:
            try:
                logger.setLevel(level)
            except Exception:
                logger.setLevel(logging.INFO)

        # 兼容旧版嵌套配置
        if "log_file" in config:
            file_conf = config.get("log_file") or {}
            enable_file = bool(file_conf.get("enable", False))
            file_path = file_conf.get("path")
            max_mb = file_conf.get("max_mb")
        else:
            enable_file = bool(config.get("log_file_enable", False))
            file_path = config.get("log_file_path")
            max_mb = config.get("log_file_max_mb")

        file_path = cls._resolve_log_path(file_path)

        existing = cls._get_file_handlers(logger)
        if not enable_file:
            cls._remove_file_handlers(logger)
            return

        # 如果已有文件处理器且路径一致，则仅同步级别
        if existing:
            handler = existing[0]
            base = getattr(handler, "baseFilename", "")
            if base and os.path.abspath(base) == os.path.abspath(file_path):
                handler.setLevel(logger.level)
                return
            cls._remove_file_handlers(logger)

        cls._add_file_handler(logger, file_path, max_mb=max_mb)

    @classmethod
    def configure_trace_logger(cls, config: dict | None):
        """为 trace 事件配置独立的文件日志，不向控制台输出。"""
        if not config:
            return

        enable = bool(
            config.get("trace_log_enable")
            or (config.get("log_file", {}) or {}).get("trace_enable", False)
        )
        path = config.get("trace_log_path")
        max_mb = config.get("trace_log_max_mb")
        if "log_file" in config:
            legacy = config.get("log_file") or {}
            path = path or legacy.get("trace_path")
            max_mb = max_mb or legacy.get("trace_max_mb")

        if not enable:
            trace_logger = logging.getLogger("astrbot.trace")
            cls._remove_trace_file_handlers(trace_logger)
            return

        file_path = cls._resolve_log_path(path or "logs/astrbot.trace.log")
        trace_logger = logging.getLogger("astrbot.trace")
        trace_logger.setLevel(logging.INFO)
        trace_logger.propagate = False

        existing = cls._get_trace_file_handlers(trace_logger)
        if existing:
            handler = existing[0]
            base = getattr(handler, "baseFilename", "")
            if base and os.path.abspath(base) == os.path.abspath(file_path):
                handler.setLevel(trace_logger.level)
                return
            cls._remove_trace_file_handlers(trace_logger)

        cls._add_file_handler(
            trace_logger,
            file_path,
            max_mb=max_mb,
            trace=True,
        )
