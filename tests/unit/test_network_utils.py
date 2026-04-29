"""Unit tests for astrbot.core.utils.network_utils.

Expands upon the existing 2 monkeypatch-based tests with comprehensive
coverage of is_connection_error, log_connection_failure, and
create_proxy_client edge cases.
"""

import os
import ssl
from unittest.mock import MagicMock, patch

import httpx
import pytest

from astrbot.core.utils import network_utils as network_utils_module
from astrbot.core.utils.network_utils import (
    create_proxy_client,
    is_connection_error,
    log_connection_failure,
)

# ---------------------------------------------------------------------------
# Existing tests (preserved verbatim)
# ---------------------------------------------------------------------------


def test_create_proxy_client_reuses_shared_ssl_context(
    monkeypatch: pytest.MonkeyPatch,
):
    captured_calls: list[dict] = []
    headers = {"X-Test-Header": "value"}

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            captured_calls.append(kwargs)

    monkeypatch.setattr(network_utils_module.httpx, "AsyncClient", _FakeAsyncClient)

    network_utils_module.create_proxy_client("OpenAI")
    network_utils_module.create_proxy_client("OpenAI", proxy="http://127.0.0.1:7890")
    network_utils_module.create_proxy_client("OpenAI", headers=headers)
    network_utils_module.create_proxy_client("OpenAI", proxy="")

    assert len(captured_calls) == 4
    assert "proxy" not in captured_calls[0]
    assert captured_calls[1]["proxy"] == "http://127.0.0.1:7890"
    assert captured_calls[2]["headers"] is headers
    assert "proxy" not in captured_calls[3]
    assert isinstance(captured_calls[0]["verify"], ssl.SSLContext)
    assert captured_calls[0]["verify"] is captured_calls[1]["verify"]
    assert captured_calls[1]["verify"] is captured_calls[2]["verify"]
    assert captured_calls[2]["verify"] is captured_calls[3]["verify"]


def test_create_proxy_client_allows_verify_override(
    monkeypatch: pytest.MonkeyPatch,
):
    captured_calls: list[dict] = []
    custom_verify = ssl.create_default_context()

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            captured_calls.append(kwargs)

    monkeypatch.setattr(network_utils_module.httpx, "AsyncClient", _FakeAsyncClient)

    network_utils_module.create_proxy_client("OpenAI", verify=custom_verify)

    assert len(captured_calls) == 1
    assert captured_calls[0]["verify"] is custom_verify


# ---------------------------------------------------------------------------
# is_connection_error
# ---------------------------------------------------------------------------


class TestIsConnectionError:
    def test_httpx_connect_error(self):
        assert is_connection_error(httpx.ConnectError("refused")) is True

    def test_httpx_timeout_errors(self):
        for exc_cls in (
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
        ):
            assert is_connection_error(exc_cls("timeout")) is True

    def test_httpx_network_errors(self):
        for exc_cls in (httpx.NetworkError, httpx.ProxyError, httpx.RequestError):
            assert is_connection_error(exc_cls("err")) is True

    def test_builtin_network_exceptions(self):
        for exc in (ConnectionError("conn"), TimeoutError("timeout"), OSError("os")):
            assert is_connection_error(exc) is True

    def test_non_network_exceptions_return_false(self):
        for exc in (
            ValueError("v"),
            TypeError("t"),
            RuntimeError("r"),
            BaseException(),
        ):
            assert is_connection_error(exc) is False

    def test_httpx_non_network_errors_return_false(self):
        request = httpx.Request("GET", "http://example.com")
        response = httpx.Response(200, request=request)
        for exc in (
            httpx.HTTPStatusError("err", request=request, response=response),
            httpx.InvalidURL("invalid"),
            httpx.DecodingError,
        ):
            instance = exc("msg") if isinstance(exc, type) else exc
            assert is_connection_error(instance) is False

    def test_cause_chain_unwraps_to_network_error(self):
        inner = httpx.ConnectError("inner")
        outer = ValueError("wrapper")
        outer.__cause__ = inner
        assert is_connection_error(outer) is True

    def test_cause_chain_no_network_error(self):
        inner = ValueError("inner")
        outer = RuntimeError("outer")
        outer.__cause__ = inner
        assert is_connection_error(outer) is False

    def test_self_cause_does_not_infinite_loop(self):
        exc = ValueError("self")
        exc.__cause__ = exc
        assert is_connection_error(exc) is False


# ---------------------------------------------------------------------------
# log_connection_failure
# ---------------------------------------------------------------------------


class TestLogConnectionFailure:
    @patch("astrbot.core.utils.network_utils.logger.error")
    def test_with_explicit_proxy(self, mock_log_error: MagicMock):
        log_connection_failure("GPT", Exception("fail"), proxy="http://proxy:8080")
        mock_log_error.assert_called_once()
        msg = mock_log_error.call_args[0][0]
        assert "GPT" in msg
        assert "http://proxy:8080" in msg
        assert "fail" in msg

    @patch("astrbot.core.utils.network_utils.logger.error")
    def test_without_proxy_falls_to_simple_message(self, mock_log_error: MagicMock):
        log_connection_failure("GPT", Exception("fail"))
        mock_log_error.assert_called_once()
        msg = mock_log_error.call_args[0][0]
        assert "网络连接失败" in msg
        assert "GPT" in msg

    @patch("astrbot.core.utils.network_utils.logger.error")
    @patch.dict(os.environ, {"http_proxy": "http://env-proxy:3128"}, clear=False)
    def test_falls_back_to_env_http_proxy(
        self, mock_log_error: MagicMock
    ):
        log_connection_failure("GPT", Exception("fail"))
        mock_log_error.assert_called_once()
        msg = mock_log_error.call_args[0][0]
        assert "http://env-proxy:3128" in msg

    @patch("astrbot.core.utils.network_utils.logger.error")
    @patch.dict(os.environ, {"https_proxy": "https://secure-proxy:8443"}, clear=False)
    def test_falls_back_to_env_https_proxy(
        self, mock_log_error: MagicMock
    ):
        log_connection_failure("GPT", Exception("fail"))
        mock_log_error.assert_called_once()
        msg = mock_log_error.call_args[0][0]
        assert "https://secure-proxy:8443" in msg

    @patch("astrbot.core.utils.network_utils.logger.error")
    def test_empty_proxy_string_uses_no_proxy_message(
        self, mock_log_error: MagicMock
    ):
        """Empty-string proxy should not trigger the proxy-specific log line."""
        with patch.dict(os.environ, {"http_proxy": "", "https_proxy": ""}):
            log_connection_failure("GPT", Exception("fail"), proxy="")
        mock_log_error.assert_called_once()
        msg = mock_log_error.call_args[0][0]
        assert "代理" not in msg

    @patch("astrbot.core.utils.network_utils.logger.error")
    def test_error_type_name_in_message(self, mock_log_error: MagicMock):
        log_connection_failure(
            "GPT", httpx.ConnectTimeout("upstream timed out")
        )
        mock_log_error.assert_called_once()
        msg = mock_log_error.call_args[0][0]
        assert "ConnectTimeout" in msg


# ---------------------------------------------------------------------------
# create_proxy_client
# ---------------------------------------------------------------------------


class TestCreateProxyClientIntegration:
    """Integration-style smoke tests against the real httpx.AsyncClient."""

    def test_returns_async_client_without_proxy(self):
        client = create_proxy_client("Test")
        assert isinstance(client, httpx.AsyncClient)
        client.aclose()

    def test_returns_async_client_with_proxy(self):
        client = create_proxy_client("Test", proxy="http://127.0.0.1:7890")
        assert isinstance(client, httpx.AsyncClient)
        client.aclose()

    def test_with_custom_headers(self):
        headers = {"Authorization": "Bearer token"}
        client = create_proxy_client("Test", headers=headers)
        assert isinstance(client, httpx.AsyncClient)
        client.aclose()

    def test_with_explicit_ssl_context(self):
        ctx = ssl.create_default_context()
        client = create_proxy_client("Test", verify=ctx)
        assert isinstance(client, httpx.AsyncClient)
        client.aclose()

    def test_with_verify_disabled(self):
        client = create_proxy_client("Test", verify=False)
        assert isinstance(client, httpx.AsyncClient)
        client.aclose()
