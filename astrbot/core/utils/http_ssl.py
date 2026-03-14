"""
HTTP SSL 上下文管理

提供线程安全的单例 SSL 上下文，用于 aiohttp 等异步 HTTP 客户端。

设计要点:
- 使用双重检查锁定确保线程安全的延迟初始化
- 全局共享 SSL 上下文避免重复加载证书
"""

import logging
import ssl
import threading

import aiohttp

from astrbot.utils.http_ssl_common import (
    build_ssl_context_with_certifi as _build_ssl_context,
)

logger = logging.getLogger("astrbot")

# 单例 SSL 上下文及其线程锁
_SHARED_TLS_CONTEXT: ssl.SSLContext | None = None
_SHARED_TLS_CONTEXT_LOCK = threading.Lock()


def build_ssl_context_with_certifi() -> ssl.SSLContext:
    """获取共享的 SSL 上下文（线程安全单例）

    使用双重检查锁定模式，确保多线程环境下只创建一次。
    """
    global _SHARED_TLS_CONTEXT

    if _SHARED_TLS_CONTEXT is not None:
        return _SHARED_TLS_CONTEXT

    with _SHARED_TLS_CONTEXT_LOCK:
        if _SHARED_TLS_CONTEXT is not None:
            return _SHARED_TLS_CONTEXT

        _SHARED_TLS_CONTEXT = _build_ssl_context(log_obj=logger)
        return _SHARED_TLS_CONTEXT


def build_tls_connector() -> aiohttp.TCPConnector:
    """创建配置了 certifi 证书验证的 aiohttp TCP 连接器"""
    return aiohttp.TCPConnector(ssl=build_ssl_context_with_certifi())
