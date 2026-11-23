"""Network helpers classify failures and construct clients without remote I/O."""

import ssl
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from astrbot.core.utils import network_utils


@pytest.mark.parametrize(
    ("error_type", "expected"),
    [
        (httpx.ConnectError, True),
        (httpx.ConnectTimeout, True),
        (httpx.ReadTimeout, True),
        (httpx.WriteTimeout, True),
        (httpx.PoolTimeout, True),
        (httpx.NetworkError, True),
        (httpx.ProxyError, True),
        (ConnectionError, True),
        (TimeoutError, True),
        (OSError, True),
        (ValueError, False),
        (TypeError, False),
        (BaseException, False),
    ],
)
def test_error_types_determine_connection_classification(error_type, expected):
    assert network_utils.is_connection_error(error_type("failure")) is expected


@pytest.mark.parametrize("inner", [httpx.ConnectError("inner"), ValueError("ordinary")])
def test_exception_causes_are_classified(inner):
    outer = ValueError("wrapper")
    outer.__cause__ = inner
    assert network_utils.is_connection_error(outer) is isinstance(
        inner, httpx.ConnectError
    )
    network_outer = httpx.ConnectError("outer")
    network_outer.__cause__ = ValueError("non-network cause")
    assert network_utils.is_connection_error(network_outer) is True


@pytest.mark.parametrize(
    ("proxy", "environment", "effective"),
    [
        ("http://explicit:8080", "http://environment:8080", "http://explicit:8080"),
        (None, "http://environment:8080", "http://environment:8080"),
        ("", "", None),
    ],
)
def test_failure_log_reports_provider_error_and_selected_proxy(
    monkeypatch, proxy, environment, effective
):
    logger = Mock()
    monkeypatch.setattr(network_utils, "logger", logger)
    monkeypatch.setenv("http_proxy", environment)
    monkeypatch.setenv("https_proxy", "")
    network_utils.log_connection_failure(
        "Provider", TimeoutError("timed out"), proxy=proxy
    )
    if effective:
        expected = (
            "[Provider] Network or proxy connection failed (TimeoutError). "
            f"Proxy: {effective}; error: timed out"
        )
    else:
        expected = "[Provider] Network connection failed (TimeoutError): timed out"
    logger.error.assert_called_once_with(expected)


@pytest.mark.parametrize(
    "proxy", [None, "", "http://127.0.0.1:7890", "socks5://127.0.0.1:1080"]
)
@pytest.mark.parametrize("verify", [None, False, "custom-ca.pem"])
@pytest.mark.parametrize("factory_mode", ["legacy-module", "typed-factory"])
def test_client_factory_forwards_proxy_headers_and_tls_options(
    proxy, verify, factory_mode
):
    sentinel = object()
    constructor = Mock(return_value=sentinel)
    headers = {"X-Test": "value"}
    factory_options = (
        {"httpx_module": SimpleNamespace(AsyncClient=constructor)}
        if factory_mode == "legacy-module"
        else {"client_factory": constructor}
    )

    client = network_utils.create_proxy_client(
        "Provider",
        proxy=proxy,
        headers=headers,
        verify=verify,
        **factory_options,
    )

    assert client is sentinel
    options = {
        "headers": headers,
        "verify": network_utils._SYSTEM_SSL_CTX if verify is None else verify,
    }
    if proxy:
        options["proxy"] = proxy
    constructor.assert_called_once_with(**options)
    if verify is None:
        assert isinstance(options["verify"], ssl.SSLContext)


@pytest.mark.asyncio
async def test_real_client_preserves_headers_and_closes():
    async with network_utils.create_proxy_client(
        "Provider", headers={"X-Test": "value"}
    ) as client:
        assert client.headers["X-Test"] == "value"
        assert not client.is_closed
    assert client.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize("sdk_name", ["openai", "anthropic"])
async def test_sdk_client_factory_preserves_client_family_and_lifecycle(sdk_name):
    """SDK HTTP clients keep their own HTTPX family and close without remote I/O."""
    sdk = import_module(sdk_name)
    factory = sdk.DefaultAsyncHttpxClient
    client = network_utils.create_proxy_client(
        sdk_name, headers={"X-Test": "sdk-client"}, client_factory=factory
    )
    try:
        assert isinstance(client, factory)
        assert client.headers["X-Test"] == "sdk-client"
        assert not client.is_closed
    finally:
        await client.aclose()
    assert client.is_closed
