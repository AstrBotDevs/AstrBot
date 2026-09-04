"""Typed dashboard JWT issuance and validation helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

DASHBOARD_ISSUER = "astrbot"
DASHBOARD_SESSION_AUDIENCE = "dashboard"
PLUGIN_ASSET_AUDIENCE = "plugin-page-assets"
DASHBOARD_SESSION_TYPE = "dashboard_session"
PLUGIN_ASSET_TYPE = "plugin_page_asset"


class DashboardTokenError(ValueError):
    """Raised when a dashboard token does not satisfy its security contract."""


def _decode_token(
    token: str, secret: str, audience: str, token_type: str
) -> dict[str, Any]:
    """Decode a JWT and require claims that distinguish its intended use.

    Args:
        token: Encoded JWT supplied by a client.
        secret: Secret dedicated to the expected token class.
        audience: Expected JWT audience.
        token_type: Expected AstrBot token type.

    Returns:
        Validated decoded claims.

    Raises:
        DashboardTokenError: If the token is expired, malformed, or for another use.
    """
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=DASHBOARD_ISSUER,
            audience=audience,
            options={"require": ["iss", "aud", "typ", "sub", "iat", "exp"]},
        )
    except jwt.InvalidTokenError as exc:
        raise DashboardTokenError("Invalid dashboard token") from exc
    if payload.get("typ") != token_type:
        raise DashboardTokenError("Unexpected dashboard token type")
    if not isinstance(payload.get("sub"), str) or not payload["sub"].strip():
        raise DashboardTokenError("Dashboard token subject is invalid")
    return payload


def issue_dashboard_session_token(
    *, username: str, secret: str, expires_at: datetime, auth_source: str
) -> str:
    """Issue a strictly typed dashboard session JWT.

    Args:
        username: Authenticated dashboard username.
        secret: Dashboard-session signing secret.
        expires_at: Aware expiration timestamp.
        auth_source: Login mechanism used to establish the session.

    Returns:
        Signed dashboard session JWT.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "iss": DASHBOARD_ISSUER,
        "aud": DASHBOARD_SESSION_AUDIENCE,
        "typ": DASHBOARD_SESSION_TYPE,
        "sub": username,
        "username": username,
        "auth_source": auth_source,
        "iat": now,
        "exp": expires_at,
    }
    return str(jwt.encode(payload, secret, algorithm="HS256"))


def decode_dashboard_session_token(token: str, *, secret: str) -> str:
    """Return the username from a valid dashboard session JWT.

    Args:
        token: Encoded dashboard session JWT.
        secret: Dashboard-session signing secret.

    Returns:
        Authenticated username.

    Raises:
        DashboardTokenError: If the token is not a valid dashboard session.
    """
    payload = _decode_token(
        token, secret, DASHBOARD_SESSION_AUDIENCE, DASHBOARD_SESSION_TYPE
    )
    username = payload.get("username")
    if (
        not isinstance(username, str)
        or username != payload["sub"]
        or not username.strip()
    ):
        raise DashboardTokenError("Dashboard token username is invalid")
    return username


def issue_plugin_asset_token(
    *,
    username: str,
    plugin_name: str,
    page_name: str,
    locale: str,
    secret: str,
    expires_at: datetime | None = None,
) -> str:
    """Issue a short-lived, page-scoped plugin asset JWT.

    Args:
        username: Dashboard user receiving the plugin page.
        plugin_name: Plugin owning the requested page.
        page_name: Requested plugin page name.
        locale: Requested page locale.
        secret: Plugin-asset signing secret.
        expires_at: Optional aware expiration timestamp.

    Returns:
        Signed plugin asset JWT.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "iss": DASHBOARD_ISSUER,
        "aud": PLUGIN_ASSET_AUDIENCE,
        "typ": PLUGIN_ASSET_TYPE,
        "sub": username,
        "username": username,
        "plugin_name": plugin_name,
        "page_name": page_name,
        "locale": locale,
        "iat": now,
        "exp": expires_at or now + timedelta(seconds=60),
    }
    return str(jwt.encode(payload, secret, algorithm="HS256"))


def decode_plugin_asset_token(token: str, *, secret: str) -> dict[str, str]:
    """Validate and return a plugin asset token's string claims.

    Args:
        token: Encoded plugin asset JWT.
        secret: Plugin-asset signing secret.

    Returns:
        Token claims needed by plugin page serving.

    Raises:
        DashboardTokenError: If the token does not describe one plugin page.
    """
    payload = _decode_token(token, secret, PLUGIN_ASSET_AUDIENCE, PLUGIN_ASSET_TYPE)
    keys = ("username", "plugin_name", "page_name", "locale")
    if any(
        not isinstance(payload.get(key), str) or not payload[key].strip()
        for key in keys
    ):
        raise DashboardTokenError("Plugin asset token claims are invalid")
    return {key: payload[key] for key in keys}
