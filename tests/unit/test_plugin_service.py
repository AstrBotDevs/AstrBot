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
    assert payload["updates_enabled"] is True
    assert payload["update_disabled_reason"] == ""


def test_serialize_plugin_base_disables_updates_without_identity() -> None:
    plugin = SimpleNamespace(
        name="",
        repo="",
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

    assert payload["updates_enabled"] is False


@pytest.mark.asyncio
async def test_resolve_market_update_info_matches_default_market_without_source(
    monkeypatch,
) -> None:
    service = PluginService.__new__(PluginService)
    plugin = SimpleNamespace(
        name="astrbot_plugin_demo",
        root_dir_name="astrbot_plugin_demo",
        repo="https://github.com/AstrBotDevs/astrbot-plugin-demo",
        reserved=False,
    )
    saved = []

    async def fake_get_plugin_install_sources():
        return {}

    async def fake_get_online_plugins(*, custom_registry, force_refresh):
        assert custom_registry is None
        assert force_refresh is False
        return {
            "astrbot-plugin-demo": {
                "author": "AstrBotDevs",
                "repo": "https://github.com/AstrBotDevs/astrbot-plugin-demo",
                "download_url": "https://cdn.example/plugin.zip",
            }
        }, None

    async def fake_save_plugin_install_sources(records):
        saved.append(records)

    monkeypatch.setattr(service, "find_plugin_by_name", lambda name: plugin)
    monkeypatch.setattr(
        service,
        "get_plugin_install_sources",
        fake_get_plugin_install_sources,
    )
    monkeypatch.setattr(service, "get_online_plugins", fake_get_online_plugins)
    monkeypatch.setattr(
        service,
        "save_plugin_install_sources",
        fake_save_plugin_install_sources,
    )

    update_info = await service.resolve_market_update_info("astrbot_plugin_demo")

    assert update_info["record"] is None
    assert update_info["download_url"] == "https://cdn.example/plugin.zip"
    assert update_info["repo"] == "https://github.com/AstrBotDevs/astrbot-plugin-demo"
    assert saved == []


@pytest.mark.asyncio
async def test_resolve_market_update_info_without_source_or_market_match_errors(
    monkeypatch,
) -> None:
    from astrbot.dashboard.services.plugin_service import (
        PLUGIN_UPDATE_SOURCE_REQUIRED_MESSAGE,
    )

    service = PluginService.__new__(PluginService)
    plugin = SimpleNamespace(
        name="astrbot_plugin_demo",
        root_dir_name="astrbot_plugin_demo",
        repo="https://github.com/AstrBotDevs/astrbot-plugin-demo",
        reserved=False,
    )

    async def fake_get_plugin_install_sources():
        return {}

    async def fake_get_online_plugins(*, custom_registry, force_refresh):
        del custom_registry, force_refresh
        return {"$meta": {"schema_version": 1}}, None

    monkeypatch.setattr(service, "find_plugin_by_name", lambda name: plugin)
    monkeypatch.setattr(
        service,
        "get_plugin_install_sources",
        fake_get_plugin_install_sources,
    )
    monkeypatch.setattr(service, "get_online_plugins", fake_get_online_plugins)

    with pytest.raises(PluginServiceError) as exc_info:
        await service.resolve_market_update_info("astrbot_plugin_demo")

    assert exc_info.value.public_message == PLUGIN_UPDATE_SOURCE_REQUIRED_MESSAGE


_DEFAULT_MARKET_REPO = "https://github.com/example/plugin"


def _repo_only_market_plugin() -> SimpleNamespace:
    return SimpleNamespace(
        name="astrbot_plugin_demo",
        root_dir_name="astrbot_plugin_demo",
        repo="",
        reserved=False,
    )


def _repo_only_update_info() -> dict[str, object]:
    return {
        "record": None,
        "market_plugin": {
            "name": "astrbot_plugin_demo",
            "repo": _DEFAULT_MARKET_REPO,
        },
        "download_url": "",
        "repo": _DEFAULT_MARKET_REPO,
    }


@pytest.mark.asyncio
async def test_resolve_default_market_update_matches_name_with_repo_only_entry(
    monkeypatch,
) -> None:
    service = PluginService.__new__(PluginService)
    plugin = _repo_only_market_plugin()
    saved: list[object] = []

    async def fake_get_plugin_install_sources():
        return {}

    async def fake_get_online_plugins(*, custom_registry, force_refresh):
        assert custom_registry is None
        assert force_refresh is False
        return {
            "astrbot-plugin-demo": {
                "name": "astrbot_plugin_demo",
                "repo": _DEFAULT_MARKET_REPO,
            }
        }, None

    async def fake_save_plugin_install_sources(records):
        saved.append(records)

    monkeypatch.setattr(service, "find_plugin_by_name", lambda _name: plugin)
    monkeypatch.setattr(
        service,
        "get_plugin_install_sources",
        fake_get_plugin_install_sources,
    )
    monkeypatch.setattr(service, "get_online_plugins", fake_get_online_plugins)
    monkeypatch.setattr(
        service,
        "save_plugin_install_sources",
        fake_save_plugin_install_sources,
    )

    update_info = await service.resolve_market_update_info(plugin.name)

    assert update_info["record"] is None
    assert update_info["download_url"] == ""
    assert update_info["repo"] == _DEFAULT_MARKET_REPO
    assert saved == []


@pytest.mark.asyncio
async def test_update_plugin_passes_default_market_repo_to_lifecycle(
    monkeypatch,
) -> None:
    service = PluginService.__new__(PluginService)
    plugin = _repo_only_market_plugin()
    update_calls: list[dict[str, str]] = []
    reload_calls: list[str] = []
    refresh_calls: list[tuple[str, dict[str, object]]] = []
    sync_calls: list[bool] = []
    update_info = _repo_only_update_info()

    async def fake_update_plugin(
        plugin_name: str,
        proxy: str = "",
        download_url: str = "",
        repo_url: str = "",
    ) -> None:
        update_calls.append(
            {
                "plugin_name": plugin_name,
                "proxy": proxy,
                "download_url": download_url,
                "repo_url": repo_url,
            }
        )

    async def fake_reload(plugin_name: str) -> None:
        reload_calls.append(plugin_name)

    async def fake_refresh(plugin_name: str, info: dict[str, object]) -> None:
        refresh_calls.append((plugin_name, info))

    async def fake_sync() -> None:
        sync_calls.append(True)

    async def fake_resolve(_plugin_name: str):
        return update_info

    monkeypatch.setattr(service, "_ensure_not_demo", lambda: None)
    monkeypatch.setattr(service, "resolve_market_update_info", fake_resolve)
    service.plugin_lifecycle = SimpleNamespace(
        update_plugin=fake_update_plugin,
        reload=fake_reload,
    )
    monkeypatch.setattr(
        service,
        "refresh_plugin_install_source_after_update",
        fake_refresh,
    )
    monkeypatch.setattr(service, "sync_skills_after_plugin_change", fake_sync)

    await service.update_plugin({"name": plugin.name})

    assert update_calls == [
        {
            "plugin_name": plugin.name,
            "proxy": "",
            "download_url": "",
            "repo_url": _DEFAULT_MARKET_REPO,
        }
    ]
    assert reload_calls == [plugin.name]
    assert refresh_calls == [(plugin.name, update_info)]
    assert sync_calls == [True]


@pytest.mark.asyncio
async def test_update_all_plugins_passes_default_market_repo_to_lifecycle(
    monkeypatch,
) -> None:
    service = PluginService.__new__(PluginService)
    plugin = _repo_only_market_plugin()
    update_calls: list[dict[str, str]] = []

    async def fake_update_plugin(
        plugin_name: str,
        proxy: str = "",
        download_url: str = "",
        repo_url: str = "",
    ) -> None:
        update_calls.append(
            {
                "plugin_name": plugin_name,
                "proxy": proxy,
                "download_url": download_url,
                "repo_url": repo_url,
            }
        )

    async def fake_reload(_plugin_name: str) -> None:
        raise AssertionError("update_all_plugins should not reload here")

    async def fake_refresh(_plugin_name: str, _info: dict[str, object]) -> None:
        return None

    async def fake_sync() -> None:
        return None

    async def fake_resolve(_plugin_name: str):
        return _repo_only_update_info()

    monkeypatch.setattr(service, "_ensure_not_demo", lambda: None)
    monkeypatch.setattr(service, "resolve_market_update_info", fake_resolve)
    service.plugin_lifecycle = SimpleNamespace(
        update_plugin=fake_update_plugin,
        reload=fake_reload,
    )
    monkeypatch.setattr(
        service,
        "refresh_plugin_install_source_after_update",
        fake_refresh,
    )
    monkeypatch.setattr(service, "sync_skills_after_plugin_change", fake_sync)

    payload, message = await service.update_all_plugins({"names": [plugin.name]})

    assert message == "批量更新完成，全部成功。"
    assert payload["results"] == [
        {"name": plugin.name, "status": "ok", "message": "更新成功"}
    ]
    assert update_calls == [
        {
            "plugin_name": plugin.name,
            "proxy": "",
            "download_url": "",
            "repo_url": _DEFAULT_MARKET_REPO,
        }
    ]


@pytest.mark.asyncio
async def test_default_market_update_refresh_does_not_persist_when_record_is_none(
    monkeypatch,
) -> None:
    service = PluginService.__new__(PluginService)
    plugin = _repo_only_market_plugin()
    saved: list[object] = []

    async def fake_get_plugin_install_sources():
        return {}

    async def fake_save_plugin_install_sources(records):
        saved.append(records)

    monkeypatch.setattr(service, "find_plugin_by_name", lambda _name: plugin)
    monkeypatch.setattr(
        service,
        "get_plugin_install_sources",
        fake_get_plugin_install_sources,
    )
    monkeypatch.setattr(
        service,
        "save_plugin_install_sources",
        fake_save_plugin_install_sources,
    )

    await service.refresh_plugin_install_source_after_update(
        plugin.name,
        _repo_only_update_info(),
    )

    assert saved == []
