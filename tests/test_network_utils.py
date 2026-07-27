"""Import smoke tests for astrbot.core.utils.network_utils."""

import ssl

import httpx

from astrbot.core.utils import network_utils as network_utils_module
from astrbot.core.utils.network_utils import (
    create_proxy_client,
    is_connection_error,
    log_connection_failure,
)


class TestImports:
    def test_module_importable(self):
        assert network_utils_module is not None

    def test_is_connection_error_callable(self):
        assert callable(is_connection_error)

    def test_log_connection_failure_callable(self):
        assert callable(log_connection_failure)

    def test_create_proxy_client_callable(self):
        assert callable(create_proxy_client)


class TestIsConnectionError:
    def test_returns_true_for_httpx_connect_error(self):
        assert is_connection_error(httpx.ConnectError("connection refused")) is True

    def test_returns_true_for_connect_timeout(self):
        assert is_connection_error(httpx.ConnectTimeout("timed out")) is True

    def test_returns_true_for_read_timeout(self):
        assert is_connection_error(httpx.ReadTimeout("read timed out")) is True

    def test_returns_true_for_write_timeout(self):
        assert is_connection_error(httpx.WriteTimeout("write timed out")) is True

    def test_returns_true_for_pool_timeout(self):
        assert is_connection_error(httpx.PoolTimeout("pool timed out")) is True

    def test_returns_true_for_network_error(self):
        assert is_connection_error(httpx.NetworkError("network error")) is True

    def test_returns_true_for_proxy_error(self):
        assert is_connection_error(httpx.ProxyError("proxy error")) is True

    def test_returns_true_for_generic_connection_error(self):
        assert is_connection_error(ConnectionError("connection error")) is True

    def test_returns_true_for_timeout_error(self):
        assert is_connection_error(TimeoutError("timeout")) is True

    def test_returns_true_for_os_error(self):
        assert is_connection_error(OSError("os error")) is True

    def test_returns_false_for_unrelated_exception(self):
        assert is_connection_error(ValueError("not a network error")) is False

    def test_returns_false_for_type_error(self):
        assert is_connection_error(TypeError("type error")) is False

    def test_returns_false_for_none(self):
        assert is_connection_error(BaseException()) is False

    def test_follows_cause_chain(self):
        inner = httpx.ConnectError("inner")
        outer = ValueError("wrapped")
        outer.__cause__ = inner
        assert is_connection_error(outer) is True

    def test_cause_chain_with_unrelated(self):
        inner = ValueError("inner")
        outer = httpx.ConnectError("outer")
        outer.__cause__ = inner
        assert is_connection_error(outer) is True


class TestLogConnectionFailure:
    def test_callable_with_all_args(self):
        log_connection_failure("TestProvider", Exception("fail"), proxy="http://proxy:8080")

    def test_callable_without_proxy(self):
        log_connection_failure("TestProvider", Exception("fail"))

    def test_callable_with_empty_proxy(self):
        log_connection_failure("TestProvider", Exception("fail"), proxy="")


class TestCreateProxyClient:
    def test_returns_async_client_without_proxy(self):
        client = create_proxy_client("TestProvider")
        assert isinstance(client, httpx.AsyncClient)
        client.aclose()

    def test_returns_async_client_with_proxy(self):
        client = create_proxy_client(
            "TestProvider",
            proxy="http://127.0.0.1:7890",
        )
        assert isinstance(client, httpx.AsyncClient)
        client.aclose()

    def test_returns_async_client_with_custom_headers(self):
        headers = {"X-Custom": "value"}
        client = create_proxy_client("TestProvider", headers=headers)
        assert isinstance(client, httpx.AsyncClient)
        client.aclose()

    def test_returns_async_client_with_ssl_context(self):
        ctx = ssl.create_default_context()
        client = create_proxy_client("TestProvider", verify=ctx)
        assert isinstance(client, httpx.AsyncClient)
        client.aclose()

    def test_returns_async_client_with_false_verify(self):
        client = create_proxy_client("TestProvider", verify=False)
        assert isinstance(client, httpx.AsyncClient)
        client.aclose()
