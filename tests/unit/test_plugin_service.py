import ipaddress
import logging
from types import SimpleNamespace

import pytest

from astrbot.core.utils.outbound_http import (
    DEFAULT_PLUGIN_MARKET_URLS,
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


def test_default_registry_prefers_astrbot_cloud(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "astrbot.dashboard.services.plugin_service.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    source = PluginService.build_registry_source(None)
    assert source.urls == list(DEFAULT_PLUGIN_MARKET_URLS)
    assert source.urls[0] == "https://cloud.astrbot.app/api/v1/market/plugins.json"
    assert any(
        url.startswith("https://raw.githubusercontent.com/") for url in source.urls
    )
    assert any("jsdelivr.net" in url for url in source.urls)
    assert source.md5_url is None


@pytest.mark.asyncio
async def test_get_online_plugins_falls_back_after_non_json_source(
    monkeypatch,
    tmp_path,
    caplog,
) -> None:
    monkeypatch.setattr(
        "astrbot.dashboard.services.plugin_service.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    service = PluginService.__new__(PluginService)
    calls: list[str] = []

    async def fake_is_cache_valid(_source) -> bool:
        return False

    async def fake_fetch_json(url, policy, **kwargs):
        del policy, kwargs
        calls.append(url)
        if "cloud.astrbot.app" in url:
            raise OutboundRequestError("The remote response is not valid JSON.")
        if "raw.githubusercontent.com" in url:
            return {"demo-plugin": {"desc": "ok", "version": "1.0.0"}}
        raise AssertionError(url)

    async def fake_fetch_remote_md5(_md5_url):
        return None

    monkeypatch.setattr(service, "is_cache_valid", fake_is_cache_valid)
    monkeypatch.setattr(
        "astrbot.dashboard.services.plugin_service.fetch_json",
        fake_fetch_json,
    )
    monkeypatch.setattr(service, "fetch_remote_md5", fake_fetch_remote_md5)

    with caplog.at_level(logging.WARNING):
        data, message = await service.get_online_plugins(
            custom_registry=None,
            force_refresh=True,
        )

    assert message is None
    assert "demo-plugin" in data
    assert calls[0] == "https://cloud.astrbot.app/api/v1/market/plugins.json"
    assert calls[1].startswith("https://raw.githubusercontent.com/")
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


@pytest.mark.asyncio
async def test_default_registry_cache_ignores_soulter_md5(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "astrbot.dashboard.services.plugin_service.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    source = PluginService.build_registry_source(None)
    PluginService.save_plugin_cache(
        source.cache_file,
        {"demo-plugin": {"desc": "stale"}},
        md5="soulter-md5",
    )
    service = PluginService.__new__(PluginService)
    assert await service.is_cache_valid(source) is False


def test_serialize_plugin_base_uses_online_version_without_install_source() -> None:
    plugin = SimpleNamespace(
        name="astrbot_plugin_demo",
        repo="https://github.com/AstrBotDevs/astrbot-plugin-demo",
        author="demo",
        desc="demo plugin",
        version="1.0.0",
        reserved=False,
        activated=True,
        display_name="Demo",
        support_platforms=[],
        astrbot_version=None,
        i18n={},
        root_dir_name="astrbot_plugin_demo",
    )

    payload = PluginService.serialize_plugin_base(
        plugin,
        logo_url=None,
        installed_at=None,
        install_source=None,
    )

    assert "online_vesion" not in payload
    assert payload["online_version"] == ""
    assert payload["updates_enabled"] is False
