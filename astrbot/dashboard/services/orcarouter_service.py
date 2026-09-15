"""Server-side state for OrcaRouter "Connect with OrcaRouter" logins.

The dashboard is a browser UI, so the PKCE code verifier must stay on the
server: only the challenge, the authorize URL and the resulting API key ever
cross the wire. One in-flight attempt is tracked per attempt ID, and every
attempt carries a monotonically increasing generation so a late response from
an abandoned login can never overwrite a newer one.

Authorization codes are single-use with a 10 minute TTL, so attempts expire.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

from astrbot import logger
from astrbot.core.provider.orcarouter_auth import (
    AUTHORIZE_TIMEOUT_SECONDS,
    OrcaRouterAuthError,
    OrcaRouterCredentials,
    PendingLogin,
    credentials_from_exchange,
    resolve_auth_base_url,
)

#: Ceiling on concurrently tracked attempts, so an abusive client cannot pin
#: unbounded server state.
MAX_PENDING_ATTEMPTS = 32


@dataclass
class LoginAttempt:
    """One tracked OrcaRouter authorization attempt."""

    attempt_id: str
    generation: int
    pending: PendingLogin
    app_name: str
    flow: Literal["loopback", "oob"]
    authorize_url: str
    created_at: float = field(default_factory=time.monotonic)
    status: Literal["pending", "completed", "cancelled", "failed"] = "pending"
    error: str = ""
    error_type: type[OrcaRouterAuthError] | None = None
    credentials: OrcaRouterCredentials | None = None

    def is_expired(self) -> bool:
        """Report whether this attempt has outlived the auth code TTL.

        Returns:
            True when the attempt can no longer be completed.
        """
        return (time.monotonic() - self.created_at) > AUTHORIZE_TIMEOUT_SECONDS


class OrcaRouterLoginService:
    """Owns in-flight OrcaRouter authorization attempts for the dashboard."""

    def __init__(self) -> None:
        """Create an empty attempt registry."""
        self._attempts: dict[str, LoginAttempt] = {}
        self._generation = 0

    def _prune(self) -> None:
        """Drop expired attempts and settle abandoned listeners.

        Completed attempts are retained so the polling UI can collect the key,
        but not indefinitely: they age out like any other attempt.
        """
        now = time.monotonic()
        for attempt_id, attempt in list(self._attempts.items()):
            if attempt.status == "pending" and attempt.is_expired():
                attempt.pending.close()
                attempt.status = "failed"
                attempt.error = "The OrcaRouter login attempt expired"
            if attempt.status == "pending":
                continue
            if (now - attempt.created_at) > AUTHORIZE_TIMEOUT_SECONDS:
                attempt.pending.close()
                self._attempts.pop(attempt_id, None)

    def start(
        self, flow: Literal["loopback", "oob"], app_name: str = "AstrBot"
    ) -> dict:
        """Begin an authorization attempt and return what the UI needs.

        Args:
            flow: ``loopback`` for a local browser, ``oob`` when the browser
                runs somewhere that cannot reach this host's loopback.
            app_name: Label shown on the consent screen.

        Returns:
            A payload with the attempt ID, authorize URL and delivery mode.

        Raises:
            ValueError: Too many attempts are already in flight.
        """
        self._prune()
        if len(self._attempts) >= MAX_PENDING_ATTEMPTS:
            raise ValueError(
                "Too many OrcaRouter login attempts are in progress; finish or "
                "cancel one first"
            )

        auth_base_url = resolve_auth_base_url()
        self._generation += 1
        attempt_id = uuid.uuid4().hex
        pending = PendingLogin(app_name)
        pending.generation = self._generation
        authorize_url = (
            pending.start_loopback(auth_base_url)
            if flow == "loopback"
            else pending.start_oob(auth_base_url)
        )
        attempt = LoginAttempt(
            attempt_id=attempt_id,
            generation=self._generation,
            pending=pending,
            app_name=app_name,
            flow=flow,
            authorize_url=authorize_url,
        )
        self._attempts[attempt_id] = attempt
        logger.info(
            "OrcaRouter login attempt %s started (flow=%s, generation=%s); "
            "authorization origin is %s",
            attempt_id,
            flow,
            self._generation,
            auth_base_url,
        )
        return {
            "attempt_id": attempt_id,
            "generation": attempt.generation,
            "flow": flow,
            "authorize_url": authorize_url,
            "expires_in": AUTHORIZE_TIMEOUT_SECONDS,
            "callback_url": auth_base_url.rstrip("/"),
        }

    def status(self, attempt_id: str) -> dict:
        """Report the state of an attempt.

        A loopback attempt is settled by the redirect listener, so polling this
        endpoint is what completes it for a local browser.

        Args:
            attempt_id: The attempt to inspect.

        Returns:
            The attempt state; credentials are included only once complete.

        Raises:
            KeyError: The attempt is unknown or already pruned.
        """
        attempt = self._attempts.get(attempt_id)
        if attempt is None:
            return {"status": "unknown", "attempt_id": attempt_id}
        if attempt.is_expired() and attempt.status == "pending":
            self.cancel(attempt_id, reason="The OrcaRouter login attempt expired")
            return {"status": "expired", "attempt_id": attempt_id}

        if attempt.status == "pending" and attempt.flow == "loopback":
            self._settle_loopback(attempt)

        return self._snapshot(attempt)

    def _settle_loopback(self, attempt: LoginAttempt) -> None:
        """Complete a loopback attempt when its redirect has arrived.

        A refusal or a state mismatch is recorded on the attempt rather than
        raised at the poller: the redirect is answered by the listener, and an
        exception here would surface as a broken poll instead of a clear
        message in the login dialog.
        """
        listener = attempt.pending.loopback
        if listener is None or not listener.settled:
            return
        try:
            code = listener.wait_for_code(timeout=0.1)
        except OrcaRouterAuthError as exc:
            attempt.status = "failed"
            attempt.error = str(exc)
            attempt.error_type = type(exc)
            return
        self._finish(attempt, code)

    def _finish(self, attempt: LoginAttempt, code: str) -> None:
        """Exchange a delivered code and record the outcome.

        The attempt stays in the registry so the polling UI can pick the
        credential up; it ages out later rather than vanishing mid-poll.
        """
        try:
            credentials = credentials_from_exchange(
                resolve_auth_base_url(), code, attempt.pending
            )
        except OrcaRouterAuthError as exc:
            attempt.status = "failed"
            attempt.error = str(exc)
            attempt.error_type = type(exc)
            attempt.pending.close()
            return
        attempt.credentials = credentials
        attempt.status = "completed"
        attempt.pending.close()

    def complete(self, attempt_id: str, code: str) -> dict:
        """Finish an out-of-band attempt with a user-supplied code.

        Args:
            attempt_id: The attempt the code belongs to.
            code: The code the consent screen displayed.

        Returns:
            The credential payload.

        Raises:
            KeyError: The attempt is unknown.
            OrcaRouterAuthError: The attempt expired or the exchange failed.
        """
        attempt = self._attempts.get(attempt_id)
        if attempt is None:
            raise KeyError("OrcaRouter login attempt is unknown or already settled")
        if attempt.is_expired():
            self.cancel(attempt_id, reason="The OrcaRouter login attempt expired")
            raise OrcaRouterAuthError(
                "The OrcaRouter login attempt expired; start a new one"
            )
        if attempt.flow == "loopback":
            listener = attempt.pending.loopback
            if listener is not None and listener.settled:
                code = listener.wait_for_code(timeout=0.1)
        self._finish(attempt, code)
        if attempt.status != "completed":
            # Re-raise the specific failure so the caller can distinguish a
            # denial from rate limiting and render the right hint.
            raise (attempt.error_type or OrcaRouterAuthError)(
                attempt.error or "OrcaRouter login failed"
            )
        return self._credential_payload(attempt)

    def cancel(self, attempt_id: str, reason: str = "cancelled by the user") -> None:
        """Abandon an attempt and release its listener.

        Safe to call repeatedly and safe to call for an unknown ID, so a
        ``pagehide`` cancellation cannot fail the page.

        Args:
            attempt_id: The attempt to release.
            reason: Why the attempt was abandoned, for the log line only.
        """
        attempt = self._attempts.pop(attempt_id, None)
        if attempt is None:
            return
        attempt.pending.close()
        attempt.status = "cancelled"
        logger.info("OrcaRouter login attempt %s released (%s)", attempt_id, reason)

    def _snapshot(self, attempt: LoginAttempt) -> dict:
        """Render the pollable state of an attempt."""
        payload = {
            "attempt_id": attempt.attempt_id,
            "generation": attempt.generation,
            "status": attempt.status,
            "flow": attempt.flow,
            "authorize_url": attempt.authorize_url,
            "error": attempt.error,
        }
        if attempt.status == "completed":
            payload.update(self._credential_payload(attempt))
        return payload

    @staticmethod
    def _credential_payload(attempt: LoginAttempt) -> dict:
        """Render the credential payload for a completed attempt."""
        credentials = attempt.credentials
        if credentials is None:  # pragma: no cover - guarded by status
            return {}
        return {
            "key": credentials.key,
            "scope": credentials.scope,
            "user_id": credentials.user_id,
            "source": credentials.source,
        }
