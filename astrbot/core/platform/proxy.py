"""Helpers for adapter-scoped outbound proxy configuration."""

from typing import Any
from urllib.parse import urlsplit

import aiohttp
from aiohttp_socks import ProxyConnector


def create_platform_client_session(
    proxy_url: str | None = None,
    **kwargs: Any,
) -> aiohttp.ClientSession:
    """Create an aiohttp session that preserves global proxy fallback.

    Args:
        proxy_url: Explicit proxy URL for one adapter instance, if configured.
        **kwargs: Additional arguments passed to ``aiohttp.ClientSession``.

    Returns:
        A configured aiohttp client session.
    """
    kwargs.setdefault("trust_env", True)
    if proxy_url and urlsplit(proxy_url).scheme.lower() == "socks5":
        existing_connector = kwargs.pop("connector", None)
        connector_kwargs = {}
        if existing_connector is not None and hasattr(existing_connector, "_ssl"):
            connector_kwargs["ssl"] = existing_connector._ssl
        kwargs["connector"] = ProxyConnector.from_url(
            proxy_url,
            **connector_kwargs,
        )
    elif proxy_url:
        kwargs["proxy"] = proxy_url
    return aiohttp.ClientSession(**kwargs)
