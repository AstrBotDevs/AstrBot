from astrbot.core.desktop_runtime import (
    DESKTOP_SESSION_SECRET_ENV,
    get_desktop_session_secret,
    is_desktop_session_auth_enabled,
    is_loopback_client_host,
    verify_desktop_session_secret,
)


def test_desktop_session_auth_requires_managed_backend(monkeypatch):
    monkeypatch.delenv("ASTRBOT_DESKTOP_MANAGED", raising=False)
    monkeypatch.setenv(DESKTOP_SESSION_SECRET_ENV, "a" * 64)

    assert get_desktop_session_secret() is None
    assert is_desktop_session_auth_enabled() is False


def test_desktop_session_auth_rejects_short_secret(monkeypatch):
    monkeypatch.setenv("ASTRBOT_DESKTOP_MANAGED", "1")
    monkeypatch.setenv(DESKTOP_SESSION_SECRET_ENV, "too-short")

    assert get_desktop_session_secret() is None
    assert is_desktop_session_auth_enabled() is False


def test_desktop_session_secret_only_matches_on_loopback(monkeypatch):
    secret = "desktop-session-secret-" * 2
    monkeypatch.setenv("ASTRBOT_DESKTOP_MANAGED", "1")
    monkeypatch.setenv(DESKTOP_SESSION_SECRET_ENV, secret)

    assert verify_desktop_session_secret(secret, "127.0.0.1") is True
    assert verify_desktop_session_secret(secret, "::1") is True
    assert verify_desktop_session_secret(secret, "::ffff:127.0.0.1") is True
    assert verify_desktop_session_secret("wrong" * 10, "127.0.0.1") is False
    assert verify_desktop_session_secret(secret, "192.168.1.10") is False


def test_loopback_client_host_rejects_names_and_unspecified_addresses():
    assert is_loopback_client_host("localhost") is False
    assert is_loopback_client_host("0.0.0.0") is False
    assert is_loopback_client_host("::") is False
    assert is_loopback_client_host(None) is False
