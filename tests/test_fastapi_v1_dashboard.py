import copy
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import httpx
import jwt
import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

import astrbot.dashboard.services.config_service as config_service
from astrbot.core import file_token_service
from astrbot.dashboard.api.app import create_dashboard_asgi_app
from astrbot.dashboard.asgi_runtime import (
    FastAPIAppAdapter,
    g,
)
from astrbot.dashboard.asgi_runtime import (
    request as dashboard_request,
)
from astrbot.dashboard.responses import ok
from astrbot.dashboard.services.api_key_service import ApiKeyService
from astrbot.dashboard.services.auth_service import DASHBOARD_JWT_COOKIE_NAME
from astrbot.dashboard.services.skills_service import SkillArchive

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


class FakeLlmTools:
    def __init__(self) -> None:
        self.config = {
            "mcpServers": {
                "demo-server": {
                    "active": True,
                    "url": "https://example.com/demo-server",
                },
                "modelscope/demo": {
                    "active": True,
                    "url": "https://example.com/modelscope-demo",
                },
            }
        }
        self.mcp_server_runtime_view = {}
        self.func_list = []
        self.enabled_servers: list[tuple[str, dict]] = []
        self.disabled_servers: list[str] = []
        self.tested_configs: list[dict] = []
        self.synced_modelscope_tokens: list[str] = []

    def load_mcp_config(self) -> dict:
        return copy.deepcopy(self.config)

    def save_mcp_config(self, config: dict) -> bool:
        self.config = copy.deepcopy(config)
        return True

    async def test_mcp_server_connection(self, config: dict) -> list[str]:
        self.tested_configs.append(copy.deepcopy(config))
        return ["demo_tool"]

    async def sync_modelscope_mcp_servers(self, access_token: str) -> None:
        self.synced_modelscope_tokens.append(access_token)

    async def enable_mcp_server(
        self,
        name: str,
        config: dict,
        *,
        timeout: int,
    ) -> None:
        self.enabled_servers.append((name, copy.deepcopy(config)))

    async def disable_mcp_server(self, name: str, *, timeout: int) -> None:
        self.disabled_servers.append(name)

    def iter_builtin_tools(self) -> list:
        return []

    def is_builtin_tool(self, _tool_name: str) -> bool:
        return False

    def activate_llm_tool(self, _tool_name: str, *, star_map) -> bool:
        return True

    def deactivate_llm_tool(self, _tool_name: str) -> bool:
        return True


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
        self.llm_tools = FakeLlmTools()

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


@dataclass
class FakeConversation:
    cid: str
    user_id: str
    platform_id: str = "webchat-main"
    message_type: str = "FriendMessage"
    title: str = "Demo conversation"
    persona_id: str | None = "persona/foo"
    history: str = "[]"
    created_at: str = "2026-01-01T00:00:00"
    updated_at: str = "2026-01-01T00:00:00"


class FakeConversationManager:
    def __init__(self) -> None:
        user_id = "webchat:FriendMessage:webchat!user!session-1"
        self.conversations: dict[tuple[str, str], FakeConversation] = {
            (user_id, "conversation/with/slash"): FakeConversation(
                cid="conversation/with/slash",
                user_id=user_id,
            )
        }

    async def get_filtered_conversations(
        self,
        *,
        page: int,
        page_size: int,
        platforms: list[str],
        message_types: list[str],
        search_query: str,
        exclude_ids: list[str],
        exclude_platforms: list[str],
    ):
        conversations = list(self.conversations.values())
        if platforms:
            conversations = [
                conversation
                for conversation in conversations
                if conversation.platform_id in platforms
            ]
        if message_types:
            conversations = [
                conversation
                for conversation in conversations
                if conversation.message_type in message_types
            ]
        if search_query:
            conversations = [
                conversation
                for conversation in conversations
                if search_query in conversation.title
            ]
        conversations = [
            conversation
            for conversation in conversations
            if conversation.cid not in exclude_ids
            and conversation.platform_id not in exclude_platforms
        ]
        start = (page - 1) * page_size
        return conversations[start : start + page_size], len(conversations)

    async def get_conversation(
        self,
        *,
        unified_msg_origin: str,
        conversation_id: str,
    ):
        return self.conversations.get((unified_msg_origin, conversation_id))

    async def update_conversation(
        self,
        *,
        unified_msg_origin: str,
        conversation_id: str,
        title: str | None = None,
        persona_id: str | None = None,
        history=None,
    ) -> None:
        conversation = self.conversations[(unified_msg_origin, conversation_id)]
        if title is not None:
            conversation.title = title
        if persona_id is not None:
            conversation.persona_id = persona_id
        if history is not None:
            conversation.history = history

    async def delete_conversation(
        self,
        *,
        unified_msg_origin: str,
        conversation_id: str,
    ) -> None:
        self.conversations.pop((unified_msg_origin, conversation_id), None)


class FakePlatform:
    def __init__(self, platform_id: str) -> None:
        self.platform_id = platform_id
        self.config = {"webhook_uuid": "demo-hook"}
        self.sent_messages = []

    def meta(self):
        return SimpleNamespace(id=self.platform_id, name=self.platform_id)

    def unified_webhook(self) -> bool:
        return True

    async def webhook_callback(self, request_obj):
        return {
            "webhook_uuid": self.config["webhook_uuid"],
            "method": request_obj.method,
            "payload": await request_obj.get_json(silent=True),
        }

    async def send_by_session(self, session, message_chain) -> None:
        self.sent_messages.append((session, message_chain))


class FakePersonaManager:
    def __init__(self) -> None:
        self.personas: dict[str, SimpleNamespace] = {
            "persona/foo": self._persona(
                persona_id="persona/foo",
                system_prompt="Demo persona",
            )
        }
        self.folders: dict[str, SimpleNamespace] = {}
        self.sort_items: list[dict] = []

    @staticmethod
    def _persona(
        *,
        persona_id: str,
        system_prompt: str,
        begin_dialogs: list | None = None,
        tools: list[str] | None = None,
        skills: list[str] | None = None,
        custom_error_message: str | None = None,
        folder_id: str | None = None,
        sort_order: int = 0,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            persona_id=persona_id,
            system_prompt=system_prompt,
            begin_dialogs=begin_dialogs,
            tools=tools,
            skills=skills,
            custom_error_message=custom_error_message,
            folder_id=folder_id,
            sort_order=sort_order,
            created_at=None,
            updated_at=None,
        )

    @staticmethod
    def _folder(
        *,
        folder_id: str,
        name: str,
        parent_id: str | None = None,
        description: str | None = None,
        sort_order: int = 0,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            folder_id=folder_id,
            name=name,
            parent_id=parent_id,
            description=description,
            sort_order=sort_order,
            created_at=None,
            updated_at=None,
        )

    async def get_all_personas(self) -> list[SimpleNamespace]:
        return list(self.personas.values())

    async def get_personas_by_folder(
        self,
        folder_id: str | None,
    ) -> list[SimpleNamespace]:
        return [
            persona
            for persona in self.personas.values()
            if persona.folder_id == folder_id
        ]

    async def get_persona(self, persona_id: str):
        return self.personas.get(persona_id)

    async def create_persona(self, **kwargs):
        persona = self._persona(**kwargs)
        self.personas[persona.persona_id] = persona
        return persona

    async def update_persona(self, persona_id: str, **kwargs) -> None:
        persona = self.personas[persona_id]
        for key, value in kwargs.items():
            if key in ("tools", "skills", "custom_error_message") or value is not None:
                setattr(persona, key, value)

    async def delete_persona(self, persona_id: str) -> None:
        self.personas.pop(persona_id, None)

    async def move_persona_to_folder(
        self,
        persona_id: str,
        folder_id: str | None,
    ) -> None:
        self.personas[persona_id].folder_id = folder_id

    async def get_folders(self, parent_id: str | None) -> list[SimpleNamespace]:
        return [
            folder for folder in self.folders.values() if folder.parent_id == parent_id
        ]

    async def get_folder_tree(self) -> list:
        return []

    async def get_folder(self, folder_id: str):
        return self.folders.get(folder_id)

    async def create_folder(self, **kwargs):
        folder_id = kwargs.get("folder_id") or kwargs["name"]
        folder = self._folder(folder_id=folder_id, **kwargs)
        self.folders[folder.folder_id] = folder
        return folder

    async def update_folder(self, folder_id: str, **kwargs) -> None:
        folder = self.folders[folder_id]
        for key, value in kwargs.items():
            if value is not None:
                setattr(folder, key, value)

    async def delete_folder(self, folder_id: str) -> None:
        self.folders.pop(folder_id, None)

    async def batch_update_sort_order(self, items: list[dict]) -> None:
        self.sort_items = list(items)


class FakeUmopConfigRouter:
    def __init__(self) -> None:
        self.umop_to_conf_id: dict[str, str] = {}

    async def update_routing_data(self, new_routing: dict[str, str]) -> None:
        self.umop_to_conf_id = dict(new_routing)

    async def update_route(self, umo: str, conf_id: str) -> None:
        self.umop_to_conf_id[umo] = conf_id

    async def delete_route(self, umo: str) -> None:
        self.umop_to_conf_id.pop(umo, None)


class FakeAstrBotUpdator:
    async def check_update(self, *_args, **_kwargs):
        return None

    async def get_releases(self):
        return []

    async def update(self, *_args, **_kwargs) -> None:
        return None

    async def download_update_package(self, *_args, **kwargs):
        return kwargs.get("path", "temp.zip")

    def apply_update_package(self, *_args, **_kwargs) -> None:
        return None


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


def _register_dashboard_alias_routes(
    app: FastAPI,
    config: dict,
    provider_manager: FakeProviderManager,
) -> None:
    def _alias_username(request: Request) -> str:
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.removeprefix("Bearer ").strip()
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload["username"]

    def alias_get(path: str):
        return app.get(path, include_in_schema=False)

    def alias_post(path: str):
        return app.post(path, include_in_schema=False)

    def alias_api_route(path: str, methods: list[str]):
        return app.api_route(path, methods=methods, include_in_schema=False)

    @alias_get("/api/config/platform/list")
    async def dashboard_alias_platform_list():
        return ok({"platforms": config["platform"]})

    @alias_get("/api/config/provider/list")
    async def dashboard_alias_provider_list(request: Request):
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

    @alias_get("/api/stat/start-time")
    async def dashboard_alias_start_time():
        return ok({"start_time": 1234567890})

    @alias_get("/api/session/active-umos")
    async def dashboard_alias_active_umos():
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

    @alias_get("/api/plugin/get")
    async def dashboard_alias_plugin_list(request: Request):
        return ok(
            {
                "plugins": [{"name": "astrbot_plugin_demo"}],
                "alias_username": _alias_username(request),
            }
        )

    @alias_post("/api/plugin/off")
    async def dashboard_alias_plugin_off(request: Request):
        return ok(
            {
                "payload": await _request_json(request),
                "alias_username": _alias_username(request),
            }
        )

    @alias_post("/api/plugin/on")
    async def dashboard_alias_plugin_on(request: Request):
        return ok(
            {
                "payload": await _request_json(request),
                "alias_username": _alias_username(request),
            }
        )

    @alias_get("/api/plugin/detail")
    async def dashboard_alias_plugin_detail(request: Request):
        return ok({"name": request.query_params.get("name")})

    @alias_post("/api/plugin/uninstall")
    async def dashboard_alias_plugin_uninstall(request: Request):
        return ok({"payload": await _request_json(request)})

    @alias_get("/api/plugin/readme")
    async def dashboard_alias_plugin_readme(request: Request):
        return ok({"name": request.query_params.get("name"), "content": "readme"})

    @alias_get("/api/plugin/changelog")
    async def dashboard_alias_plugin_changelog(request: Request):
        return ok({"name": request.query_params.get("name"), "content": "changes"})

    @alias_post("/api/plugin/reload")
    async def dashboard_alias_plugin_reload(request: Request):
        return ok({"payload": await _request_json(request)})

    @alias_post("/api/plugin/update")
    async def dashboard_alias_plugin_update(request: Request):
        return ok({"payload": await _request_json(request)})

    @alias_post("/api/plugin/check-compat")
    async def dashboard_alias_plugin_version_support(request: Request):
        return ok(
            {
                "payload": await _request_json(request),
                "alias_username": _alias_username(request),
            }
        )

    @alias_get("/api/config/get")
    async def dashboard_alias_config_get(request: Request):
        return ok(
            {
                "plugin_name": request.query_params.get("plugin_name"),
                "schema": {"type": "object"},
            }
        )

    @alias_post("/api/config/plugin/update")
    async def dashboard_alias_plugin_config_update(request: Request):
        return ok(
            {
                "plugin_name": request.query_params.get("plugin_name"),
                "payload": await _request_json(request),
            }
        )

    @alias_api_route("/api/plug/{plugin_path:path}", methods=["GET", "POST"])
    async def dashboard_alias_plugin_extension(plugin_path: str, request: Request):
        return ok(
            {
                "plugin_path": plugin_path,
                "method": request.method,
                "payload": await _request_json(request, silent=True),
                "alias_username": _alias_username(request),
            }
        )

    @alias_get("/api/config/file/get")
    async def dashboard_alias_config_file_get(request: Request):
        return ok(
            {
                "scope": request.query_params.get("scope"),
                "name": request.query_params.get("name"),
                "key": request.query_params.get("key"),
            }
        )

    @alias_post("/api/config/file/upload")
    async def dashboard_alias_config_file_upload(request: Request):
        return ok(
            {
                "scope": request.query_params.get("scope"),
                "name": request.query_params.get("name"),
                "key": request.query_params.get("key"),
                "payload": await _request_json(request, silent=True),
            }
        )

    @alias_post("/api/config/file/delete")
    async def dashboard_alias_config_file_delete(request: Request):
        return ok(
            {
                "scope": request.query_params.get("scope"),
                "name": request.query_params.get("name"),
                "payload": await _request_json(request),
            }
        )

    @alias_get("/api/skills")
    async def dashboard_alias_skill_list():
        return ok({"skills": [{"name": "demo_skill"}], "runtime": "local"})

    @alias_post("/api/skills/update")
    async def dashboard_alias_skill_update(request: Request):
        return ok({"payload": await _request_json(request)})

    @alias_post("/api/skills/delete")
    async def dashboard_alias_skill_delete(request: Request):
        return ok({"payload": await _request_json(request)})

    @alias_get("/api/skills/download")
    async def dashboard_alias_skill_download(request: Request):
        return ok({"name": request.query_params.get("name")})

    @alias_get("/api/skills/files")
    async def dashboard_alias_skill_files(request: Request):
        return ok(
            {
                "name": request.query_params.get("name"),
                "path": request.query_params.get("path"),
            }
        )

    @alias_get("/api/skills/file")
    async def dashboard_alias_skill_file_get(request: Request):
        return ok(
            {
                "name": request.query_params.get("name"),
                "path": request.query_params.get("path"),
            }
        )

    @alias_post("/api/skills/file")
    async def dashboard_alias_skill_file_update(request: Request):
        return ok({"payload": await _request_json(request)})

    @alias_post("/api/config/provider/get_embedding_dim")
    async def dashboard_alias_provider_embedding_dim(request: Request):
        return ok({"payload": await _request_json(request)})

    @alias_get("/api/file/{file_token}")
    async def dashboard_alias_token_file(file_token: str):
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

    demo_plugin = SimpleNamespace(
        name="astrbot_plugin_demo",
        repo=None,
        author="demo",
        desc="Demo plugin",
        version="1.0.0",
        reserved=False,
        activated=True,
        display_name="AstrBot Plugin Demo",
        logo=None,
        logo_path=None,
        support_platforms=[],
        astrbot_version="",
        i18n={},
        root_dir_name=None,
        star_handler_full_names=[],
        skills=[],
    )

    async def turn_off_plugin(plugin_name: str) -> None:
        if plugin_name == demo_plugin.name:
            demo_plugin.activated = False

    async def turn_on_plugin(plugin_name: str) -> None:
        if plugin_name == demo_plugin.name:
            demo_plugin.activated = True

    async def reload_plugin(plugin_name: str | None = None):
        return True, f"reloaded {plugin_name or 'all'}"

    def validate_astrbot_version_specifier(version_spec: str):
        return True, f"supported: {version_spec}"

    async def plugin_extension(plugin_path: str):
        return ok(
            {
                "plugin_path": plugin_path,
                "method": dashboard_request.method,
                "payload": await dashboard_request.get_json(silent=True),
                "username": g.username,
            }
        )

    return SimpleNamespace(
        astrbot_config=config,
        astrbot_updator=FakeAstrBotUpdator(),
        start_time=1234567890,
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
        persona_mgr=FakePersonaManager(),
        conversation_manager=FakeConversationManager(),
        platform_message_history_manager=SimpleNamespace(),
        plugin_manager=SimpleNamespace(
            context=SimpleNamespace(get_all_stars=lambda: [demo_plugin]),
            failed_plugin_info=None,
            failed_plugin_dict={},
            turn_off_plugin=turn_off_plugin,
            turn_on_plugin=turn_on_plugin,
            reload=reload_plugin,
            _validate_astrbot_version_specifier=validate_astrbot_version_specifier,
        ),
        star_context=SimpleNamespace(
            registered_web_apis=[
                ("/<path:plugin_path>", plugin_extension, ["GET", "POST"], "demo")
            ]
        ),
        kb_manager=None,
    )


@pytest.fixture
def asgi_app(fake_core_lifecycle, fake_db: FakeDb):
    app = create_dashboard_asgi_app(
        core_lifecycle=fake_core_lifecycle,
        db=fake_db,
        jwt_secret=JWT_SECRET,
    )
    app.state.dashboard_app_adapter = FastAPIAppAdapter(app)
    _register_dashboard_alias_routes(
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


def test_fastapi_app_adapter_registers_on_app_state():
    app = FastAPI()
    adapter = FastAPIAppAdapter(app)

    assert app.state.dashboard_app_adapter is adapter


@pytest.mark.asyncio
async def test_v1_scope_dependencies_accept_dashboard_cookie(
    asgi_client: httpx.AsyncClient,
):
    token = jwt.encode(
        {"username": "fastapi-v1-cookie-test"},
        JWT_SECRET,
        algorithm="HS256",
    )

    response = await asgi_client.get(
        "/api/v1/bots",
        headers={"Cookie": f"{DASHBOARD_JWT_COOKIE_NAME}={token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert isinstance(data["data"]["bots"], list)


@pytest.mark.asyncio
async def test_v1_openapi_is_served_by_fastapi(asgi_client: httpx.AsyncClient):
    response = await asgi_client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    spec = response.json()
    assert spec["openapi"].startswith("3.")
    assert all(path.startswith("/api/v1/") for path in spec["paths"])
    assert "/api/v1/bots" in spec["paths"]
    assert "/api/v1/providers" in spec["paths"]
    assert "/api/v1/plugins" in spec["paths"]
    assert "/api/v1/conversations" in spec["paths"]
    assert "/api/v1/mcp/servers" in spec["paths"]
    assert "/api/v1/skills" in spec["paths"]


def test_static_openapi_v1_paths_include_api_version():
    spec_path = Path(__file__).resolve().parents[1] / "openspec" / "openapi-v1.yaml"
    in_paths = False
    path_keys = []
    for line in spec_path.read_text(encoding="utf-8").splitlines():
        if line == "paths:":
            in_paths = True
            continue
        if line == "components:":
            in_paths = False
        if in_paths and line.startswith("  /") and line.endswith(":"):
            path_keys.append(line.strip()[:-1])

    assert path_keys
    assert all(path.startswith("/api/v1/") for path in path_keys)


@pytest.mark.asyncio
async def test_dashboard_static_dist_files_are_served(
    fake_core_lifecycle,
    fake_db: FakeDb,
    tmp_path: Path,
):
    static_folder = tmp_path / "dist"
    assets_folder = static_folder / "assets"
    assets_folder.mkdir(parents=True)
    (static_folder / "index.html").write_text(
        '<script type="module" src="/assets/index-demo.js"></script>',
        encoding="utf-8",
    )
    (static_folder / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    (assets_folder / "index-demo.js").write_text(
        "window.__astrbotStaticTest = true;",
        encoding="utf-8",
    )
    (tmp_path / "secret.txt").write_text("outside static root", encoding="utf-8")

    app = create_dashboard_asgi_app(
        core_lifecycle=fake_core_lifecycle,
        db=fake_db,
        jwt_secret=JWT_SECRET,
        static_folder=str(static_folder),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        asset_response = await client.get("/assets/index-demo.js")
        favicon_response = await client.get("/favicon.svg")
        page_response = await client.get("/config")
        missing_response = await client.get("/assets/missing.js")
        traversal_response = await client.get("/assets/%2E%2E/%2E%2E/secret.txt")
        api_response = await client.get("/api/not-found")

    assert asset_response.status_code == 200
    assert "window.__astrbotStaticTest" in asset_response.text
    assert favicon_response.status_code == 200
    assert favicon_response.text == "<svg></svg>"
    assert page_response.status_code == 200
    assert "/assets/index-demo.js" in page_response.text
    assert missing_response.status_code == 404
    assert traversal_response.status_code == 404
    assert api_response.status_code == 404


@pytest.mark.asyncio
async def test_v1_backup_path_rejects_traversal(asgi_client: httpx.AsyncClient):
    download_response = await asgi_client.get(
        "/api/v1/backups/%2E%2E/secret.zip",
        params={"token": "demo"},
    )
    delete_response = await asgi_client.delete(
        "/api/v1/backups/%2E%2E/secret.zip",
        headers=_jwt_headers(),
    )

    assert download_response.status_code == 200
    assert delete_response.status_code == 200
    assert download_response.json()["status"] == "error"
    assert delete_response.json()["status"] == "error"
    assert "非法路径" in download_response.json()["message"]
    assert "非法路径" in delete_response.json()["message"]


@pytest.mark.asyncio
async def test_v1_openapi_uses_pydantic_request_bodies(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    spec = response.json()
    schemas = spec["components"]["schemas"]
    assert "BotRegistrationRequest" in schemas
    assert "ConfigContentRequest" in schemas

    bot_registration = spec["paths"]["/api/v1/bot-types/{bot_type}/registration"][
        "post"
    ]
    assert bot_registration["parameters"][0]["name"] == "bot_type"
    assert bot_registration["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/BotRegistrationRequest")

    config_profile_update = spec["paths"]["/api/v1/config-profiles/{config_id}"]["put"]
    assert config_profile_update["requestBody"]["content"]["application/json"][
        "schema"
    ]["$ref"].endswith("/ConfigContentRequest")

    system_config_update = spec["paths"]["/api/v1/system-config"]["put"]
    assert system_config_update["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/ConfigContentRequest")


@pytest.mark.asyncio
async def test_v1_conversation_path_id_allows_slash(asgi_client: httpx.AsyncClient):
    response = await asgi_client.get(
        "/api/v1/conversations/conversation%2Fwith%2Fslash",
        params={"user_id": "webchat:FriendMessage:webchat!user!session-1"},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["data"]["cid"] == "conversation/with/slash"


@pytest.mark.asyncio
async def test_v1_conversation_detail_requires_user_id(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.get(
        "/api/v1/conversations/conversation%2Fwith%2Fslash",
        headers=_jwt_headers(),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_dashboard_alias_conversation_detail_uses_fastapi_service(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.post(
        "/api/conversation/detail",
        json={
            "user_id": "webchat:FriendMessage:webchat!user!session-1",
            "cid": "conversation/with/slash",
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["data"]["cid"] == "conversation/with/slash"


@pytest.mark.asyncio
async def test_v1_bots_matches_dashboard_platform_alias_list(
    asgi_client: httpx.AsyncClient,
):
    headers = _jwt_headers()

    dashboard_alias_response = await asgi_client.get(
        "/api/config/platform/list",
        headers=headers,
    )
    v1_response = await asgi_client.get("/api/v1/bots", headers=headers)

    assert dashboard_alias_response.status_code == 200
    assert v1_response.status_code == 200
    dashboard_alias_data = dashboard_alias_response.json()
    v1_data = v1_response.json()
    assert dashboard_alias_data["status"] == "ok"
    assert v1_data["status"] == "ok"
    assert v1_data["data"]["bots"] == dashboard_alias_data["data"]["platforms"]


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
async def test_v1_providers_matches_dashboard_provider_alias_list(
    asgi_client: httpx.AsyncClient,
):
    headers = _jwt_headers()

    dashboard_alias_response = await asgi_client.get(
        "/api/config/provider/list?provider_type=chat_completion",
        headers=headers,
    )
    v1_response = await asgi_client.get(
        "/api/v1/providers?capability=chat",
        headers=headers,
    )

    assert dashboard_alias_response.status_code == 200
    assert v1_response.status_code == 200
    dashboard_alias_data = dashboard_alias_response.json()
    v1_data = v1_response.json()
    assert dashboard_alias_data["status"] == "ok"
    assert v1_data["status"] == "ok"
    assert v1_data["data"]["providers"] == dashboard_alias_data["data"]


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
async def test_v1_create_standalone_provider_matches_dashboard_alias_capability(
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
    assert fake_db.touched_key_ids == ["config-key", "config-key", "config-key"]


@pytest.mark.asyncio
async def test_dashboard_alias_route_still_works_through_asgi_app(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.get("/api/stat/start-time")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["start_time"] == 1234567890


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
    plugin = fake_core_lifecycle.plugin_manager.context.get_all_stars()[0]
    assert plugin.activated is False


@pytest.mark.asyncio
async def test_v1_plugin_version_support_check_uses_service(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.post(
        "/api/v1/plugins/version-support/check",
        json={"plugin_ids": ["astrbot_plugin_demo"]},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"] == {
        "supported": True,
        "message": "supported: ",
        "astrbot_version": "",
    }


@pytest.mark.asyncio
async def test_v1_plugin_url_install_accepts_download_url_and_missing_body(
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
        },
        headers=_jwt_headers(),
    )
    empty_body_response = await asgi_client.post(
        "/api/v1/plugins/install/url",
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
    }
    assert empty_body_response.status_code == 200
    empty_body_data = empty_body_response.json()
    assert empty_body_data["status"] == "error"
    assert empty_body_data["message"] == "插件操作失败，请查看服务端日志。"
    assert "missing url" not in str(empty_body_data)


@pytest.mark.asyncio
async def test_v1_plugin_update_all_hides_internal_exceptions(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.post(
        "/api/v1/plugins/update",
        json={"plugin_ids": ["astrbot_plugin_demo"]},
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
        "username": "fastapi-v1-test",
    }


@pytest.mark.asyncio
async def test_v1_plugin_extension_supports_astrbot_web_api(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    from astrbot.api.web import json_response
    from astrbot.api.web import request as plugin_request

    async def astrbot_web_plugin_extension(item_id: str):
        return json_response(
            {
                "item_id": item_id,
                "path_value": plugin_request.path_params["item_id"],
                "path": plugin_request.path,
                "method": plugin_request.method,
                "limit": plugin_request.query.get("limit", 20, type=int),
                "tags": plugin_request.query.getlist("tag"),
                "payload": await plugin_request.json(default={}),
                "username": plugin_request.username,
                "plugin_name": plugin_request.plugin_name,
            },
            status_code=201,
        )

    fake_core_lifecycle.star_context.registered_web_apis = [
        ("/web/<item_id>", astrbot_web_plugin_extension, ["POST"], "web")
    ]

    response = await asgi_client.post(
        "/api/v1/plugins/extensions/web/demo-item?limit=7&tag=one&tag=two",
        json={"value": "demo"},
        headers=_jwt_headers(),
    )

    assert response.status_code == 201
    data = response.json()
    assert data == {
        "item_id": "demo-item",
        "path_value": "demo-item",
        "path": "/api/v1/plugins/extensions/web/demo-item",
        "method": "POST",
        "limit": 7,
        "tags": ["one", "two"],
        "payload": {"value": "demo"},
        "username": "fastapi-v1-test",
        "plugin_name": "web",
    }


@pytest.mark.asyncio
async def test_v1_plugin_extension_astrbot_web_api_reads_form_and_files(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    from astrbot.api.web import PluginUploadFile, json_response
    from astrbot.api.web import request as plugin_request

    async def astrbot_web_upload_extension():
        form = await plugin_request.form()
        files = await plugin_request.files()
        upload: PluginUploadFile | None = files.get("file")
        assert isinstance(upload, PluginUploadFile)
        return json_response(
            {
                "tags": form.getlist("tag"),
                "filename": upload.filename,
                "content_type": upload.content_type,
                "content": (await upload.read()).decode("utf-8"),
            }
        )

    fake_core_lifecycle.star_context.registered_web_apis = [
        ("/upload", astrbot_web_upload_extension, ["POST"], "upload")
    ]

    response = await asgi_client.post(
        "/api/v1/plugins/extensions/upload",
        files=[
            ("tag", (None, "one")),
            ("tag", (None, "two")),
            ("file", ("demo.txt", b"hello", "text/plain")),
        ],
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {
        "tags": ["one", "two"],
        "filename": "demo.txt",
        "content_type": "text/plain",
        "content": "hello",
    }


def test_astrbot_web_request_requires_plugin_context():
    from astrbot.api.web import request as plugin_request

    with pytest.raises(RuntimeError, match="plugin Web API handler"):
        _ = plugin_request.method


def test_astrbot_web_request_proxy_exposes_typed_methods():
    from typing import get_type_hints

    from astrbot.api.web import (
        PluginMultiDict,
        PluginRequestProxy,
        PluginUploadFile,
    )
    from astrbot.api.web import request as plugin_request

    assert isinstance(plugin_request, PluginRequestProxy)
    assert get_type_hints(type(plugin_request).form)["return"] == PluginMultiDict[str]
    assert (
        get_type_hints(type(plugin_request).files)["return"]
        == PluginMultiDict[PluginUploadFile]
    )


@pytest.mark.asyncio
async def test_v1_plugin_extension_supports_quart_request_context(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    from quart import g as quart_g
    from quart import jsonify as quart_jsonify
    from quart import request as quart_request

    async def quart_plugin_extension(item_id: str):
        return quart_jsonify(
            {
                "status": "ok",
                "data": {
                    "item_id": item_id,
                    "path": quart_request.path,
                    "method": quart_request.method,
                    "source": quart_request.args.get("source"),
                    "payload": await quart_request.get_json(),
                    "username": quart_g.username,
                },
            }
        )

    fake_core_lifecycle.star_context.registered_web_apis = [
        ("/quart/<item_id>", quart_plugin_extension, ["POST"], "quart")
    ]

    response = await asgi_client.post(
        "/api/v1/plugins/extensions/quart/demo-item?source=v1",
        json={"value": "demo"},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"] == {
        "item_id": "demo-item",
        "path": "/api/plug/quart/demo-item",
        "method": "POST",
        "source": "v1",
        "payload": {"value": "demo"},
        "username": "fastapi-v1-test",
    }


@pytest.mark.asyncio
async def test_multipart_parts_preserves_duplicate_form_values():
    from starlette.datastructures import FormData

    from astrbot.dashboard.api.multipart import multipart_parts

    class FakeRequest:
        async def form(self):
            return FormData([("tag", "one"), ("tag", "two")])

    form, files = await multipart_parts(FakeRequest())

    assert form.getlist("tag") == ["one", "two"]
    assert not files


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
    assert enabled_response.json()["data"]["payload"] == {
        "name": plugin_id,
        "enabled": False,
    }
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
async def test_v1_command_patch_updates_service(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_toggle(handler_full_name: str | None, enabled):
        return {
            "handler_full_name": handler_full_name,
            "enabled": enabled,
        }

    monkeypatch.setattr(
        asgi_app.state.services.commands,
        "toggle_command",
        fake_toggle,
    )

    response = await asgi_client.patch(
        "/api/v1/commands/plugin.handler",
        json={"enabled": False},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"] == {
        "handler_full_name": "plugin.handler",
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
    tmp_path: Path,
):
    token_file = tmp_path / "token-file.txt"
    token_file.write_text("token:demo-token", encoding="utf-8")
    file_token = await file_token_service.register_file(str(token_file), timeout=60)

    response = await asgi_client.get(f"/api/v1/files/tokens/{file_token}")

    assert response.status_code == 200
    assert response.text == "token:demo-token"
    assert response.headers["content-type"].startswith("text/plain")


def test_v1_openapi_alias_websocket_routes_are_mounted(asgi_app):
    assert str(asgi_app.url_path_for("chat_ws")) == "/api/v1/chat/ws"
    assert str(asgi_app.url_path_for("live_chat_ws")) == "/api/v1/live-chat/ws"
    assert str(asgi_app.url_path_for("unified_chat_ws")) == "/api/v1/unified-chat/ws"


def test_dashboard_config_aliases_are_registered_on_fastapi(asgi_app):
    assert (
        str(asgi_app.url_path_for("dashboard_alias_platform_list"))
        == "/api/config/platform/list"
    )
    assert (
        str(asgi_app.url_path_for("dashboard_alias_provider_list"))
        == "/api/config/provider/list"
    )
    assert (
        str(asgi_app.url_path_for("update_dashboard_alias_provider_source"))
        == "/api/config/provider_sources/update"
    )


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
    mcp_servers = fake_core_lifecycle.provider_manager.llm_tools.config["mcpServers"]
    assert mcp_servers["demo-server"]["active"] is False


@pytest.mark.asyncio
async def test_v1_safe_mcp_routes_accept_slash_server_names(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    server_name = "modelscope/demo"
    headers = _jwt_headers()
    fake_tools = fake_core_lifecycle.provider_manager.llm_tools

    enabled_response = await asgi_client.patch(
        "/api/v1/mcp/servers/enabled",
        json={"server_name": server_name, "enabled": False},
        headers=headers,
    )
    assert enabled_response.status_code == 200
    assert fake_tools.config["mcpServers"][server_name]["active"] is False

    test_response = await asgi_client.post(
        "/api/v1/mcp/servers/test",
        json={"server_name": server_name},
        headers=headers,
    )
    assert test_response.status_code == 200
    assert test_response.json()["data"] == ["demo_tool"]
    assert fake_tools.tested_configs[-1] == {
        "active": False,
        "url": "https://example.com/modelscope-demo",
    }

    delete_response = await asgi_client.delete(
        "/api/v1/mcp/servers/by-name",
        params={"server_name": server_name},
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
async def test_v1_safe_persona_routes_accept_slash_ids(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    persona_id = "persona/foo"
    headers = _jwt_headers()
    persona_mgr = fake_core_lifecycle.persona_mgr

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
    assert detail_response.json()["data"]["persona_id"] == persona_id
    assert detail_response.json()["data"]["system_prompt"] == "Demo persona"
    assert update_response.status_code == 200
    assert update_response.json()["data"] == {"message": "人格更新成功"}
    assert delete_response.status_code == 200
    assert delete_response.json()["data"] == {"message": "人格删除成功"}
    assert persona_id not in persona_mgr.personas


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
        "/api/v1/personas/by-id",
        json={"persona_id": persona_id, "tools": None, "skills": None},
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
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"] == {
        "webhook_uuid": "demo-hook",
        "method": "POST",
        "payload": {"challenge": "ping"},
    }
