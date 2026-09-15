"""OrcaRouter credential acquisition.

OrcaRouter exposes two ways for a user to end up with the same ordinary
``sk-orca-…`` API key:

* :func:`api_key_credentials` — the user pastes a key they already have.
* :func:`start_oauth_login` / :func:`complete_oauth_login` — the user authorizes
  in a browser with OAuth 2.0 + PKCE (RFC 7636) and the program receives the key.

Both adapters return the same :class:`OrcaRouterCredentials`, so provider
inference and model discovery below this seam never learn where the key came
from.

Authentication and inference live on different public origins and are never
derived from one another:

* authorization + code exchange: ``https://www.orcarouter.ai``
* inference + model catalog: ``https://api.orcarouter.ai/v1``

A PKCE-issued key is a durable API key, not a refresh token. There is no
refresh grant to call; a ``401`` from the relay means the user must
re-authorize.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import os
import secrets
import threading
import time
import urllib.parse
from dataclasses import dataclass
from typing import Literal

import httpx

from astrbot import logger

DEFAULT_AUTH_BASE_URL = "https://www.orcarouter.ai"
DEFAULT_API_BASE_URL = "https://api.orcarouter.ai/v1"

AUTHORIZE_PATH = "/auth"
EXCHANGE_PATH = "/api/v1/auth/keys"

# OrcaRouter rejects anything else before a code is minted.
ALLOWED_SCOPES = ("api", "connector")
DEFAULT_SCOPE = "api"

# Auth codes are single-use with a 10 minute TTL.
AUTHORIZE_TIMEOUT_SECONDS = 600

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


class OrcaRouterAuthError(Exception):
    """Base class for every terminal OrcaRouter credential failure."""


class OrcaRouterDeniedError(OrcaRouterAuthError):
    """The user declined the authorization request."""


class OrcaRouterStateMismatchError(OrcaRouterAuthError):
    """The redirect carried a ``state`` this process did not issue."""


class OrcaRouterCodeError(OrcaRouterAuthError):
    """The auth code is unknown, expired, already used, or unmatched."""


class OrcaRouterRateLimitedError(OrcaRouterAuthError):
    """Too many PKCE keys were issued for this user in the last 24 hours."""


class OrcaRouterNetworkError(OrcaRouterAuthError):
    """The auth origin could not be reached or answered unusably."""


class OrcaRouterNeedsReauthError(OrcaRouterAuthError):
    """A stored credential was rejected and must be replaced by a new login."""


@dataclass
class OrcaRouterCredentials:
    """One usable OrcaRouter credential, whatever produced it."""

    key: str
    source: Literal["api_key", "pkce"]
    scope: str = DEFAULT_SCOPE
    user_id: str = ""

    def __post_init__(self) -> None:
        self.key = (self.key or "").strip()
        if not self.key:
            raise OrcaRouterAuthError("OrcaRouter API key is empty")
        self.scope = (self.scope or "").strip() or DEFAULT_SCOPE

    def __repr__(self) -> str:  # pragma: no cover - defensive
        return (
            f"OrcaRouterCredentials(source={self.source!r}, scope={self.scope!r}, "
            f"user_id={self.user_id!r}, key=<redacted>)"
        )

    __str__ = __repr__


def b64url(raw: bytes) -> str:
    """Encode ``raw`` as unpadded base64url.

    Args:
        raw: Bytes to encode.

    Returns:
        The unpadded base64url text.
    """
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def generate_verifier() -> str:
    """Create a fresh PKCE code verifier from a cryptographic RNG.

    Returns:
        A 43 character unpadded base64url string derived from 32 random bytes.
    """
    return b64url(secrets.token_bytes(32))


def generate_state() -> str:
    """Create a fresh opaque ``state`` value from a cryptographic RNG.

    Returns:
        A 43 character unpadded base64url string derived from 32 random bytes.
    """
    return b64url(secrets.token_bytes(32))


def code_challenge_for(verifier: str) -> str:
    """Derive the S256 challenge for ``verifier``.

    Args:
        verifier: The PKCE code verifier.

    Returns:
        ``base64url(sha256(verifier))`` without padding.
    """
    return b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def _is_loopback(host: str) -> bool:
    """Report whether ``host`` is a loopback address.

    Args:
        host: Hostname from a parsed origin.

    Returns:
        True when the host is localhost or a loopback literal.
    """
    return host.strip().lower() in _LOOPBACK_HOSTS


def _validate_origin(value: str, name: str) -> str:
    """Validate a configured OrcaRouter origin and normalise it.

    Remote origins must use HTTPS; plain HTTP is only tolerated for loopback
    development.

    Args:
        value: The configured origin.
        name: Environment/config variable name, used in the error message.

    Returns:
        The origin without a trailing slash.

    Raises:
        ValueError: The origin is missing, malformed, or insecure.
    """
    origin = (value or "").strip().rstrip("/")
    if not origin:
        raise ValueError(f"{name} is empty")
    parsed = urllib.parse.urlsplit(origin)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"{name} must be an absolute http(s) origin: {origin!r}")
    if parsed.scheme == "http" and not _is_loopback(parsed.hostname):
        raise ValueError(
            f"{name} must use https for non-loopback hosts (got {origin!r})"
        )
    return origin


def resolve_auth_base_url(explicit: str | None = None) -> str:
    """Resolve the origin used for authorization and code exchange.

    Precedence is explicit argument, then ``ORCA_AUTH_BASE_URL``, then the
    shared self-hosted ``ORCA_BASE_URL``, then the public default.

    Args:
        explicit: Operator-configured value from the provider config.

    Returns:
        The auth origin, without a trailing slash.

    Raises:
        ValueError: The resolved origin is insecure or malformed.
    """
    candidate = (
        explicit
        or os.environ.get("ORCA_AUTH_BASE_URL")
        or os.environ.get("ORCA_BASE_URL")
        or DEFAULT_AUTH_BASE_URL
    )
    return _validate_origin(candidate, "ORCA_AUTH_BASE_URL")


def resolve_api_base_url(explicit: str | None = None) -> str:
    """Resolve the origin used for inference and model discovery.

    Precedence is explicit argument, then ``ORCA_API_BASE_URL``, then the
    shared self-hosted ``ORCA_BASE_URL``, then the public default. This is
    deliberately independent of :func:`resolve_auth_base_url` — one public
    origin is never derived from the other.

    Args:
        explicit: Operator-configured value from the provider config.

    Returns:
        The API origin including the ``/v1`` suffix, without a trailing slash.

    Raises:
        ValueError: The resolved origin is insecure or malformed.
    """
    candidate = (
        explicit
        or os.environ.get("ORCA_API_BASE_URL")
        or os.environ.get("ORCA_BASE_URL")
        or DEFAULT_API_BASE_URL
    )
    origin = _validate_origin(candidate, "ORCA_API_BASE_URL")
    if not origin.endswith("/v1"):
        # The relay always speaks the OpenAI wire format under /v1. This only
        # ever normalises the *inference* base; the auth origin is resolved
        # separately and is never derived from this value.
        origin = f"{origin}/v1"
    return origin


def api_key_credentials(api_key: str) -> OrcaRouterCredentials:
    """Adapt a user-pasted API key into the shared credential shape.

    Args:
        api_key: The key the user pasted. Never logged.

    Returns:
        Credentials marked with ``source="api_key"``.

    Raises:
        OrcaRouterAuthError: The value is empty.
    """
    return OrcaRouterCredentials(key=api_key, source="api_key")


def build_authorize_url(
    *,
    auth_base_url: str,
    app_name: str,
    code_challenge: str,
    state: str,
    callback_url: str,
    scope: str = DEFAULT_SCOPE,
) -> str:
    """Build the consent-screen URL for an authorization attempt.

    The verifier is intentionally absent from the URL — only its S256 digest
    travels here.

    Args:
        auth_base_url: Origin hosting the consent screen.
        app_name: Label shown on the consent screen.
        code_challenge: ``base64url(sha256(verifier))``.
        state: Opaque CSRF value echoed back on redirect.
        callback_url: ``oob`` for the out-of-band flow, otherwise an absolute
            loopback redirect URL.
        scope: Requested scope; must be ``api`` or ``connector``.

    Returns:
        The absolute authorize URL.

    Raises:
        ValueError: The scope or callback URL is not acceptable.
    """
    if scope not in ALLOWED_SCOPES:
        raise ValueError(f"unsupported OrcaRouter scope: {scope!r}")
    if callback_url != "oob":
        parsed = urllib.parse.urlsplit(callback_url)
        if parsed.scheme == "http" and not _is_loopback(parsed.hostname or ""):
            raise ValueError("http callback_url is only allowed for loopback hosts")
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(f"invalid callback_url: {callback_url!r}")
        if parsed.username or parsed.password:
            raise ValueError("callback_url must not contain userinfo")
        if parsed.fragment:
            raise ValueError("callback_url must not contain a fragment")

    query = {
        "callback_url": callback_url,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "app_name": app_name,
        "scope": scope,
    }
    return f"{auth_base_url}{AUTHORIZE_PATH}?{urllib.parse.urlencode(query)}"


def exchange_code(
    *,
    auth_base_url: str,
    code: str,
    code_verifier: str,
    timeout: float = 30.0,
) -> OrcaRouterCredentials:
    """Exchange an auth code for a durable OrcaRouter API key.

    The verifier stays in this process and is sent only to the auth origin.

    Args:
        auth_base_url: Origin hosting the exchange endpoint.
        code: The one-time authorization code.
        code_verifier: The verifier generated for this attempt.
        timeout: Request timeout in seconds.

    Returns:
        Credentials marked with ``source="pkce"``.

    Raises:
        OrcaRouterCodeError: The code is unknown, expired, already used, or
            does not match the stored challenge.
        OrcaRouterRateLimitedError: The per-user PKCE key cap was reached.
        OrcaRouterNetworkError: The auth origin was unreachable or answered
            with an unusable body.
        OrcaRouterAuthError: Any other terminal failure.
    """
    url = f"{auth_base_url}{EXCHANGE_PATH}"
    payload = {
        "code": code,
        "code_verifier": code_verifier,
        "code_challenge_method": "S256",
    }

    try:
        response = httpx.post(url, json=payload, timeout=timeout)
    except httpx.HTTPError as exc:
        # Deliberately omit the request body: it carries the verifier.
        raise OrcaRouterNetworkError(
            f"could not reach the OrcaRouter auth origin: {type(exc).__name__}"
        ) from None

    if response.status_code == 200:
        try:
            data = response.json()
        except ValueError:
            raise OrcaRouterNetworkError(
                "OrcaRouter token endpoint returned a non-JSON body"
            ) from None
        if not isinstance(data, dict) or not data.get("key"):
            raise OrcaRouterNetworkError(
                "OrcaRouter token endpoint response did not contain a key"
            )
        granted_scope = str(data.get("scope") or DEFAULT_SCOPE)
        if granted_scope not in ALLOWED_SCOPES:
            raise OrcaRouterAuthError(
                f"OrcaRouter granted an unusable scope: {granted_scope!r}"
            )
        if granted_scope != DEFAULT_SCOPE:
            # The user's workspace role may permit less than we asked for.
            logger.warning(
                "OrcaRouter granted scope %r rather than %r; continuing with the "
                "granted scope",
                granted_scope,
                DEFAULT_SCOPE,
            )
        return OrcaRouterCredentials(
            key=str(data["key"]),
            source="pkce",
            scope=granted_scope,
            user_id=str(data.get("user_id") or ""),
        )

    if response.status_code == 400:
        raise OrcaRouterCodeError(
            "OrcaRouter rejected the code challenge method; the authorization "
            "attempt cannot be completed"
        )
    if response.status_code == 403:
        raise OrcaRouterCodeError(
            "The OrcaRouter authorization code is unknown, expired, already used, "
            "or does not match this login attempt"
        )
    if response.status_code == 429:
        raise OrcaRouterRateLimitedError(
            "OrcaRouter refused to issue another key for this account in the last "
            "24 hours; reuse the stored key or revoke the app first"
        )
    raise OrcaRouterAuthError(
        f"OrcaRouter token exchange failed with HTTP {response.status_code}"
    )


def classify_terminal_status(status_code: int) -> type[OrcaRouterAuthError] | None:
    """Map an inference HTTP status to a terminal credential failure.

    Only ``401`` is terminal. A PKCE-issued key is durable rather than
    refreshable, so a rejected credential means the user must authorize again —
    there is no refresh grant to attempt. Other statuses, including ``403``
    from content policy or ``429``, are ordinary request errors and must not
    touch credential state.

    Args:
        status_code: HTTP status returned by the inference relay.

    Returns:
        The error class to raise, or None when the status is not an
        authentication failure.
    """
    if status_code == 401:
        return OrcaRouterNeedsReauthError
    return None


class _LoopbackCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Serves the single OAuth redirect that Flow A waits for."""

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != self.server.callback_path:  # type: ignore[attr-defined]
            self.send_response(404)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(parsed.query)
        state = (params.get("state") or [""])[0]
        error = (params.get("error") or [""])[0]
        code = (params.get("code") or [""])[0]

        # The state check is the only thing standing between this listener and a
        # code another page dropped on it.
        if not secrets.compare_digest(state, self.server.expected_state):  # type: ignore[attr-defined]
            body = b"<p>Login could not be verified. You can close this tab.</p>"
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
            self.server.deliver(None, OrcaRouterStateMismatchError("state mismatch"))  # type: ignore[attr-defined]
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<p>Connected. You can close this tab.</p>"
            if not error
            else b"<p>Authorization was refused. You can close this tab.</p>"
        )

        if error:
            self.server.deliver(None, OrcaRouterDeniedError(error))  # type: ignore[attr-defined]
        else:
            self.server.deliver(code or None, None)  # type: ignore[attr-defined]

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib naming
        """Silence the default stderr access log."""
        return


class LoopbackLoginServer:
    """Flow A: a one-shot loopback redirect listener for a single attempt."""

    def __init__(self, expected_state: str, callback_path: str = "/cb") -> None:
        """Bind the listener before the browser is opened.

        Args:
            expected_state: The opaque ``state`` value this attempt issued.
            callback_path: Path the redirect must target.
        """
        self._server = http.server.HTTPServer(
            ("127.0.0.1", 0), _LoopbackCallbackHandler
        )
        self._server.callback_path = callback_path  # type: ignore[attr-defined]
        self._server.expected_state = expected_state  # type: ignore[attr-defined]
        self._server.deliver = self._deliver  # type: ignore[attr-defined]
        self._code: str | None = None
        self._error: OrcaRouterAuthError | None = None
        self._settled = threading.Event()
        self._settled_at: float | None = None
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def _deliver(self, code: str | None, error: OrcaRouterAuthError | None) -> None:
        """Record the redirect result and stop accepting connections."""
        if self._settled.is_set():
            return
        self._code, self._error = code, error
        self._settled_at = time.monotonic()
        self._settled.set()
        threading.Thread(target=self._server.shutdown, daemon=True).start()

    @property
    def settled(self) -> bool:
        """Report whether the redirect listener has received a result.

        Returns:
            True once the redirect arrived or the listener gave up.
        """
        return self._settled.is_set()

    @property
    def port(self) -> int:
        """Return the bound loopback port."""
        return int(self._server.server_address[1])

    @property
    def redirect_uri(self) -> str:
        """Return the absolute callback URL to hand to the consent screen."""
        return f"http://127.0.0.1:{self.port}/cb"

    def start(self) -> None:
        """Begin serving on a background thread."""
        self._thread.start()

    def wait_for_code(self, timeout: float = AUTHORIZE_TIMEOUT_SECONDS) -> str:
        """Block until the redirect arrives or the attempt expires.

        Args:
            timeout: Seconds to wait for the user to finish in the browser.

        Returns:
            The authorization code.

        Raises:
            OrcaRouterStateMismatchError: The redirect state did not match.
            OrcaRouterDeniedError: The user declined.
            OrcaRouterAuthError: The attempt timed out.
        """
        if not self._settled.wait(timeout):
            self.close()
            raise OrcaRouterAuthError(
                "OrcaRouter login timed out before the browser returned a code"
            )
        self.close()
        if self._error is not None:
            raise self._error
        if not self._code:
            raise OrcaRouterAuthError("OrcaRouter redirect did not include a code")
        return self._code

    def close(self) -> None:
        """Stop the listener and release the loopback port."""
        try:
            self._server.server_close()
        except OSError:  # pragma: no cover - already closed
            pass


class PendingLogin:
    """Server-side state for one in-flight authorization attempt.

    The verifier lives here and never leaves the process. ``generation`` is
    monotonically increasing so a late response from an abandoned attempt can
    never overwrite a newer login.
    """

    def __init__(self, app_name: str, scope: str = DEFAULT_SCOPE) -> None:
        """Create an attempt with a fresh verifier and state.

        Args:
            app_name: Label shown on the consent screen.
            scope: Requested scope, ``api`` or ``connector``.
        """
        self.generation = 0
        self.app_name = app_name
        self.scope = scope
        self.flow: Literal["loopback", "oob"] = "oob"
        self.verifier = generate_verifier()
        self.state = generate_state()
        self.created_at = time.monotonic()
        self.authorize_url = ""
        self.loopback: LoopbackLoginServer | None = None

    def start_oob(self, auth_base_url: str) -> str:
        """Prepare an out-of-band attempt and return its authorize URL.

        Args:
            auth_base_url: Origin hosting the consent screen.

        Returns:
            The absolute authorize URL to show or open.
        """
        self.flow = "oob"
        self.authorize_url = build_authorize_url(
            auth_base_url=auth_base_url,
            app_name=self.app_name,
            code_challenge=code_challenge_for(self.verifier),
            state=self.state,
            callback_url="oob",
            scope=self.scope,
        )
        return self.authorize_url

    def start_loopback(self, auth_base_url: str) -> str:
        """Prepare a loopback attempt and bind its listener.

        Args:
            auth_base_url: Origin hosting the consent screen.

        Returns:
            The absolute authorize URL to open.
        """
        self.flow = "loopback"
        self.loopback = LoopbackLoginServer(self.state)
        self.loopback.start()
        self.authorize_url = build_authorize_url(
            auth_base_url=auth_base_url,
            app_name=self.app_name,
            code_challenge=code_challenge_for(self.verifier),
            state=self.state,
            callback_url=self.loopback.redirect_uri,
            scope=self.scope,
        )
        return self.authorize_url

    def is_expired(self, ttl: float = AUTHORIZE_TIMEOUT_SECONDS) -> bool:
        """Report whether this attempt has outlived the auth code TTL.

        Args:
            ttl: Maximum attempt lifetime in seconds.

        Returns:
            True when the attempt should no longer be completed.
        """
        return (time.monotonic() - self.created_at) > ttl

    def close(self) -> None:
        """Release any listener held by this attempt."""
        if self.loopback is not None:
            self.loopback.close()
            self.loopback = None


def credentials_from_exchange(
    auth_base_url: str, code: str, pending: PendingLogin
) -> OrcaRouterCredentials:
    """Complete a pending attempt by exchanging its code.

    Args:
        auth_base_url: Origin hosting the exchange endpoint.
        code: The code the user supplied or the redirect delivered.
        pending: The attempt holding the matching verifier.

    Returns:
        The resulting credentials.

    Raises:
        OrcaRouterAuthError: The attempt expired or the exchange failed.
    """
    if pending.is_expired():
        raise OrcaRouterCodeError(
            "The OrcaRouter login attempt expired; start a new one"
        )
    return exchange_code(
        auth_base_url=auth_base_url,
        code=code,
        code_verifier=pending.verifier,
    )


def parse_authorize_redirect(query: str, expected_state: str) -> str:
    """Extract and validate an authorization code from a redirect query.

    Args:
        query: Raw query string from the redirect target.
        expected_state: The ``state`` this process issued.

    Returns:
        The authorization code.

    Raises:
        OrcaRouterStateMismatchError: The state did not match.
        OrcaRouterDeniedError: The redirect reported a denial.
        OrcaRouterAuthError: No code was present.
    """
    params = urllib.parse.parse_qs(query)
    state = (params.get("state") or [""])[0]
    if not secrets.compare_digest(state, expected_state):
        raise OrcaRouterStateMismatchError("state mismatch")
    error = (params.get("error") or [""])[0]
    if error:
        raise OrcaRouterDeniedError(error)
    code = (params.get("code") or [""])[0]
    if not code:
        raise OrcaRouterAuthError("OrcaRouter redirect did not include a code")
    return code


def redact_key(key: str) -> str:
    """Render a key safe for logs and UI.

    Args:
        key: The raw key.

    Returns:
        A masked form that keeps only a short prefix.
    """
    key = key or ""
    if len(key) <= 8:
        return "****"
    return f"{key[:8]}…{key[-4:]}"
