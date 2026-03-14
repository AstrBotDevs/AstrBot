"""
SSL 上下文构建工具

提供基于 certifi 的 SSL 上下文，确保 HTTPS 请求能正确验证服务器证书。

使用场景:
- 系统信任库不完整时，使用 certifi 提供的 Mozilla CA bundle
- 需要可靠证书验证的 HTTP 客户端

注意: 若 certifi 加载失败，会回退到系统默认信任库。
"""

import logging
import ssl
from typing import Any

import certifi

_LOGGER = logging.getLogger(__name__)


def build_ssl_context_with_certifi(log_obj: Any | None = None) -> ssl.SSLContext:
    """构建带有 certifi CA bundle 的 SSL 上下文

    Args:
        log_obj: 可选的日志记录器，未提供时使用模块 logger

    Returns:
        配置了 certifi CA 证书的 SSLContext
    """
    logger = log_obj or _LOGGER

    ssl_context = ssl.create_default_context()
    try:
        ssl_context.load_verify_locations(cafile=certifi.where())
    except Exception as exc:
        if logger and hasattr(logger, "warning"):
            logger.warning(
                "Failed to load certifi CA bundle into SSL context; "
                "falling back to system trust store only: %s",
                exc,
            )

    return ssl_context
