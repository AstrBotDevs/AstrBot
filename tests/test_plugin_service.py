import ipaddress

import pytest

from astrbot.core.utils.outbound_http import (
    OutboundRequestError,
    reject_unsafe_plugin_fetch,
)
from astrbot.dashboard.services.plugin_service import PluginService, PluginServiceError


def _public(*ips: str):
    return [ipaddress.ip_address(ip) for ip in ips]


def test_download_url_rejected_before_lifecycle() -> None:
    with pytest.raises(OutboundRequestError):
        reject_unsafe_plugin_fetch(download_url="file:///tmp/plugin.zip")
    with pytest.raises(OutboundRequestError):
        reject_unsafe_plugin_fetch(download_url="https://127.0.0.1/plugin.zip")


def test_mirror_rejected_before_updater() -> None:
    with pytest.raises(OutboundRequestError):
        reject_unsafe_plugin_fetch(proxy="http://mirror.example")
    with pytest.raises(OutboundRequestError):
        reject_unsafe_plugin_fetch(proxy="https://127.0.0.1")


@pytest.mark.asyncio
async def test_install_plugin_rejects_private_download_url(monkeypatch) -> None:
    service = PluginService.__new__(PluginService)
    service._ensure_not_demo = lambda: None
    called = False

    async def boom(*args, **kwargs):
        nonlocal called
        called = True

    service.plugin_lifecycle = SimpleLifecycle(boom)
    service.resolve_market_install_info = _async_none
    with pytest.raises(PluginServiceError):
        await service.install_plugin(
            {
                "url": "https://github.com/a/b",
                "download_url": "https://127.0.0.1/evil.zip",
            }
        )
    assert called is False


class SimpleLifecycle:
    def __init__(self, fn) -> None:
        self.install_plugin = fn


async def _async_none(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_ghproxy_and_plugin_mirror_share_the_same_origin_validator() -> None:
    from astrbot.core.utils.outbound_http import validate_github_mirror_origin
    from astrbot.dashboard.services.stat_service import StatService, StatServiceError

    with pytest.raises(Exception):
        validate_github_mirror_origin("https://127.0.0.1")

    service = StatService.__new__(StatService)
    with pytest.raises(StatServiceError, match="镜像测试失败"):
        await service.test_ghproxy_connection("https://127.0.0.1")
