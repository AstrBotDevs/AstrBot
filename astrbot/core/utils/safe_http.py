"""Bounded HTTP helpers for URLs supplied by untrusted sources."""

from __future__ import annotations

import ipaddress
import json
import socket
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import aiohttp

from astrbot.core.utils.http_ssl import build_ssl_context_with_certifi


class UnsafeRemoteTarget(ValueError):
    """Raised when a remote URL violates the outbound network policy."""


class RemoteResponseTooLarge(ValueError):
    """Raised when a remote response exceeds its byte budget."""


class RemoteRedirectError(ValueError):
    """Raised when a remote response exceeds its redirect budget."""


@dataclass(frozen=True, slots=True)
class PrivateTargetRule:
    """Allow one exact hostname to resolve into specific private networks.

    Args:
        host: Exact lower-case hostname or IP literal.
        networks: Private networks that resolved addresses may belong to.
    """

    host: str
    networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]

    @classmethod
    def from_config(cls, value: object) -> PrivateTargetRule:
        """Parse one private-target rule from configuration.

        Args:
            value: Mapping containing ``host`` and a non-empty ``cidrs`` list.

        Returns:
            Parsed immutable rule.

        Raises:
            ValueError: If the rule is malformed or contains a wildcard.
        """
        if not isinstance(value, dict):
            raise ValueError("Private target rule must be an object")
        host = str(value.get("host") or "").strip().rstrip(".").lower()
        cidrs = value.get("cidrs")
        if not host or "*" in host or not isinstance(cidrs, list) or not cidrs:
            raise ValueError("Private target rule requires an exact host and CIDRs")
        networks = tuple(
            ipaddress.ip_network(str(item), strict=False) for item in cidrs
        )
        return cls(host=host, networks=networks)


@dataclass(frozen=True, slots=True)
class RemoteFetchPolicy:
    """Network and resource limits for one untrusted remote fetch.

    Args:
        max_bytes: Maximum response body size.
        total_timeout_seconds: Total request timeout across each HTTP hop.
        max_redirects: Maximum number of redirects.
        allow_private_targets: Exact private-host rules.
    """

    max_bytes: int
    total_timeout_seconds: float
    max_redirects: int = 3
    allow_private_targets: tuple[PrivateTargetRule, ...] = ()

    def __post_init__(self) -> None:
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if self.total_timeout_seconds <= 0:
            raise ValueError("total_timeout_seconds must be positive")
        if self.max_redirects < 0:
            raise ValueError("max_redirects must not be negative")


def safe_url_for_log(url: str) -> str:
    """Return a URL representation without credentials, query, or fragment.

    Args:
        url: URL that may contain sensitive components.

    Returns:
        Sanitized URL suitable for logs.
    """
    try:
        parsed = urlsplit(str(url))
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port else ""
        return urlunsplit((parsed.scheme, f"{host}{port}", parsed.path, "", ""))
    except (TypeError, ValueError):
        return "<invalid-url>"


def parse_private_target_rules(values: object) -> tuple[PrivateTargetRule, ...]:
    """Parse a list of exact private-target rules.

    Args:
        values: Configuration list.

    Returns:
        Parsed rules.

    Raises:
        ValueError: If the value or any rule is invalid.
    """
    if values in (None, []):
        return ()
    if not isinstance(values, list):
        raise ValueError("Private target rules must be a list")
    return tuple(PrivateTargetRule.from_config(item) for item in values)


def _matching_rule(
    host: str,
    rules: Sequence[PrivateTargetRule],
) -> PrivateTargetRule | None:
    normalized = host.strip().rstrip(".").lower()
    return next((rule for rule in rules if rule.host == normalized), None)


def _address_allowed(
    host: str,
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    rules: Sequence[PrivateTargetRule],
) -> bool:
    if address.is_global:
        return True
    rule = _matching_rule(host, rules)
    return bool(rule and any(address in network for network in rule.networks))


def _validate_url_syntax(url: str, policy: RemoteFetchPolicy) -> str:
    try:
        parsed = urlsplit(str(url).strip())
    except ValueError as exc:
        raise UnsafeRemoteTarget("Invalid remote URL") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise UnsafeRemoteTarget("Only absolute HTTP(S) URLs are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeRemoteTarget("Remote URLs must not contain credentials")
    host = parsed.hostname.rstrip(".").lower()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return parsed.geturl()
    if not _address_allowed(host, address, policy.allow_private_targets):
        raise UnsafeRemoteTarget("Remote target address is not allowed")
    return parsed.geturl()


class _ValidatingResolver(aiohttp.abc.AbstractResolver):
    """Resolve a hostname and reject every address outside the policy."""

    def __init__(self, policy: RemoteFetchPolicy) -> None:
        self._policy = policy
        self._resolver = aiohttp.DefaultResolver()

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: int = socket.AF_UNSPEC,
    ) -> list[dict[str, Any]]:
        """Resolve and validate all candidate addresses.

        Args:
            host: Requested hostname.
            port: Requested port.
            family: Requested address family.

        Returns:
            aiohttp resolver records.

        Raises:
            UnsafeRemoteTarget: If any candidate address is disallowed.
        """
        records = await self._resolver.resolve(host, port, family)
        if not records:
            raise UnsafeRemoteTarget("Remote hostname did not resolve")
        for record in records:
            try:
                address = ipaddress.ip_address(str(record["host"]))
            except (KeyError, ValueError) as exc:
                raise UnsafeRemoteTarget(
                    "Remote hostname returned an invalid address"
                ) from exc
            if not _address_allowed(host, address, self._policy.allow_private_targets):
                raise UnsafeRemoteTarget(
                    "Remote hostname resolved to a blocked address"
                )
        return records

    async def close(self) -> None:
        """Close the delegated aiohttp resolver."""
        await self._resolver.close()


async def _read_response_body(
    response: aiohttp.ClientResponse, max_bytes: int
) -> bytes:
    declared = response.headers.get("content-length")
    if declared:
        try:
            declared_bytes = int(declared)
        except ValueError:
            pass
        else:
            if declared_bytes > max_bytes:
                raise RemoteResponseTooLarge("Remote response exceeds the byte limit")
    body = bytearray()
    async for chunk in response.content.iter_chunked(8192):
        body.extend(chunk)
        if len(body) > max_bytes:
            raise RemoteResponseTooLarge("Remote response exceeds the byte limit")
    return bytes(body)


async def read_public_bytes(url: str, *, policy: RemoteFetchPolicy) -> bytes:
    """Read a bounded response from a policy-checked HTTP(S) URL.

    Args:
        url: Untrusted URL.
        policy: Network and byte limits.

    Returns:
        Response body.

    Raises:
        UnsafeRemoteTarget: If the URL or resolved target is blocked.
        RemoteRedirectError: If too many redirects are returned.
        RemoteResponseTooLarge: If the body exceeds ``policy.max_bytes``.
        aiohttp.ClientResponseError: If the final HTTP status is unsuccessful.
    """
    current_url = _validate_url_syntax(url, policy)
    timeout = aiohttp.ClientTimeout(total=policy.total_timeout_seconds)
    for redirect_count in range(policy.max_redirects + 1):
        resolver = _ValidatingResolver(policy)
        connector = aiohttp.TCPConnector(
            ssl=build_ssl_context_with_certifi(),
            resolver=resolver,
            use_dns_cache=False,
        )
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            trust_env=False,
        ) as session:
            async with session.get(current_url, allow_redirects=False) as response:
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise RemoteRedirectError("Remote redirect is missing Location")
                    if redirect_count >= policy.max_redirects:
                        raise RemoteRedirectError("Remote redirect limit exceeded")
                    current_url = _validate_url_syntax(
                        urljoin(current_url, location),
                        policy,
                    )
                    continue
                response.raise_for_status()
                return await _read_response_body(response, policy.max_bytes)
    raise RemoteRedirectError("Remote redirect limit exceeded")


async def fetch_public_json(url: str, *, policy: RemoteFetchPolicy) -> object:
    """Fetch and decode bounded JSON from an untrusted URL.

    Args:
        url: Untrusted URL.
        policy: Network and byte limits.

    Returns:
        Decoded JSON value.

    Raises:
        ValueError: If the response is not valid JSON.
    """
    body = await read_public_bytes(url, policy=policy)
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Remote response is not valid JSON") from exc


async def download_public_url(
    url: str,
    destination: Path,
    *,
    policy: RemoteFetchPolicy,
) -> None:
    """Download a checked response and atomically replace the destination.

    Args:
        url: Untrusted URL.
        destination: Final local path.
        policy: Network and byte limits.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.part")
    try:
        body = await read_public_bytes(url, policy=policy)
        temporary.write_bytes(body)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
