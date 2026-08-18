"""Explicit three-state proxy routing for providers, platforms, and HTTP clients."""

from __future__ import annotations

import ssl
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from astrbot.core.utils.error_redaction import redact_sensitive_text
from astrbot.utils.http_ssl_common import build_ssl_context_with_certifi

ProxyMode = Literal["inherit", "direct", "custom"]
_SYSTEM_SSL_CTX = build_ssl_context_with_certifi()
_GLOBAL_NETWORK_CONFIG: dict[str, Any] = {"http_proxy": "", "no_proxy": []}


def set_global_network_config(*, http_proxy: str = "", no_proxy: object = ()) -> None:
    """Store the runtime global proxy settings without touching process env.

    Args:
        http_proxy: Root ``http_proxy`` value.
        no_proxy: Root ``no_proxy`` list or comma string.
    """

    _GLOBAL_NETWORK_CONFIG["http_proxy"] = str(http_proxy or "")
    _GLOBAL_NETWORK_CONFIG["no_proxy"] = no_proxy


def get_global_network_config() -> dict[str, Any]:
    """Return the current global proxy snapshot."""

    return dict(_GLOBAL_NETWORK_CONFIG)


class ProxyRouteMode(StrEnum):
    """How an outbound client should choose a proxy."""

    INHERIT = "inherit"
    DIRECT = "direct"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class ProxyRoute:
    """Resolved network route for one outbound client."""

    mode: ProxyRouteMode
    proxy_url: str | None
    no_proxy: tuple[str, ...]
    trust_env: bool
    display_proxy: str

    @property
    def httpx_proxy(self) -> str | None:
        """Proxy URL for httpx, or None when connecting directly."""

        return self.proxy_url


def normalize_proxy_mode(value: object) -> ProxyRouteMode:
    """Normalize a configured proxy mode.

    Args:
        value: Raw config value.

    Returns:
        One of inherit, direct, or custom. Unknown values become inherit.
    """

    if value in {ProxyRouteMode.INHERIT, ProxyRouteMode.DIRECT, ProxyRouteMode.CUSTOM}:
        return ProxyRouteMode(str(value))
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in ProxyRouteMode._value2member_map_:
            return ProxyRouteMode(candidate)
    return ProxyRouteMode.INHERIT


def redact_proxy_url(proxy_url: str | None) -> str:
    """Return a credential-free proxy description for logs.

    Args:
        proxy_url: Configured proxy URL.

    Returns:
        Redacted display string, or empty when unused.
    """

    if not proxy_url:
        return ""
    return redact_sensitive_text(proxy_url)


def _normalize_no_proxy(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    elif isinstance(value, (list, tuple)):
        items = [str(item).strip() for item in value]
    else:
        items = []
    return tuple(item for item in items if item)


def _wildcard_match(host: str, pattern: str) -> bool:
    host = host.lower().rstrip(".")
    pattern = pattern.lower().strip()
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return (
            host == prefix or host.startswith(f"{prefix}.") or host.startswith(prefix)
        )
    if pattern.startswith("."):
        return host.endswith(pattern) or host == pattern[1:]
    if "*" in pattern:
        prefix, _, suffix = pattern.partition("*")
        return host.startswith(prefix) and host.endswith(suffix)
    return host == pattern or host.endswith(f".{pattern}")


def host_matches_no_proxy(host: str, no_proxy: Sequence[str]) -> bool:
    """Return whether a destination host should bypass the configured proxy.

    Args:
        host: Destination hostname or IP.
        no_proxy: Bypass patterns from global configuration.

    Returns:
        True when the host should be contacted directly.
    """

    hostname = (host or "").strip().lower().rstrip(".")
    if not hostname:
        return False
    return any(_wildcard_match(hostname, pattern) for pattern in no_proxy)


def resolve_proxy_route(
    *,
    local_config: Mapping[str, Any] | None = None,
    global_config: Mapping[str, Any] | None = None,
    destination_host: str | None = None,
) -> ProxyRoute:
    """Resolve the custom > inherit > direct route for one client.

    Empty global ``http_proxy`` does not inherit process ``HTTP_PROXY``.
    ``direct`` always disables environment proxies.

    Args:
        local_config: Provider or platform config.
        global_config: Root AstrBot config.
        destination_host: Optional host used to apply ``no_proxy``.

    Returns:
        An explicit route with ``trust_env=False``.
    """

    local = local_config or {}
    root = global_config if global_config is not None else _GLOBAL_NETWORK_CONFIG
    mode = normalize_proxy_mode(local.get("proxy_mode", ProxyRouteMode.INHERIT))
    no_proxy = _normalize_no_proxy(root.get("no_proxy", ()))
    global_proxy = str(root.get("http_proxy") or "").strip() or None
    custom_proxy = str(local.get("proxy_url") or "").strip() or None

    if mode is ProxyRouteMode.CUSTOM:
        proxy_url = custom_proxy
    elif mode is ProxyRouteMode.DIRECT:
        proxy_url = None
    else:
        proxy_url = global_proxy

    if (
        proxy_url
        and destination_host
        and host_matches_no_proxy(destination_host, no_proxy)
    ):
        proxy_url = None

    return ProxyRoute(
        mode=mode,
        proxy_url=proxy_url,
        no_proxy=no_proxy,
        trust_env=False,
        display_proxy=redact_proxy_url(proxy_url),
    )


def destination_host_from_url(url: str | None) -> str | None:
    """Extract a hostname from an API base or endpoint URL.

    Args:
        url: Absolute URL.

    Returns:
        Lowercased hostname, or None when missing.
    """

    if not url:
        return None
    hostname = urlparse(url).hostname
    return hostname.lower() if hostname else None


def apply_httpx_route(
    *,
    route: ProxyRoute,
    verify: ssl.SSLContext | str | bool | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | httpx.Timeout | None = None,
    httpx_module: Any = httpx,
    follow_redirects: bool = False,
    **kwargs: Any,
) -> Any:
    """Create an httpx AsyncClient from an explicit route.

    Args:
        route: Resolved proxy route.
        verify: TLS verification setting.
        headers: Optional default headers.
        timeout: Optional client timeout.
        httpx_module: httpx or httpx2 module.
        follow_redirects: Automatic redirects stay disabled by default.
        **kwargs: Extra AsyncClient keyword arguments.

    Returns:
        Configured async client. The caller owns its lifetime.
    """

    client_kwargs: dict[str, Any] = {
        "trust_env": False,
        "follow_redirects": follow_redirects,
        "verify": _SYSTEM_SSL_CTX if verify is None else verify,
        **kwargs,
    }
    if headers is not None:
        client_kwargs["headers"] = headers
    if timeout is not None:
        client_kwargs["timeout"] = timeout
    if route.proxy_url:
        client_kwargs["proxy"] = route.proxy_url
    return httpx_module.AsyncClient(**client_kwargs)


def httpx_client_kwargs(route: ProxyRoute) -> dict[str, Any]:
    """Return AsyncClient kwargs for an explicit route."""

    kwargs: dict[str, Any] = {"trust_env": False, "follow_redirects": False}
    if route.proxy_url:
        kwargs["proxy"] = route.proxy_url
    return kwargs


def apply_aiohttp_session_kwargs(route: ProxyRoute | None = None) -> dict[str, Any]:
    """Return ClientSession kwargs that honor an explicit route.

    Args:
        route: Resolved proxy route. When omitted, the current global route is used.

    Returns:
        Keyword arguments for ``aiohttp.ClientSession``.
    """

    del route
    return {"trust_env": False}


def current_aiohttp_proxy() -> str | None:
    """Return the explicit proxy URL for one aiohttp request."""

    return resolve_proxy_route().proxy_url


def create_aiohttp_session(**kwargs: Any):
    """Create an aiohttp session that never inherits process proxy env.

    Args:
        **kwargs: Extra ``ClientSession`` arguments.

    Returns:
        Session with ``trust_env=False``.
    """

    import aiohttp

    kwargs["trust_env"] = False
    return aiohttp.ClientSession(**kwargs)


def aiohttp_request_proxy(route: ProxyRoute) -> str | None:
    """Return the per-request aiohttp proxy argument.

    Args:
        route: Resolved proxy route.

    Returns:
        Proxy URL or None.
    """

    return route.proxy_url


def create_routed_client(
    provider_label: str,
    route: ProxyRoute,
    *,
    headers: dict[str, str] | None = None,
    verify: ssl.SSLContext | str | bool | None = None,
    httpx_module: Any = httpx,
) -> Any:
    """Create a provider HTTP client without logging proxy credentials.

    Args:
        provider_label: Provider name used in logs.
        route: Resolved proxy route.
        headers: Optional default headers.
        verify: TLS verification setting.
        httpx_module: httpx or httpx2 module.

    Returns:
        Configured async client.
    """

    from astrbot import logger

    if route.proxy_url:
        logger.info(
            "[%s] Using configured proxy: %s", provider_label, route.display_proxy
        )
    return apply_httpx_route(
        route=route,
        verify=verify,
        headers=headers,
        httpx_module=httpx_module,
    )
