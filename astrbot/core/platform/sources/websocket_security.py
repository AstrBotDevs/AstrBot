import ipaddress
from urllib.parse import SplitResult, urlsplit, urlunsplit

_ALLOWED_INSECURE_SUFFIXES = (".local", ".internal")


def _is_local_or_private_host(hostname: str | None) -> bool:
    if not hostname:
        return False

    normalized = hostname.strip("[]").lower()
    if normalized == "localhost":
        return True
    if normalized.endswith(_ALLOWED_INSECURE_SUFFIXES):
        return True

    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False

    return address.is_loopback or address.is_private or address.is_link_local


def require_secure_transport_url(
    url: str,
    *,
    label: str,
    allowed_schemes: set[str],
) -> SplitResult:
    parsed = urlsplit(url)
    if parsed.scheme not in allowed_schemes:
        allowed = ", ".join(sorted(allowed_schemes))
        raise ValueError(f"{label} must use one of: {allowed}")

    if parsed.scheme in {"http", "ws"} and not _is_local_or_private_host(
        parsed.hostname
    ):
        raise ValueError(
            f"{label} must use wss:// or https:// for non-local endpoints: {url}",
        )

    return parsed


def to_websocket_url(url: str, *, label: str = "WebSocket URL") -> str:
    normalized_url = url.rstrip("/")
    parsed = urlsplit(normalized_url)
    allowed_schemes = {"http", "https", "ws", "wss"}

    if parsed.scheme not in allowed_schemes:
        raise ValueError(
            f"{label} must use http://, https://, ws:// or wss://: {normalized_url}",
        )

    parsed = require_secure_transport_url(
        normalized_url,
        label=label,
        allowed_schemes=allowed_schemes,
    )
    scheme_map = {
        "http": "ws",
        "https": "wss",
        "ws": "ws",
        "wss": "wss",
    }

    try:
        ws_scheme = scheme_map[parsed.scheme]
    except KeyError as exc:
        raise ValueError(
            f"{label} must use http://, https://, ws:// or wss://: "
            f"{normalized_url}",
        ) from exc

    return urlunsplit(
        parsed._replace(scheme=ws_scheme),
    )
