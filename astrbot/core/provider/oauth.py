"""OAuth 2.0 public-client support for plugin-defined AI providers."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import re
import secrets
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx


class OAuth2Error(Exception):
    """An OAuth failure with a credential-free, user-facing message."""


@dataclass(frozen=True)
class OAuth2Token:
    """Credentials kept in a plugin's private store, never provider configuration.

    Args:
        access_token: Bearer credential returned by the authorization server.
        refresh_token: Optional credential for the refresh grant.
        expires_at: Expiry as Unix time, or None when the server omits it.
        scope: Granted scope, as returned by the server.
    """

    access_token: str = field(repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    expires_at: float | None = None
    scope: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.access_token, str) or not re.fullmatch(
            r"[A-Za-z0-9\-._~+/]+=*", self.access_token
        ):
            raise OAuth2Error("Invalid OAuth access token.")
        if self.refresh_token is not None and (
            not isinstance(self.refresh_token, str) or not self.refresh_token
        ):
            raise OAuth2Error("Invalid OAuth refresh token.")
        if self.expires_at is not None and (
            isinstance(self.expires_at, bool)
            or not isinstance(self.expires_at, (float, int))
            or not math.isfinite(self.expires_at)
        ):
            raise OAuth2Error("Invalid OAuth token expiry.")
        if self.scope is not None and not isinstance(self.scope, str):
            raise OAuth2Error("Invalid OAuth token scope.")


class OAuth2Session:
    """One account's PKCE login, refresh and request authentication.

    Share one instance across all models belonging to the same provider source.
    Do not share an instance between accounts. The plugin owns its HTTP client
    and private persistence; this class does not add public callback routes.

    Args:
        client_id: Public client ID registered with the AI supplier.
        authorization_endpoint: Supplier's authorization URL.
        token_endpoint: Supplier's token URL.
        redirect_uri: Exact redirect URI registered for this client.
        api_base: Only this API origin and path may receive the Bearer token.
        http_client: Plugin-owned client for token requests (including proxy).
        load_token: Async callback loading this account's private credentials.
        save_token: Async callback persisting credentials; None deletes them.
        scopes: Requested OAuth scopes.

    Raises:
        ValueError: If endpoints or client configuration are invalid.
    """

    def __init__(
        self,
        *,
        client_id: str,
        authorization_endpoint: str,
        token_endpoint: str,
        redirect_uri: str,
        api_base: str,
        http_client: httpx.AsyncClient,
        load_token: Callable[[], Awaitable[OAuth2Token | None]],
        save_token: Callable[[OAuth2Token | None], Awaitable[None]],
        scopes: tuple[str, ...] = (),
    ) -> None:
        if not isinstance(client_id, str) or not client_id.strip():
            raise ValueError("An OAuth client ID is required.")
        for value in (authorization_endpoint, token_endpoint, redirect_uri, api_base):
            try:
                if not isinstance(value, str) or any(ord(c) < 33 for c in value):
                    raise ValueError
                url = urlsplit(value)
                valid = (
                    bool(url.hostname)
                    and url.username is None
                    and url.password is None
                    and not url.fragment
                    and (
                        url.scheme == "https"
                        or (
                            url.scheme == "http"
                            and url.hostname in {"localhost", "127.0.0.1", "::1"}
                        )
                    )
                )
                _ = url.port
            except (ValueError, TypeError):
                valid = False
            if not valid:
                raise ValueError("OAuth URLs must use HTTPS (HTTP only on loopback).")
        # Keep protocol parameters unambiguous; supplier-specific parameters
        # such as audience can be supplied in the authorization endpoint URL.
        reserved = {
            "client_id",
            "redirect_uri",
            "response_type",
            "scope",
            "state",
            "code_challenge",
            "code_challenge_method",
            "code",
            "error",
        }
        for value in (authorization_endpoint, redirect_uri):
            if reserved.intersection(
                parse_qs(urlsplit(value).query, keep_blank_values=True)
            ):
                raise ValueError("OAuth URL contains reserved query parameters.")
        if urlsplit(api_base).query:
            raise ValueError("The provider API base must not contain a query.")
        if any(
            not isinstance(scope, str) or not scope or any(c.isspace() for c in scope)
            for scope in scopes
        ):
            raise ValueError("OAuth scopes must be non-empty scope tokens.")
        self._client_id = client_id
        self._authorization_endpoint = authorization_endpoint
        self._token_endpoint = token_endpoint
        self._redirect_uri = redirect_uri
        self._api_base = httpx.URL(api_base)
        self._http = http_client
        self._load_token = load_token
        self._save_token = save_token
        self._scopes = scopes
        self._lock = asyncio.Lock()
        self._token: OAuth2Token | None = None
        self._loaded = False
        self._closed = False
        self._pending: tuple[str, str, str, float] | None = None

    async def begin_authorization(self, *, owner: str) -> str:
        """Start a ten-minute login, replacing any previous pending attempt.

        Args:
            owner: Authenticated Dashboard user, not a username from the body.

        Returns:
            Authorization URL safe to display to that user.

        Raises:
            OAuth2Error: If the owner is missing or the session is closed.
        """
        if not isinstance(owner, str) or not owner:
            raise OAuth2Error("An authenticated login owner is required.")
        async with self._lock:
            if self._closed:
                raise OAuth2Error("OAuth provider is closed.")
            state = secrets.token_urlsafe(32)
            verifier = secrets.token_urlsafe(64)
            challenge = (
                base64.urlsafe_b64encode(
                    hashlib.sha256(verifier.encode("ascii")).digest()
                )
                .rstrip(b"=")
                .decode("ascii")
            )
            self._pending = (owner, state, verifier, time.monotonic() + 600)
            url = urlsplit(self._authorization_endpoint)
            query = urlencode(
                {
                    "client_id": self._client_id,
                    "redirect_uri": self._redirect_uri,
                    "response_type": "code",
                    "scope": " ".join(self._scopes),
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
            )
            return urlunsplit(
                url._replace(query=f"{url.query}&{query}" if url.query else query)
            )

    async def complete_authorization(self, callback_url: str, *, owner: str) -> None:
        """Validate a pasted callback URL and exchange its one-time code.

        Args:
            callback_url: Full URL after the supplier redirects the browser.
            owner: The same authenticated Dashboard user who started the login.

        Raises:
            OAuth2Error: For invalid, expired, denied or failed authorization.
        """
        async with self._lock:
            if self._closed:
                raise OAuth2Error("OAuth provider is closed.")
            pending = self._pending
            if pending is None or time.monotonic() >= pending[3]:
                self._pending = None
                raise OAuth2Error("OAuth login has expired; start a new login.")
            if owner != pending[0]:
                raise OAuth2Error("OAuth login belongs to another user.")
            if not isinstance(callback_url, str) or len(callback_url) > 8192:
                raise OAuth2Error("Invalid OAuth callback URL.")
            try:
                callback = urlsplit(callback_url)
                expected = urlsplit(self._redirect_uri)
                params = parse_qs(
                    callback.query, keep_blank_values=True, max_num_fields=32
                )
                fixed_params = parse_qs(expected.query, keep_blank_values=True)
                valid = (
                    callback[:3] == expected[:3]
                    and not callback.fragment
                    and len(params.get("state", [])) == 1
                    and secrets.compare_digest(
                        params["state"][0].encode("utf-8"), pending[1].encode("ascii")
                    )
                    and all(params.get(k) == v for k, v in fixed_params.items())
                )
            except (ValueError, UnicodeError):
                valid = False
            if not valid:
                raise OAuth2Error("Invalid OAuth callback URL or state.")
            # Consume before any network I/O: cancellation and errors cannot
            # make an authorization code available for a second exchange.
            self._pending = None
            if "error" in params:
                raise OAuth2Error("OAuth authorization was denied.")
            if len(params.get("code", [])) != 1 or not params["code"][0]:
                raise OAuth2Error("OAuth callback is missing an authorization code.")
            token = await self._request_token(
                {
                    "grant_type": "authorization_code",
                    "code": params["code"][0],
                    "redirect_uri": self._redirect_uri,
                    "code_verifier": pending[2],
                }
            )
            try:
                await self._save_token(token)
            except Exception:
                raise OAuth2Error("Could not persist OAuth credentials.") from None
            # A new account must never inherit the previous account's refresh token.
            self._token, self._loaded = token, True

    async def cancel_authorization(self, *, owner: str) -> None:
        """Cancel this user's pending login without disconnecting the account.

        Args:
            owner: Authenticated Dashboard user cancelling the login.

        Raises:
            OAuth2Error: If a different user owns the pending login.
        """
        async with self._lock:
            if self._pending is not None:
                if owner != self._pending[0]:
                    raise OAuth2Error("OAuth login belongs to another user.")
                self._pending = None

    async def get_access_token(self) -> str:
        """Load or refresh credentials, coalescing concurrent refresh requests.

        Returns:
            Access token for server-side use only.

        Raises:
            OAuth2Error: If sign-in is required, storage fails or refresh fails.
        """
        async with self._lock:
            if self._closed:
                raise OAuth2Error("OAuth provider is closed.")
            if not self._loaded:
                try:
                    token = await self._load_token()
                    if token is not None and not isinstance(token, OAuth2Token):
                        raise TypeError
                except Exception:
                    raise OAuth2Error("Could not load OAuth credentials.") from None
                self._token, self._loaded = token, True
            token = self._token
            if token is None:
                raise OAuth2Error("OAuth sign-in is required.")
            if token.expires_at is None or token.expires_at > time.time() + 30:
                return token.access_token
            if not token.refresh_token:
                raise OAuth2Error("OAuth token has expired; sign in again.")
            refreshed = await self._request_token(
                {"grant_type": "refresh_token", "refresh_token": token.refresh_token},
                previous=token,
            )
            try:
                await self._save_token(refreshed)
            except Exception:
                # A rotated refresh token cannot safely be retried with the old one.
                self._token = None
                raise OAuth2Error(
                    "Could not persist OAuth credentials; sign in again."
                ) from None
            self._token = refreshed
            return refreshed.access_token

    async def authorize_request(self, request: httpx.Request) -> None:
        """HTTPX request hook attaching a token only to the configured API.

        Install on the provider's HTTP client, not the token-exchange client.
        Hooks run again on redirects, preventing cross-origin credential leaks.
        This covers model discovery, streaming and ordinary inference without
        mutating a shared SDK client's API key or replaying a failed request.

        Args:
            request: Outbound provider request.

        Raises:
            OAuth2Error: If the target is outside this provider or login fails.
        """
        url, base = request.url, self._api_base
        prefix = base.path.rstrip("/")
        if (
            (url.scheme, url.host, url.port) != (base.scheme, base.host, base.port)
            or any(part in {".", ".."} for part in url.path.split("/"))
            or "\\" in url.path
            or not (url.path == prefix or url.path.startswith(prefix + "/"))
        ):
            request.headers.pop("Authorization", None)
            raise OAuth2Error(
                "Refusing to send OAuth credentials outside the provider API."
            )
        request.headers["Authorization"] = f"Bearer {await self.get_access_token()}"

    async def disconnect(self) -> None:
        """Forget local credentials and pending login, without claiming revocation.

        Raises:
            OAuth2Error: If the private store cannot be cleared.
        """
        async with self._lock:
            self._pending = None
            self._token, self._loaded = None, True
            try:
                await self._save_token(None)
            except Exception:
                raise OAuth2Error("Could not delete OAuth credentials.") from None

    async def close(self) -> None:
        """Disable authentication on plugin unload; retain persisted credentials."""
        async with self._lock:
            self._closed = True
            self._pending = None
            self._token = None

    async def _request_token(
        self, data: dict[str, str], previous: OAuth2Token | None = None
    ) -> OAuth2Token:
        """Exchange credentials without exposing server errors or following redirects.

        Args:
            data: Grant-specific form fields.
            previous: Previous token only when performing a refresh grant.

        Returns:
            Validated Bearer credentials.

        Raises:
            OAuth2Error: If transport, protocol or token validation fails.
        """
        try:
            async with self._http.stream(
                "POST",
                self._token_endpoint,
                data={**data, "client_id": self._client_id},
                headers={"Accept": "application/json"},
                follow_redirects=False,
                timeout=30,
            ) as response:
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise OAuth2Error("OAuth token response is too large.")
                payload = json.loads(body)
                if not isinstance(payload, Mapping):
                    raise OAuth2Error("Invalid OAuth token response.")
                if not response.is_success or "error" in payload:
                    if previous is not None and payload.get("error") == "invalid_grant":
                        self._token, self._loaded = None, True
                        await self._save_token(None)
                        raise OAuth2Error(
                            "OAuth authorization has expired; sign in again."
                        )
                    raise OAuth2Error("OAuth token request failed.")
                if str(payload.get("token_type", "")).lower() != "bearer":
                    raise OAuth2Error("OAuth server did not return a Bearer token.")
                expires_at = None
                if "expires_in" in payload:
                    expires_in = payload["expires_in"]
                    if isinstance(expires_in, bool):
                        raise ValueError
                    lifetime = float(expires_in)
                    if not math.isfinite(lifetime) or lifetime <= 0:
                        raise ValueError
                    expires_at = time.time() + lifetime
                return OAuth2Token(
                    access_token=payload.get("access_token"),
                    refresh_token=payload.get(
                        "refresh_token", previous.refresh_token if previous else None
                    ),
                    expires_at=expires_at,
                    scope=payload.get("scope", previous.scope if previous else None),
                )
        except OAuth2Error:
            raise
        except Exception:
            raise OAuth2Error("OAuth token request failed.") from None
