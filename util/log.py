import logging, asyncio, colorlog
from type.cached_queue import CachedQueue

log_color_config = {
    'DEBUG': 'bold_blue', 'INFO': 'bold_cyan',
    'WARNING': 'bold_yellow', 'ERROR': 'red',
    'CRITICAL': 'bold_red', 'RESET': 'reset',
    'asctime': 'green'
}

class LogQueueHandler(logging.Handler):
    def __init__(self, log_queue: CachedQueue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        log_entry = self.format(record)
        try:
            self.log_queue.put_nowait(log_entry)
        except Exception:
            pass

class LogManager:

    @classmethod
    def GetLogger(cls, log_name: str = 'default'):
        logger = logging.getLogger(log_name)
        if logger.hasHandlers():
            return logger
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_formatter = colorlog.ColoredFormatter(
            fmt='%(log_color)s [%(asctime)s| %(levelname)s] [%(funcName)s|%(filename)s:%(lineno)d]: %(message)s %(reset)s',
            datefmt='%H:%M:%S',
            log_colors=log_color_config
        )
        console_handler.setFormatter(console_formatter)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(console_handler)
        
        return logger
    
    @classmethod
    def set_queue_handler(cls, logger: logging.Logger, log_queue: CachedQueue):
        handler = LogQueueHandler(log_queue)
        handler.setLevel(logging.DEBUG)
        if logger.handlers:
            handler.setFormatter(logger.handlers[0].formatter)
        else:
            handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)