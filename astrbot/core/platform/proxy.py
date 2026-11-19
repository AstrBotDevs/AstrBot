"""Helpers for adapter-scoped outbound proxy configuration."""

from typing import Any

import aiohttp


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
    if proxy_url:
        kwargs["proxy"] = proxy_url
    return aiohttp.ClientSession(**kwargs)
