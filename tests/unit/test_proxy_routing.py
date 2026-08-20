import pytest

from astrbot.core.utils.network_utils import create_proxy_client
from astrbot.core.utils.proxy_route import (
    ProxyRouteMode,
    redact_proxy_url,
    resolve_proxy_route,
    set_global_network_config,
)


@pytest.fixture(autouse=True)
def _reset_global_network_config():
    set_global_network_config(http_proxy="", no_proxy=[])
    yield
    set_global_network_config(http_proxy="", no_proxy=[])


def test_custom_uses_only_local_proxy() -> None:
    set_global_network_config(http_proxy="http://global.example:8080")
    route = resolve_proxy_route(
        local_config={
            "proxy_mode": "custom",
            "proxy_url": "http://custom.example:7890",
        }
    )
    assert route.mode is ProxyRouteMode.CUSTOM
    assert route.proxy_url == "http://custom.example:7890"
    assert route.trust_env is False


def test_inherit_uses_global_proxy() -> None:
    set_global_network_config(http_proxy="http://global.example:8080")
    route = resolve_proxy_route(local_config={"proxy_mode": "inherit"})
    assert route.mode is ProxyRouteMode.INHERIT
    assert route.proxy_url == "http://global.example:8080"
    assert route.trust_env is False


def test_direct_disables_proxy_and_env() -> None:
    set_global_network_config(http_proxy="http://global.example:8080")
    route = resolve_proxy_route(local_config={"proxy_mode": "direct"})
    assert route.mode is ProxyRouteMode.DIRECT
    assert route.proxy_url is None
    assert route.trust_env is False


def test_empty_global_proxy_does_not_inherit_process_env(
    monkeypatch,
) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://host-proxy.example:8080")
    set_global_network_config(http_proxy="", no_proxy=["localhost"])
    route = resolve_proxy_route(local_config={"proxy_mode": "inherit"})
    assert route.proxy_url is None
    assert route.trust_env is False


def test_no_proxy_bypasses_global_proxy() -> None:
    set_global_network_config(
        http_proxy="http://global.example:8080",
        no_proxy=["localhost", "10.*", "internal.example"],
    )
    route = resolve_proxy_route(
        local_config={"proxy_mode": "inherit"},
        destination_host="internal.example",
    )
    assert route.proxy_url is None


def test_proxy_credentials_are_redacted() -> None:
    redacted = redact_proxy_url("http://user:s3cret@proxy.example:8080")
    assert "s3cret" not in redacted
    route = resolve_proxy_route(
        local_config={
            "proxy_mode": "custom",
            "proxy_url": "http://user:s3cret@proxy.example:8080",
        }
    )
    assert "s3cret" not in route.display_proxy


@pytest.mark.asyncio
async def test_provider_types_create_direct_clients() -> None:
    set_global_network_config(http_proxy="http://global.example:8080")
    for label in ("Chat", "STT", "TTS", "Embedding", "Rerank"):
        route = resolve_proxy_route(
            local_config={"proxy_mode": "direct", "proxy_url": "http://unused:1"}
        )
        client = create_proxy_client(label, route=route)
        try:
            assert client.trust_env is False
        finally:
            await client.aclose()


def test_platform_discord_telegram_slack_share_route() -> None:
    set_global_network_config(http_proxy="http://global.example:8080")
    for platform in ("discord", "telegram", "slack"):
        route = resolve_proxy_route(
            local_config={"proxy_mode": "custom", "proxy_url": "http://p.example:1"}
        )
        assert route.proxy_url == "http://p.example:1"
        del platform
