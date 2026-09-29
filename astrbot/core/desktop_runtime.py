import ipaddress
import os
import secrets

DESKTOP_MANAGED_RESTART_MESSAGE = (
    "AstrBot Desktop manages this backend process. Please restart or update from "
    "the desktop app instead of the core WebUI."
)

DESKTOP_SESSION_SECRET_ENV = "ASTRBOT_DESKTOP_SESSION_SECRET"
DESKTOP_SESSION_SECRET_MIN_LENGTH = 32


def is_desktop_managed_backend() -> bool:
    return os.environ.get("ASTRBOT_DESKTOP_MANAGED") == "1"


def get_desktop_session_secret() -> str | None:
    """Return the in-memory secret when desktop session auth is enabled."""
    if not is_desktop_managed_backend():
        return None

    secret = os.environ.get(DESKTOP_SESSION_SECRET_ENV, "").strip()
    if len(secret) < DESKTOP_SESSION_SECRET_MIN_LENGTH:
        return None
    return secret


def is_desktop_session_auth_enabled() -> bool:
    return get_desktop_session_secret() is not None


def is_loopback_client_host(host: str | None) -> bool:
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False

    if address.is_loopback:
        return True
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped.is_loopback
    return False


def verify_desktop_session_secret(
    provided_secret: str | None,
    client_host: str | None,
) -> bool:
    configured_secret = get_desktop_session_secret()
    if configured_secret is None or not is_loopback_client_host(client_host):
        return False
    if not isinstance(provided_secret, str):
        return False
    return secrets.compare_digest(
        provided_secret.encode("utf-8"),
        configured_secret.encode("utf-8"),
    )
