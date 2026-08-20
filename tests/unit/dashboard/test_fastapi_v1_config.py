from __future__ import annotations

import pytest

from tests.unit.dashboard.fastapi_v1_support import *  # noqa: F403


@pytest.mark.asyncio
async def test_v1_bot_stats_match_platform_manager(asgi_client: httpx.AsyncClient):
    response = await asgi_client.get("/api/v1/bots/stats", headers=_jwt_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["platforms"] == [{"id": "webchat-main", "status": "running"}]


@pytest.mark.asyncio
async def test_v1_config_routes_can_replace_all_routes(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    routing = {
        "webchat-main:private:*": "default",
        "webchat-main:group:demo": "group-conf",
    }

    response = await asgi_client.put(
        "/api/v1/config-routes",
        headers=_jwt_headers(),
        json={"routing": routing},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert fake_core_lifecycle.umop_config_router.umop_to_conf_id == routing

    list_response = await asgi_client.get(
        "/api/v1/config-routes",
        headers=_jwt_headers(),
    )
    assert list_response.status_code == 200
    assert list_response.json()["data"]["routing"] == routing


@pytest.mark.asyncio
async def test_v1_active_umos_uses_session_service(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.get(
        "/api/v1/sessions/active-umos",
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["umos"] == ["webchat:FriendMessage:webchat!user!session-1"]
    assert data["data"]["umo_infos"][0]["platform"] == "webchat"


@pytest.mark.asyncio
async def test_v1_system_config_update_preserves_independent_bot_provider_sections(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_save_config_async(
        post_config: dict,
        config: FakeAstrBotConfig,
        is_core=False,
    ) -> bool:
        _ = is_core
        return await config.save_config_async(post_config)

    monkeypatch.setattr(config_service, "save_config_async", fake_save_config_async)

    original_platform = copy.deepcopy(fake_core_lifecycle.astrbot_config["platform"])
    original_provider_sources = copy.deepcopy(
        fake_core_lifecycle.astrbot_config["provider_sources"]
    )
    original_providers = copy.deepcopy(fake_core_lifecycle.astrbot_config["provider"])
    payload = copy.deepcopy(fake_core_lifecycle.astrbot_config)
    payload["platform"] = []
    payload["provider_sources"] = []
    payload["provider"] = []
    payload["provider_settings"] = {"default_provider_id": "gpt-mini"}

    response = await asgi_client.put(
        "/api/v1/system-config",
        headers=_jwt_headers(),
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert fake_core_lifecycle.astrbot_config["platform"] == original_platform
    assert (
        fake_core_lifecycle.astrbot_config["provider_sources"]
        == original_provider_sources
    )
    assert fake_core_lifecycle.astrbot_config["provider"] == original_providers
    assert fake_core_lifecycle.astrbot_config["provider_settings"] == {
        "default_provider_id": "gpt-mini"
    }
    assert fake_core_lifecycle.reloaded_config_ids == ["default"]


@pytest.mark.asyncio
async def test_v1_system_config_returns_system_metadata(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.get(
        "/api/v1/system-config",
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "system_group" in data["data"]["metadata"]
    assert "platform_group" not in data["data"]["metadata"]


@pytest.mark.asyncio
async def test_v1_provider_schema_keeps_reasoning_in_model_metadata(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    fake_core_lifecycle.astrbot_config["provider"][0]["reasoning"] = True
    model_metadata = {
        "id": "gpt-4o-mini",
        "reasoning": True,
        "tool_call": True,
        "knowledge": "2023-10",
        "release_date": "2024-07-18",
        "modalities": {"input": ["text"], "output": ["text"]},
        "open_weights": False,
        "limit": {"context": 128000, "output": 16384},
    }
    fake_core_lifecycle.services.llm_metadata_catalog.replace(
        {"gpt-4o-mini": model_metadata}
    )

    response = await asgi_client.get(
        "/api/v1/providers/schema",
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    provider = next(item for item in data["providers"] if item["id"] == "gpt-mini")
    assert "reasoning" not in provider
    assert data["model_metadata"]["gpt-4o-mini"] == model_metadata


@pytest.mark.asyncio
async def test_v1_provider_source_rename_updates_provider_refs(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_save_config_async(
        post_config: dict,
        config: FakeAstrBotConfig,
        **_kwargs,
    ) -> bool:
        return await config.save_config_async(post_config)

    monkeypatch.setattr(
        "astrbot.dashboard.services.config_service.save_config_async",
        fake_save_config_async,
    )

    response = await asgi_client.put(
        "/api/v1/provider-sources/openai-source",
        json={
            "config": {
                "id": "openai-renamed",
                "type": "openai_chat_completions",
                "provider_type": "chat_completion",
                "api_base": "https://api.example.test/v1",
                "key": ["test-key"],
            }
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    config = fake_core_lifecycle.astrbot_config
    assert config["provider_sources"][0]["id"] == "openai-renamed"
    assert config["provider"][0]["provider_source_id"] == "openai-renamed"
    assert (
        fake_core_lifecycle.provider_manager.provider_sources_config[0]["id"]
        == "openai-renamed"
    )
    assert fake_core_lifecycle.provider_manager.reloaded_providers == [
        config["provider"][0]
    ]


@pytest.mark.asyncio
async def test_v1_provider_source_rejects_legacy_top_level_id_field(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.put(
        "/api/v1/provider-sources/openai-source",
        json={
            "id": "openai-renamed",
            "config": {
                "id": "openai-renamed",
                "type": "openai_chat_completions",
                "provider_type": "chat_completion",
            },
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_v1_provider_update_keeps_dashboard_id_rename_behavior(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    response = await asgi_client.put(
        "/api/v1/providers/gpt-mini",
        json={
            "config": {
                "id": "gpt-renamed",
                "provider_source_id": "openai-source",
                "model": "gpt-4o-mini",
                "enable": True,
                "reasoning": True,
            }
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    config = fake_core_lifecycle.astrbot_config
    assert config["provider"][0]["id"] == "gpt-renamed"
    assert "reasoning" not in config["provider"][0]
    assert fake_core_lifecycle.provider_manager.reloaded_providers == [
        config["provider"][0]
    ]


@pytest.mark.asyncio
async def test_v1_create_source_provider_strips_reasoning_metadata(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    response = await asgi_client.post(
        "/api/v1/providers",
        json={
            "config": {
                "id": "gpt-source-model",
                "provider_source_id": "openai-source",
                "model": "gpt-4o-mini",
                "enable": True,
                "reasoning": True,
            }
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    provider = fake_core_lifecycle.astrbot_config["provider"][-1]
    assert provider["id"] == "gpt-source-model"
    assert "reasoning" not in provider


@pytest.mark.asyncio
async def test_v1_create_standalone_provider_keeps_reasoning_field(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    response = await asgi_client.post(
        "/api/v1/providers",
        json={
            "config": {
                "id": "standalone-agent-runner",
                "type": "dify",
                "provider_type": "agent_runner",
                "enable": True,
                "reasoning": True,
            }
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert fake_core_lifecycle.astrbot_config["provider"][-1] == {
        "id": "standalone-agent-runner",
        "type": "dify",
        "provider_type": "agent_runner",
        "enable": True,
        "reasoning": True,
    }


@pytest.mark.asyncio
async def test_v1_provider_update_rejects_legacy_top_level_fields(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.put(
        "/api/v1/providers/gpt-mini",
        json={
            "provider_source_id": "openai-source",
            "enabled": False,
            "config": {
                "id": "gpt-mini",
                "provider_source_id": "openai-source",
                "model": "gpt-4o-mini",
                "enable": False,
            },
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_v1_safe_provider_routes_accept_slash_ids(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_save_config_async(
        post_config: dict,
        config: FakeAstrBotConfig,
        **_kwargs,
    ) -> bool:
        return await config.save_config_async(post_config)

    monkeypatch.setattr(config_service, "save_config_async", fake_save_config_async)

    source_id = "https://example.com/source"
    provider_id = "qianxun/kimi-k2-0905-preview"
    config = fake_core_lifecycle.astrbot_config
    config["provider_sources"].append(
        {
            "id": source_id,
            "type": "openai_chat_completions",
            "provider_type": "chat_completion",
            "api_base": "https://api.example.test/v1",
            "key": ["test-key"],
        }
    )
    config["provider"].append(
        {
            "id": provider_id,
            "provider_source_id": source_id,
            "model": "kimi-k2-0905-preview",
            "enable": True,
        }
    )
    provider_instance = FakeProviderInstance(provider_id)
    fake_core_lifecycle.provider_manager.inst_map[provider_id] = provider_instance

    async def fake_list_models(_service, requested_source_id: str):
        return {"provider_source_id": requested_source_id, "models": ["model/a"]}

    monkeypatch.setattr(
        config_service.ProviderConfigService,
        "list_provider_source_models",
        fake_list_models,
    )

    headers = _jwt_headers()
    get_response = await asgi_client.get(
        "/api/v1/providers/qianxun%2Fkimi-k2-0905-preview",
        params={"merged": True},
        headers=headers,
    )
    schema_response = await asgi_client.get(
        "/api/v1/providers/schema",
        headers=headers,
    )
    path_test_response = await asgi_client.post(
        "/api/v1/providers/qianxun%2Fkimi-k2-0905-preview/test",
        headers=headers,
    )
    enabled_response = await asgi_client.patch(
        "/api/v1/providers/qianxun%2Fkimi-k2-0905-preview/enabled",
        json={"enabled": False},
        headers=headers,
    )
    embedding_response = await asgi_client.post(
        "/api/v1/providers/qianxun%2Fkimi-k2-0905-preview/embedding-dimension",
        json={"config": {"model": "model/a"}},
        headers=headers,
    )
    source_models_response = await asgi_client.get(
        "/api/v1/provider-sources/https:%2F%2Fexample.com%2Fsource/models",
        headers=headers,
    )
    source_providers_response = await asgi_client.get(
        "/api/v1/provider-sources/https:%2F%2Fexample.com%2Fsource/providers",
        params={"provider_type": "chat_completion"},
        headers=headers,
    )
    legacy_get_response = await asgi_client.get(
        "/api/v1/providers/by-id",
        params={"provider_id": provider_id},
        headers=headers,
    )
    filtered_list_response = await asgi_client.get(
        "/api/v1/providers",
        params={
            "provider_type": "chat_completion",
            "provider_source_id": source_id,
            "enabled": "false",
        },
        headers=headers,
    )
    legacy_list_response = await asgi_client.get(
        "/api/v1/providers",
        params={"capability": "chat"},
        headers=headers,
    )
    legacy_source_list_response = await asgi_client.get(
        "/api/v1/provider-sources/https:%2F%2Fexample.com%2Fsource/providers",
        params={"capability": "chat"},
        headers=headers,
    )

    assert get_response.status_code == 200
    assert get_response.json()["data"]["provider"]["id"] == provider_id
    assert schema_response.status_code == 200
    config_schema = schema_response.json()["data"]["config_schema"]
    reasoning_effort_preset = config_schema["provider"]["items"]["custom_extra_body"][
        "template_schema"
    ]["reasoning_effort"]
    assert reasoning_effort_preset["type"] == "string"
    assert reasoning_effort_preset["default"] == "high"
    assert path_test_response.status_code == 200
    assert path_test_response.json()["data"]["status"] == "available"
    assert provider_instance.tested is True
    assert enabled_response.status_code == 200
    assert config["provider"][-1]["enable"] is False
    assert embedding_response.status_code == 400
    assert embedding_response.json()["status"] == "error"
    assert embedding_response.json()["message"] in {
        "提供商适配器加载失败，请检查提供商类型配置或查看服务端日志",
        "提供商不是 EmbeddingProvider 类型",
    }
    assert source_models_response.status_code == 200
    assert source_models_response.json()["data"]["provider_source_id"] == source_id
    assert source_providers_response.status_code == 200
    assert source_providers_response.json()["data"]["providers"][0]["id"] == provider_id
    assert filtered_list_response.status_code == 200
    assert filtered_list_response.json()["data"]["providers"] == [
        source_providers_response.json()["data"]["providers"][0]
    ]
    assert legacy_get_response.status_code == 400
    assert legacy_list_response.status_code == 400
    assert legacy_source_list_response.status_code == 400


@pytest.mark.asyncio
async def test_v1_provider_api_normalizes_provider_type_from_adapter_metadata(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        config_service.ProviderConfigService,
        "_resolve_provider_type_value",
        lambda _self, adapter_type: {
            "openai_chat_completions": "chat_completion",
            "dify": "agent_runner",
        }.get(adapter_type),
    )
    fake_core_lifecycle.astrbot_config["provider_sources"][0].pop("provider_type", None)
    fake_core_lifecycle.astrbot_config["provider"][1].pop("provider_type", None)

    schema_response = await asgi_client.get(
        "/api/v1/providers/schema",
        headers=_jwt_headers(),
    )
    filtered_response = await asgi_client.get(
        "/api/v1/providers",
        params={"provider_type": "agent_runner"},
        headers=_jwt_headers(),
    )

    assert schema_response.status_code == 200
    schema_payload = schema_response.json()["data"]
    assert schema_payload["provider_sources"][0]["provider_type"] == "chat_completion"
    assert schema_payload["providers"][0]["provider_type"] == "chat_completion"
    assert schema_payload["providers"][1]["provider_type"] == "agent_runner"

    assert filtered_response.status_code == 200
    filtered_providers = filtered_response.json()["data"]["providers"]
    assert [provider["id"] for provider in filtered_providers] == ["agent-runner"]
    assert filtered_providers[0]["provider_type"] == "agent_runner"


@pytest.mark.asyncio
async def test_v1_bot_create_rejects_legacy_top_level_fields(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.post(
        "/api/v1/bots",
        json={
            "id": "demo-bot",
            "type": "webchat",
            "enabled": True,
            "config": {
                "id": "demo-bot",
                "type": "webchat",
                "enable": True,
            },
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_v1_bot_types_include_napcat_schema_and_actions(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.get(
        "/api/v1/bot-types",
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

    napcat = next(
        item for item in data["data"]["bot_types"] if item["type"] == "napcat"
    )
    assert napcat["display_name"] == "NapCat"
    assert napcat["default_config"]["type"] == "napcat"
    assert napcat["default_config"]["ws_url"] == "ws://127.0.0.1:3001"
    assert "send_poke" in napcat["supported_actions"]
    assert "send_group_notice" in napcat["supported_actions"]
    assert napcat["schema"]["timeout_seconds"]["type"] == "float"
    assert napcat["schema"]["timeout_seconds"]["collapsed"] is True
    assert napcat["schema"]["reconnect_interval_seconds"]["type"] == "float"
    assert napcat["schema"]["max_frame_size_mb"]["type"] == "int"


@pytest.mark.asyncio
async def test_v1_safe_bot_routes_accept_slash_ids(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_save_config_async(
        post_config: dict,
        config: FakeAstrBotConfig,
        **_kwargs,
    ) -> bool:
        return await config.save_config_async(post_config)

    monkeypatch.setattr(config_service, "save_config_async", fake_save_config_async)

    bot_id = "group/a"
    fake_core_lifecycle.astrbot_config["platform"].append(
        {"id": bot_id, "type": "webchat", "enable": True}
    )
    headers = _jwt_headers()

    get_response = await asgi_client.get(
        "/api/v1/bots/group%2Fa",
        headers=headers,
    )
    enabled_response = await asgi_client.patch(
        "/api/v1/bots/group%2Fa/enabled",
        json={"enabled": False},
        headers=headers,
    )
    test_response = await asgi_client.post(
        "/api/v1/bots/group%2Fa/test",
        headers=headers,
    )
    delete_response = await asgi_client.delete(
        "/api/v1/bots/group%2Fa",
        headers=headers,
    )
    legacy_get_response = await asgi_client.get(
        "/api/v1/bots/by-id",
        params={"bot_id": bot_id},
        headers=headers,
    )

    assert get_response.status_code == 200
    assert get_response.json()["data"]["bot"]["id"] == bot_id
    assert enabled_response.status_code == 200
    assert fake_core_lifecycle.platform_reload_configs[-1]["id"] == bot_id
    assert fake_core_lifecycle.platform_reload_configs[-1]["enable"] is False
    assert test_response.status_code == 200
    assert test_response.json()["data"] == {"id": bot_id, "status": "unsupported"}
    assert delete_response.status_code == 200
    assert fake_core_lifecycle.terminated_platform_ids == [bot_id]
    assert legacy_get_response.status_code == 400


@pytest.mark.asyncio
async def test_v1_bot_action_route_uses_platform_service(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_invoke(platform_id: str, action_name: str, payload: dict | None):
        return {
            "platform_id": platform_id,
            "action_name": action_name,
            "payload": payload,
        }

    monkeypatch.setattr(
        asgi_app.state.services.platforms,
        "invoke_platform_action",
        fake_invoke,
    )

    response = await asgi_client.post(
        "/api/v1/bots/group%2Fa/actions",
        json={
            "action_name": "send_poke",
            "payload": {"user_id": "123456", "target_id": "654321"},
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"] == {
        "platform_id": "group/a",
        "action_name": "send_poke",
        "payload": {"user_id": "123456", "target_id": "654321"},
    }


@pytest.mark.asyncio
async def test_v1_bot_action_route_maps_platform_service_errors(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_invoke(_platform_id: str, _action_name: str, _payload: dict | None):
        raise PlatformServiceError("group_id is required", 400)

    monkeypatch.setattr(
        asgi_app.state.services.platforms,
        "invoke_platform_action",
        fake_invoke,
    )

    response = await asgi_client.post(
        "/api/v1/bots/napcat-main/actions",
        json={"action_name": "send_group_notice", "payload": {}},
        headers=_jwt_headers(),
    )

    assert response.status_code == 400
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "group_id is required"


@pytest.mark.asyncio
async def test_v1_config_scope_includes_bot_and_provider(
    asgi_client: httpx.AsyncClient,
    fake_db: FakeDb,
):
    config_key = "abk_fastapi_v1_config"
    fake_db.add_api_key(config_key, scopes=["config"])

    bot_response = await asgi_client.get(
        "/api/v1/bots",
        headers={"X-API-Key": config_key},
    )
    provider_response = await asgi_client.get(
        "/api/v1/providers/schema",
        headers={"X-API-Key": config_key},
    )

    assert bot_response.status_code == 200
    assert provider_response.status_code == 200

    bot_key = "abk_fastapi_v1_bot"
    fake_db.add_api_key(bot_key, scopes=["bot"])

    response = await asgi_client.get(
        "/api/v1/bots",
        headers={"X-API-Key": bot_key},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert isinstance(data["data"]["bots"], list)
    assert fake_db.touched_key_ids == [
        "key-abk_fastapi_v1_config",
        "key-abk_fastapi_v1_config",
        "key-abk_fastapi_v1_bot",
    ]
