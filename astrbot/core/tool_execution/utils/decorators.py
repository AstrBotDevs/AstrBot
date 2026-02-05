"""AOP装饰器"""

import asyncio
import functools
import time
from typing import Callable


def log_execution(func: Callable) -> Callable:
    """日志装饰器"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        from astrbot import logger
        start = time.time()
        try:
            result = await func(*args, **kwargs)
            logger.debug(f"{func.__name__} took {time.time()-start:.2f}s")
            return result
        except Exception as e:
            logger.error(f"{func.__name__} failed: {e}")
            raise
    return wrapper


def with_timeout(timeout: float):
    """超时装饰器"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=timeout
            )
        return wrapper
    return decorator
