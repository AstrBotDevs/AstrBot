import copy
from dataclasses import dataclass
from types import SimpleNamespace

import httpx
import jwt
import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

import astrbot.dashboard.services.config_service as config_service
from astrbot.dashboard.services.api_key_service import ApiKeyService
from astrbot.dashboard.v1.app import create_v1_asgi_app
from astrbot.dashboard.v1.responses import ok

JWT_SECRET = "fastapi-v1-test-secret-with-32-bytes"


@dataclass
class FakeApiKey:
    key_id: str
    scopes: list[str] | None


class _FakeScalarResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def all(self) -> list[object]:
        return self.items


class _FakeDbResult:
    def __init__(self, db: "FakeDb") -> None:
        self.db = db

    def fetchall(self) -> list[tuple[str]]:
        return [(umo,) for umo in self.db.umo_ids]

    def scalars(self) -> _FakeScalarResult:
        return _FakeScalarResult(self.db.preferences)


class _FakeDbSession:
    def __init__(self, db: "FakeDb") -> None:
        self.db = db

    async def execute(self, _statement) -> _FakeDbResult:
        return _FakeDbResult(self.db)


class _FakeDbContext:
    def __init__(self, db: "FakeDb") -> None:
        self.db = db

    async def __aenter__(self) -> _FakeDbSession:
        return _FakeDbSession(self.db)

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class FakeDb:
    def __init__(self) -> None:
        self.api_keys: dict[str, FakeApiKey] = {}
        self.touched_key_ids: list[str] = []
        self.umo_ids = ["webchat:FriendMessage:webchat!user!session-1"]
        self.preferences: list[object] = []

    async def get_active_api_key_by_hash(self, key_hash: str) -> FakeApiKey | None:
        return self.api_keys.get(key_hash)

    async def touch_api_key(self, key_id: str) -> None:
        self.touched_key_ids.append(key_id)

    async def get_attachment_by_id(self, _attachment_id: str):
        return None

    def get_db(self) -> _FakeDbContext:
        return _FakeDbContext(self)

    async def get_umo_aliases(self, _umos: list[str] | None = None) -> list[object]:
        return []

    def add_api_key(self, raw_key: str, scopes: list[str]) -> None:
        self.api_keys[ApiKeyService.hash_key(raw_key)] = FakeApiKey(
            key_id="config-key",
            scopes=scopes,
        )


class FakeProviderManager:
    def __init__(self, config: dict) -> None:
        self.providers_config = config["provider"]
        self.provider_sources_config = config["provider_sources"]
        self.reloaded_providers: list[dict] = []
        self.deleted_provider_filters: list[dict] = []
        self.inst_map: dict[str, object] = {}
        self.provider_insts: list[object] = []
        self.stt_provider_insts: list[object] = []
        self.tts_provider_insts: list[object] = []
        self.set_provider_calls: list[dict] = []

    def get_merged_provider_config(self, provider_config: dict) -> dict:
        config = copy.deepcopy(provider_config)
        source_id = config.get("provider_source_id")
        if not source_id:
            return config
        source = next(
            (
                item
                for item in self.provider_sources_config
                if item.get("id") == source_id
            ),
            None,
        )
        if not source:
            return config
        merged = {**source, **config}
        merged["id"] = config["id"]
        return merged

    def get_provider_config_by_id(
        self,
        provider_id: str,
        *,
        merged: bool = False,
    ) -> dict | None:
        for provider in self.providers_config:
            if provider.get("id") != provider_id:
                continue
            if merged:
                return self.get_merged_provider_config(provider)
            return copy.deepcopy(provider)
        return None

    async def update_provider(self, origin_provider_id: str, new_config: dict) -> None:
        next_id = new_config.get("id")
        for provider in self.providers_config:
            if provider.get("id") == next_id and next_id != origin_provider_id:
                raise ValueError(f"Provider ID {next_id} already exists")
        for idx, provider in enumerate(self.providers_config):
            if provider.get("id") == origin_provider_id:
                self.providers_config[idx] = copy.deepcopy(new_config)
                await self.reload(new_config)
                return
        raise ValueError(f"Provider ID {origin_provider_id} not found")

    async def create_provider(self, new_config: dict) -> None:
        next_id = new_config.get("id")
        if any(provider.get("id") == next_id for provider in self.providers_config):
            raise ValueError(f"Provider ID {next_id} already exists")
        self.providers_config.append(copy.deepcopy(new_config))

    async def delete_provider(
        self,
        provider_id: str | None = None,
        provider_source_id: str | None = None,
    ) -> None:
        self.deleted_provider_filters.append(
            {"provider_id": provider_id, "provider_source_id": provider_source_id}
        )
        if provider_id:
            self.providers_config[:] = [
                provider
                for provider in self.providers_config
                if provider.get("id") != provider_id
            ]
        if provider_source_id:
            self.providers_config[:] = [
                provider
                for provider in self.providers_config
                if provider.get("provider_source_id") != provider_source_id
            ]

    async def reload(self, provider: dict) -> None:
        self.reloaded_providers.append(copy.deepcopy(provider))

    async def set_provider(self, provider_id: str, provider_type, umo: str) -> None:
        self.set_provider_calls.append(
            {
                "provider_id": provider_id,
                "provider_type": provider_type,
                "umo": umo,
            }
        )


class FakeProviderInstance:
    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        self.tested = False

    def meta(self):
        return SimpleNamespace(
            id=self.provider_id,
            model="kimi-k2-0905-preview",
            provider_type=SimpleNamespace(value="chat_completion"),
        )

    async def test(self) -> None:
        self.tested = True


class FakePlatform:
    def __init__(self, platform_id: str) -> None:
        self.platform_id = platform_id
        self.sent_messages = []

    def meta(self):
        return SimpleNamespace(id=self.platform_id, name=self.platform_id)

    async def send_by_session(self, session, message_chain) -> None:
        self.sent_messages.append((session, message_chain))


class FakeUmopConfigRouter:
    def __init__(self) -> None:
        self.umop_to_conf_id: dict[str, str] = {}

    async def update_routing_data(self, new_routing: dict[str, str]) -> None:
        self.umop_to_conf_id = dict(new_routing)

    async def update_route(self, umo: str, conf_id: str) -> None:
        self.umop_to_conf_id[umo] = conf_id

    async def delete_route(self, umo: str) -> None:
        self.umop_to_conf_id.pop(umo, None)


class FakeAstrBotConfig(dict):
    def save_config(self, post_config: dict) -> None:
        self.clear()
        self.update(copy.deepcopy(post_config))


def _build_fake_config() -> dict:
    return FakeAstrBotConfig(
        {
            "platform": [
                {
                    "id": "webchat-main",
                    "type": "webchat",
                    "enable": True,
                    "settings": {"session_timeout": 60},
                }
            ],
            "provider_sources": [
                {
                    "id": "openai-source",
                    "type": "openai_chat_completion",
                    "provider_type": "chat_completion",
                    "api_base": "https://api.example.test/v1",
                    "key": ["test-key"],
                }
            ],
            "provider": [
                {
                    "id": "gpt-mini",
                    "provider_source_id": "openai-source",
                    "model": "gpt-4o-mini",
                    "enable": True,
                },
                {
                    "id": "agent-runner",
                    "type": "dify",
                    "provider_type": "agent_runner",
                    "enable": False,
                },
            ],
        }
    )


async def _request_json(request: Request, *, silent: bool = False):
    try:
        return await request.json()
    except Exception:
        if silent:
            return None
        raise


def _register_legacy_routes(
    app: FastAPI,
    config: dict,
    provider_manager: FakeProviderManager,
) -> None:
    def _legacy_username(request: Request) -> str:
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.removeprefix("Bearer ").strip()
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload["username"]

    def compat_get(path: str):
        return app.get(path, include_in_schema=False)

    def compat_post(path: str):
        return app.post(path, include_in_schema=False)

    def compat_api_route(path: str, methods: list[str]):
        return app.api_route(path, methods=methods, include_in_schema=False)

    @compat_get("/api/config/platform/list")
    async def legacy_platform_list():
        return ok({"platforms": config["platform"]})

    @compat_get("/api/config/provider/list")
    async def legacy_provider_list(request: Request):
        provider_type = request.query_params.get("provider_type")
        provider_types = provider_type.split(",") if provider_type else []
        provider_source_types = {
            source["id"]: source.get("provider_type", "chat_completion")
            for source in provider_manager.provider_sources_config
        }
        providers = []
        for provider in provider_manager.providers_config:
            source_id = provider.get("provider_source_id")
            if source_id:
                if provider_source_types.get(source_id) in provider_types:
                    providers.append(
                        provider_manager.get_merged_provider_config(provider)
                    )
                continue
            if provider.get("provider_type") in provider_types:
                providers.append(provider)
        return ok(providers)

    @compat_get("/api/stat/start-time")
    async def legacy_start_time():
        return ok({"start_time": 1234567890})

    @compat_get("/api/session/active-umos")
    async def legacy_active_umos():
        return ok(
            {
                "umos": ["webchat:FriendMessage:webchat!user!session-1"],
                "umo_infos": [
                    {
                        "umo": "webchat:FriendMessage:webchat!user!session-1",
                        "platform": "webchat",
                        "message_type": "FriendMessage",
                        "session_id": "webchat!user!session-1",
                    }
                ],
            }
        )

    @compat_get("/api/plugin/get")
    async def legacy_plugin_list(request: Request):
        return ok(
            {
                "plugins": [{"name": "astrbot_plugin_demo"}],
                "legacy_username": _legacy_username(request),
            }
        )

    @compat_post("/api/plugin/off")
    async def legacy_plugin_off(request: Request):
        return ok(
            {
                "payload": await _request_json(request),
                "legacy_username": _legacy_username(request),
            }
        )

    @compat_post("/api/plugin/on")
    async def legacy_plugin_on(request: Request):
        return ok(
            {
                "payload": await _request_json(request),
                "legacy_username": _legacy_username(request),
            }
        )

    @compat_get("/api/plugin/detail")
    async def legacy_plugin_detail(request: Request):
        return ok({"name": request.query_params.get("name")})

    @compat_post("/api/plugin/uninstall")
    async def legacy_plugin_uninstall(request: Request):
        return ok({"payload": await _request_json(request)})

    @compat_get("/api/plugin/readme")
    async def legacy_plugin_readme(request: Request):
        return ok({"name": request.query_params.get("name"), "content": "readme"})

    @compat_get("/api/plugin/changelog")
    async def legacy_plugin_changelog(request: Request):
        return ok({"name": request.query_params.get("name"), "content": "changes"})

    @compat_post("/api/plugin/reload")
    async def legacy_plugin_reload(request: Request):
        return ok({"payload": await _request_json(request)})

    @compat_post("/api/plugin/update")
    async def legacy_plugin_update(request: Request):
        return ok({"payload": await _request_json(request)})

    @compat_post("/api/plugin/check-compat")
    async def legacy_plugin_check_compat(request: Request):
        return ok(
            {
                "payload": await _request_json(request),
                "legacy_username": _legacy_username(request),
            }
        )

    @compat_get("/api/config/get")
    async def legacy_config_get(request: Request):
        return ok(
            {
                "plugin_name": request.query_params.get("plugin_name"),
                "schema": {"type": "object"},
            }
        )

    @compat_post("/api/config/plugin/update")
    async def legacy_plugin_config_update(request: Request):
        return ok(
            {
                "plugin_name": request.query_params.get("plugin_name"),
                "payload": await _request_json(request),
            }
        )

    @compat_api_route("/api/plug/{plugin_path:path}", methods=["GET", "POST"])
    async def legacy_plugin_extension(plugin_path: str, request: Request):
        return ok(
            {
                "plugin_path": plugin_path,
                "method": request.method,
                "payload": await _request_json(request, silent=True),
                "legacy_username": _legacy_username(request),
            }
        )

    @compat_get("/api/config/file/get")
    async def legacy_config_file_get(request: Request):
        return ok(
            {
                "scope": request.query_params.get("scope"),
                "name": request.query_params.get("name"),
                "key": request.query_params.get("key"),
            }
        )

    @compat_post("/api/config/file/upload")
    async def legacy_config_file_upload(request: Request):
        return ok(
            {
                "scope": request.query_params.get("scope"),
                "name": request.query_params.get("name"),
                "key": request.query_params.get("key"),
                "payload": await _request_json(request, silent=True),
            }
        )

    @compat_post("/api/config/file/delete")
    async def legacy_config_file_delete(request: Request):
        return ok(
            {
                "scope": request.query_params.get("scope"),
                "name": request.query_params.get("name"),
                "payload": await _request_json(request),
            }
        )

    @compat_post("/api/commands/toggle")
    async def legacy_command_toggle(request: Request):
        return ok({"payload": await _request_json(request)})

    @compat_get("/api/tools/list")
    async def legacy_tool_list():
        return ok({"tools": [{"name": "demo_tool"}]})

    @compat_post("/api/tools/mcp/update")
    async def legacy_mcp_update(request: Request):
        return ok({"payload": await _request_json(request)})

    @compat_post("/api/tools/mcp/delete")
    async def legacy_mcp_delete(request: Request):
        return ok({"payload": await _request_json(request)})

    @compat_post("/api/tools/mcp/test")
    async def legacy_mcp_test(request: Request):
        return ok({"payload": await _request_json(request)})

    @compat_post("/api/tools/mcp/sync-provider")
    async def legacy_mcp_sync_provider(request: Request):
        return ok({"payload": await _request_json(request)})

    @compat_get("/api/skills")
    async def legacy_skill_list():
        return ok({"skills": [{"name": "demo_skill"}], "runtime": "local"})

    @compat_post("/api/skills/update")
    async def legacy_skill_update(request: Request):
        return ok({"payload": await _request_json(request)})

    @compat_post("/api/skills/delete")
    async def legacy_skill_delete(request: Request):
        return ok({"payload": await _request_json(request)})

    @compat_get("/api/skills/download")
    async def legacy_skill_download(request: Request):
        return ok({"name": request.query_params.get("name")})

    @compat_get("/api/skills/files")
    async def legacy_skill_files(request: Request):
        return ok(
            {
                "name": request.query_params.get("name"),
                "path": request.query_params.get("path"),
            }
        )

    @compat_get("/api/skills/file")
    async def legacy_skill_file_get(request: Request):
        return ok(
            {
                "name": request.query_params.get("name"),
                "path": request.query_params.get("path"),
            }
        )

    @compat_post("/api/skills/file")
    async def legacy_skill_file_update(request: Request):
        return ok({"payload": await _request_json(request)})

    @compat_post("/api/config/provider/get_embedding_dim")
    async def legacy_provider_embedding_dim(request: Request):
        return ok({"payload": await _request_json(request)})

    @compat_post("/api/persona/detail")
    async def legacy_persona_detail(request: Request):
        return ok({"payload": await _request_json(request)})

    @compat_post("/api/persona/update")
    async def legacy_persona_update(request: Request):
        return ok({"payload": await _request_json(request)})

    @compat_post("/api/persona/delete")
    async def legacy_persona_delete(request: Request):
        return ok({"payload": await _request_json(request)})

    @compat_post("/api/platform/registration/{bot_type}")
    async def legacy_platform_registration(bot_type: str, request: Request):
        return ok(
            {
                "bot_type": bot_type,
                "payload": await _request_json(request),
                "legacy_username": _legacy_username(request),
            }
        )

    @compat_api_route("/api/platform/webhook/{webhook_uuid}", methods=["GET", "POST"])
    async def legacy_platform_webhook(webhook_uuid: str, request: Request):
        payload = await _request_json(request, silent=True)
        return ok(
            {
                "webhook_uuid": webhook_uuid,
                "method": request.method,
                "payload": payload,
            }
        )

    @compat_get("/api/file/{file_token}")
    async def legacy_token_file(file_token: str):
        return PlainTextResponse(f"token:{file_token}")


@pytest.fixture
def fake_db() -> FakeDb:
    return FakeDb()


@pytest.fixture
def fake_core_lifecycle():
    config = _build_fake_config()
    provider_manager = FakeProviderManager(config)
    platform = FakePlatform("webchat-main")
    umop_config_router = FakeUmopConfigRouter()
    reloaded_config_ids = []
    platform_reload_configs = []
    terminated_platform_ids = []

    async def reload_pipeline_scheduler(config_id: str) -> None:
        reloaded_config_ids.append(config_id)

    async def reload_platform(config: dict) -> None:
        platform_reload_configs.append(copy.deepcopy(config))

    async def load_platform(config: dict) -> None:
        platform_reload_configs.append(copy.deepcopy(config))

    async def terminate_platform(platform_id: str) -> None:
        terminated_platform_ids.append(platform_id)

    return SimpleNamespace(
        astrbot_config=config,
        astrbot_config_mgr=SimpleNamespace(
            confs={"default": config}, default_conf=config
        ),
        reload_pipeline_scheduler=reload_pipeline_scheduler,
        reloaded_config_ids=reloaded_config_ids,
        platform_reload_configs=platform_reload_configs,
        terminated_platform_ids=terminated_platform_ids,
        umop_config_router=umop_config_router,
        platform_manager=SimpleNamespace(
            platform_insts=[platform],
            fake_platform=platform,
            reload=reload_platform,
            load_platform=load_platform,
            terminate_platform=terminate_platform,
            get_all_stats=lambda: {
                "platforms": [{"id": "webchat-main", "status": "running"}]
            },
        ),
        provider_manager=provider_manager,
        persona_mgr=SimpleNamespace(personas_v3=[]),
        plugin_manager=SimpleNamespace(
            context=SimpleNamespace(get_all_stars=lambda: [])
        ),
        kb_manager=None,
    )


@pytest.fixture
def asgi_app(fake_core_lifecycle, fake_db: FakeDb):
    app = create_v1_asgi_app(
        core_lifecycle=fake_core_lifecycle,
        db=fake_db,
        jwt_secret=JWT_SECRET,
    )
    _register_legacy_routes(
        app,
        fake_core_lifecycle.astrbot_config,
        fake_core_lifecycle.provider_manager,
    )
    return app


@pytest_asyncio.fixture
async def asgi_client(asgi_app):
    transport = httpx.ASGITransport(app=asgi_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client


def _jwt_headers() -> dict[str, str]:
    token = jwt.encode(
        {"username": "fastapi-v1-test"},
        JWT_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_v1_openapi_is_served_by_fastapi(asgi_client: httpx.AsyncClient):
    response = await asgi_client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    spec = response.json()
    assert spec["openapi"].startswith("3.")
    assert "/api/v1/bots" in spec["paths"]
    assert "/api/v1/providers" in spec["paths"]
    assert "/api/v1/plugins" in spec["paths"]
    assert "/api/v1/mcp/servers" in spec["paths"]
    assert "/api/v1/skills" in spec["paths"]


@pytest.mark.asyncio
async def test_v1_bots_matches_legacy_platform_list(asgi_client: httpx.AsyncClient):
    headers = _jwt_headers()

    legacy_response = await asgi_client.get(
        "/api/config/platform/list",
        headers=headers,
    )
    v1_response = await asgi_client.get("/api/v1/bots", headers=headers)

    assert legacy_response.status_code == 200
    assert v1_response.status_code == 200
    legacy_data = legacy_response.json()
    v1_data = v1_response.json()
    assert legacy_data["status"] == "ok"
    assert v1_data["status"] == "ok"
    assert v1_data["data"]["bots"] == legacy_data["data"]["platforms"]


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
    def fake_save_config(post_config: dict, config: FakeAstrBotConfig, is_core=False):
        config.save_config(post_config)

    monkeypatch.setattr(config_service, "save_config", fake_save_config)

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
async def test_v1_providers_matches_legacy_chat_provider_list(
    asgi_client: httpx.AsyncClient,
):
    headers = _jwt_headers()

    legacy_response = await asgi_client.get(
        "/api/config/provider/list?provider_type=chat_completion",
        headers=headers,
    )
    v1_response = await asgi_client.get(
        "/api/v1/providers?capability=chat",
        headers=headers,
    )

    assert legacy_response.status_code == 200
    assert v1_response.status_code == 200
    legacy_data = legacy_response.json()
    v1_data = v1_response.json()
    assert legacy_data["status"] == "ok"
    assert v1_data["status"] == "ok"
    assert v1_data["data"]["providers"] == legacy_data["data"]


@pytest.mark.asyncio
async def test_v1_provider_source_rename_updates_provider_refs(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "astrbot.dashboard.services.config_service.save_config",
        lambda *_args, **_kwargs: None,
    )

    response = await asgi_client.put(
        "/api/v1/provider-sources/openai-source",
        json={
            "config": {
                "id": "openai-renamed",
                "type": "openai_chat_completion",
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
async def test_v1_provider_update_keeps_legacy_id_rename_behavior(
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
            }
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    config = fake_core_lifecycle.astrbot_config
    assert config["provider"][0]["id"] == "gpt-renamed"
    assert fake_core_lifecycle.provider_manager.reloaded_providers == [
        config["provider"][0]
    ]


@pytest.mark.asyncio
async def test_v1_create_standalone_provider_matches_legacy_capability(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    response = await asgi_client.post(
        "/api/v1/providers",
        json={
            "config": {
                "id": "tts-main",
                "type": "edge_tts",
                "provider_type": "text_to_speech",
                "enable": True,
            }
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert fake_core_lifecycle.astrbot_config["provider"][-1] == {
        "id": "tts-main",
        "type": "edge_tts",
        "provider_type": "text_to_speech",
        "enable": True,
    }


@pytest.mark.asyncio
async def test_v1_safe_provider_routes_accept_slash_ids(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(config_service, "save_config", lambda *_args, **_kwargs: None)

    source_id = "https://example.com/source"
    provider_id = "qianxun/kimi-k2-0905-preview"
    config = fake_core_lifecycle.astrbot_config
    config["provider_sources"].append(
        {
            "id": source_id,
            "type": "openai_chat_completion",
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
        "/api/v1/providers/by-id",
        params={"provider_id": provider_id, "merged": True},
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
    safe_test_response = await asgi_client.post(
        "/api/v1/providers/test",
        json={"provider_id": provider_id},
        headers=headers,
    )
    enabled_response = await asgi_client.patch(
        "/api/v1/providers/enabled",
        json={"provider_id": provider_id, "enabled": False},
        headers=headers,
    )
    embedding_response = await asgi_client.post(
        "/api/v1/providers/embedding-dimension",
        json={"provider_id": provider_id, "provider_config": {"model": "model/a"}},
        headers=headers,
    )
    source_models_response = await asgi_client.get(
        "/api/v1/provider-sources/models",
        params={"source_id": source_id},
        headers=headers,
    )
    source_providers_response = await asgi_client.get(
        "/api/v1/provider-sources/providers",
        params={"source_id": source_id},
        headers=headers,
    )

    assert get_response.status_code == 200
    assert get_response.json()["data"]["provider"]["id"] == provider_id
    assert schema_response.status_code == 200
    assert "config_schema" in schema_response.json()["data"]
    assert path_test_response.status_code == 200
    assert path_test_response.json()["data"]["status"] == "available"
    assert safe_test_response.status_code == 200
    assert safe_test_response.json()["data"]["status"] == "available"
    assert provider_instance.tested is True
    assert enabled_response.status_code == 200
    assert config["provider"][-1]["enable"] is False
    assert embedding_response.status_code == 200
    assert embedding_response.json()["data"]["payload"] == {
        "provider_id": provider_id,
        "provider_config": {"model": "model/a"},
    }
    assert source_models_response.status_code == 200
    assert source_models_response.json()["data"]["provider_source_id"] == source_id
    assert source_providers_response.status_code == 200
    assert source_providers_response.json()["data"]["providers"][0]["id"] == provider_id


@pytest.mark.asyncio
async def test_v1_safe_bot_routes_accept_slash_ids(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(config_service, "save_config", lambda *_args, **_kwargs: None)

    bot_id = "group/a"
    fake_core_lifecycle.astrbot_config["platform"].append(
        {"id": bot_id, "type": "webchat", "enable": True}
    )
    headers = _jwt_headers()

    get_response = await asgi_client.get(
        "/api/v1/bots/by-id",
        params={"bot_id": bot_id},
        headers=headers,
    )
    enabled_response = await asgi_client.patch(
        "/api/v1/bots/enabled",
        json={"bot_id": bot_id, "enabled": False},
        headers=headers,
    )
    test_response = await asgi_client.post(
        "/api/v1/bots/test",
        json={"bot_id": bot_id},
        headers=headers,
    )
    delete_response = await asgi_client.delete(
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


@pytest.mark.asyncio
async def test_v1_config_scope_accepts_api_key(
    asgi_client: httpx.AsyncClient,
    fake_db: FakeDb,
):
    raw_key = "abk_fastapi_v1_config"
    fake_db.add_api_key(raw_key, scopes=["config"])

    response = await asgi_client.get(
        "/api/v1/bots",
        headers={"X-API-Key": raw_key},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert isinstance(data["data"]["bots"], list)
    assert fake_db.touched_key_ids == ["config-key"]


@pytest.mark.asyncio
async def test_legacy_route_still_works_through_asgi_app(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.get("/api/stat/start-time")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["start_time"] == 1234567890


@pytest.mark.asyncio
async def test_v1_plugin_bridge_accepts_api_key_and_uses_internal_jwt(
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
    assert data["data"]["plugins"] == [{"name": "astrbot_plugin_demo"}]
    assert data["data"]["legacy_username"] == "api_key:config-key"


@pytest.mark.asyncio
async def test_v1_plugin_enabled_patch_maps_to_legacy_payload(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.patch(
        "/api/v1/plugins/astrbot_plugin_demo/enabled",
        json={"enabled": False},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["payload"] == {"name": "astrbot_plugin_demo"}
    assert data["data"]["legacy_username"] == "fastapi-v1-test"


@pytest.mark.asyncio
async def test_v1_plugin_compatibility_check_maps_to_legacy(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.post(
        "/api/v1/plugins/compatibility/check",
        json={"plugin_ids": ["astrbot_plugin_demo"]},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["payload"] == {"plugin_ids": ["astrbot_plugin_demo"]}
    assert data["data"]["legacy_username"] == "fastapi-v1-test"


@pytest.mark.asyncio
async def test_v1_plugin_extension_maps_nested_plugin_path(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.post(
        "/api/v1/plugins/extensions/astrbot_plugin_demo/api/action",
        json={"value": "demo"},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"] == {
        "plugin_path": "astrbot_plugin_demo/api/action",
        "method": "POST",
        "payload": {"value": "demo"},
        "legacy_username": "fastapi-v1-test",
    }


@pytest.mark.asyncio
async def test_v1_plugin_config_file_routes_map_to_legacy_query(
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

    assert list_response.status_code == 200
    assert list_response.json()["data"] == {
        "scope": "plugin",
        "name": "astrbot_plugin_demo",
        "key": "assets",
    }
    assert upload_response.status_code == 200
    assert upload_response.json()["data"] == {
        "scope": "plugin",
        "name": "astrbot_plugin_demo",
        "key": "assets",
        "payload": {"filename": "demo.txt"},
    }
    assert delete_response.status_code == 200
    assert delete_response.json()["data"] == {
        "scope": "plugin",
        "name": "astrbot_plugin_demo",
        "payload": {"path": "demo.txt"},
    }


@pytest.mark.asyncio
async def test_v1_safe_plugin_routes_accept_slash_ids(
    asgi_client: httpx.AsyncClient,
):
    plugin_id = "plugin/foo"
    headers = _jwt_headers()

    detail_response = await asgi_client.get(
        "/api/v1/plugins/by-id",
        params={"plugin_id": plugin_id},
        headers=headers,
    )
    enabled_response = await asgi_client.patch(
        "/api/v1/plugins/enabled",
        json={"plugin_id": plugin_id, "enabled": False},
        headers=headers,
    )
    update_response = await asgi_client.post(
        "/api/v1/plugins/update",
        json={"plugin_id": plugin_id, "reinstall": True},
        headers=headers,
    )
    readme_response = await asgi_client.get(
        "/api/v1/plugins/readme",
        params={"plugin_id": plugin_id},
        headers=headers,
    )
    schema_response = await asgi_client.get(
        "/api/v1/plugins/config/schema",
        params={"plugin_id": plugin_id},
        headers=headers,
    )
    config_files_response = await asgi_client.get(
        "/api/v1/plugins/config-files",
        params={"plugin_id": plugin_id, "config_key": "assets/path"},
        headers=headers,
    )

    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["name"] == plugin_id
    assert enabled_response.status_code == 200
    assert enabled_response.json()["data"]["payload"] == {"name": plugin_id}
    assert update_response.status_code == 200
    assert update_response.json()["data"]["payload"] == {
        "name": plugin_id,
        "reinstall": True,
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
async def test_v1_safe_plugin_source_delete_accepts_slash_ids(
    asgi_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    source_id = "https://example.com/source"
    sources = [{"id": source_id}, {"id": "keep"}]

    async def fake_global_get(_key, _default=None):
        return list(sources)

    async def fake_global_put(_key, value):
        sources[:] = value

    monkeypatch.setattr(
        "astrbot.dashboard.services.plugin_service.sp.global_get",
        fake_global_get,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.plugin_service.sp.global_put",
        fake_global_put,
    )

    response = await asgi_client.delete(
        "/api/v1/plugin-sources/by-id",
        params={"source_id": source_id},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    assert response.json()["data"]["sources"] == [{"id": "keep"}]


@pytest.mark.asyncio
async def test_v1_command_patch_maps_to_legacy_toggle(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.patch(
        "/api/v1/commands/plugin.handler",
        json={"enabled": False},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["payload"] == {
        "handler_full_name": "plugin.handler",
        "enabled": False,
    }


@pytest.mark.asyncio
async def test_v1_bot_type_registration_maps_to_legacy(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.post(
        "/api/v1/bot-types/webchat/registration",
        json={"registration_code": "abc123"},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"] == {
        "bot_type": "webchat",
        "payload": {"registration_code": "abc123"},
        "legacy_username": "fastapi-v1-test",
    }


@pytest.mark.asyncio
async def test_v1_token_file_is_public_compat_route(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.get("/api/v1/files/tokens/demo-token")

    assert response.status_code == 200
    assert response.text == "token:demo-token"
    assert response.headers["content-type"].startswith("text/plain")


def test_v1_openapi_compat_websocket_routes_are_mounted(asgi_app):
    websocket_paths = {
        route.path
        for route in asgi_app.router.routes
        if "websocket" in route.__class__.__name__.lower()
    }

    assert "/api/v1/chat/ws" in websocket_paths
    assert "/api/v1/live-chat/ws" in websocket_paths
    assert "/api/v1/unified-chat/ws" in websocket_paths


def test_legacy_config_aliases_are_registered_on_fastapi(asgi_app):
    http_paths = {
        route.path
        for route in asgi_app.router.routes
        if "route" in route.__class__.__name__.lower()
    }

    assert "/api/config/platform/list" in http_paths
    assert "/api/config/provider/list" in http_paths
    assert "/api/config/provider_sources/update" in http_paths


@pytest.mark.asyncio
async def test_v1_mcp_enabled_patch_maps_to_legacy_active(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.patch(
        "/api/v1/mcp/servers/demo-server/enabled",
        json={"enabled": False},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["payload"] == {
        "name": "demo-server",
        "oldName": "demo-server",
        "active": False,
    }


@pytest.mark.asyncio
async def test_v1_safe_mcp_routes_accept_slash_server_names(
    asgi_client: httpx.AsyncClient,
):
    server_name = "modelscope/demo"
    headers = _jwt_headers()

    enabled_response = await asgi_client.patch(
        "/api/v1/mcp/servers/enabled",
        json={"server_name": server_name, "enabled": False},
        headers=headers,
    )
    test_response = await asgi_client.post(
        "/api/v1/mcp/servers/test",
        json={"server_name": server_name},
        headers=headers,
    )
    delete_response = await asgi_client.delete(
        "/api/v1/mcp/servers/by-name",
        params={"server_name": server_name},
        headers=headers,
    )
    sync_response = await asgi_client.post(
        "/api/v1/mcp/providers/modelscope/sync",
        json={"access_token": "token"},
        headers=headers,
    )

    assert enabled_response.status_code == 200
    assert enabled_response.json()["data"]["payload"] == {
        "name": server_name,
        "oldName": server_name,
        "active": False,
    }
    assert test_response.status_code == 200
    assert test_response.json()["data"]["payload"] == {
        "mcp_server_config": {"name": server_name}
    }
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["payload"] == {"name": server_name}
    assert sync_response.status_code == 200
    assert sync_response.json()["data"]["payload"] == {
        "name": "modelscope",
        "access_token": "token",
    }


@pytest.mark.asyncio
async def test_v1_skill_bridge_uses_skill_scope(
    asgi_client: httpx.AsyncClient,
    fake_db: FakeDb,
):
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


@pytest.mark.asyncio
async def test_v1_safe_skill_routes_accept_slash_names(
    asgi_client: httpx.AsyncClient,
):
    skill_name = "skill/foo"
    headers = _jwt_headers()

    enabled_response = await asgi_client.patch(
        "/api/v1/skills/by-name",
        json={"skill_name": skill_name, "enabled": False},
        headers=headers,
    )
    archive_response = await asgi_client.get(
        "/api/v1/skills/archive",
        params={"skill_name": skill_name},
        headers=headers,
    )
    files_response = await asgi_client.get(
        "/api/v1/skills/files",
        params={"skill_name": skill_name, "path": "src"},
        headers=headers,
    )
    file_response = await asgi_client.get(
        "/api/v1/skills/file",
        params={"skill_name": skill_name, "path": "src/main.py"},
        headers=headers,
    )
    update_file_response = await asgi_client.put(
        "/api/v1/skills/file",
        json={"skill_name": skill_name, "path": "src/main.py", "content": "print(1)"},
        headers=headers,
    )
    delete_response = await asgi_client.delete(
        "/api/v1/skills/by-name",
        params={"skill_name": skill_name},
        headers=headers,
    )

    assert enabled_response.status_code == 200
    assert enabled_response.json()["data"]["payload"] == {
        "name": skill_name,
        "active": False,
    }
    assert archive_response.status_code == 200
    assert archive_response.json()["data"]["name"] == skill_name
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
async def test_v1_safe_persona_routes_accept_slash_ids(
    asgi_client: httpx.AsyncClient,
):
    persona_id = "persona/foo"
    headers = _jwt_headers()

    detail_response = await asgi_client.get(
        "/api/v1/personas/by-id",
        params={"persona_id": persona_id},
        headers=headers,
    )
    update_response = await asgi_client.put(
        "/api/v1/personas/by-id",
        json={"persona_id": persona_id, "name": "Demo Persona"},
        headers=headers,
    )
    delete_response = await asgi_client.delete(
        "/api/v1/personas/by-id",
        params={"persona_id": persona_id},
        headers=headers,
    )

    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["payload"] == {"persona_id": persona_id}
    assert update_response.status_code == 200
    assert update_response.json()["data"]["payload"] == {
        "persona_id": persona_id,
        "name": "Demo Persona",
    }
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["payload"] == {"persona_id": persona_id}


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
async def test_v1_platform_webhook_is_public_compat_route(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.post(
        "/api/v1/webhooks/platforms/demo-hook",
        json={"challenge": "ping"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"] == {
        "webhook_uuid": "demo-hook",
        "method": "POST",
        "payload": {"challenge": "ping"},
    }
