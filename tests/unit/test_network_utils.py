"""Tests for network utility helpers."""

import builtins

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


def test_sanitize_proxy_url_returns_original_when_no_credentials():
    proxy = "http://127.0.0.1:1080"
    assert network_utils._sanitize_proxy_url(proxy) == proxy


def test_sanitize_proxy_url_returns_original_for_non_url_text():
    proxy = "not a url"
    assert network_utils._sanitize_proxy_url(proxy) == proxy


def test_sanitize_proxy_url_returns_original_for_empty_string():
    assert network_utils._sanitize_proxy_url("") == ""


def test_sanitize_proxy_url_masks_credentials_for_ipv6_host():
    proxy = "http://user:secret@[::1]:1080"
    assert network_utils._sanitize_proxy_url(proxy) == "http://****@[::1]:1080"


def test_sanitize_proxy_url_falls_back_to_placeholder_on_parse_error(monkeypatch):
    proxy = "http://user:secret@127.0.0.1:1080"
    original_import = builtins.__import__

    def guarded_import(name, globals_=None, locals_=None, fromlist=(), level=0):
        if name == "urllib.parse":
            raise ImportError("boom")
        return original_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    assert network_utils._sanitize_proxy_url(proxy) == "****"


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


def test_log_connection_failure_without_proxy_does_not_log_proxy_label(monkeypatch):
    captured = {}

    def fake_error(message: str):
        captured["message"] = message

    monkeypatch.setattr(network_utils.logger, "error", fake_error)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)

    network_utils.log_connection_failure(
        provider_label="OpenAI",
        error=RuntimeError("connection failed"),
        proxy=None,
    )

    assert "代理地址" not in captured["message"]
    assert "connection failed" in captured["message"]


def test_log_connection_failure_keeps_error_text_when_no_proxy_text(monkeypatch):
    proxy = "http://token@127.0.0.1:1080"
    captured = {}

    def fake_error(message: str):
        captured["message"] = message

    monkeypatch.setattr(network_utils.logger, "error", fake_error)

    network_utils.log_connection_failure(
        provider_label="OpenAI",
        error=RuntimeError("connect timeout"),
        proxy=proxy,
    )

    assert "http://****@127.0.0.1:1080" in captured["message"]
    assert "connect timeout" in captured["message"]
