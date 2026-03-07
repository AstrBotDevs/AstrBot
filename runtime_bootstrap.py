"""
运行时 SSL 引导模块

在应用启动时修补 aiohttp 的默认 SSL 上下文，使其使用 certifi CA bundle。

使用方式:
    from runtime_bootstrap import initialize_runtime_bootstrap
    initialize_runtime_bootstrap()  # 在应用启动时调用一次

注意: 这是全局性修改，影响所有后续的 aiohttp 请求。
"""

import logging
import ssl
from typing import Any

import aiohttp.connector as aiohttp_connector

from astrbot.utils.http_ssl_common import build_ssl_context_with_certifi

logger = logging.getLogger(__name__)


def _try_patch_aiohttp_ssl_context(
    ssl_context: ssl.SSLContext,
    log_obj: Any | None = None,
) -> bool:
    """尝试修补 aiohttp 的内部 SSL 上下文

    修改 aiohttp.connector._SSL_CONTEXT_VERIFIED，使其使用 certifi 证书。

    Returns:
        True 表示修补成功，False 表示不支持或类型不匹配
    """
    log = log_obj or logger
    attr_name = "_SSL_CONTEXT_VERIFIED"

    if not hasattr(aiohttp_connector, attr_name):
        log.warning(
            "aiohttp connector does not expose _SSL_CONTEXT_VERIFIED; skipped patch.",
        )
        return False

    current_value = getattr(aiohttp_connector, attr_name, None)
    if current_value is not None and not isinstance(current_value, ssl.SSLContext):
        log.warning(
            "aiohttp connector exposes _SSL_CONTEXT_VERIFIED with unexpected type; skipped patch.",
        )
        return False

    setattr(aiohttp_connector, attr_name, ssl_context)
    log.info("Configured aiohttp verified SSL context with system+certifi trust chain.")
    return True


def configure_runtime_ca_bundle(log_obj: Any | None = None) -> bool:
    """配置运行时 CA 证书包

    构建 SSL 上下文并修补 aiohttp，使其默认使用 certifi CA bundle。
    """
    log = log_obj or logger

    try:
        log.info("Bootstrapping runtime CA bundle.")
        ssl_context = build_ssl_context_with_certifi(log_obj=log)
        return _try_patch_aiohttp_ssl_context(ssl_context, log_obj=log)
    except Exception as exc:
        log.error("Failed to configure runtime CA bundle for aiohttp: %r", exc)
        return False


def initialize_runtime_bootstrap(log_obj: Any | None = None) -> bool:
    """初始化运行时 SSL 配置

    应用启动时调用，确保 aiohttp 使用完整的 CA 证书链。
    """
    return configure_runtime_ca_bundle(log_obj=log_obj)
