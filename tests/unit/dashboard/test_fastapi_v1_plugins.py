from __future__ import annotations

import pytest

from tests.unit.dashboard.fastapi_v1_support import *  # noqa: F403


@pytest.mark.asyncio
async def test_v1_plugins_accept_api_key(
    asgi_client: httpx.AsyncClient,
    fake_db: FakeDb,
):
    raw_key = "abk_fastapi_v1_plugin"
    fake_db.add_api_key(raw_key, scopes=["plugin"])

    response = await asgi_client.get(
        "/api/v1/plugins",
        headers={"X-API-Key": raw_key},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert [item["name"] for item in data["data"]] == ["astrbot_plugin_demo"]


@pytest.mark.asyncio
async def test_v1_plugin_enabled_patch_calls_service(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    response = await asgi_client.patch(
        "/api/v1/plugins/astrbot_plugin_demo/enabled",
        json={"enabled": False},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["message"] == "停用成功。"
    plugin = fake_core_lifecycle.catalogs.plugins.all()[0]
    assert plugin.activated is False


@pytest.mark.asyncio
async def test_v1_plugin_url_install_accepts_download_url(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    captured_payloads = []
    plugin_service = asgi_app.state.services.plugins

    async def fake_install_plugin(payload):
        captured_payloads.append(payload)
        if not payload.get("url"):
            raise RuntimeError("missing url")
        return {"name": "astrbot_plugin_demo"}, "安装成功。"

    monkeypatch.setattr(plugin_service, "install_plugin", fake_install_plugin)

    response = await asgi_client.post(
        "/api/v1/plugins/install/url",
        json={
            "url": "https://github.com/AstrBotDevs/astrbot-plugin-demo",
            "download_url": "https://cdn.example/plugin.zip",
            "ignore_version_check": True,
            "install_method": "market",
            "registry_url": "https://example.com/plugins.json",
            "market_plugin_id": "AstrBotDevs/astrbot-plugin-demo",
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert captured_payloads[0] == {
        "url": "https://github.com/AstrBotDevs/astrbot-plugin-demo",
        "download_url": "https://cdn.example/plugin.zip",
        "proxy": None,
        "ignore_version_check": True,
        "install_method": "market",
        "registry_url": "https://example.com/plugins.json",
        "market_plugin_id": "AstrBotDevs/astrbot-plugin-demo",
    }


@pytest.mark.asyncio
async def test_v1_plugin_install_routes_reject_wrong_fields_and_missing_body(
    asgi_client: httpx.AsyncClient,
):
    github_response = await asgi_client.post(
        "/api/v1/plugins/install/github",
        json={"url": "https://github.com/AstrBotDevs/astrbot-plugin-demo"},
        headers=_jwt_headers(),
    )
    url_response = await asgi_client.post(
        "/api/v1/plugins/install/url",
        json={"repository": "AstrBotDevs/astrbot-plugin-demo"},
        headers=_jwt_headers(),
    )
    missing_body_response = await asgi_client.post(
        "/api/v1/plugins/install/url",
        headers=_jwt_headers(),
    )

    assert github_response.status_code == 422
    assert url_response.status_code == 422
    assert missing_body_response.status_code == 422


@pytest.mark.asyncio
async def test_plugin_service_market_install_uses_registry_entry(
    asgi_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_service = asgi_app.state.services.plugins
    captured = {}

    async def fake_get_online_plugins(*, custom_registry, force_refresh):
        captured["registry_url"] = custom_registry
        captured["force_refresh"] = force_refresh
        return {
            "$meta": {
                "schema_version": 1,
                "name": "Test Market",
                "version": "2026.06.27",
            },
            "astrbot-plugin-demo": {
                "author": "AstrBotDevs",
                "repo": "https://github.com/AstrBotDevs/astrbot-plugin-demo",
                "download_url": "https://cdn.example/market-plugin.zip",
            },
        }, None

    async def fake_install_plugin(
        repo_url,
        proxy="",
        ignore_version_check=False,
        download_url="",
    ):
        captured["repo_url"] = repo_url
        captured["proxy"] = proxy
        captured["ignore_version_check"] = ignore_version_check
        captured["download_url"] = download_url
        return {"name": "astrbot_plugin_demo"}

    async def fake_persist_plugin_install_source(
        plugin_info,
        payload,
        *,
        install_method,
        repo_url,
        download_url,
    ):
        captured["persist_payload"] = payload
        captured["persist_install_method"] = install_method
        captured["persist_repo_url"] = repo_url
        captured["persist_download_url"] = download_url

    async def fake_sync_skills_after_plugin_change():
        captured["synced"] = True

    monkeypatch.setattr(
        "astrbot.dashboard.services.plugin_service.reject_unsafe_plugin_fetch",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(plugin_service, "get_online_plugins", fake_get_online_plugins)
    monkeypatch.setattr(
        plugin_service.plugin_lifecycle,
        "install_plugin",
        fake_install_plugin,
    )
    monkeypatch.setattr(
        plugin_service,
        "persist_plugin_install_source",
        fake_persist_plugin_install_source,
    )
    monkeypatch.setattr(
        plugin_service,
        "sync_skills_after_plugin_change",
        fake_sync_skills_after_plugin_change,
    )

    result, message = await plugin_service.install_plugin(
        {
            "url": "https://github.com/SomeoneElse/wrong-plugin",
            "download_url": "https://cdn.example/wrong-plugin.zip",
            "install_method": "market",
            "registry_url": "https://example.com/plugins.json",
            "market_plugin_id": "AstrBotDevs/astrbot-plugin-demo",
            "proxy": "https://proxy.example",
            "ignore_version_check": True,
        }
    )

    assert result == {"name": "astrbot_plugin_demo"}
    assert message == "安装成功。"
    assert captured["registry_url"] == "https://example.com/plugins.json"
    assert captured["force_refresh"] is False
    assert captured["repo_url"] == "https://github.com/AstrBotDevs/astrbot-plugin-demo"
    assert captured["download_url"] == "https://cdn.example/market-plugin.zip"
    assert captured["proxy"] == "https://proxy.example"
    assert captured["ignore_version_check"] is True
    assert captured["persist_install_method"] == "market"
    assert (
        captured["persist_repo_url"]
        == "https://github.com/AstrBotDevs/astrbot-plugin-demo"
    )
    assert captured["persist_download_url"] == "https://cdn.example/market-plugin.zip"
    assert (
        captured["persist_payload"]["registry_url"]
        == "https://example.com/plugins.json"
    )
    assert (
        captured["persist_payload"]["market_plugin_id"]
        == "AstrBotDevs/astrbot-plugin-demo"
    )
    assert captured["synced"] is True


@pytest.mark.asyncio
async def test_plugin_service_bind_market_source_validates_and_persists(
    asgi_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_service = asgi_app.state.services.plugins
    plugin = SimpleNamespace(
        name="astrbot_plugin_demo",
        root_dir_name="astrbot_plugin_demo",
        repo="https://github.com/AstrBotDevs/astrbot-plugin-demo",
    )
    captured = {}

    async def fake_get_online_plugins(*, custom_registry, force_refresh):
        captured["registry_url"] = custom_registry
        captured["force_refresh"] = force_refresh
        return {
            "$meta": {
                "schema_version": 1,
                "name": "Test Market",
                "version": "2026.06.27",
            },
            "astrbot-plugin-demo": {
                "author": "AstrBotDevs",
                "repo": "https://github.com/AstrBotDevs/astrbot-plugin-demo.git",
                "download_url": "https://cdn.example/plugin.zip",
            },
        }, None

    async def fake_get_plugin_install_sources():
        return {"astrbot_plugin_demo": {"installed_at": "2026-06-26T00:00:00+00:00"}}

    async def fake_save_plugin_install_sources(records):
        captured["records"] = records

    monkeypatch.setattr(plugin_service, "find_plugin_by_name", lambda name: plugin)
    monkeypatch.setattr(plugin_service, "get_online_plugins", fake_get_online_plugins)
    monkeypatch.setattr(
        plugin_service,
        "get_plugin_install_sources",
        fake_get_plugin_install_sources,
    )
    monkeypatch.setattr(
        plugin_service,
        "save_plugin_install_sources",
        fake_save_plugin_install_sources,
    )

    record, message = await plugin_service.bind_plugin_market_source(
        {
            "name": "astrbot_plugin_demo",
            "registry_url": "https://example.com/plugins.json",
            "market_plugin_id": "AstrBotDevs/astrbot-plugin-demo",
        }
    )

    assert message == "插件源已更新。"
    assert captured["registry_url"] == "https://example.com/plugins.json"
    assert captured["force_refresh"] is False
    assert record["install_method"] == "market"
    assert record["registry_url"] == "https://example.com/plugins.json"
    assert record["market_plugin_id"] == "AstrBotDevs/astrbot-plugin-demo"
    assert record["repo"] == "https://github.com/AstrBotDevs/astrbot-plugin-demo.git"
    assert record["download_url"] == "https://cdn.example/plugin.zip"
    assert record["installed_at"] == "2026-06-26T00:00:00+00:00"
    assert captured["records"]["astrbot_plugin_demo"] == record


@pytest.mark.asyncio
async def test_plugin_service_bind_repo_source_persists_github_method(
    asgi_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_service = asgi_app.state.services.plugins
    plugin = SimpleNamespace(
        name="astrbot_plugin_demo",
        root_dir_name="astrbot_plugin_demo",
        repo="https://github.com/AstrBotDevs/astrbot-plugin-demo",
    )
    captured = {}

    async def fake_get_plugin_install_sources():
        return {"astrbot_plugin_demo": {"installed_at": "2026-06-26T00:00:00+00:00"}}

    async def fake_save_plugin_install_sources(records):
        captured["records"] = records

    monkeypatch.setattr(plugin_service, "find_plugin_by_name", lambda name: plugin)
    monkeypatch.setattr(
        plugin_service,
        "get_plugin_install_sources",
        fake_get_plugin_install_sources,
    )
    monkeypatch.setattr(
        plugin_service,
        "save_plugin_install_sources",
        fake_save_plugin_install_sources,
    )

    record, message = await plugin_service.bind_plugin_market_source(
        {
            "name": "astrbot_plugin_demo",
            "install_method": "github",
        }
    )

    assert message == "插件源已更新。"
    assert record["install_method"] == "github"
    assert record["registry_url"] is None
    assert record["registry_name"] == "Repository"
    assert record["repo"] == "https://github.com/AstrBotDevs/astrbot-plugin-demo"
    assert record["installed_at"] == "2026-06-26T00:00:00+00:00"
    assert captured["records"]["astrbot_plugin_demo"] == record


@pytest.mark.asyncio
async def test_plugin_service_bind_market_source_rejects_repo_mismatch(
    asgi_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_service = asgi_app.state.services.plugins
    plugin = SimpleNamespace(
        name="astrbot_plugin_demo",
        root_dir_name="astrbot_plugin_demo",
        repo="https://github.com/AstrBotDevs/astrbot-plugin-demo",
    )

    async def fake_get_online_plugins(*, custom_registry, force_refresh):
        return {
            "$meta": {
                "schema_version": 1,
                "name": "Test Market",
                "version": "2026.06.27",
            },
            "astrbot-plugin-demo": {
                "author": "AstrBotDevs",
                "repo": "https://github.com/SomeoneElse/astrbot-plugin-demo",
            },
        }, None

    monkeypatch.setattr(plugin_service, "find_plugin_by_name", lambda name: plugin)
    monkeypatch.setattr(plugin_service, "get_online_plugins", fake_get_online_plugins)

    with pytest.raises(Exception) as exc_info:
        await plugin_service.bind_plugin_market_source(
            {
                "name": "astrbot_plugin_demo",
                "market_plugin_id": "AstrBotDevs/astrbot-plugin-demo",
            }
        )

    assert "插件仓库地址与所选插件源不一致" in str(exc_info.value)


def test_plugin_service_repo_identifier_accepts_github_url_without_scheme(
    asgi_app: FastAPI,
):
    plugin_service = asgi_app.state.services.plugins

    assert (
        plugin_service.repo_identifier_from_url("github.com/AstrBotDevs/demo.git")
        == "AstrBotDevs/demo"
    )


def test_plugin_service_resolves_market_entry_by_repo_identifier(
    asgi_app: FastAPI,
):
    plugin_service = asgi_app.state.services.plugins
    record = {
        "repo": "https://github.com/AstrBotDevs/astrbot-plugin-demo.git",
    }
    market_data = {
        "$meta": {"schema_version": 1},
        "astrbot-plugin-demo": {
            "author": "AstrBotDevs",
            "repo": "https://www.github.com/AstrBotDevs/astrbot-plugin-demo",
        },
    }

    entry = plugin_service.resolve_market_plugin_entry(market_data, record)

    assert entry is not None
    assert entry["author"] == "AstrBotDevs"
    assert entry["name"] == "astrbot-plugin-demo"
    assert entry["repo"] == "https://www.github.com/AstrBotDevs/astrbot-plugin-demo"


@pytest.mark.asyncio
async def test_plugin_service_persist_install_source_resolves_registry_before_read(
    asgi_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_service = asgi_app.state.services.plugins
    plugin = SimpleNamespace(
        name="astrbot_plugin_demo",
        root_dir_name="astrbot_plugin_demo",
        repo="https://github.com/AstrBotDevs/astrbot-plugin-demo",
    )
    events = []
    captured = {}

    async def fake_resolve_registry_name(registry_url):
        events.append(("resolve", registry_url))
        return "Custom"

    async def fake_get_plugin_install_sources():
        events.append(("get", None))
        return {}

    async def fake_save_plugin_install_sources(records):
        events.append(("save", None))
        captured["records"] = records

    monkeypatch.setattr(plugin_service, "find_plugin_by_name", lambda name: plugin)
    monkeypatch.setattr(
        plugin_service,
        "resolve_registry_name",
        fake_resolve_registry_name,
    )
    monkeypatch.setattr(
        plugin_service,
        "get_plugin_install_sources",
        fake_get_plugin_install_sources,
    )
    monkeypatch.setattr(
        plugin_service,
        "save_plugin_install_sources",
        fake_save_plugin_install_sources,
    )

    await plugin_service.persist_plugin_install_source(
        {"name": "astrbot_plugin_demo"},
        {
            "registry_url": "https://example.com/plugins.json",
            "install_method": "market",
            "market_plugin_id": "AstrBotDevs/astrbot-plugin-demo",
        },
        install_method="market",
        repo_url="https://github.com/AstrBotDevs/astrbot-plugin-demo",
        download_url="",
    )

    assert events == [
        ("resolve", "https://example.com/plugins.json"),
        ("get", None),
        ("save", None),
    ]
    record = captured["records"]["astrbot_plugin_demo"]
    assert record["registry_name"] == "Custom"


def test_plugin_service_missing_install_source_returns_none(
    asgi_app: FastAPI,
):
    plugin_service = asgi_app.state.services.plugins
    plugin = SimpleNamespace(
        name="astrbot_plugin_demo",
        root_dir_name="astrbot_plugin_demo",
        repo="https://github.com/AstrBotDevs/astrbot-plugin-demo",
        reserved=False,
    )

    record = plugin_service.resolve_effective_plugin_install_source(plugin, {})

    assert record is None


@pytest.mark.asyncio
async def test_plugin_service_update_missing_source_requires_selection(
    asgi_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_service = asgi_app.state.services.plugins
    plugin = SimpleNamespace(
        name="astrbot_plugin_demo",
        root_dir_name="astrbot_plugin_demo",
        repo="https://github.com/AstrBotDevs/astrbot-plugin-demo",
        reserved=False,
    )

    async def fake_get_plugin_install_sources():
        return {}

    monkeypatch.setattr(plugin_service, "find_plugin_by_name", lambda name: plugin)
    monkeypatch.setattr(
        plugin_service,
        "get_plugin_install_sources",
        fake_get_plugin_install_sources,
    )

    with pytest.raises(PluginServiceError) as exc_info:
        await plugin_service.resolve_market_update_info("astrbot_plugin_demo")

    assert exc_info.value.public_message == PLUGIN_UPDATE_SOURCE_REQUIRED_MESSAGE


@pytest.mark.asyncio
async def test_plugin_service_update_github_source_uses_plugin_repo(
    asgi_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_service = asgi_app.state.services.plugins
    plugin = SimpleNamespace(
        name="astrbot_plugin_demo",
        root_dir_name="astrbot_plugin_demo",
        repo="https://github.com/AstrBotDevs/astrbot-plugin-demo",
        reserved=False,
    )

    async def fake_get_plugin_install_sources():
        return {
            "astrbot_plugin_demo": {
                "install_method": "github",
                "repo": "https://github.com/AstrBotDevs/astrbot-plugin-demo",
            }
        }

    monkeypatch.setattr(plugin_service, "find_plugin_by_name", lambda name: plugin)
    monkeypatch.setattr(
        plugin_service,
        "get_plugin_install_sources",
        fake_get_plugin_install_sources,
    )

    update_info = await plugin_service.resolve_market_update_info("astrbot_plugin_demo")

    assert update_info["repo"] == "https://github.com/AstrBotDevs/astrbot-plugin-demo"
    assert update_info["download_url"] == ""
    assert update_info["record"]["install_method"] == "github"


@pytest.mark.asyncio
async def test_v1_plugin_update_all_hides_internal_exceptions(
    asgi_client: httpx.AsyncClient,
    asgi_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fail_update_resolution(_name: str):
        raise RuntimeError("internal update failure")

    monkeypatch.setattr(
        asgi_app.state.services.plugins,
        "resolve_market_update_info",
        fail_update_resolution,
    )

    response = await asgi_client.post(
        "/api/v1/plugins/update",
        json={"names": ["astrbot_plugin_demo"]},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    result = data["data"]["results"][0]
    assert result["status"] == "error"
    assert result["message"] == "更新失败，请查看服务端日志。"
    assert "AttributeError" not in str(data)
    assert "update_plugin" not in str(data)


@pytest.mark.asyncio
async def test_v1_plugin_update_all_rejects_legacy_plugin_ids_field(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.post(
        "/api/v1/plugins/update",
        json={"plugin_ids": ["astrbot_plugin_demo"]},
        headers=_jwt_headers(),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_save_upload_to_path_writes_starlette_upload(tmp_path: Path):
    from starlette.datastructures import UploadFile

    from astrbot.dashboard.upload_utils import save_upload_to_path

    source = SpooledTemporaryFile()
    source.write(b"upload-bytes")
    upload = UploadFile(file=source, filename="demo.txt")

    destination = tmp_path / "demo.txt"
    await save_upload_to_path(upload, destination)

    assert destination.read_bytes() == b"upload-bytes"


@pytest.mark.asyncio
async def test_v1_plugin_config_file_routes_reach_service_layer(
    asgi_client: httpx.AsyncClient,
):
    headers = _jwt_headers()

    list_response = await asgi_client.get(
        "/api/v1/plugins/astrbot_plugin_demo/config-files/assets",
        headers=headers,
    )
    upload_response = await asgi_client.post(
        "/api/v1/plugins/astrbot_plugin_demo/config-files/assets",
        json={"filename": "demo.txt"},
        headers=headers,
    )
    delete_response = await asgi_client.request(
        "DELETE",
        "/api/v1/plugins/astrbot_plugin_demo/config-files",
        json={"path": "demo.txt"},
        headers=headers,
    )

    assert list_response.status_code == 400
    assert list_response.json()["status"] == "error"
    assert upload_response.status_code == 400
    assert upload_response.json()["status"] == "error"
    assert delete_response.status_code == 400
    assert delete_response.json()["status"] == "error"


@pytest.mark.asyncio
async def test_v1_plugin_log_levels_are_scoped_to_the_live_catalog(
    asgi_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    from astrbot.core.log import LogManager

    monkeypatch.setattr(
        LogManager,
        "_plugin_log_levels_path",
        lambda: tmp_path / "plugin_log_levels.json",
    )
    monkeypatch.setattr(LogManager, "_plugin_level_overrides", {})
    monkeypatch.setattr(LogManager, "_plugin_logger_names", set())

    headers = _jwt_headers()
    updated = await asgi_client.put(
        "/api/v1/plugins/astrbot_plugin_demo/log-level",
        json={"level": "WARNING"},
        headers=headers,
    )
    config = await asgi_client.get(
        "/api/v1/plugins/astrbot_plugin_demo/config",
        headers=headers,
    )
    missing = await asgi_client.put(
        "/api/v1/plugins/not-live/log-level",
        json={"level": "INFO"},
        headers=headers,
    )

    assert updated.status_code == 200
    assert updated.json()["data"] == {"log_level": "WARNING"}
    assert config.status_code == 200
    assert config.json()["data"]["log_level"] == "WARNING"
    assert missing.status_code == 404
    assert missing.json()["message"] == "Plugin not found"


@pytest.mark.asyncio
async def test_v1_safe_plugin_routes_accept_slash_ids(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_id = "plugin/foo"
    headers = _jwt_headers()
    plugin_service = asgi_app.state.services.plugins
    config_display_service = asgi_app.state.services.config_display
    config_file_service = asgi_app.state.services.config_files

    async def fake_get_plugin_detail(**kwargs):
        return {"name": kwargs["plugin_name"]}

    async def fake_set_plugin_enabled(data, *, enabled: bool):
        return {"payload": {"name": data["name"], "enabled": enabled}}

    async def fake_update_plugin(data):
        return {"payload": data}

    def fake_get_plugin_readme(name: str):
        return {"name": name, "content": "readme"}, "ok"

    async def fake_get_configs(name: str):
        return {"schema": {"name": name}}

    def fake_list_config_files(*, scope: str, name: str, key_path: str):
        return {"scope": scope, "name": name, "key": key_path}

    monkeypatch.setattr(plugin_service, "get_plugin_detail", fake_get_plugin_detail)
    monkeypatch.setattr(plugin_service, "set_plugin_enabled", fake_set_plugin_enabled)
    monkeypatch.setattr(plugin_service, "update_plugin", fake_update_plugin)
    monkeypatch.setattr(plugin_service, "get_plugin_readme", fake_get_plugin_readme)
    monkeypatch.setattr(config_display_service, "get_configs", fake_get_configs)
    monkeypatch.setattr(
        config_file_service,
        "list_config_files",
        fake_list_config_files,
    )

    detail_response = await asgi_client.get(
        f"/api/v1/plugins/{plugin_id}",
        headers=headers,
    )
    enabled_response = await asgi_client.patch(
        f"/api/v1/plugins/{plugin_id}/enabled",
        json={"enabled": False},
        headers=headers,
    )
    update_response = await asgi_client.post(
        f"/api/v1/plugins/{plugin_id}/update",
        json={"proxy": "https://mirror.example"},
        headers=headers,
    )
    readme_response = await asgi_client.get(
        f"/api/v1/plugins/{plugin_id}/readme",
        headers=headers,
    )
    schema_response = await asgi_client.get(
        f"/api/v1/plugins/{plugin_id}/config/schema",
        headers=headers,
    )
    config_files_response = await asgi_client.get(
        f"/api/v1/plugins/{plugin_id}/config-files/assets%2Fpath",
        headers=headers,
    )

    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["name"] == plugin_id
    assert enabled_response.status_code == 200
    assert enabled_response.json()["data"]["payload"] == {
        "name": plugin_id,
        "enabled": False,
    }
    assert update_response.status_code == 200
    assert update_response.json()["data"]["payload"] == {
        "name": plugin_id,
        "proxy": "https://mirror.example",
    }
    assert readme_response.status_code == 200
    assert readme_response.json()["data"]["name"] == plugin_id
    assert schema_response.status_code == 200
    assert schema_response.json()["data"]["plugin_name"] == plugin_id
    assert config_files_response.status_code == 200
    assert config_files_response.json()["data"] == {
        "scope": "plugin",
        "name": plugin_id,
        "key": "assets/path",
    }


@pytest.mark.asyncio
async def test_v1_plugins_reject_legacy_plugin_id_query(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.get(
        "/api/v1/plugins",
        params={"plugin_id": "astrbot_plugin_demo"},
        headers=_jwt_headers(),
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_v1_plugin_source_delete_uses_path_ids(
    asgi_client: httpx.AsyncClient,
    asgi_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    source_id = "https://example.com/source"
    sources = [{"id": source_id}, {"id": "keep"}]

    async def fake_global_get(_key, _default=None):
        return list(sources)

    async def fake_global_put(_key, value):
        sources[:] = value

    preferences = asgi_app.state.services.plugins.preferences
    monkeypatch.setattr(preferences, "global_get", fake_global_get)
    monkeypatch.setattr(preferences, "global_put", fake_global_put)

    response = await asgi_client.delete(
        "/api/v1/plugin-sources/https:%2F%2Fexample.com%2Fsource",
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    assert response.json()["data"]["sources"] == [{"id": "keep"}]


@pytest.mark.asyncio
async def test_v1_command_patch_updates_service(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_toggle(command_id: str | None, enabled):
        return {
            "command_id": command_id,
            "enabled": enabled,
        }

    monkeypatch.setattr(
        asgi_app.state.services.commands,
        "toggle_command",
        fake_toggle,
    )

    response = await asgi_client.patch(
        "/api/v1/commands/demo:hello",
        json={"enabled": False},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"] == {
        "command_id": "demo:hello",
        "enabled": False,
    }


@pytest.mark.asyncio
async def test_v1_bot_type_registration_uses_platform_service(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_registration(platform_type: str, payload: dict):
        return {"platform_type": platform_type, "payload": payload}

    monkeypatch.setattr(
        asgi_app.state.services.platforms,
        "handle_platform_registration",
        fake_registration,
    )

    response = await asgi_client.post(
        "/api/v1/bot-types/webchat/registration",
        json={"registration_code": "abc123"},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"] == {
        "platform_type": "webchat",
        "payload": {"registration_code": "abc123"},
    }


@pytest.mark.asyncio
async def test_v1_token_file_is_public(
    asgi_client: httpx.AsyncClient,
    asgi_app: FastAPI,
    tmp_path: Path,
):
    token_file = tmp_path / "token-file.txt"
    token_file.write_text("token:demo-token", encoding="utf-8")
    file_token = await asgi_app.state.services.files.file_token_service.register_file(
        str(token_file), ttl_seconds=60
    )

    response = await asgi_client.get(f"/api/v1/files/tokens/{file_token}")

    assert response.status_code == 200
    assert response.text == "token:demo-token"
    assert response.headers["content-type"].startswith("text/plain")


def test_v1_openapi_websocket_routes_are_mounted(asgi_app):
    assert str(asgi_app.url_path_for("chat_ws")) == "/api/v1/chat/ws"
    assert str(asgi_app.url_path_for("live_chat_ws")) == "/api/v1/live-chat/ws"
    assert str(asgi_app.url_path_for("unified_chat_ws")) == "/api/v1/unified-chat/ws"
