import asyncio
import base64
import inspect
import ipaddress
import logging
import os
import shutil
import socket
import ssl
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar, cast
from urllib.parse import unquote, urljoin, urlparse

import aiohttp
import certifi
import psutil
from aiohttp.abc import AbstractResolver
from PIL import Image
from yarl import URL

from .astrbot_path import get_astrbot_temp_path

logger = logging.getLogger("astrbot")

_T = TypeVar("_T")
_MAX_REDIRECTS = 5
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class SSRFProtectionError(ValueError):
    """Raised when a remote URL violates the outbound request policy."""


class _PinnedResolver(AbstractResolver):
    """Resolve hostnames only to addresses validated before each request."""

    def __init__(self) -> None:
        self._addresses: dict[str, list[dict[str, Any]]] = {}

    def pin(self, hostname: str, addresses: list[dict[str, Any]]) -> None:
        """Pin the validated addresses for the next request to a hostname."""
        self._addresses[hostname.rstrip(".").lower()] = addresses

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: int = socket.AF_INET,
    ) -> list[dict[str, Any]]:
        """Return only the addresses validated for the requested hostname."""
        addresses = self._addresses.get(host.rstrip(".").lower())
        if addresses is None:
            raise SSRFProtectionError(
                f"Resolver requested an unvalidated hostname: {host!r}"
            )

        if family in (socket.AF_INET, socket.AF_INET6):
            addresses = [
                address for address in addresses if address["family"] == family
            ]
        return [dict(address) for address in addresses]

    async def close(self) -> None:
        """Close the resolver."""


def _is_public_ip(address: str) -> bool:
    """Return whether an IP address is safe for an untrusted URL target."""
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    return ip.is_global and not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_unspecified
        or ip.is_multicast
        or ip.is_reserved
    )


async def _resolve_and_validate_url(
    url: str,
    allow_private_network: bool,
    allowed_origin: URL | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Validate a URL and return DNS results pinned for the next request.

    Args:
        url: URL that will be requested.
        allow_private_network: Whether the caller explicitly trusts private
            network destinations.
        allowed_origin: Optional normalized origin that the URL must match.

    Returns:
        The normalized hostname and validated resolver records.

    Raises:
        SSRFProtectionError: If the URL is malformed or resolves to a blocked
            destination.
    """
    try:
        parsed = URL(url)
    except ValueError as exc:
        raise SSRFProtectionError("Outbound URL is malformed") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise SSRFProtectionError(
            f"Unsupported URL scheme for outbound request: {parsed.scheme or '<empty>'}"
        )
    if parsed.user or parsed.password:
        raise SSRFProtectionError("Outbound URLs must not contain user credentials")
    if not parsed.raw_host:
        raise SSRFProtectionError("Outbound URL is missing a hostname")

    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise SSRFProtectionError("Outbound URL contains an invalid port") from exc

    hostname = parsed.raw_host
    if allowed_origin is not None and parsed.origin() != allowed_origin:
        raise SSRFProtectionError(
            f"Outbound request origin {parsed.origin()!s} is not the trusted origin "
            f"{allowed_origin!s}"
        )
    try:
        address_info = await asyncio.get_running_loop().getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except OSError as exc:
        raise SSRFProtectionError(
            f"Could not resolve outbound URL host {hostname!r}"
        ) from exc

    addresses: list[dict[str, Any]] = []
    seen_addresses: set[tuple[int, str]] = set()
    for family, _socktype, proto, _canonname, sockaddr in address_info:
        address = str(sockaddr[0]).split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise SSRFProtectionError(
                f"DNS returned an invalid address for {hostname!r}"
            ) from exc

        if not allow_private_network and not _is_public_ip(str(ip)):
            raise SSRFProtectionError(
                f"Outbound request to non-public address {ip} is blocked"
            )

        key = (family, str(ip))
        if key in seen_addresses:
            continue
        seen_addresses.add(key)
        addresses.append(
            {
                "hostname": hostname,
                "host": str(ip),
                "port": port,
                "family": family,
                "proto": proto,
                "flags": socket.AI_NUMERICHOST,
            }
        )

    if not addresses:
        raise SSRFProtectionError(f"No usable address was found for {hostname!r}")
    return hostname, addresses


async def _request_with_ssrf_protection(
    url: str,
    *,
    method: str,
    json_data: dict | None,
    ssl_context: ssl.SSLContext,
    timeout: float,
    allow_private_network: bool,
    allowed_origin: str | None,
    response_handler: Callable[[aiohttp.ClientResponse, str], Awaitable[_T]],
) -> _T:
    """Perform an HTTP request with validated DNS and redirect targets.

    Args:
        url: Initial URL.
        method: HTTP method, currently GET or POST.
        json_data: Optional JSON payload for POST requests.
        ssl_context: TLS context for the request.
        timeout: Request timeout in seconds.
        allow_private_network: Whether private destinations are trusted.
        allowed_origin: Optional configured origin for all request targets and
            redirects.
        response_handler: Callback that consumes the final response.

    Returns:
        The value returned by ``response_handler``.

    Raises:
        SSRFProtectionError: If a request target or redirect is blocked.
    """
    current_url = url
    current_method = method.upper()
    current_json_data = json_data
    allowed_origin_key = None
    if allowed_origin:
        try:
            allowed_origin_url = URL(allowed_origin)
        except ValueError as exc:
            raise SSRFProtectionError("Trusted origin is malformed") from exc
        if (
            allowed_origin_url.scheme not in {"http", "https"}
            or allowed_origin_url.user
            or allowed_origin_url.password
            or not allowed_origin_url.raw_host
        ):
            raise SSRFProtectionError(
                "Trusted origin must be an HTTP URL without credentials"
            )
        allowed_origin_key = allowed_origin_url.origin()

    resolver = _PinnedResolver()
    connector = aiohttp.TCPConnector(
        ssl=ssl_context,
        resolver=resolver,
        use_dns_cache=False,
    )

    # Environment proxies resolve the target on the proxy host and would
    # bypass the pinned DNS result. Protected requests therefore connect
    # directly; trusted callers can still opt into private destinations,
    # but proxy routing is not part of this helper's security contract.
    async with aiohttp.ClientSession(
        trust_env=False,
        connector=connector,
    ) as session:
        for _ in range(_MAX_REDIRECTS + 1):
            hostname, addresses = await _resolve_and_validate_url(
                current_url,
                allow_private_network,
                allowed_origin_key,
            )
            resolver.pin(hostname, addresses)
            request = session.post if current_method == "POST" else session.get
            async with request(
                current_url,
                json=current_json_data if current_method == "POST" else None,
                allow_redirects=False,
                timeout=timeout,
            ) as response:
                if response.status not in _REDIRECT_STATUSES:
                    return await response_handler(response, current_url)

                location = response.headers.get("Location")
                if not location:
                    raise SSRFProtectionError(
                        f"Redirect from {_safe_url_for_log(current_url)} has no Location"
                    )
                next_url = urljoin(current_url, location)
                if response.status in {301, 302, 303} and current_method == "POST":
                    current_method = "GET"
                    current_json_data = None
                current_url = next_url

    raise SSRFProtectionError(
        f"Too many redirects while requesting {_safe_url_for_log(url)}"
    )


def _safe_url_for_log(url: str) -> str:
    """Return a URL summary that omits query strings and fragments.

    Args:
        url: URL that may contain signed query parameters.

    Returns:
        A short description suitable for logs.
    """

    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        filename = Path(unquote(parsed.path or "")).name
        suffix = f" file={filename!r}" if filename else ""
        return f"{parsed.scheme} URL host={parsed.netloc!r}{suffix} len={len(url)}"
    return f"URL len={len(url)}"


def on_error(func, path, exc_info) -> None:
    """A callback of the rmtree function."""
    import stat

    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise exc_info[1]


def remove_dir(file_path: str) -> bool:
    if not os.path.lexists(file_path):
        return True
    if os.path.isfile(file_path) or os.path.islink(file_path):
        os.remove(file_path)
    else:
        shutil.rmtree(file_path, onerror=on_error)
    return True


def ensure_dir(dir_path: str | Path) -> None:
    """确保目录存在。如果路径处存在非目录的文件或损坏的符号链接，则先将其删除。"""
    p = Path(dir_path)
    if (p.exists() or p.is_symlink()) and not p.is_dir():
        logger.warning(
            f"Path {p} exists but is not a directory; removing it before creating "
            "the directory."
        )
        try:
            if p.is_dir():
                shutil.rmtree(p, onerror=on_error)
            else:
                p.unlink()
        except Exception as e:
            logger.error(f"Failed to remove conflicting path {p}: {e!s}")
            raise RuntimeError(f"Could not remove conflicting path {p}: {e!s}") from e

    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create directory {p}: {e!s}")
        raise RuntimeError(f"Could not create directory {p}: {e!s}") from e


def port_checker(port: int, host: str = "localhost") -> bool:
    sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sk.settimeout(1)
    try:
        sk.connect((host, port))
        sk.close()
        return True
    except Exception:
        sk.close()
        return False


def save_temp_img(img: Image.Image | bytes) -> str:
    temp_dir = get_astrbot_temp_path()
    # 获得时间戳
    timestamp = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    p = os.path.join(temp_dir, f"io_temp_img_{timestamp}.jpg")

    if isinstance(img, Image.Image):
        cast(Image.Image, img).save(p)
    else:
        with open(p, "wb") as f:
            f.write(img)
    return p


async def download_image_by_url(
    url: str,
    post: bool = False,
    post_data: dict | None = None,
    path: str | None = None,
    allow_private_network: bool = False,
    allowed_origin: str | None = None,
) -> str:
    """Download an image from a validated URL and return its local path.

    Args:
        url: Remote image or rendering endpoint URL.
        post: Whether to send a POST request instead of GET.
        post_data: JSON payload for POST requests.
        path: Optional destination path.
        allow_private_network: Whether the caller explicitly trusts private
            network destinations.
        allowed_origin: Optional origin that must be used for the request and
            every redirect.

    Returns:
        The destination path containing the response body.
    """

    async def handle_response(resp: aiohttp.ClientResponse, _final_url: str) -> str:
        if not path:
            return save_temp_img(await resp.read())
        with open(path, "wb") as f:
            f.write(await resp.read())
        return path

    try:
        ssl_context = ssl.create_default_context(
            cafile=certifi.where(),
        )  # 使用 certifi 提供的 CA 证书
        return await _request_with_ssrf_protection(
            url,
            method="POST" if post else "GET",
            json_data=post_data,
            ssl_context=ssl_context,
            timeout=1800,
            allow_private_network=allow_private_network,
            allowed_origin=allowed_origin,
            response_handler=handle_response,
        )
    except (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError):
        # 关闭SSL验证（仅在证书验证失败时作为fallback）
        logger.warning(
            f"SSL certificate verification failed for {_safe_url_for_log(url)}. "
            "Disabling SSL verification (CERT_NONE) as a fallback. "
            "This is insecure and exposes the application to man-in-the-middle attacks. "
            "Please investigate and resolve certificate issues."
        )
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return await _request_with_ssrf_protection(
            url,
            method="POST" if post else "GET",
            json_data=post_data,
            ssl_context=ssl_context,
            timeout=120,
            allow_private_network=allow_private_network,
            allowed_origin=allowed_origin,
            response_handler=handle_response,
        )


async def _emit_download_progress(progress_callback, payload: dict) -> None:
    if not progress_callback:
        return
    result = progress_callback(payload)
    if inspect.isawaitable(result):
        await result


class DownloadFileHTTPError(RuntimeError):
    """Raised when a file download returns an unsuccessful HTTP status."""


def _raise_for_download_status(resp, url: str) -> None:
    if resp.status == 200:
        return
    logger.error(
        "Failed to download file from %s. HTTP status code: %s",
        _safe_url_for_log(url),
        resp.status,
    )
    raise DownloadFileHTTPError(
        "Failed to download file from "
        f"{_safe_url_for_log(url)}. HTTP status code: {resp.status}"
    )


async def _download_response_to_file(
    resp,
    file_obj,
    url: str,
    show_progress: bool,
    progress_callback,
    show_downloading_label: bool = True,
) -> None:
    """Write a successful download response to a local file.

    Args:
        resp: aiohttp response object to read from.
        file_obj: Open writable binary file object.
        url: Source URL used for progress events and sanitized errors.
        show_progress: Whether to print progress to stdout.
        progress_callback: Optional callback for progress payloads.
        show_downloading_label: Whether to use the standard download heading.

    """

    total_size = int(resp.headers.get("content-length", 0))
    downloaded_size = 0
    start_time = time.time()
    if show_progress:
        if show_downloading_label:
            print(
                f"Downloading: {_safe_url_for_log(url)} | "
                f"Size: {total_size / 1024:.2f} KB"
            )
        else:
            print(f"Size: {total_size / 1024:.2f} KB | URL: {_safe_url_for_log(url)}")
    await _emit_download_progress(
        progress_callback,
        {
            "url": url,
            "downloaded": 0,
            "total": total_size,
            "percent": 0,
            "speed": 0,
        },
    )
    while True:
        chunk = await resp.content.read(8192)
        if not chunk:
            break
        file_obj.write(chunk)
        downloaded_size += len(chunk)
        elapsed_time = time.time() - start_time if time.time() - start_time > 0 else 1
        speed = downloaded_size / 1024 / elapsed_time  # KB/s
        percent = downloaded_size / total_size if total_size > 0 else 0
        await _emit_download_progress(
            progress_callback,
            {
                "url": url,
                "downloaded": downloaded_size,
                "total": total_size,
                "percent": percent,
                "speed": speed,
            },
        )
        if show_progress:
            print(
                f"\rProgress: {percent:.2%} Speed: {speed:.2f} KB/s",
                end="",
            )
    await _emit_download_progress(
        progress_callback,
        {
            "url": url,
            "downloaded": downloaded_size,
            "total": total_size,
            "percent": 1,
            "speed": 0,
        },
    )


async def download_file(
    url: str,
    path: str,
    show_progress: bool = False,
    progress_callback=None,
    allow_insecure_ssl_fallback: bool = True,
    allow_private_network: bool = False,
    allowed_origin: str | None = None,
) -> None:
    """Download a remote file to a local path.

    Args:
        url: Remote URL to download.
        path: Local destination path.
        show_progress: Whether to print progress to stdout.
        progress_callback: Optional callback for progress payloads.
        allow_insecure_ssl_fallback: Whether certificate failures may retry with
            TLS certificate verification disabled.
        allow_private_network: Whether the caller explicitly trusts private
            network destinations.
        allowed_origin: Optional origin that must be used for the request and
            every redirect.

    Returns:
        None.
    """

    show_downloading_label = True

    async def handle_response(
        resp: aiohttp.ClientResponse,
        final_url: str,
    ) -> None:
        _raise_for_download_status(resp, final_url)
        with open(path, "wb") as f:
            await _download_response_to_file(
                resp,
                f,
                final_url,
                show_progress,
                progress_callback,
                show_downloading_label=show_downloading_label,
            )

    try:
        ssl_context = ssl.create_default_context(
            cafile=certifi.where(),
        )  # 使用 certifi 提供的 CA 证书
        await _request_with_ssrf_protection(
            url,
            method="GET",
            json_data=None,
            ssl_context=ssl_context,
            timeout=1800,
            allow_private_network=allow_private_network,
            allowed_origin=allowed_origin,
            response_handler=handle_response,
        )
    except (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError):
        if not allow_insecure_ssl_fallback:
            raise
        # 关闭SSL验证（仅在证书验证失败时作为fallback）
        logger.warning(
            f"SSL certificate verification failed for {_safe_url_for_log(url)}. "
            "Falling back to unverified connection (CERT_NONE). "
        )
        logger.warning(
            f"SSL certificate verification failed for {_safe_url_for_log(url)}. "
            "Falling back to unverified connection (CERT_NONE). "
            "This is insecure and exposes the application to man-in-the-middle attacks. "
            "Please investigate certificate issues with the remote server."
        )
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        show_downloading_label = False

        await _request_with_ssrf_protection(
            url,
            method="GET",
            json_data=None,
            ssl_context=ssl_context,
            timeout=120,
            allow_private_network=allow_private_network,
            allowed_origin=allowed_origin,
            response_handler=handle_response,
        )
    if show_progress:
        print()


def file_to_base64(file_path: str) -> str:
    with open(file_path, "rb") as f:
        data_bytes = f.read()
        base64_str = base64.b64encode(data_bytes).decode()
    return "base64://" + base64_str


def get_local_ip_addresses():
    net_interfaces = psutil.net_if_addrs()
    network_ips = []

    for interface, addrs in net_interfaces.items():
        for addr in addrs:
            if addr.family == socket.AF_INET:  # 使用 socket.AF_INET 代替 psutil.AF_INET
                network_ips.append(addr.address)

    return network_ips
