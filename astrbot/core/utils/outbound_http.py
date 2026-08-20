"""Central outbound URL validation, pinned resolution, and safe downloads."""

from __future__ import annotations

import asyncio
import gzip
import io
import ipaddress
import socket
import ssl
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import aiohttp
import certifi
from aiohttp.abc import AbstractResolver

from astrbot.core.utils.error_redaction import redact_sensitive_text, safe_error
from astrbot.core.utils.io import ensure_dir

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None] | None]

_DEFAULT_MAX_URL_LENGTH = 2048
_PLUGIN_ARCHIVE_MAX_BYTES = 50 * 1024 * 1024
_CORE_ARCHIVE_MAX_BYTES = 200 * 1024 * 1024
_MIRROR_TEST_MAX_BYTES = 64 * 1024
_JSON_MAX_BYTES = 8 * 1024 * 1024
_DEFAULT_HTTPS_PORTS = frozenset({443})
_JSON_REQUEST_HEADERS = {
    "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
    "Accept-Encoding": "identity",
    "User-Agent": "AstrBot",
}
_BLOCKED_SCHEMES = frozenset(
    {"file", "gopher", "data", "ftp", "ftps", "ws", "wss", "javascript"}
)
_METADATA_HOSTS = frozenset(
    {
        "metadata.google.internal",
        "metadata.goog",
        "metadata.google.com",
        "instance-data",
        "metadata",
        "kubernetes.default.svc",
        "kubernetes.default.svc.cluster.local",
    }
)
_METADATA_ADDRESSES = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),
        ipaddress.ip_address("169.254.170.2"),
        ipaddress.ip_address("100.100.100.200"),
        ipaddress.ip_address("fd00:ec2::254"),
    }
)
_LOCAL_HOSTNAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})
# fake-ip.
_PROXY_FAKE_IP_NETWORKS = (ipaddress.ip_network("198.18.0.0/15"),)
GITHUB_RELATED_HOSTS = frozenset(
    {
        "github.com",
        "www.github.com",
        "api.github.com",
        "raw.githubusercontent.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
        "github-releases.githubusercontent.com",
        "codeload.github.com",
        "gist.github.com",
        "gist.githubusercontent.com",
        "media.githubusercontent.com",
        "user-images.githubusercontent.com",
        "avatars.githubusercontent.com",
        "camo.githubusercontent.com",
        "github.githubassets.com",
    }
)
SOULTER_REGISTRY_HOSTS = frozenset(
    {
        "api.soulter.top",
        "astrbot-registry.soulter.top",
    }
)
DEFAULT_PLUGIN_MARKET_URLS = (
    "https://raw.githubusercontent.com/AstrBotDevs/AstrBot_Plugins_Collection/main/plugin_cache_original.json",
    "https://cdn.jsdelivr.net/gh/AstrBotDevs/AstrBot_Plugins_Collection@main/plugin_cache_original.json",
    "https://api.soulter.top/astrbot/plugins",
)
_ARCHIVE_CONTENT_TYPES = frozenset(
    {
        "application/zip",
        "application/x-zip-compressed",
        "application/octet-stream",
        "binary/octet-stream",
        "application/x-gzip",
        "application/gzip",
    }
)


class OutboundRequestError(ValueError):
    """Raised when an outbound URL or response violates policy."""


class OutboundRedirectError(OutboundRequestError):
    """Raised when a redirect is missing, excessive, or unsafe."""


class OutboundSizeLimitError(OutboundRequestError):
    """Raised when a response exceeds the configured size limit."""


@dataclass(frozen=True, slots=True)
class OutboundRequestPolicy:
    """Declarative constraints for one outbound HTTP use case."""

    allowed_schemes: frozenset[str]
    allowed_hosts: frozenset[str] | None
    allowed_ports: frozenset[int] | None
    allow_private_network: bool
    max_redirects: int
    max_url_length: int
    max_response_bytes: int | None
    timeout_seconds: float
    allowed_content_types: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class ValidatedOutboundURL:
    """A parsed URL plus the addresses that passed policy checks."""

    url: str
    scheme: str
    hostname: str
    port: int
    addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]


CORE_UPDATE = OutboundRequestPolicy(
    allowed_schemes=frozenset({"https"}),
    allowed_hosts=GITHUB_RELATED_HOSTS | SOULTER_REGISTRY_HOSTS,
    allowed_ports=_DEFAULT_HTTPS_PORTS,
    allow_private_network=False,
    max_redirects=5,
    max_url_length=_DEFAULT_MAX_URL_LENGTH,
    max_response_bytes=_CORE_ARCHIVE_MAX_BYTES,
    timeout_seconds=1800.0,
    allowed_content_types=_ARCHIVE_CONTENT_TYPES,
)
PLUGIN_REPOSITORY = OutboundRequestPolicy(
    allowed_schemes=frozenset({"https"}),
    allowed_hosts=GITHUB_RELATED_HOSTS | SOULTER_REGISTRY_HOSTS,
    allowed_ports=_DEFAULT_HTTPS_PORTS,
    allow_private_network=False,
    max_redirects=5,
    max_url_length=_DEFAULT_MAX_URL_LENGTH,
    max_response_bytes=_PLUGIN_ARCHIVE_MAX_BYTES,
    timeout_seconds=1800.0,
    allowed_content_types=_ARCHIVE_CONTENT_TYPES,
)
PLUGIN_DOWNLOAD_URL = OutboundRequestPolicy(
    allowed_schemes=frozenset({"https"}),
    allowed_hosts=None,
    allowed_ports=_DEFAULT_HTTPS_PORTS,
    allow_private_network=False,
    max_redirects=5,
    max_url_length=_DEFAULT_MAX_URL_LENGTH,
    max_response_bytes=_PLUGIN_ARCHIVE_MAX_BYTES,
    timeout_seconds=1800.0,
    allowed_content_types=_ARCHIVE_CONTENT_TYPES,
)
GITHUB_MIRROR_TEST = OutboundRequestPolicy(
    allowed_schemes=frozenset({"https"}),
    allowed_hosts=None,
    allowed_ports=_DEFAULT_HTTPS_PORTS,
    allow_private_network=False,
    max_redirects=0,
    max_url_length=_DEFAULT_MAX_URL_LENGTH,
    max_response_bytes=_MIRROR_TEST_MAX_BYTES,
    timeout_seconds=10.0,
    allowed_content_types=None,
)
PLUGIN_REGISTRY = OutboundRequestPolicy(
    allowed_schemes=frozenset({"https"}),
    allowed_hosts=None,
    allowed_ports=_DEFAULT_HTTPS_PORTS,
    allow_private_network=False,
    max_redirects=2,
    max_url_length=_DEFAULT_MAX_URL_LENGTH,
    max_response_bytes=_JSON_MAX_BYTES,
    timeout_seconds=30.0,
    allowed_content_types=None,
)
MCP_REMOTE = OutboundRequestPolicy(
    allowed_schemes=frozenset({"http", "https"}),
    allowed_hosts=None,
    allowed_ports=None,
    allow_private_network=False,
    max_redirects=0,
    max_url_length=_DEFAULT_MAX_URL_LENGTH,
    max_response_bytes=None,
    timeout_seconds=30.0,
    allowed_content_types=None,
)
JSON_FETCH = OutboundRequestPolicy(
    allowed_schemes=frozenset({"https"}),
    allowed_hosts=GITHUB_RELATED_HOSTS | SOULTER_REGISTRY_HOSTS,
    allowed_ports=_DEFAULT_HTTPS_PORTS,
    allow_private_network=False,
    max_redirects=2,
    max_url_length=_DEFAULT_MAX_URL_LENGTH,
    max_response_bytes=_JSON_MAX_BYTES,
    timeout_seconds=30.0,
    allowed_content_types=None,
)


def redact_outbound_url(url: str) -> str:
    """Return a log-safe URL description without credentials or query tokens."""

    return redact_sensitive_text(url)


def _default_port(scheme: str, port: int | None) -> int:
    if port is not None:
        return port
    if scheme == "https":
        return 443
    if scheme == "http":
        return 80
    raise OutboundRequestError("URL scheme is not allowed.")


def _normalize_hostname(hostname: str) -> str:
    return hostname.strip(".").lower()


def _iter_check_addresses(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [address]
    if isinstance(address, ipaddress.IPv6Address):
        mapped = address.ipv4_mapped
        if mapped is not None:
            addresses.append(mapped)
        if address.sixtofour is not None:
            addresses.append(address.sixtofour)
    return addresses


def _is_ip_literal(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True


def _is_proxy_fake_ip(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    return any(address in network for network in _PROXY_FAKE_IP_NETWORKS)


def _is_disallowed_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    allow_private_network: bool,
    hostname: str | None = None,
) -> bool:
    hostname_is_literal = bool(hostname) and _is_ip_literal(hostname)
    for candidate in _iter_check_addresses(address):
        if candidate in _METADATA_ADDRESSES:
            return True
        if allow_private_network:
            continue
        if not hostname_is_literal and _is_proxy_fake_ip(candidate):
            continue
        if (
            candidate.is_private
            or candidate.is_loopback
            or candidate.is_link_local
            or candidate.is_multicast
            or candidate.is_reserved
            or candidate.is_unspecified
        ):
            return True
    return False


def resolve_host_addresses(
    hostname: str,
    port: int,
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve every A/AAAA record for a hostname.

    Args:
        hostname: DNS name or literal IP.
        port: Destination port used for ``getaddrinfo``.

    Returns:
        Deduplicated resolved addresses.

    Raises:
        OutboundRequestError: If DNS resolution fails.
    """

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        return [literal]

    try:
        records = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise OutboundRequestError(
            "The destination hostname could not be resolved."
        ) from exc

    resolved: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[str] = set()
    for record in records:
        address = ipaddress.ip_address(record[4][0])
        key = str(address)
        if key in seen:
            continue
        seen.add(key)
        resolved.append(address)
    if not resolved:
        raise OutboundRequestError("The destination hostname could not be resolved.")
    return resolved


def validate_outbound_url(
    url: str,
    policy: OutboundRequestPolicy,
    *,
    resolve_addresses: Callable[
        [str, int], Sequence[ipaddress.IPv4Address | ipaddress.IPv6Address]
    ]
    | None = None,
) -> ValidatedOutboundURL:
    """Parse and validate an outbound URL against a policy.

    Args:
        url: Absolute URL to validate.
        policy: Constraints for this request class.
        resolve_addresses: Optional resolver used by tests.

    Returns:
        The validated URL and every resolved address.

    Raises:
        OutboundRequestError: If the URL or any resolved address is disallowed.
    """

    if not isinstance(url, str) or not url.strip():
        raise OutboundRequestError("A destination URL is required.")
    if len(url) > policy.max_url_length:
        raise OutboundRequestError("The destination URL is too long.")

    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme in _BLOCKED_SCHEMES or scheme not in policy.allowed_schemes:
        raise OutboundRequestError("The destination URL scheme is not allowed.")
    if parsed.username is not None or parsed.password is not None:
        raise OutboundRequestError("The destination URL must not contain credentials.")
    if not parsed.hostname:
        raise OutboundRequestError("The destination URL must include a hostname.")

    hostname = _normalize_hostname(parsed.hostname)
    if hostname in _LOCAL_HOSTNAMES and not policy.allow_private_network:
        raise OutboundRequestError("The destination URL cannot target a local host.")
    if hostname in _METADATA_HOSTS:
        raise OutboundRequestError(
            "The destination URL cannot target a metadata service."
        )
    if policy.allowed_hosts is not None and hostname not in policy.allowed_hosts:
        raise OutboundRequestError("The destination host is not allowed.")

    port = _default_port(scheme, parsed.port)
    if policy.allowed_ports is not None and port not in policy.allowed_ports:
        raise OutboundRequestError("The destination port is not allowed.")

    resolver = resolve_addresses or resolve_host_addresses
    addresses = list(resolver(hostname, port))
    if not addresses:
        raise OutboundRequestError("The destination hostname could not be resolved.")
    if any(
        _is_disallowed_address(
            address,
            allow_private_network=policy.allow_private_network,
            hostname=hostname,
        )
        for address in addresses
    ):
        raise OutboundRequestError(
            "The destination URL cannot target a private or reserved address."
        )

    normalized = urlunparse(
        (
            scheme,
            parsed.netloc,
            parsed.path or "/",
            parsed.params,
            parsed.query,
            "",
        )
    )
    return ValidatedOutboundURL(
        url=normalized,
        scheme=scheme,
        hostname=hostname,
        port=port,
        addresses=tuple(addresses),
    )


def validate_github_mirror_origin(
    mirror: str,
    *,
    resolve_addresses: Callable[
        [str, int], Sequence[ipaddress.IPv4Address | ipaddress.IPv6Address]
    ]
    | None = None,
) -> ValidatedOutboundURL:
    """Validate a GitHub URL-prefix mirror as an independent HTTPS origin.

    Args:
        mirror: Candidate prefix such as ``https://mirror.example``.
        resolve_addresses: Optional resolver used by tests.

    Returns:
        The validated origin.

    Raises:
        OutboundRequestError: If the value is not a safe public HTTPS origin.
    """

    if not isinstance(mirror, str) or not mirror.strip():
        raise OutboundRequestError("A GitHub mirror origin is required.")
    parsed = urlparse(mirror.strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise OutboundRequestError("A GitHub mirror must be an HTTPS origin.")
    if parsed.username or parsed.password:
        raise OutboundRequestError("A GitHub mirror must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise OutboundRequestError("A GitHub mirror must not contain query parameters.")
    if parsed.path not in {"", "/"}:
        raise OutboundRequestError("A GitHub mirror must be an origin without a path.")
    origin = f"https://{parsed.netloc}"
    return validate_outbound_url(
        origin,
        GITHUB_MIRROR_TEST,
        resolve_addresses=resolve_addresses,
    )


def compose_github_mirror_url(
    mirror: str,
    github_url: str,
    *,
    resolve_addresses: Callable[
        [str, int], Sequence[ipaddress.IPv4Address | ipaddress.IPv6Address]
    ]
    | None = None,
) -> str:
    """Compose a prefix-mirror URL after validating both sides.

    Args:
        mirror: HTTPS origin used as a GitHub URL prefix.
        github_url: Official GitHub URL being mirrored.
        resolve_addresses: Optional resolver used by tests.

    Returns:
        The prefixed download URL.

    Raises:
        OutboundRequestError: If either side fails validation.
    """

    validated_mirror = validate_github_mirror_origin(
        mirror,
        resolve_addresses=resolve_addresses,
    )
    validated_github = validate_outbound_url(
        github_url,
        PLUGIN_REPOSITORY,
        resolve_addresses=resolve_addresses,
    )
    return f"{validated_mirror.url.rstrip('/')}/{validated_github.url}"


def reject_unsafe_plugin_fetch(
    *,
    download_url: str = "",
    proxy: str = "",
    resolve_addresses: Callable[
        [str, int], Sequence[ipaddress.IPv4Address | ipaddress.IPv6Address]
    ]
    | None = None,
) -> None:
    """Reject plugin download or mirror inputs before the updater runs.

    Args:
        download_url: Explicit archive URL.
        proxy: GitHub URL-prefix mirror origin.
        resolve_addresses: Optional resolver used by tests.

    Raises:
        OutboundRequestError: If either value is unsafe.
    """

    if proxy:
        validate_github_mirror_origin(proxy, resolve_addresses=resolve_addresses)
    if download_url:
        validate_outbound_url(
            download_url,
            PLUGIN_DOWNLOAD_URL,
            resolve_addresses=resolve_addresses,
        )


def policy_for_github_mirror_download(mirror_host: str) -> OutboundRequestPolicy:
    """Return a download policy that allows one validated mirror plus GitHub.

    Args:
        mirror_host: Hostname of a previously validated mirror origin.

    Returns:
        Policy used for the mirrored archive request and its redirects.
    """

    hosts = frozenset({_normalize_hostname(mirror_host)}) | GITHUB_RELATED_HOSTS
    return OutboundRequestPolicy(
        allowed_schemes=frozenset({"https"}),
        allowed_hosts=hosts,
        allowed_ports=_DEFAULT_HTTPS_PORTS,
        allow_private_network=False,
        max_redirects=5,
        max_url_length=_DEFAULT_MAX_URL_LENGTH,
        max_response_bytes=_PLUGIN_ARCHIVE_MAX_BYTES,
        timeout_seconds=1800.0,
        allowed_content_types=_ARCHIVE_CONTENT_TYPES,
    )


class ValidatingAiohttpResolver(AbstractResolver):
    """aiohttp resolver that rejects mixed public/private DNS answers.

    The connector uses these resolved records for the TCP connection, so the
    validated addresses are the addresses that are actually dialed. This is
    not a global ``getaddrinfo`` monkeypatch.
    """

    def __init__(
        self,
        policy: OutboundRequestPolicy,
        *,
        resolve_addresses: Callable[
            [str, int], Sequence[ipaddress.IPv4Address | ipaddress.IPv6Address]
        ]
        | None = None,
    ) -> None:
        self._policy = policy
        self._resolve_addresses = resolve_addresses or resolve_host_addresses

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_UNSPEC,
    ) -> list[dict[str, Any]]:
        hostname = _normalize_hostname(host)
        if hostname in _LOCAL_HOSTNAMES and not self._policy.allow_private_network:
            raise OutboundRequestError(
                "The destination URL cannot target a local host."
            )
        if hostname in _METADATA_HOSTS:
            raise OutboundRequestError(
                "The destination URL cannot target a metadata service."
            )
        if (
            self._policy.allowed_hosts is not None
            and hostname not in self._policy.allowed_hosts
        ):
            raise OutboundRequestError("The destination host is not allowed.")
        addresses = list(self._resolve_addresses(hostname, port or 443))
        if not addresses:
            raise OutboundRequestError(
                "The destination hostname could not be resolved."
            )
        if any(
            _is_disallowed_address(
                address,
                allow_private_network=self._policy.allow_private_network,
                hostname=hostname,
            )
            for address in addresses
        ):
            raise OutboundRequestError(
                "The destination URL cannot target a private or reserved address."
            )
        records: list[dict[str, Any]] = []
        for address in addresses:
            family_value = socket.AF_INET6 if address.version == 6 else socket.AF_INET
            if family not in {socket.AF_UNSPEC, family_value}:
                continue
            records.append(
                {
                    "hostname": hostname,
                    "host": str(address),
                    "port": port or 443,
                    "family": family_value,
                    "proto": socket.IPPROTO_TCP,
                    "flags": socket.AI_NUMERICHOST,
                }
            )
        if not records:
            raise OutboundRequestError(
                "The destination hostname could not be resolved."
            )
        return records

    async def close(self) -> None:
        return None


def _build_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=certifi.where())
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    return context


def _content_type_allowed(value: str | None, policy: OutboundRequestPolicy) -> bool:
    if policy.allowed_content_types is None:
        return True
    if not value:
        return True
    media_type = value.split(";", 1)[0].strip().lower()
    return media_type in policy.allowed_content_types


def _decompress_gzip_limited(data: bytes, max_bytes: int) -> bytes:
    """Decompress gzip bytes without allowing a size-limit bypass."""

    chunks: list[bytes] = []
    total = 0
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as handle:
            while True:
                remaining = max_bytes - total
                chunk = handle.read(min(65536, remaining + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise OutboundSizeLimitError(
                        "The response is larger than the allowed size."
                    )
                chunks.append(chunk)
    except OutboundSizeLimitError:
        raise
    except (EOFError, OSError, gzip.BadGzipFile) as exc:
        raise OutboundRequestError(
            safe_error("The remote response could not be decoded.", exc)
        ) from exc
    return b"".join(chunks)


def _decode_text_payload(raw: bytes, *, max_bytes: int | None = None) -> str:
    """Decode a JSON/text payload, including accidental gzip wrappers."""

    limit = _JSON_MAX_BYTES if max_bytes is None else max_bytes
    if raw.startswith(b"\x1f\x8b"):
        payload = _decompress_gzip_limited(raw, limit)
    else:
        payload = raw
        if len(payload) > limit:
            raise OutboundSizeLimitError(
                "The response is larger than the allowed size."
            )
    return payload.decode("utf-8-sig")


def _proxy_for_url(url: str) -> str | None:
    """Return the configured forward proxy for one destination URL."""

    from astrbot.core.utils.proxy_route import (
        destination_host_from_url,
        resolve_proxy_route,
    )

    return resolve_proxy_route(
        destination_host=destination_host_from_url(url),
    ).proxy_url


def _open_connector(
    policy: OutboundRequestPolicy,
    *,
    proxy: str | None,
    resolve_addresses: Callable[
        [str, int], Sequence[ipaddress.IPv4Address | ipaddress.IPv6Address]
    ]
    | None,
) -> tuple[aiohttp.TCPConnector, ValidatingAiohttpResolver | None]:
    if proxy:
        return aiohttp.TCPConnector(ssl=_build_ssl_context()), None
    resolver = ValidatingAiohttpResolver(
        policy,
        resolve_addresses=resolve_addresses,
    )
    return aiohttp.TCPConnector(ssl=_build_ssl_context(), resolver=resolver), resolver


def _raise_http_status(status: int, url: str) -> None:
    raise OutboundRequestError(
        f"Download failed with HTTP {status} from {redact_outbound_url(url)}."
    )


async def _follow_redirect_url(
    current_url: str,
    location: str,
    policy: OutboundRequestPolicy,
    *,
    resolve_addresses: Callable[
        [str, int], Sequence[ipaddress.IPv4Address | ipaddress.IPv6Address]
    ]
    | None,
) -> ValidatedOutboundURL:
    if not location:
        raise OutboundRedirectError("Redirect is missing a Location header.")
    next_url = urljoin(current_url, location)
    return validate_outbound_url(
        next_url,
        policy,
        resolve_addresses=resolve_addresses,
    )


async def _request_with_manual_redirects(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    policy: OutboundRequestPolicy,
    *,
    resolve_addresses: Callable[
        [str, int], Sequence[ipaddress.IPv4Address | ipaddress.IPv6Address]
    ]
    | None,
    allow_redirects: bool,
    proxy: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> aiohttp.ClientResponse:
    current = validate_outbound_url(url, policy, resolve_addresses=resolve_addresses)
    hops = 0
    max_hops = policy.max_redirects if allow_redirects else 0
    request_kwargs: dict[str, Any] = {
        "allow_redirects": False,
        "timeout": aiohttp.ClientTimeout(total=policy.timeout_seconds),
    }
    if headers:
        request_kwargs["headers"] = headers
    if proxy:
        request_kwargs["proxy"] = proxy
    while True:
        response = await session.request(
            method,
            current.url,
            **request_kwargs,
        )
        if response.status not in {301, 302, 303, 307, 308}:
            return response
        await response.release()
        if hops >= max_hops:
            raise OutboundRedirectError("Too many HTTP redirects.")
        location = response.headers.get("Location", "")
        current = await _follow_redirect_url(
            current.url,
            location,
            policy,
            resolve_addresses=resolve_addresses,
        )
        hops += 1


async def download_to_path(
    url: str,
    path: str | Path,
    policy: OutboundRequestPolicy,
    *,
    progress_callback: ProgressCallback | None = None,
    resolve_addresses: Callable[
        [str, int], Sequence[ipaddress.IPv4Address | ipaddress.IPv6Address]
    ]
    | None = None,
    trust_env: bool = False,
    proxy: str | None = None,
) -> None:
    """Stream a URL to disk with size limits and temporary-file cleanup.

    Args:
        url: Destination URL.
        path: Local destination path.
        policy: Validation and size policy.
        progress_callback: Optional progress hook.
        resolve_addresses: Optional resolver used by tests.
        trust_env: Must stay false so process proxy env is ignored.
        proxy: Optional explicit forward proxy URL.

    Raises:
        OutboundRequestError: If validation, size, type, or HTTP status fails.
    """

    del trust_env
    target = Path(path)
    ensure_dir(target.parent)
    validate_outbound_url(url, policy, resolve_addresses=resolve_addresses)
    forward_proxy = proxy or _proxy_for_url(url)

    async def emit(payload: dict[str, Any]) -> None:
        if progress_callback is None:
            return
        result = progress_callback(payload)
        if asyncio.iscoroutine(result):
            await result

    connector, resolver = _open_connector(
        policy,
        proxy=forward_proxy,
        resolve_addresses=resolve_addresses,
    )
    downloaded = 0
    try:
        async with aiohttp.ClientSession(
            connector=connector,
            trust_env=False,
        ) as session:
            response = await _request_with_manual_redirects(
                session,
                "GET",
                url,
                policy,
                resolve_addresses=resolve_addresses,
                allow_redirects=policy.max_redirects > 0,
                proxy=forward_proxy,
            )
            async with response:
                if response.status != 200:
                    _raise_http_status(response.status, url)
                if not _content_type_allowed(
                    response.headers.get("Content-Type"),
                    policy,
                ):
                    raise OutboundRequestError(
                        "The download Content-Type is not allowed."
                    )
                content_length = response.headers.get("Content-Length")
                if content_length and policy.max_response_bytes is not None:
                    try:
                        declared = int(content_length)
                    except ValueError:
                        declared = -1
                    if declared > policy.max_response_bytes:
                        raise OutboundSizeLimitError(
                            "The download is larger than the allowed size."
                        )
                await emit(
                    {
                        "url": redact_outbound_url(url),
                        "downloaded": 0,
                        "total": int(content_length or 0),
                        "percent": 0,
                        "speed": 0,
                    }
                )
                with target.open("wb") as handle:
                    async for chunk in response.content.iter_chunked(8192):
                        downloaded += len(chunk)
                        if (
                            policy.max_response_bytes is not None
                            and downloaded > policy.max_response_bytes
                        ):
                            raise OutboundSizeLimitError(
                                "The download is larger than the allowed size."
                            )
                        handle.write(chunk)
                await emit(
                    {
                        "url": redact_outbound_url(url),
                        "downloaded": downloaded,
                        "total": downloaded,
                        "percent": 1,
                        "speed": 0,
                    }
                )
    except Exception as exc:
        if target.exists():
            target.unlink(missing_ok=True)
        if isinstance(exc, OutboundRequestError):
            raise
        raise OutboundRequestError(
            safe_error("Outbound download failed.", exc)
        ) from exc
    finally:
        await connector.close()
        if resolver is not None:
            await resolver.close()


async def fetch_text(
    url: str,
    policy: OutboundRequestPolicy,
    *,
    resolve_addresses: Callable[
        [str, int], Sequence[ipaddress.IPv4Address | ipaddress.IPv6Address]
    ]
    | None = None,
) -> tuple[int, str, Mapping[str, str]]:
    """Fetch a small text response after validating every hop.

    Args:
        url: Destination URL.
        policy: Validation and size policy.
        resolve_addresses: Optional resolver used by tests.

    Returns:
        Status code, decoded body, and response headers.

    Raises:
        OutboundRequestError: If validation or the size limit fails.
    """

    validate_outbound_url(url, policy, resolve_addresses=resolve_addresses)
    forward_proxy = _proxy_for_url(url)
    connector, resolver = _open_connector(
        policy,
        proxy=forward_proxy,
        resolve_addresses=resolve_addresses,
    )
    try:
        async with aiohttp.ClientSession(
            connector=connector,
            trust_env=False,
        ) as session:
            response = await _request_with_manual_redirects(
                session,
                "GET",
                url,
                policy,
                resolve_addresses=resolve_addresses,
                allow_redirects=policy.max_redirects > 0,
                proxy=forward_proxy,
                headers=_JSON_REQUEST_HEADERS,
            )
            async with response:
                limit = (
                    policy.max_response_bytes
                    if policy.max_response_bytes is not None
                    else _JSON_MAX_BYTES
                )
                raw = await response.content.read(limit + 1)
                if len(raw) > limit:
                    raise OutboundSizeLimitError(
                        "The response is larger than the allowed size."
                    )
                try:
                    text = _decode_text_payload(raw, max_bytes=limit)
                except UnicodeDecodeError as exc:
                    raise OutboundRequestError(
                        safe_error("The remote response could not be decoded.", exc)
                    ) from exc
                return response.status, text, response.headers
    except OutboundRequestError:
        raise
    except Exception as exc:
        raise OutboundRequestError(safe_error("Outbound request failed.", exc)) from exc
    finally:
        await connector.close()
        if resolver is not None:
            await resolver.close()


class PinnedAsyncNetworkBackend:
    """httpcore/httpx2 backend that dials a validated address, not a second DNS lookup."""

    def __init__(self, inner: Any, policy: OutboundRequestPolicy) -> None:
        self._inner = inner
        self._policy = policy

    async def connect_tcp(self, host: str, port: int = 0, **kwargs: Any) -> Any:
        hostname = _normalize_hostname(host)
        if hostname in _LOCAL_HOSTNAMES and not self._policy.allow_private_network:
            raise OutboundRequestError(
                "The destination URL cannot target a local host."
            )
        if hostname in _METADATA_HOSTS:
            raise OutboundRequestError(
                "The destination URL cannot target a metadata service."
            )
        if (
            self._policy.allowed_hosts is not None
            and hostname not in self._policy.allowed_hosts
        ):
            raise OutboundRequestError("The destination host is not allowed.")
        addresses = resolve_host_addresses(hostname, port or 443)
        if any(
            _is_disallowed_address(
                address,
                allow_private_network=self._policy.allow_private_network,
                hostname=hostname,
            )
            for address in addresses
        ):
            raise OutboundRequestError(
                "The destination URL cannot target a private or reserved address."
            )
        return await self._inner.connect_tcp(str(addresses[0]), port, **kwargs)

    async def connect_unix_socket(self, path: str, **kwargs: Any) -> Any:
        del path, kwargs
        raise OutboundRequestError("Unix sockets are not allowed.")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def pin_httpx_transport(transport: Any, policy: OutboundRequestPolicy) -> Any:
    """Replace a transport's network backend with a pinned validating backend.

    Args:
        transport: httpx or httpx2 ``AsyncHTTPTransport``.
        policy: Address policy used for every TCP connect.

    Returns:
        The same transport instance.
    """

    pool = getattr(transport, "_pool", None)
    backend = getattr(pool, "_network_backend", None) if pool is not None else None
    if backend is None:
        return transport
    pool._network_backend = PinnedAsyncNetworkBackend(backend, policy)
    return transport


async def fetch_json(
    url: str,
    policy: OutboundRequestPolicy,
    *,
    resolve_addresses: Callable[
        [str, int], Sequence[ipaddress.IPv4Address | ipaddress.IPv6Address]
    ]
    | None = None,
) -> Any:
    """Fetch and decode a JSON body from a validated URL.

    Args:
        url: Destination URL.
        policy: Validation and size policy.
        resolve_addresses: Optional resolver used by tests.

    Returns:
        Parsed JSON payload.

    Raises:
        OutboundRequestError: If validation, HTTP status, or JSON decoding fails.
    """

    import json

    status, text, _headers = await fetch_text(
        url,
        policy,
        resolve_addresses=resolve_addresses,
    )
    if status != 200:
        _raise_http_status(status, url)
    stripped = text.lstrip("\ufeff \t\r\n")
    if stripped[:1] == "<" or stripped.lower().startswith(("<!doctype", "<html")):
        raise OutboundRequestError("The remote response is HTML, not JSON.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise OutboundRequestError(
            f"The remote response is not valid JSON (len={len(text)})."
        ) from exc
