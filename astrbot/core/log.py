import logging
import colorlog
import asyncio
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
            fmt="%(log_color)s [%(asctime)s] [%(levelname)-5s] [%(filename)s:%(lineno)d]: %(message)s %(reset)s",
            datefmt="%H:%M:%S",
            log_colors=log_color_config,
        )
        console_handler.setFormatter(console_formatter)
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
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
            )
        logger.addHandler(handler)
