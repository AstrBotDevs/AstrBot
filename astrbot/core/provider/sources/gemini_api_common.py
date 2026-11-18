import os
import threading
from collections.abc import Mapping
from typing import Any

import httpx
from google import genai
from google.genai import types

from astrbot import logger
from astrbot.core.utils.http_ssl import build_ssl_context_with_certifi
from astrbot.core.utils.network_utils import create_proxy_client

_SHARED_SYNC_HTTPX_CLIENT: httpx.Client | None = None
_SHARED_SYNC_HTTPX_CLIENT_LOCK = threading.Lock()


def gemini_api_version() -> str | None:
    """Keep the Developer API on v1beta by default for preview models.

    Returns:
        The Developer API default, or None to let the SDK resolve an explicit
        environment override or its Enterprise (Vertex AI) default.
    """
    enterprise = os.getenv(
        "GOOGLE_GENAI_USE_ENTERPRISE", os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "")
    )
    if os.getenv("GOOGLE_GENAI_API_VERSION") or enterprise.lower() in {"true", "1"}:
        return None
    return "v1beta"


def _get_shared_sync_httpx_client() -> httpx.Client:
    """Return a shared sync httpx.Client reusing the global SSLContext.

    Gemini providers only call the async ``.aio`` client, but ``genai.Client``
    eagerly constructs an internal sync ``httpx.Client`` (and its own SSL
    context) unless ``http_options.httpx_client`` is supplied. Because the
    caller supplies this client, ``genai.Client.aclose()`` leaves it open.

    Returns:
        The shared synchronous ``httpx.Client`` instance.
    """
    global _SHARED_SYNC_HTTPX_CLIENT
    if _SHARED_SYNC_HTTPX_CLIENT is not None:
        return _SHARED_SYNC_HTTPX_CLIENT
    with _SHARED_SYNC_HTTPX_CLIENT_LOCK:
        if _SHARED_SYNC_HTTPX_CLIENT is None:
            _SHARED_SYNC_HTTPX_CLIENT = httpx.Client(
                verify=build_ssl_context_with_certifi()
            )
        return _SHARED_SYNC_HTTPX_CLIENT


def create_genai_async_client(
    *,
    provider_label: str,
    api_key: str,
    request_headers: Mapping[str, str],
    api_base: str | None = None,
    timeout: int | float = 180,
    proxy: str = "",
) -> tuple[Any, httpx.AsyncClient]:
    """Create a ``genai.Client(...).aio`` and its owned ``httpx.AsyncClient``.

    Reuses the shared hybrid SSLContext across the async httpx client, the
    unused sync httpx client placeholder, and ``async_client_args`` (used for
    the SDK's websocket SSL setup) so no per-provider CA store is loaded.

    Args:
        provider_label: Label prefix used for proxy logging.
        api_key: Gemini API key passed to ``genai.Client``.
        request_headers: Provider HTTP headers including User-Agent.
        api_base: Optional API base URL override.
        timeout: Request timeout in seconds.
        proxy: Optional proxy URL string.

    Returns:
        A tuple of ``(async_client, http_client)`` where ``http_client`` is
        owned by the caller and should be closed on termination.
    """
    normalized_base = api_base.removesuffix("/") or None if api_base else None
    headers = dict(request_headers)
    shared_ssl_ctx = build_ssl_context_with_certifi()

    http_client = create_proxy_client(
        provider_label,
        proxy,
        base_url=normalized_base,
        timeout=timeout,
        trust_env=not bool(proxy),
        verify=shared_ssl_ctx,
    )

    try:
        http_options = types.HttpOptions(
            api_version=gemini_api_version(),
            headers=headers,
            base_url=normalized_base,
            timeout=int(timeout * 1000),
            httpx_client=_get_shared_sync_httpx_client(),
            httpx_async_client=http_client,
        )
        if hasattr(http_options, "async_client_args"):
            http_options.async_client_args = {"ssl": shared_ssl_ctx}

        async_client = genai.Client(
            api_key=api_key,
            http_options=http_options,
        ).aio
    except BaseException:
        try:
            http_client._transport.close()
        except Exception:
            pass
        raise

    # Keep only AstrBot's UA across SDK versions that merge header case variants.
    sdk_headers = async_client._api_client._http_options.headers
    if isinstance(sdk_headers, dict) and "User-Agent" in request_headers:
        sdk_headers["user-agent"] = request_headers["User-Agent"]
        sdk_headers.pop("User-Agent", None)

    return async_client, http_client


async def close_httpx_client(
    client: httpx.AsyncClient | None,
    *,
    label: str = "Gemini",
) -> None:
    """Safely close an httpx.AsyncClient, swallowing errors for idempotency.

    Args:
        client: The ``httpx.AsyncClient`` to close, or ``None``.
        label: Log prefix identifying the provider adapter.
    """
    if client is None:
        return
    try:
        await client.aclose()
    except Exception as exc:
        logger.debug(f"[{label}] Ignored error while closing httpx client: {exc}")
