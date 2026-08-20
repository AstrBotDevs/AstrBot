from __future__ import annotations

import pytest

from tests.unit.dashboard.fastapi_v1_support import *  # noqa: F403


@pytest.mark.asyncio
async def test_v1_mcp_enabled_patch_updates_stored_active_flag(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    response = await asgi_client.patch(
        "/api/v1/mcp/servers/demo-server/enabled",
        json={"enabled": False},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["message"] == "Successfully updated MCP server demo-server"
    mcp_servers = fake_core_lifecycle.provider_manager.tool_manager.config["mcpServers"]
    assert mcp_servers["demo-server"]["active"] is False


@pytest.mark.asyncio
async def test_v1_mcp_list_never_returns_configured_header_secrets(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    fake_tools = fake_core_lifecycle.provider_manager.tool_manager
    fake_tools.config["mcpServers"]["demo-server"]["headers"] = {
        "Authorization": "Bearer dashboard-must-not-see-this"
    }

    response = await asgi_client.get("/api/v1/mcp/servers", headers=_jwt_headers())

    assert response.status_code == 200
    server = next(
        item for item in response.json()["data"] if item["name"] == "demo-server"
    )
    assert "headers" not in server
    assert server["headers_configured"] is True


@pytest.mark.asyncio
async def test_v1_safe_mcp_routes_accept_slash_server_names(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    server_name = "modelscope/demo"
    headers = _jwt_headers()
    fake_tools = fake_core_lifecycle.provider_manager.tool_manager

    enabled_response = await asgi_client.patch(
        "/api/v1/mcp/servers/modelscope%2Fdemo/enabled",
        json={"enabled": False},
        headers=headers,
    )
    assert enabled_response.status_code == 200
    assert fake_tools.config["mcpServers"][server_name]["active"] is False

    test_response = await asgi_client.post(
        "/api/v1/mcp/servers/modelscope%2Fdemo/test",
        headers=headers,
    )
    assert test_response.status_code == 200
    assert test_response.json()["data"] == ["demo_tool"]
    assert fake_tools.tested_configs[-1] == {
        "active": False,
        "url": "https://93.184.216.34/modelscope-demo",
        "transport": "streamable_http",
    }

    delete_response = await asgi_client.delete(
        "/api/v1/mcp/servers/modelscope%2Fdemo",
        headers=headers,
    )
    assert delete_response.status_code == 200
    assert server_name not in fake_tools.config["mcpServers"]

    sync_response = await asgi_client.post(
        "/api/v1/mcp/providers/modelscope/sync",
        json={"access_token": "token"},
        headers=headers,
    )
    assert sync_response.status_code == 200
    assert fake_tools.synced_modelscope_tokens == ["token"]


@pytest.mark.asyncio
async def test_v1_mcp_scope_accepts_api_key(
    asgi_client: httpx.AsyncClient,
    fake_db: FakeDb,
):
    raw_key = "abk_fastapi_v1_mcp"
    fake_db.add_api_key(raw_key, scopes=["mcp"])

    response = await asgi_client.get(
        "/api/v1/mcp/servers",
        headers={"X-API-Key": raw_key},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert any(server["name"] == "demo-server" for server in data["data"])


@pytest.mark.asyncio
async def test_v1_mcp_create_rejects_legacy_mcpservers_payload(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.post(
        "/api/v1/mcp/servers",
        json={
            "name": "demo-server",
            "mcpServers": {
                "demo-server": {
                    "url": "https://example.com/demo",
                }
            },
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_v1_mcp_test_by_name_rejects_legacy_mcp_server_config_field(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.post(
        "/api/v1/mcp/servers/demo-server/test",
        json={
            "mcp_server_config": {"url": "https://example.com/demo"},
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_v1_tool_toggle_uses_async_manager(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    fake_tools = fake_core_lifecycle.provider_manager.tool_manager
    headers = _jwt_headers()

    activate_response = await asgi_client.patch(
        "/api/v1/tools/demo-tool/enabled",
        json={"enabled": True},
        headers=headers,
    )
    deactivate_response = await asgi_client.patch(
        "/api/v1/tools/demo-tool/enabled",
        json={"enabled": False},
        headers=headers,
    )

    assert activate_response.status_code == 200
    assert deactivate_response.status_code == 200
    assert fake_tools.activated_tools == ["demo-tool"]
    assert fake_tools.deactivated_tools == ["demo-tool"]


@pytest.mark.asyncio
async def test_v1_session_groups_use_async_shared_preferences(
    asgi_client: httpx.AsyncClient,
    asgi_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    store: dict[str, dict] = {}

    async def fake_global_get(key: str, default=None):
        return store.get(key, default)

    async def fake_global_put(key: str, value):
        store[key] = copy.deepcopy(value)

    preferences = asgi_app.state.services.sessions.preferences
    monkeypatch.setattr(preferences, "global_get", fake_global_get)
    monkeypatch.setattr(preferences, "global_put", fake_global_put)

    headers = _jwt_headers()
    create_response = await asgi_client.post(
        "/api/v1/session-groups",
        json={"name": "Ops", "umos": ["webchat:FriendMessage:umo-1"]},
        headers=headers,
    )
    assert create_response.status_code == 200
    group_id = create_response.json()["data"]["group"]["id"]

    list_response = await asgi_client.get("/api/v1/session-groups", headers=headers)
    update_response = await asgi_client.put(
        f"/api/v1/session-groups/{group_id}",
        json={"add_umos": ["webchat:FriendMessage:umo-2"]},
        headers=headers,
    )
    delete_response = await asgi_client.delete(
        f"/api/v1/session-groups/{group_id}",
        headers=headers,
    )

    assert list_response.status_code == 200
    assert list_response.json()["data"]["groups"] == [
        {
            "id": group_id,
            "name": "Ops",
            "umos": ["webchat:FriendMessage:umo-1"],
            "umo_count": 1,
        }
    ]
    assert update_response.status_code == 200
    assert set(update_response.json()["data"]["group"]["umos"]) == {
        "webchat:FriendMessage:umo-1",
        "webchat:FriendMessage:umo-2",
    }
    assert delete_response.status_code == 200
    assert store["session_groups"] == {}


@pytest.mark.asyncio
async def test_v1_batch_session_service_uses_async_shared_preferences(
    asgi_client: httpx.AsyncClient,
    asgi_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    store = {
        ("webchat:FriendMessage:umo-1", "session_service_config"): {
            "llm_enabled": True,
            "tts_enabled": True,
        }
    }

    async def fake_session_get(umo: str, key: str, default=None):
        return copy.deepcopy(store.get((umo, key), default))

    async def fake_session_put(umo: str, key: str, value):
        store[(umo, key)] = copy.deepcopy(value)

    preferences = asgi_app.state.services.sessions.preferences
    monkeypatch.setattr(preferences, "session_get", fake_session_get)
    monkeypatch.setattr(preferences, "session_put", fake_session_put)

    response = await asgi_client.patch(
        "/api/v1/sessions/service",
        json={
            "umos": ["webchat:FriendMessage:umo-1"],
            "llm_enabled": False,
            "session_enabled": False,
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    assert response.json()["data"]["success_count"] == 1
    assert store[("webchat:FriendMessage:umo-1", "session_service_config")] == {
        "llm_enabled": False,
        "tts_enabled": True,
        "session_enabled": False,
    }


@pytest.mark.asyncio
async def test_v1_session_provider_rule_uses_provider_manager_cache_path(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    response = await asgi_client.post(
        "/api/v1/sessions/rules",
        json={
            "umo": "webchat:FriendMessage:umo-1",
            "rule_key": "provider_perf_chat_completion",
            "rule_value": "gpt-mini",
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    assert len(fake_core_lifecycle.provider_manager.set_provider_calls) == 1
    call = fake_core_lifecycle.provider_manager.set_provider_calls[0]
    assert call["provider_id"] == "gpt-mini"
    assert call["umo"] == "webchat:FriendMessage:umo-1"
    assert getattr(call["provider_type"], "value", None) == "chat_completion"


@pytest.mark.asyncio
async def test_v1_delete_session_provider_rule_clears_provider_manager_cache_path(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    response = await asgi_client.post(
        "/api/v1/sessions/rules/delete",
        json={
            "umo": "webchat:FriendMessage:umo-1",
            "rule_key": "provider_perf_chat_completion",
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    assert len(fake_core_lifecycle.provider_manager.cleared_provider_calls) == 1
    call = fake_core_lifecycle.provider_manager.cleared_provider_calls[0]
    assert call["umo"] == "webchat:FriendMessage:umo-1"
    assert getattr(call["provider_type"], "value", None) == "chat_completion"


@pytest.mark.asyncio
async def test_v1_subagent_config_rejects_legacy_enable_field(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.put(
        "/api/v1/subagents/config",
        json={
            "enable": True,
            "remove_main_duplicate_tools": False,
            "agents": [],
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_v1_trace_settings_use_enabled_field(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    fake_core_lifecycle.astrbot_config["trace_enable"] = False

    get_response = await asgi_client.get(
        "/api/v1/trace/settings",
        headers=_jwt_headers(),
    )
    update_response = await asgi_client.put(
        "/api/v1/trace/settings",
        json={"enabled": True},
        headers=_jwt_headers(),
    )

    assert get_response.status_code == 200
    assert get_response.json()["data"] == {"enabled": False}
    assert update_response.status_code == 200
    assert update_response.json()["message"] == "Trace 设置已更新"
    assert fake_core_lifecycle.astrbot_config["trace_enable"] is True


@pytest.mark.asyncio
async def test_v1_trace_settings_reject_legacy_trace_enable_field(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.put(
        "/api/v1/trace/settings",
        json={"trace_enable": False},
        headers=_jwt_headers(),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_v1_skill_scope_accepts_api_key_and_rejects_plural_scope(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    fake_db: FakeDb,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        asgi_app.state.services.skills,
        "get_skills",
        lambda: {"skills": [{"name": "demo_skill"}]},
    )

    plural_key = "abk_fastapi_v1_skills"
    fake_db.add_api_key(plural_key, scopes=["skills"])
    plural_response = await asgi_client.get(
        "/api/v1/skills",
        headers={"X-API-Key": plural_key},
    )

    assert plural_response.status_code == 403
    data = plural_response.json()
    assert data["status"] == "error"
    assert data["message"] == "Insufficient API key scope"

    raw_key = "abk_fastapi_v1_skill"
    fake_db.add_api_key(raw_key, scopes=["skill"])
    response = await asgi_client.get(
        "/api/v1/skills",
        headers={"X-API-Key": raw_key},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["skills"] == [{"name": "demo_skill"}]

    named = await asgi_client.get(
        "/api/v1/skills/demo_skill/files",
        headers={"X-API-Key": raw_key},
    )
    assert named.status_code == 403


@pytest.mark.asyncio
async def test_v1_neo_skill_sync_accepts_skill_key_target(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_sync(data):
        return {"synced": data["skill_key"]}

    monkeypatch.setattr(asgi_app.state.services.skills, "sync_neo_release", fake_sync)

    response = await asgi_client.post(
        "/api/v1/skills/neo/sync",
        json={"skill_key": "neo.demo"},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"synced": "neo.demo"}


@pytest.mark.asyncio
async def test_v1_safe_skill_routes_accept_slash_names(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    skill_name = "skill/foo"
    headers = _jwt_headers()
    skill_service = asgi_app.state.services.skills
    archive_path = tmp_path / "skill.zip"
    archive_path.write_bytes(b"zip")

    async def fake_update_skill(data):
        return {"payload": data}

    async def fake_delete_skill(data):
        return {"payload": data}

    def fake_prepare_skill_archive(name: str):
        assert name == skill_name
        return SkillArchive(path=archive_path, filename="skill.zip")

    def fake_list_skill_files(name: str, path: str):
        return {"name": name, "path": path}

    def fake_get_skill_file(name: str, path: str):
        return {"name": name, "path": path}

    async def fake_update_skill_file(data):
        return {"payload": data}

    monkeypatch.setattr(skill_service, "update_skill", fake_update_skill)
    monkeypatch.setattr(skill_service, "delete_skill", fake_delete_skill)
    monkeypatch.setattr(
        skill_service,
        "prepare_skill_archive",
        fake_prepare_skill_archive,
    )
    monkeypatch.setattr(skill_service, "list_skill_files", fake_list_skill_files)
    monkeypatch.setattr(skill_service, "get_skill_file", fake_get_skill_file)
    monkeypatch.setattr(skill_service, "update_skill_file", fake_update_skill_file)

    enabled_response = await asgi_client.patch(
        f"/api/v1/skills/{skill_name}",
        json={"active": False},
        headers=headers,
    )
    archive_response = await asgi_client.get(
        f"/api/v1/skills/{skill_name}/archive",
        headers=headers,
    )
    files_response = await asgi_client.get(
        f"/api/v1/skills/{skill_name}/files",
        params={"path": "src"},
        headers=headers,
    )
    file_response = await asgi_client.get(
        f"/api/v1/skills/{skill_name}/files/src%2Fmain.py",
        headers=headers,
    )
    update_file_response = await asgi_client.put(
        f"/api/v1/skills/{skill_name}/files/src%2Fmain.py",
        content="print(1)",
        headers={**headers, "Content-Type": "text/plain; charset=utf-8"},
    )
    delete_response = await asgi_client.delete(
        f"/api/v1/skills/{skill_name}",
        headers=headers,
    )

    assert enabled_response.status_code == 200
    assert enabled_response.json()["data"]["payload"] == {
        "name": skill_name,
        "active": False,
    }
    assert archive_response.status_code == 200
    assert archive_response.content == b"zip"
    assert files_response.status_code == 200
    assert files_response.json()["data"] == {"name": skill_name, "path": "src"}
    assert file_response.status_code == 200
    assert file_response.json()["data"] == {
        "name": skill_name,
        "path": "src/main.py",
    }
    assert update_file_response.status_code == 200
    assert update_file_response.json()["data"]["payload"] == {
        "name": skill_name,
        "path": "src/main.py",
        "content": "print(1)",
    }
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["payload"] == {"name": skill_name}


@pytest.mark.asyncio
async def test_v1_skill_by_name_rejects_legacy_enabled_field(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.patch(
        "/api/v1/skills/demo_skill",
        json={"enabled": False},
        headers=_jwt_headers(),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_v1_skill_archive_errors_return_http_status(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    skill_service = asgi_app.state.services.skills

    def fake_prepare_skill_archive_404(_name: str):
        raise SkillsServiceError("Local skill not found", status_code=404)

    monkeypatch.setattr(
        skill_service,
        "prepare_skill_archive",
        fake_prepare_skill_archive_404,
    )

    path_response = await asgi_client.get(
        "/api/v1/skills/missing_skill/archive",
        headers=_jwt_headers(),
    )

    assert path_response.status_code == 404
    assert path_response.headers["content-type"].startswith("application/json")
    assert path_response.json()["status"] == "error"
    assert path_response.json()["message"] == "Local skill not found"

    def fake_prepare_skill_archive_400(_name: str):
        raise SkillsServiceError("Invalid skill name")

    monkeypatch.setattr(
        skill_service,
        "prepare_skill_archive",
        fake_prepare_skill_archive_400,
    )

    bad_request_response = await asgi_client.get(
        "/api/v1/skills/invalid_skill/archive",
        headers=_jwt_headers(),
    )

    assert bad_request_response.status_code == 400
    assert bad_request_response.headers["content-type"].startswith("application/json")
    assert bad_request_response.json()["status"] == "error"
    assert bad_request_response.json()["message"] == "Invalid skill name"

    def fake_prepare_skill_archive_500(_name: str):
        raise RuntimeError("Unexpected database error")

    monkeypatch.setattr(
        skill_service,
        "prepare_skill_archive",
        fake_prepare_skill_archive_500,
    )

    server_error_response = await asgi_client.get(
        "/api/v1/skills/error_skill/archive",
        headers=_jwt_headers(),
    )

    assert server_error_response.status_code == 500
    assert server_error_response.headers["content-type"].startswith("application/json")
    assert server_error_response.json()["status"] == "error"
    assert server_error_response.json()["message"] == "Failed to prepare skill archive"
    assert "Unexpected database error" not in server_error_response.text


@pytest.mark.asyncio
async def test_v1_safe_persona_routes_accept_slash_ids(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    persona_id = "persona/foo"
    headers = _jwt_headers()
    persona_mgr = fake_core_lifecycle.persona_mgr

    detail_response = await asgi_client.get(
        "/api/v1/personas/persona%2Ffoo",
        headers=headers,
    )
    update_response = await asgi_client.put(
        "/api/v1/personas/persona%2Ffoo",
        json={"name": "Demo Persona"},
        headers=headers,
    )
    delete_response = await asgi_client.delete(
        "/api/v1/personas/persona%2Ffoo",
        headers=headers,
    )

    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["persona_id"] == persona_id
    assert detail_response.json()["data"]["system_prompt"] == "Demo persona"
    assert update_response.status_code == 200
    assert update_response.json()["data"] == {"message": "人格更新成功"}
    assert delete_response.status_code == 200
    assert delete_response.json()["data"] == {"message": "人格删除成功"}
    assert persona_id not in persona_mgr.personas


@pytest.mark.asyncio
async def test_v1_persona_create_preserves_explicit_empty_tools_and_skills(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    response = await asgi_client.post(
        "/api/v1/personas",
        json={
            "persona_id": "persona/no-capabilities",
            "system_prompt": "Do not use capabilities.",
            "tools": [],
            "skills": [],
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    persona = fake_core_lifecycle.persona_mgr.personas["persona/no-capabilities"]
    assert persona.tools == []
    assert persona.skills == []


@pytest.mark.asyncio
async def test_v1_persona_by_id_update_preserves_explicit_null_tools_and_skills(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    persona_id = "persona/foo"
    headers = _jwt_headers()
    persona = fake_core_lifecycle.persona_mgr.personas[persona_id]
    persona.tools = ["tool-a"]
    persona.skills = ["skill-a"]

    response = await asgi_client.put(
        "/api/v1/personas/persona%2Ffoo",
        json={"tools": None, "skills": None},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"message": "人格更新成功"}
    assert persona.tools is None
    assert persona.skills is None


@pytest.mark.asyncio
async def test_v1_im_routes_use_im_scope_and_running_platform(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
    fake_db: FakeDb,
):
    raw_key = "abk_fastapi_v1_im"
    fake_db.add_api_key(raw_key, scopes=["im"])

    bots_response = await asgi_client.get(
        "/api/v1/im/bots",
        headers={"X-API-Key": raw_key},
    )
    send_response = await asgi_client.post(
        "/api/v1/im/messages",
        json={
            "umo": "webchat-main:FriendMessage:test-session",
            "message": "hello",
        },
        headers={"X-API-Key": raw_key},
    )

    assert bots_response.status_code == 200
    assert send_response.status_code == 200
    assert bots_response.json()["data"]["bot_ids"] == ["webchat-main"]
    sent_messages = fake_core_lifecycle.platform_manager.fake_platform.sent_messages
    assert len(sent_messages) == 1
    session, message_chain = sent_messages[0]
    assert str(session) == "webchat-main:FriendMessage:test-session"
    assert message_chain.chain[0].text == "hello"


@pytest.mark.asyncio
async def test_v1_platform_webhook_is_public_route(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.post(
        "/api/v1/webhooks/platforms/demo-hook",
        json={"challenge": "ping"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "webhook_uuid": "demo-hook",
        "method": "POST",
        "payload": {"challenge": "ping"},
    }


@pytest.mark.asyncio
async def test_v1_platform_webhook_preserves_plain_response(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.post(
        "/api/v1/webhooks/platforms/demo-hook",
        json={"response_mode": "plain"},
    )

    assert response.status_code == 200
    assert response.text == "success"


@pytest.mark.asyncio
async def test_v1_platform_webhook_preserves_tuple_response(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.post(
        "/api/v1/webhooks/platforms/demo-hook",
        json={"response_mode": "tuple"},
    )

    assert response.status_code == 202
    assert response.headers["content-type"] == "text/plain"
    assert response.text == "accepted"


@pytest.mark.asyncio
@pytest.mark.parametrize("exception_type", [RuntimeError, ValueError])
@pytest.mark.parametrize(
    (
        "surface",
        "service_name",
        "service_method",
        "method",
        "path",
        "payload",
        "service_error",
        "business_status",
        "logger_module",
    ),
    _DASHBOARD_API_ERROR_CASES,
)
async def test_v1_unknown_dashboard_api_errors_are_sanitized(
    asgi_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
    service_name: str,
    service_method: str,
    method: str,
    path: str,
    payload: dict | None,
    service_error: type[Exception],
    business_status: int,
    logger_module,
    exception_type: type[Exception],
):
    """Unknown service failures never disclose internal details to Dashboard users."""
    _ = surface, service_error, business_status

    async def raise_internal_error(*_args, **_kwargs):
        raise exception_type(_SENSITIVE_INTERNAL_ERROR)

    logger = _RecordingErrorLogger()
    monkeypatch.setattr(logger_module, "logger", logger)
    monkeypatch.setattr(
        getattr(asgi_app.state.services, service_name),
        service_method,
        raise_internal_error,
    )

    transport = httpx.ASGITransport(app=asgi_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await _request_api_error_case(
            client,
            method=method,
            path=path,
            payload=payload,
        )

    assert response.status_code == 500
    assert response.json() == {
        "status": "error",
        "message": "Internal server error",
    }
    for fragment in _SENSITIVE_ERROR_FRAGMENTS:
        assert fragment not in response.text
    _assert_error_log_is_redacted(logger)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "surface",
        "service_name",
        "service_method",
        "method",
        "path",
        "payload",
        "service_error",
        "business_status",
        "logger_module",
    ),
    _DASHBOARD_API_ERROR_CASES,
)
async def test_v1_dashboard_api_service_errors_preserve_business_message(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
    service_name: str,
    service_method: str,
    method: str,
    path: str,
    payload: dict | None,
    service_error: type[Exception],
    business_status: int,
    logger_module,
):
    """Expected service validation failures retain their deliberate messages."""
    _ = logger_module
    message = f"{surface} validation failed"

    async def raise_service_error(*_args, **_kwargs):
        raise service_error(message)

    monkeypatch.setattr(
        getattr(asgi_app.state.services, service_name),
        service_method,
        raise_service_error,
    )

    response = await _request_api_error_case(
        asgi_client,
        method=method,
        path=path,
        payload=payload,
    )

    assert response.status_code == business_status
    assert response.json()["status"] == "error"
    assert response.json()["message"] == message
