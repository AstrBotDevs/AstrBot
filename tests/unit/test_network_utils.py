"""Tests for network utility helpers."""

from astrbot.core.utils import network_utils


def test_sanitize_proxy_url_masks_password_credentials():
    proxy = "http://user:secret@127.0.0.1:1080"
    assert network_utils._sanitize_proxy_url(proxy) == "http://****@127.0.0.1:1080"


def test_sanitize_proxy_url_masks_username_only_credentials():
    proxy = "http://token@127.0.0.1:1080"
    assert network_utils._sanitize_proxy_url(proxy) == "http://****@127.0.0.1:1080"


def test_sanitize_proxy_url_masks_empty_password_credentials():
    proxy = "http://user:@127.0.0.1:1080"
    assert network_utils._sanitize_proxy_url(proxy) == "http://****@127.0.0.1:1080"


def test_is_socks_proxy_detects_supported_schemes():
    assert network_utils._is_socks_proxy("socks5://127.0.0.1:1080")
    assert network_utils._is_socks_proxy("socks4://127.0.0.1:1080")
    assert network_utils._is_socks_proxy("socks5h://127.0.0.1:1080")
    assert not network_utils._is_socks_proxy("http://127.0.0.1:1080")


def test_log_connection_failure_redacts_proxy_in_error_text(monkeypatch):
    proxy = "http://token@127.0.0.1:1080"
    captured = {}

    def fake_error(message: str):
        captured["message"] = message

    monkeypatch.setattr(network_utils.logger, "error", fake_error)

    network_utils.log_connection_failure(
        provider_label="OpenAI",
        error=RuntimeError(f"proxy connect failed: {proxy}"),
        proxy=proxy,
    )

    assert "http://token@127.0.0.1:1080" not in captured["message"]
    assert "http://****@127.0.0.1:1080" in captured["message"]
