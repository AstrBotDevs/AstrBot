"""SSRF guard for outbound MCP server URLs.

MCP HTTP/SSE/streamable-HTTP server URLs are user-configured (via the
dashboard or config files) and are dialed by the backend itself. Without
validation, a malicious or compromised config could point AstrBot at
internal-only services or cloud metadata endpoints (e.g. 169.254.169.254),
turning the MCP client into a server-side request forgery primitive.

This module resolves the configured hostname and rejects addresses that fall
into private, loopback, link-local, reserved, multicast, or unspecified
ranges before any request is made.
"""

import ipaddress
import os
import socket
from urllib.parse import urlparse

_ALLOW_PRIVATE_ENV = "ASTRBOT_MCP_ALLOW_PRIVATE_NETWORK_URLS"


class UnsafeMcpUrlError(ValueError):
    """Raised when an MCP server URL is unsafe to connect to."""


def _private_network_urls_allowed() -> bool:
    return os.environ.get(_ALLOW_PRIVATE_ENV, "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_mcp_url(url: str) -> None:
    """Raise UnsafeMcpUrlError if `url` is unsafe to connect to.

    Checks the URL scheme and resolves the hostname, rejecting any address
    that resolves to a private/loopback/link-local/reserved/multicast range.
    Set ASTRBOT_MCP_ALLOW_PRIVATE_NETWORK_URLS=1 to disable this check for
    trusted deployments that intentionally run MCP servers on internal hosts.
    """
    if _private_network_urls_allowed():
        return

    if not isinstance(url, str) or not url:
        raise UnsafeMcpUrlError("MCP server URL must be a non-empty string.")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeMcpUrlError(
            f"MCP server URL scheme `{parsed.scheme}` is not allowed; only http/https are supported."
        )

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeMcpUrlError("MCP server URL is missing a hostname.")

    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UnsafeMcpUrlError(
            f"Could not resolve MCP server host `{hostname}`: {exc}"
        ) from exc

    if not addrinfo:
        raise UnsafeMcpUrlError(f"Could not resolve MCP server host `{hostname}`.")

    for _family, _type, _proto, _canonname, sockaddr in addrinfo:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            raise UnsafeMcpUrlError(
                f"MCP server URL `{url}` resolves to a private/reserved address ({ip}); "
                f"connecting is blocked to prevent SSRF. Set {_ALLOW_PRIVATE_ENV}=1 if you "
                f"trust this MCP server and intend to connect to an internal host."
            )
