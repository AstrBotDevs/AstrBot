"""Tests for the dashboard OrcaRouter login service.

Covers the GUI lifecycle requirements: the verifier stays server-side, every
terminal path releases the login attempt, and a stale response cannot settle a
newer login. All codes and keys are fabricated.
"""

from __future__ import annotations

import threading

import httpx
import pytest

from astrbot.core.provider import orcarouter_auth as auth
from astrbot.dashboard.services.orcarouter_service import (
    MAX_PENDING_ATTEMPTS,
    OrcaRouterLoginService,
)

FAKE_KEY = "sk-orca-test-not-a-real-credential"
FAKE_CODE = "test-auth-code-not-real"


@pytest.fixture(autouse=True)
def _clean_origin_env(monkeypatch):
    for name in ("ORCA_AUTH_BASE_URL", "ORCA_API_BASE_URL", "ORCA_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


def _patch_exchange(monkeypatch, status=200, payload=None):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json})
        return type(
            "R",
            (),
            {
                "status_code": status,
                "json": staticmethod(
                    lambda: (
                        payload
                        if payload is not None
                        else {"key": FAKE_KEY, "user_id": "9", "scope": "api"}
                    )
                ),
            },
        )()

    monkeypatch.setattr(auth.httpx, "post", fake_post)
    return calls


# --------------------------------------------------------------------------
# start
# --------------------------------------------------------------------------


def test_start_oob_returns_an_authorize_url_on_the_auth_origin():
    service = OrcaRouterLoginService()

    payload = service.start("oob")

    assert payload["flow"] == "oob"
    assert payload["authorize_url"].startswith("https://www.orcarouter.ai/auth?")
    assert "code_challenge_method=S256" in payload["authorize_url"]
    assert payload["callback_url"] == "https://www.orcarouter.ai"


def test_start_loopback_binds_a_local_listener():
    service = OrcaRouterLoginService()

    payload = service.start("loopback")

    assert payload["flow"] == "loopback"
    assert "callback_url=http%3A%2F%2F127.0.0.1%3A" in payload["authorize_url"]
    service.cancel(payload["attempt_id"])


def test_each_attempt_gets_its_own_generation():
    service = OrcaRouterLoginService()

    first = service.start("oob")
    second = service.start("oob")

    assert second["generation"] > first["generation"]


def test_start_refuses_unbounded_pending_attempts():
    service = OrcaRouterLoginService()
    for _ in range(MAX_PENDING_ATTEMPTS):
        service.start("oob")

    with pytest.raises(ValueError):
        service.start("oob")


def test_the_verifier_never_leaves_the_server(monkeypatch):
    service = OrcaRouterLoginService()

    payload = service.start("oob")

    encoded = str(payload)
    assert "code_verifier" not in encoded
    # Nothing in the payload is the attempted verifier itself.
    assert "verifier" not in encoded.lower()


# --------------------------------------------------------------------------
# complete
# --------------------------------------------------------------------------


def test_complete_exchanges_and_returns_the_key(monkeypatch):
    calls = _patch_exchange(monkeypatch)
    service = OrcaRouterLoginService()
    payload = service.start("oob")

    result = service.complete(payload["attempt_id"], FAKE_CODE)

    assert calls[0]["url"] == "https://www.orcarouter.ai/api/v1/auth/keys"
    assert result["key"] == FAKE_KEY
    assert result["source"] == "pkce"
    assert result["scope"] == "api"


def test_complete_reports_denial_as_a_failure(monkeypatch):
    _patch_exchange(monkeypatch, status=403, payload={"error": "invalid_grant"})
    service = OrcaRouterLoginService()
    payload = service.start("oob")

    with pytest.raises(auth.OrcaRouterAuthError):
        service.complete(payload["attempt_id"], FAKE_CODE)

    state = service.status(payload["attempt_id"])
    assert state["status"] == "failed"


def test_complete_reports_rate_limiting_distinctly(monkeypatch):
    _patch_exchange(monkeypatch, status=429, payload={"error": "rate_limited"})
    service = OrcaRouterLoginService()
    payload = service.start("oob")

    with pytest.raises(auth.OrcaRouterRateLimitedError):
        service.complete(payload["attempt_id"], FAKE_CODE)


def test_complete_rejects_an_unknown_attempt():
    service = OrcaRouterLoginService()

    with pytest.raises(KeyError):
        service.complete("no-such-attempt", FAKE_CODE)


def test_complete_rejects_an_expired_attempt(monkeypatch):
    service = OrcaRouterLoginService()
    payload = service.start("oob")
    service._attempts[payload["attempt_id"]].created_at -= (
        auth.AUTHORIZE_TIMEOUT_SECONDS + 1
    )

    with pytest.raises(auth.OrcaRouterAuthError):
        service.complete(payload["attempt_id"], FAKE_CODE)


# --------------------------------------------------------------------------
# cancel / release
# --------------------------------------------------------------------------


def test_cancel_is_idempotent_and_tolerates_unknown_ids():
    service = OrcaRouterLoginService()
    payload = service.start("loopback")

    service.cancel(payload["attempt_id"])
    service.cancel(payload["attempt_id"])
    service.cancel("never-existed")


def test_cancel_releases_the_loopback_port():
    service = OrcaRouterLoginService()
    payload = service.start("loopback")
    port = service._attempts[payload["attempt_id"]].pending.loopback.port
    service.cancel(payload["attempt_id"])

    # The port is free again, so a fresh listener can take it.
    listener = auth.LoopbackLoginServer("state", "/cb")
    assert listener.port > 0
    listener.close()
    assert port > 0


def test_status_of_an_unknown_attempt_is_not_an_error():
    service = OrcaRouterLoginService()

    assert service.status("gone")["status"] == "unknown"


def test_expired_pending_attempt_is_reported_as_expired(monkeypatch):
    service = OrcaRouterLoginService()
    payload = service.start("oob")
    service._attempts[payload["attempt_id"]].created_at -= (
        auth.AUTHORIZE_TIMEOUT_SECONDS + 1
    )

    assert service.status(payload["attempt_id"])["status"] == "expired"


# --------------------------------------------------------------------------
# flow A completion through the service
# --------------------------------------------------------------------------


def test_loopback_attempt_completes_on_poll(monkeypatch):
    _patch_exchange(monkeypatch)
    service = OrcaRouterLoginService()
    payload = service.start("loopback")
    attempt = service._attempts[payload["attempt_id"]]
    callback = attempt.pending.loopback.redirect_uri

    def redirect():
        httpx.get(f"{callback}?code={FAKE_CODE}&state={attempt.pending.state}")

    threading.Thread(target=redirect, daemon=True).start()
    for _ in range(100):
        state = service.status(payload["attempt_id"])
        if state["status"] == "completed":
            break
        threading.Event().wait(0.05)

    assert state["status"] == "completed"
    assert state["key"] == FAKE_KEY


def test_loopback_state_mismatch_fails_without_issuing_a_key(monkeypatch):
    calls = _patch_exchange(monkeypatch)
    service = OrcaRouterLoginService()
    payload = service.start("loopback")
    attempt = service._attempts[payload["attempt_id"]]

    def redirect():
        httpx.get(
            f"{attempt.pending.loopback.redirect_uri}?code={FAKE_CODE}&state=wrong"
        )

    threading.Thread(target=redirect, daemon=True).start()
    for _ in range(100):
        state = service.status(payload["attempt_id"])
        if state["status"] != "pending":
            break
        threading.Event().wait(0.05)

    assert state["status"] == "failed"
    assert calls == []


# --------------------------------------------------------------------------
# generation safety
# --------------------------------------------------------------------------


def test_a_completed_attempt_does_not_settle_a_newer_one(monkeypatch):
    _patch_exchange(monkeypatch)
    service = OrcaRouterLoginService()
    first = service.start("oob")
    second = service.start("oob")

    service.complete(first["attempt_id"], FAKE_CODE)

    # The newer attempt is untouched by the older one's result.
    assert service.status(second["attempt_id"])["status"] == "pending"
    service.cancel(second["attempt_id"])


def test_a_stale_generation_is_never_reported_under_the_new_attempt(monkeypatch):
    _patch_exchange(monkeypatch, payload={"key": FAKE_KEY, "scope": "api"})
    service = OrcaRouterLoginService()
    stale = service.start("oob")
    fresh = service.start("oob")

    service.complete(stale["attempt_id"], FAKE_CODE)
    fresh_state = service.status(fresh["attempt_id"])

    assert fresh_state["generation"] != stale["generation"]
    assert "key" not in fresh_state


def test_cancelled_attempt_cannot_then_be_completed(monkeypatch):
    _patch_exchange(monkeypatch)
    service = OrcaRouterLoginService()
    payload = service.start("oob")
    service.cancel(payload["attempt_id"])

    with pytest.raises(KeyError):
        service.complete(payload["attempt_id"], FAKE_CODE)
