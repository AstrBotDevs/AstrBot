from __future__ import annotations

import pytest

from tests.unit.dashboard.dashboard_lifecycle_support import *  # noqa: F403


@pytest.mark.asyncio
async def test_get_stat(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = DashboardTestClient(app)
    response = await test_client.get("/api/v1/stats")
    assert response.status_code == 401
    await core_lifecycle_td.db.insert_platform_stats(
        "test-platform",
        "test",
        count=3,
        timestamp=datetime.now(),
    )
    response = await test_client.get("/api/v1/stats", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok" and "platform" in data["data"]
    assert data["data"]["message_count"] >= 3
    assert any(
        item["name"] == "test-platform" and item["count"] >= 3
        for item in data["data"]["platform"]
    )


@pytest.mark.asyncio
async def test_get_t2i_runtime_stats_requires_system_scope(
    app: FastAPI,
    authenticated_header: dict,
):
    test_client = DashboardTestClient(app)

    unauthorized = await test_client.get("/api/v1/stats/t2i")
    response = await test_client.get(
        "/api/v1/stats/t2i",
        headers=authenticated_header,
    )
    data = await response.get_json()

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert data["status"] == "ok"
    assert data["data"]["successful_renders"] >= 0
    assert data["data"]["active_pages"] >= 0


@pytest.mark.asyncio
async def test_dashboard_ssl_missing_cert_and_key_falls_back_to_http(
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    shutdown_event = asyncio.Event()
    server = await AstrBotDashboard.create(
        core_lifecycle_td.runtime,
        core_lifecycle_td,
        core_lifecycle_td.db,
        shutdown_event,
    )
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config.get("dashboard", {}),
    )
    warning_messages = []
    info_messages = []

    async def fake_serve(app, config, shutdown_trigger):
        return config

    def capture(messages):
        def append(message, *args):
            messages.append(message % args if args else message)

        return append

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["ssl"] = {
            "enable": True,
            "cert_file": "",
            "key_file": "",
        }
        monkeypatch.setattr(server, "check_port_in_use", lambda port: False)
        monkeypatch.setattr("astrbot.dashboard.server.serve", fake_serve)
        monkeypatch.setattr(
            "astrbot.dashboard.server.logger.warning",
            capture(warning_messages),
        )
        monkeypatch.setattr(
            "astrbot.dashboard.server.logger.info",
            capture(info_messages),
        )

        config = await server.run()

        assert getattr(config, "certfile", None) is None
        assert getattr(config, "keyfile", None) is None
        assert any(
            "cert_file or key_file is missing" in message
            for message in warning_messages
        )
        assert any("Starting WebUI at http://" in message for message in info_messages)
    finally:
        core_lifecycle_td.astrbot_config["dashboard"] = original_dashboard_config


@pytest.mark.asyncio
async def test_subagent_config_accepts_default_persona(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = DashboardTestClient(app)
    old_cfg = copy.deepcopy(
        core_lifecycle_td.astrbot_config.get("subagent_orchestrator", {})
    )
    payload = {
        "main_enable": True,
        "remove_main_duplicate_tools": True,
        "agents": [
            {
                "name": "planner",
                "persona_id": "default",
                "public_description": "planner",
                "system_prompt": "",
                "enabled": True,
            }
        ],
    }

    try:
        response = await test_client.put(
            "/api/v1/subagents/config",
            json=payload,
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"

        get_response = await test_client.get(
            "/api/v1/subagents/config", headers=authenticated_header
        )
        assert get_response.status_code == 200
        get_data = await get_response.get_json()
        assert get_data["status"] == "ok"
        assert get_data["data"]["agents"][0]["persona_id"] == "default"
    finally:
        await test_client.put(
            "/api/v1/subagents/config",
            json=old_cfg,
            headers=authenticated_header,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [[], "x"])
async def test_batch_delete_sessions_rejects_non_object_payload(
    app: FastAPI, authenticated_header: dict, payload
):
    test_client = DashboardTestClient(app)
    response = await test_client.post(
        "/api/v1/chat/sessions/batch-delete",
        json=payload,
        headers=authenticated_header,
    )

    assert response.status_code == 422
    data = await response.get_json()
    assert data == {"status": "error", "message": "Invalid request payload"}


@pytest.mark.asyncio
async def test_batch_delete_sessions_masks_internal_error(
    app: FastAPI, authenticated_header: dict, monkeypatch
):
    test_client = DashboardTestClient(app)

    create_session_response = await test_client.get(
        "/api/v1/chat/sessions/new", headers=authenticated_header
    )
    assert create_session_response.status_code == 200
    create_session_data = await create_session_response.get_json()
    session_id = create_session_data["data"]["session_id"]

    async def _raise_error(*args, **kwargs):
        raise RuntimeError("secret-internal-error")

    monkeypatch.setattr(
        "astrbot.dashboard.services.chat_service.ChatService.delete_session_internal",
        _raise_error,
    )

    response = await test_client.post(
        "/api/v1/chat/sessions/batch-delete",
        json={"session_ids": [session_id]},
        headers=authenticated_header,
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["deleted_count"] == 0
    assert data["data"]["failed_count"] == 1
    assert data["data"]["failed_items"][0]["session_id"] == session_id
    assert data["data"]["failed_items"][0]["reason"] == "internal_error"


@pytest.mark.asyncio
async def test_batch_delete_sessions_uses_batch_lookup(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    test_client = DashboardTestClient(app)
    db = core_lifecycle_td.db

    create_session_response = await test_client.get(
        "/api/v1/chat/sessions/new", headers=authenticated_header
    )
    assert create_session_response.status_code == 200
    create_session_data = await create_session_response.get_json()
    session_id = create_session_data["data"]["session_id"]

    original_batch_lookup = db.get_platform_sessions_by_ids
    called = {"batch_lookup_count": 0}

    async def _wrapped_batch_lookup(session_ids: list[str]):
        called["batch_lookup_count"] += 1
        return await original_batch_lookup(session_ids)

    # Ensure the optimized batch lookup path is used.
    async def _should_not_call_single_lookup(session_id: str):
        raise AssertionError(
            f"single-session lookup should not be called: {session_id}"
        )

    monkeypatch.setattr(db, "get_platform_sessions_by_ids", _wrapped_batch_lookup)
    monkeypatch.setattr(
        db, "get_platform_session_by_id", _should_not_call_single_lookup
    )

    response = await test_client.post(
        "/api/v1/chat/sessions/batch-delete",
        json={"session_ids": [session_id]},
        headers=authenticated_header,
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["deleted_count"] == 1
    assert data["data"]["failed_count"] == 0
    assert called["batch_lookup_count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path_template", "expected_status", "expected_message"),
    [
        ("/api/chat/get_session?session_id={session_id}", 404, None),
        ("/api/v1/chat/sessions/{session_id}", 200, "Permission denied"),
    ],
)
async def test_get_chat_session_rejects_session_owned_by_another_user(
    app: DashboardTestClient,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    path_template: str,
    expected_status: int,
    expected_message: str | None,
):
    test_client = DashboardTestClient(app)
    session_id = f"foreign_get_session_{uuid.uuid4().hex[:8]}"
    await core_lifecycle_td.db.create_platform_session(
        creator="not_dashboard_user",
        platform_id="webchat",
        session_id=session_id,
        display_name="Foreign Session",
        is_group=0,
    )
    await core_lifecycle_td.platform_message_history_manager.insert(
        platform_id="webchat",
        user_id=session_id,
        content={
            "type": "user",
            "message": [{"type": "text", "text": "foreign session secret"}],
        },
        sender_id="not_dashboard_user",
        sender_name="not_dashboard_user",
    )

    response = await test_client.get(
        path_template.format(session_id=session_id),
        headers=authenticated_header,
    )

    assert response.status_code == expected_status
    if expected_message is None:
        return
    data = await response.get_json()
    assert data["status"] == "error"
    assert data["message"] == expected_message


@pytest.mark.asyncio
async def test_plugins(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    """Tests plugin API endpoints with mocked install and update paths."""
    test_client = DashboardTestClient(app)

    async def plugin_deploy_headers() -> dict[str, str]:
        step_up = await test_client.post(
            "/api/v1/authorization/step-up",
            json={
                "action": "extension.plugin_install",
                "resource_type": "dashboard-api",
                "resource_id": "post-plugin",
                "password": _resolve_dashboard_password(core_lifecycle_td),
            },
            headers=authenticated_header,
        )
        assert step_up.status_code == 200
        return {
            **authenticated_header,
            "X-AstrBot-Step-Up": (await step_up.get_json())["data"]["token"],
        }

    async def mock_get_online_plugins(_service, *, custom_registry, force_refresh):
        del _service, custom_registry, force_refresh
        return [], None

    monkeypatch.setattr(
        PluginService,
        "get_online_plugins",
        mock_get_online_plugins,
    )

    response = await test_client.get("/api/v1/plugins", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    for plugin in data["data"]:
        assert "installed_at" in plugin
        assert "components" not in plugin
        installed_at = plugin["installed_at"]
        if installed_at is None:
            continue
        assert isinstance(installed_at, str)
        datetime.fromisoformat(installed_at)

    response = await test_client.get(
        "/api/v1/plugins/market",
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"

    plugin_store_path = core_lifecycle_td.plugin_manager.packages.store_path
    builder = MockPluginBuilder(plugin_store_path)
    test_plugin_name = "test_mock_plugin"
    test_repo_url = f"https://github.com/test/{test_plugin_name}"
    mock_install = create_mock_updater_install(
        builder,
        repo_to_plugin={test_repo_url: test_plugin_name},
    )
    mock_update = create_mock_updater_update(builder)

    monkeypatch.setattr(
        core_lifecycle_td.plugin_manager.packages._updator, "install", mock_install
    )
    monkeypatch.setattr(
        core_lifecycle_td.plugin_manager.packages._updator,
        "update",
        mock_update,
    )

    try:
        response = await test_client.post(
            "/api/v1/plugins/install/github",
            json={"repository": test_repo_url},
            headers=await plugin_deploy_headers(),
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok", (
            f"安装失败: {data.get('message', 'unknown error')}"
        )

        response = await test_client.get(
            f"/api/v1/plugins?name={test_plugin_name}",
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"
        assert len(data["data"]) >= 1
        target = next(
            (item for item in data["data"] if item["name"] == test_plugin_name),
            None,
        )
        assert target is not None
        assert "components" not in target
        installed_at = target["installed_at"]
        assert installed_at is not None
        datetime.fromisoformat(installed_at)
        assert target["install_source"]["install_method"] == "github"
        assert target["install_source"]["repo"] == test_repo_url
        assert target["updates_enabled"] is True
        assert target["update_disabled_reason"] == ""

        response = await test_client.get(
            f"/api/v1/plugins/{test_plugin_name}",
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"]["name"] == test_plugin_name
        assert "components" in data["data"]
        assert isinstance(data["data"]["components"], list)

        exists = any(
            md.name == test_plugin_name
            for md in core_lifecycle_td.runtime.catalogs.plugins.all()
        )
        assert exists is True, f"插件 {test_plugin_name} 未成功载入"

        response = await test_client.post(
            f"/api/v1/plugins/{test_plugin_name}/update",
            json={},
            headers=await plugin_deploy_headers(),
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"

        plugin_dir = builder.get_plugin_path(test_plugin_name)
        assert (plugin_dir / ".updated").read_text(encoding="utf-8") == "ok"

        response = await test_client.delete(
            f"/api/v1/plugins/{test_plugin_name}",
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"

        exists = any(
            md.name == test_plugin_name
            for md in core_lifecycle_td.runtime.catalogs.plugins.all()
        )
        assert exists is False, f"插件 {test_plugin_name} 未成功卸载"
        exists = any(
            test_plugin_name in md.handler_module_path
            for md in core_lifecycle_td.runtime.catalogs.handlers
        )
        assert exists is False, f"插件 {test_plugin_name} handler 未成功清理"
    finally:
        builder.cleanup(test_plugin_name)


@pytest.mark.asyncio
async def test_plugins_when_installed_at_unresolved(
    app: FastAPI,
    authenticated_header: dict,
    monkeypatch,
):
    """Tests plugin payload when installed_at cannot be resolved."""
    test_client = DashboardTestClient(app)

    monkeypatch.setattr(PluginService, "get_plugin_installed_at", lambda *_args: None)

    response = await test_client.get("/api/v1/plugins", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"

    for plugin in data["data"]:
        assert "name" in plugin
        assert "installed_at" in plugin
        assert plugin["installed_at"] is None


@pytest.mark.asyncio
async def test_commands_api(app: FastAPI, authenticated_header: dict):
    """Tests the command management API endpoints."""
    test_client = DashboardTestClient(app)

    # GET /api/v1/commands - list commands
    response = await test_client.get("/api/v1/commands", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert "items" in data["data"]
    assert "summary" in data["data"]
    summary = data["data"]["summary"]
    assert "total" in summary
    assert "disabled" in summary
    assert "conflicts" in summary

    # GET /api/v1/commands/conflicts - list conflicts
    response = await test_client.get(
        "/api/v1/commands/conflicts", headers=authenticated_header
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    # conflicts is a list
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_t2i_set_active_template_syncs_all_configs(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = DashboardTestClient(app)
    template_name = f"sync_tpl_{uuid.uuid4().hex[:8]}"
    created_conf_ids: list[str] = []

    try:
        for name in ("sync-a", "sync-b"):
            response = await test_client.post(
                "/api/v1/config-profiles",
                json={"name": name},
                headers=authenticated_header,
            )
            assert response.status_code == 200
            data = await response.get_json()
            assert data["status"] == "ok"
            created_conf_ids.append(data["data"]["conf_id"])

        response = await test_client.post(
            "/api/v1/t2i/templates",
            json={
                "name": template_name,
                "content": "<html><body>{{ text }}</body></html>",
            },
            headers=authenticated_header,
        )
        assert response.status_code == 201
        data = await response.get_json()
        assert data["status"] == "ok"

        response = await test_client.put(
            "/api/v1/t2i/templates/active",
            json={"name": template_name},
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"

        conf_ids = set(core_lifecycle_td.astrbot_config_mgr.confs.keys())
        assert "default" in conf_ids
        for conf_id in conf_ids:
            conf = core_lifecycle_td.astrbot_config_mgr.confs[conf_id]
            assert conf.get("t2i_active_template") == template_name
            assert conf_id in core_lifecycle_td.pipeline_scheduler_mapping
    finally:
        await test_client.put(
            "/api/v1/t2i/templates/active",
            json={"name": "base"},
            headers=authenticated_header,
        )
        await test_client.delete(
            f"/api/v1/t2i/templates/{template_name}",
            headers=authenticated_header,
        )
        for conf_id in created_conf_ids:
            await test_client.delete(
                f"/api/v1/config-profiles/{conf_id}",
                headers=authenticated_header,
            )


@pytest.mark.asyncio
async def test_t2i_reset_default_template_syncs_all_configs(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = DashboardTestClient(app)
    template_name = f"reset_tpl_{uuid.uuid4().hex[:8]}"
    created_conf_ids: list[str] = []

    try:
        for name in ("reset-a", "reset-b"):
            response = await test_client.post(
                "/api/v1/config-profiles",
                json={"name": name},
                headers=authenticated_header,
            )
            assert response.status_code == 200
            data = await response.get_json()
            assert data["status"] == "ok"
            created_conf_ids.append(data["data"]["conf_id"])

        response = await test_client.post(
            "/api/v1/t2i/templates",
            json={
                "name": template_name,
                "content": "<html><body>{{ text }} reset</body></html>",
            },
            headers=authenticated_header,
        )
        assert response.status_code == 201
        data = await response.get_json()
        assert data["status"] == "ok"

        response = await test_client.put(
            "/api/v1/t2i/templates/active",
            json={"name": template_name},
            headers=authenticated_header,
        )
        assert response.status_code == 200

        response = await test_client.post(
            "/api/v1/t2i/templates/default/reset",
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"

        conf_ids = set(core_lifecycle_td.astrbot_config_mgr.confs.keys())
        assert "default" in conf_ids
        for conf_id in conf_ids:
            conf = core_lifecycle_td.astrbot_config_mgr.confs[conf_id]
            assert conf.get("t2i_active_template") == "base"
            assert conf_id in core_lifecycle_td.pipeline_scheduler_mapping
    finally:
        await test_client.put(
            "/api/v1/t2i/templates/active",
            json={"name": "base"},
            headers=authenticated_header,
        )
        await test_client.delete(
            f"/api/v1/t2i/templates/{template_name}",
            headers=authenticated_header,
        )
        for conf_id in created_conf_ids:
            await test_client.delete(
                f"/api/v1/config-profiles/{conf_id}",
                headers=authenticated_header,
            )


@pytest.mark.asyncio
async def test_t2i_update_active_template_reloads_all_schedulers(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = DashboardTestClient(app)
    template_name = f"update_tpl_{uuid.uuid4().hex[:8]}"
    created_conf_ids: list[str] = []

    try:
        for name in ("update-a", "update-b"):
            response = await test_client.post(
                "/api/v1/config-profiles",
                json={"name": name},
                headers=authenticated_header,
            )
            assert response.status_code == 200
            data = await response.get_json()
            assert data["status"] == "ok"
            created_conf_ids.append(data["data"]["conf_id"])

        response = await test_client.post(
            "/api/v1/t2i/templates",
            json={
                "name": template_name,
                "content": "<html><body>{{ text }} v1</body></html>",
            },
            headers=authenticated_header,
        )
        assert response.status_code == 201

        response = await test_client.put(
            "/api/v1/t2i/templates/active",
            json={"name": template_name},
            headers=authenticated_header,
        )
        assert response.status_code == 200

        conf_ids = list(core_lifecycle_td.astrbot_config_mgr.confs.keys())
        old_schedulers = {
            conf_id: core_lifecycle_td.pipeline_scheduler_mapping[conf_id]
            for conf_id in conf_ids
        }

        response = await test_client.put(
            f"/api/v1/t2i/templates/{template_name}",
            json={"content": "<html><body>{{ text }} v2</body></html>"},
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"

        for conf_id in conf_ids:
            assert conf_id in core_lifecycle_td.pipeline_scheduler_mapping
            assert (
                core_lifecycle_td.pipeline_scheduler_mapping[conf_id]
                is not old_schedulers[conf_id]
            )
    finally:
        await test_client.put(
            "/api/v1/t2i/templates/active",
            json={"name": "base"},
            headers=authenticated_header,
        )
        await test_client.delete(
            f"/api/v1/t2i/templates/{template_name}",
            headers=authenticated_header,
        )
        for conf_id in created_conf_ids:
            await test_client.delete(
                f"/api/v1/config-profiles/{conf_id}",
                headers=authenticated_header,
            )
