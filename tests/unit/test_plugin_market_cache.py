from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import astrbot.dashboard.services.plugin_service as plugin_service
from astrbot.dashboard.services.plugin_service import (
    PluginService,
    PluginServiceError,
    RegistrySource,
)

PRIMARY = "https://registry.example/plugins"
MIRROR = "https://mirror.example/plugins.json"
MD5_URL = "https://registry.example/plugins-md5"


def _payload_bytes(payload) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _payload_md5(payload) -> str:
    return hashlib.md5(_payload_bytes(payload)).hexdigest()


class _FakeResponse:
    def __init__(self, status: int, payload, url: str | None = None) -> None:
        self.status = status
        self.url = url
        self._payload = payload

    async def read(self) -> bytes:
        return _payload_bytes(self._payload)

    async def json(self):
        return self._payload


class _FakeGet:
    def __init__(self, response: _FakeResponse, url: str) -> None:
        self._response = response
        self._url = url

    async def __aenter__(self) -> _FakeResponse:
        if self._response.url is None:
            self._response.url = self._url
        return self._response

    async def __aexit__(self, *_exc) -> bool:
        return False


class _FakeSession:
    responses: dict[str, _FakeResponse] = {}
    requested: list[str] = []

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_exc) -> bool:
        return False

    def get(self, url: str) -> _FakeGet:
        type(self).requested.append(url)
        return _FakeGet(type(self).responses[url], url)


class _NoDownloadSession:
    attempted: list[str] = []

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def __aenter__(self) -> _NoDownloadSession:
        return self

    async def __aexit__(self, *_exc) -> bool:
        return False

    def get(self, url: str) -> _FakeGet:
        type(self).attempted.append(url)
        raise AssertionError("a registry download was not expected")


@pytest.fixture(autouse=True)
def _fail_on_unexpected_download():
    _NoDownloadSession.attempted = []
    yield
    assert _NoDownloadSession.attempted == []


def _install_session(monkeypatch, responses: dict[str, _FakeResponse]) -> None:
    _FakeSession.responses = responses
    _FakeSession.requested = []
    monkeypatch.setattr(plugin_service.aiohttp, "ClientSession", _FakeSession)


def _forbid_downloads(monkeypatch) -> None:
    monkeypatch.setattr(plugin_service.aiohttp, "ClientSession", _NoDownloadSession)


def _make_service(tmp_path: Path, monkeypatch, fetch_md5: AsyncMock):
    service = PluginService(MagicMock(), MagicMock())
    source = RegistrySource(
        urls=[PRIMARY, MIRROR],
        cache_file=str(tmp_path / "plugins.json"),
        md5_url=MD5_URL,
    )
    monkeypatch.setattr(service, "build_registry_source", lambda _custom: source)
    monkeypatch.setattr(service, "fetch_remote_md5", fetch_md5)
    return service, source


def _save_cache(
    service: PluginService,
    source: RegistrySource,
    data,
    md5: str = "",
    source_index: int = 0,
    registry_id: str | None = None,
    timestamp: str | None = None,
) -> None:
    service.save_plugin_cache(
        source.cache_file,
        data,
        md5,
        registry_id=registry_id or service.registry_id(source),
        source_index=source_index,
        timestamp=timestamp or datetime.now().isoformat(),
    )


def _read_cache(source: RegistrySource) -> dict:
    return json.loads(Path(source.cache_file).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_primary_download_saves_md5_and_provenance(tmp_path, monkeypatch):
    payload = {"a/b": {"name": "b"}}
    payload_md5 = _payload_md5(payload)
    fetch_md5 = AsyncMock(return_value=payload_md5)
    service, source = _make_service(tmp_path, monkeypatch, fetch_md5)
    _install_session(monkeypatch, {PRIMARY: _FakeResponse(200, payload)})

    data, message = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )

    assert data == payload
    assert message is None
    cached = _read_cache(source)
    assert cached["md5"] == payload_md5
    assert cached["registry_id"] == service.registry_id(source)
    assert cached["source_index"] == 0
    assert _FakeSession.requested == [PRIMARY]


@pytest.mark.asyncio
async def test_mirror_download_stores_no_md5(tmp_path, monkeypatch):
    fetch_md5 = AsyncMock(return_value="md5-1")
    service, source = _make_service(tmp_path, monkeypatch, fetch_md5)
    payload = {"mirror": {"name": "m"}}
    _install_session(
        monkeypatch,
        {PRIMARY: _FakeResponse(502, {}), MIRROR: _FakeResponse(200, payload)},
    )

    data, _ = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )

    assert data == payload
    cached = _read_cache(source)
    assert cached["md5"] == ""
    assert cached["source_index"] == 1
    fetch_md5.assert_not_awaited()


@pytest.mark.asyncio
async def test_redirected_primary_is_cached_as_mirror(tmp_path, monkeypatch):
    fetch_md5 = AsyncMock(return_value="md5-1")
    service, source = _make_service(tmp_path, monkeypatch, fetch_md5)
    payload = {"redirected": {"name": "r"}}
    _install_session(
        monkeypatch,
        {PRIMARY: _FakeResponse(200, payload, url=MIRROR)},
    )

    data, _ = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )

    assert data == payload
    cached = _read_cache(source)
    assert cached["source_index"] == 1
    assert cached["md5"] == ""
    fetch_md5.assert_not_awaited()


@pytest.mark.asyncio
async def test_normal_load_serves_cache_when_md5_is_unavailable(tmp_path, monkeypatch):
    fetch_md5 = AsyncMock(return_value=None)
    service, source = _make_service(tmp_path, monkeypatch, fetch_md5)
    _save_cache(service, source, {"cached": {"name": "c"}}, "md5-1")
    _forbid_downloads(monkeypatch)

    data, message = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )

    assert data == {"cached": {"name": "c"}}
    assert message is None


@pytest.mark.asyncio
async def test_normal_load_downloads_when_md5_changed(tmp_path, monkeypatch):
    payload = {"fresh": {"name": "f"}}
    fetch_md5 = AsyncMock(return_value=_payload_md5(payload))
    service, source = _make_service(tmp_path, monkeypatch, fetch_md5)
    _save_cache(service, source, {"cached": {"name": "c"}}, "md5-1")
    _install_session(monkeypatch, {PRIMARY: _FakeResponse(200, payload)})

    data, message = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )

    assert data == payload
    assert message is None
    assert _read_cache(source)["md5"] == _payload_md5(payload)


@pytest.mark.asyncio
async def test_mirror_cache_serves_normal_load_while_primary_is_down(
    tmp_path, monkeypatch
):
    fetch_md5 = AsyncMock(return_value=None)
    service, source = _make_service(tmp_path, monkeypatch, fetch_md5)
    _save_cache(service, source, {"mirror": {}}, "", source_index=1)
    _forbid_downloads(monkeypatch)

    data, message = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )

    assert data == {"mirror": {}}
    assert message is None


@pytest.mark.asyncio
async def test_mirror_cache_is_refreshed_when_primary_recovers(tmp_path, monkeypatch):
    payload = {"fresh": {"name": "f"}}
    fetch_md5 = AsyncMock(return_value=_payload_md5(payload))
    service, source = _make_service(tmp_path, monkeypatch, fetch_md5)
    _save_cache(service, source, {"mirror": {}}, "", source_index=1)
    _install_session(monkeypatch, {PRIMARY: _FakeResponse(200, payload)})

    data, _ = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )

    assert data == payload
    assert _read_cache(source)["source_index"] == 0
    assert _read_cache(source)["md5"] == _payload_md5(payload)


@pytest.mark.asyncio
async def test_legacy_cache_without_provenance_is_rebuilt(tmp_path, monkeypatch):
    fetch_md5 = AsyncMock(return_value="md5-1")
    service, source = _make_service(tmp_path, monkeypatch, fetch_md5)
    Path(source.cache_file).write_text(
        json.dumps({"timestamp": "t", "data": {"legacy": {}}, "md5": "md5-1"}),
        encoding="utf-8",
    )
    payload = {"fresh": {"name": "f"}}
    _install_session(monkeypatch, {PRIMARY: _FakeResponse(200, payload)})

    data, message = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )

    assert data == payload
    assert message is None
    cached = _read_cache(source)
    assert cached["registry_id"] == service.registry_id(source)
    assert cached["source_index"] == 0


@pytest.mark.asyncio
async def test_cache_for_another_registry_is_rebuilt(tmp_path, monkeypatch):
    fetch_md5 = AsyncMock(return_value="md5-1")
    service, source = _make_service(tmp_path, monkeypatch, fetch_md5)
    _save_cache(
        service,
        source,
        {"other": {}},
        "md5-1",
        registry_id="0000000000000000",
    )
    payload = {"fresh": {"name": "f"}}
    _install_session(monkeypatch, {PRIMARY: _FakeResponse(200, payload)})

    data, _ = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )

    assert data == payload


@pytest.mark.asyncio
async def test_primary_cache_without_md5_is_rechecked_on_normal_load(
    tmp_path, monkeypatch
):
    payload = {"fresh": {"name": "f"}}
    fetch_md5 = AsyncMock(return_value=_payload_md5(payload))
    service, source = _make_service(tmp_path, monkeypatch, fetch_md5)
    _save_cache(service, source, {"cached": {"name": "c"}}, "")
    _install_session(monkeypatch, {PRIMARY: _FakeResponse(200, payload)})

    data, _ = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )

    assert data == payload
    assert _read_cache(source)["md5"] == _payload_md5(payload)


@pytest.mark.asyncio
async def test_market_cache_is_parsed_once_per_request(tmp_path, monkeypatch):
    fetch_md5 = AsyncMock(return_value="md5-1")
    service, source = _make_service(tmp_path, monkeypatch, fetch_md5)
    _save_cache(service, source, {"cached": {"name": "c"}}, "md5-1")
    _forbid_downloads(monkeypatch)

    calls: list[str] = []
    original = PluginService.load_plugin_cache_entry

    def counting_loader(cache_file: str):
        calls.append(cache_file)
        return original(cache_file)

    monkeypatch.setattr(
        PluginService,
        "load_plugin_cache_entry",
        staticmethod(counting_loader),
    )

    data, message = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )

    assert data == {"cached": {"name": "c"}}
    assert message is None
    assert calls == [source.cache_file]


@pytest.mark.asyncio
async def test_market_download_failure_without_cache_raises(tmp_path, monkeypatch):
    fetch_md5 = AsyncMock(return_value=None)
    service, _source = _make_service(tmp_path, monkeypatch, fetch_md5)
    _install_session(
        monkeypatch,
        {PRIMARY: _FakeResponse(502, {}), MIRROR: _FakeResponse(500, {})},
    )

    with pytest.raises(PluginServiceError):
        await service.get_online_plugins(
            custom_registry=None,
            force_refresh=False,
        )


@pytest.mark.asyncio
async def test_normal_load_serves_primary_cache_when_md5_is_unreadable(
    tmp_path, monkeypatch
):
    fetch_md5 = AsyncMock(return_value=None)
    service, source = _make_service(tmp_path, monkeypatch, fetch_md5)
    _save_cache(service, source, {"cached": {"name": "c"}}, "")
    _forbid_downloads(monkeypatch)

    data, message = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )

    assert data == {"cached": {"name": "c"}}
    assert message is None


@pytest.mark.asyncio
async def test_custom_registry_without_md5_serves_cache_on_normal_load(
    tmp_path, monkeypatch
):
    fetch_md5 = AsyncMock(return_value=None)
    service = PluginService(MagicMock(), MagicMock())
    custom_url = "https://example.com/registry.json"
    source = RegistrySource(
        urls=[custom_url],
        cache_file=str(tmp_path / "custom.json"),
        md5_url=None,
    )
    monkeypatch.setattr(service, "build_registry_source", lambda _custom: source)
    monkeypatch.setattr(service, "fetch_remote_md5", fetch_md5)
    _save_cache(service, source, {"cached": {"name": "c"}})
    _forbid_downloads(monkeypatch)

    data, message = await service.get_online_plugins(
        custom_registry=custom_url,
        force_refresh=False,
    )

    assert data == {"cached": {"name": "c"}}
    assert message is None


@pytest.mark.asyncio
async def test_fetch_remote_md5_treats_blank_value_as_missing():
    response = _FakeResponse(200, {"md5": ""})

    async def fake_get(*_args, **_kwargs):
        return None

    class _Session:
        def __init__(self, *_a, **_k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        def get(self, _url):
            class _Ctx:
                async def __aenter__(self_inner):
                    return response

                async def __aexit__(self_inner, *_exc):
                    return False

            return _Ctx()

    original = plugin_service.aiohttp.ClientSession
    plugin_service.aiohttp.ClientSession = _Session
    try:
        assert await PluginService.fetch_remote_md5(MD5_URL) is None
    finally:
        plugin_service.aiohttp.ClientSession = original


@pytest.mark.asyncio
async def test_fallback_returns_cache_when_all_downloads_fail(tmp_path, monkeypatch):
    fetch_md5 = AsyncMock(return_value="md5-2")
    service, source = _make_service(tmp_path, monkeypatch, fetch_md5)
    _save_cache(service, source, {"cached": {"name": "c"}}, "md5-1")
    _install_session(
        monkeypatch,
        {PRIMARY: _FakeResponse(502, {}), MIRROR: _FakeResponse(500, {})},
    )

    data, message = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )

    assert data == {"cached": {"name": "c"}}
    assert message == "使用缓存数据，可能不是最新版本"
    assert _FakeSession.requested == [PRIMARY, MIRROR]


@pytest.mark.asyncio
async def test_malformed_cache_file_is_ignored(tmp_path, monkeypatch):
    payload = {"fresh": {"name": "f"}}
    fetch_md5 = AsyncMock(return_value=_payload_md5(payload))
    service, source = _make_service(tmp_path, monkeypatch, fetch_md5)
    Path(source.cache_file).write_text("{not json", encoding="utf-8")
    _install_session(monkeypatch, {PRIMARY: _FakeResponse(200, payload)})

    data, message = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )

    assert data == payload
    assert message is None


def test_build_registry_source_marks_primary_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin_service, "get_astrbot_data_path", lambda: str(tmp_path))

    source = PluginService.build_registry_source(None)

    assert source.urls[0] == "https://api.soulter.top/astrbot/plugins"
    assert source.urls[1].startswith("https://github.com/AstrBotDevs/")
    assert source.md5_url == "https://api.soulter.top/astrbot/plugins-md5"
    assert source.cache_file.endswith("plugins.json")

    custom = PluginService.build_registry_source("https://example.com/registry.json")

    assert custom.urls == ["https://example.com/registry.json"]
    assert custom.md5_url == "https://example.com/registry-md5.json"
    assert "plugins_custom_" in custom.cache_file


@pytest.mark.asyncio
async def test_redirected_primary_to_unknown_host_is_cached_as_primary(
    tmp_path, monkeypatch
):
    payload = {"a/b": {"name": "b"}}
    payload_md5 = _payload_md5(payload)
    fetch_md5 = AsyncMock(return_value=payload_md5)
    service, source = _make_service(tmp_path, monkeypatch, fetch_md5)
    _install_session(
        monkeypatch,
        {PRIMARY: _FakeResponse(200, payload, url="https://cdn.example/plugins.json")},
    )

    data, _ = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )

    assert data == payload
    cached = _read_cache(source)
    assert cached["source_index"] == 0
    assert cached["md5"] == payload_md5

    _forbid_downloads(monkeypatch)
    again, message = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )
    assert again == payload
    assert message is None


@pytest.mark.asyncio
async def test_unverifiable_cache_expires(tmp_path, monkeypatch):
    fetch_md5 = AsyncMock(return_value=None)
    service, source = _make_service(tmp_path, monkeypatch, fetch_md5)
    expired = (datetime.now() - timedelta(hours=1)).isoformat()
    _save_cache(service, source, {"cached": {"name": "c"}}, "", timestamp=expired)
    payload = {"fresh": {"name": "f"}}
    _install_session(monkeypatch, {PRIMARY: _FakeResponse(200, payload)})

    data, _ = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )

    assert data == payload


@pytest.mark.asyncio
async def test_unverifiable_cache_with_offset_timestamp_is_served(
    tmp_path, monkeypatch
):
    fetch_md5 = AsyncMock(return_value=None)
    service, source = _make_service(tmp_path, monkeypatch, fetch_md5)
    recent = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    _save_cache(service, source, {"cached": {"name": "c"}}, "", timestamp=recent)
    _forbid_downloads(monkeypatch)

    data, message = await service.get_online_plugins(
        custom_registry=None,
        force_refresh=False,
    )

    assert data == {"cached": {"name": "c"}}
    assert message is None
