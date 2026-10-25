import asyncio
import copy
import io
import json
import os
import stat
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import jwt
import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, PlainTextResponse
from PIL import Image as PILImage

import astrbot.dashboard.services.config_service as config_service
import astrbot.dashboard.services.stat_service as stat_service
from astrbot.core import file_token_service
from astrbot.core.utils import llm_metadata
from astrbot.dashboard.api.app import create_dashboard_asgi_app
from astrbot.dashboard.api.backups import download_backup as download_backup_route
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
from astrbot.dashboard.services.backup_service import BackupDownload
from astrbot.dashboard.services.plugin_service import (
    PLUGIN_UPDATE_SOURCE_REQUIRED_MESSAGE,
    PluginServiceError,
)
from astrbot.dashboard.services.skills_service import SkillArchive, SkillsServiceError

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

    async def get_conversation_platform_ids(self) -> list[str]:
        return ["webchat-main"]

    async def get_platform_sessions_by_ids(
        self, _session_ids: list[str]
    ) -> list[object]:
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

    async def activate_llm_tool_async(self, _tool_name: str, *, star_map) -> bool:
        return True

    def deactivate_llm_tool(self, _tool_name: str) -> bool:
        return True

    async def deactivate_llm_tool_async(self, _tool_name: str) -> bool:
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
    token_usage: int = 0
    created_at: str = "2026-01-01T00:00:00"
    updated_at: str = "2026-01-01T00:00:00"


class FakeConversationManager:
    def __init__(self) -> None:
        user_id = "webchat:FriendMessage:webchat!user!session-1"
        self.last_filter_args: dict[str, list[str]] = {}
        self.last_include_history = True
        self.last_keyword_query = ""
        self.last_umo_query = ""
        self.last_sort = ("created_at", "desc")
        self.last_group_by_session = False
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
        keyword_query: str = "",
        umo_query: str = "",
        sort_by: str = "created_at",
        sort_order: str = "desc",
        group_by_session: bool = False,
        include_history: bool = True,
    ):
        self.last_include_history = include_history
        self.last_keyword_query = keyword_query
        self.last_umo_query = umo_query
        self.last_sort = (sort_by, sort_order)
        self.last_group_by_session = group_by_session
        self.last_filter_args = {
            "platforms": platforms,
            "message_types": message_types,
            "exclude_ids": exclude_ids,
            "exclude_platforms": exclude_platforms,
        }
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
        if keyword_query:
            conversations = [
                conversation
                for conversation in conversations
                if keyword_query in conversation.title
                or keyword_query in conversation.history
            ]
        if umo_query:
            conversations = [
                conversation
                for conversation in conversations
                if umo_query in conversation.user_id
            ]
        conversations = [
            conversation
            for conversation in conversations
            if conversation.cid not in exclude_ids
            and conversation.platform_id not in exclude_platforms
        ]
        conversations.sort(
            key=lambda conversation: getattr(conversation, sort_by),
            reverse=sort_order == "desc",
        )
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
        payload = await request_obj.get_json(silent=True)
        if payload.get("response_mode") == "plain":
            return "success"
        if payload.get("response_mode") == "tuple":
            return "accepted", 202, {"Content-Type": "text/plain"}
        return {
            "webhook_uuid": self.config["webhook_uuid"],
            "method": request_obj.method,
            "payload": payload,
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


class FakeAstrBotUpdater:
    async def check_update(self, *_args, **_kwargs):
        return None

    async def get_releases(self):
        return []

    async def update(self, *_args, **_kwargs) -> None:
        return None

    async def ensure_dashboard(self) -> Path:
        return Path("data/dist")


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
        astrbot_updater=FakeAstrBotUpdater(),
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


@pytest.mark.asyncio
@pytest.mark.parametrize("desktop_auth", [False, True])
@pytest.mark.parametrize("status", ["missing", "unavailable", "detected"])
async def test_version_routes_return_startup_runtime_snapshot(
    monkeypatch, tmp_path, fake_core_lifecycle, fake_db: FakeDb, desktop_auth, status
):
    """Both version routes and auth modes expose the same startup snapshot."""
    platform = SimpleNamespace(
        system=Mock(return_value="Linux"), machine=Mock(return_value="aarch64")
    )
    from astrbot.core.computer import process_sandbox

    process_sandbox.get_process_sandbox_status.cache_clear()
    monkeypatch.setattr(process_sandbox, "platform", platform)
    which = Mock(return_value=None if status == "missing" else "/usr/bin/bwrap")
    monkeypatch.setattr(stat_service, "platform", platform)
    monkeypatch.setattr(process_sandbox, "shutil", SimpleNamespace(which=which))
    error = "bwrap: setting up uid map: Permission denied"
    sandbox = Mock()
    sandbox.run.return_value = SimpleNamespace(
        returncode=1 if status == "unavailable" else 0, stderr=error.encode()
    )
    factory = Mock(return_value=sandbox)
    monkeypatch.setattr(process_sandbox, "create_process_sandbox", factory)
    monkeypatch.setattr(process_sandbox, "get_astrbot_temp_path", lambda: str(tmp_path))
    monkeypatch.setattr(
        stat_service, "is_desktop_session_auth_enabled", lambda: desktop_auth
    )
    monkeypatch.setattr(
        stat_service, "get_dashboard_version", AsyncMock(return_value="v1.2.3")
    )
    monkeypatch.setattr(
        stat_service, "is_password_storage_upgraded", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        stat_service,
        "get_dashboard_password_hash",
        lambda *args, **kwargs: "stored-hash",
    )
    monkeypatch.setattr(
        stat_service.StatService, "is_default_cred", AsyncMock(return_value=False)
    )
    app = create_dashboard_asgi_app(
        core_lifecycle=fake_core_lifecycle, db=fake_db, jwt_secret=JWT_SECRET
    )

    # Environment changes take effect in this snapshot after restarting AstrBot.
    which.return_value = "/usr/bin/bwrap"
    sandbox.run.return_value.returncode = 0
    expected_sandbox = {"backend": "bubblewrap", "status": status}
    if status == "unavailable":
        expected_sandbox["error"] = error
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        for path in ("/api/v1/stats/version", "/api/stat/version"):
            response = await client.get(path, headers=_jwt_headers())
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "ok"
            assert payload["data"]["runtime"] == {
                "os": "linux",
                "arch": "aarch64",
                "sandbox": expected_sandbox,
            }
            assert payload["data"]["version"]
            assert payload["data"]["dashboard_version"] == "v1.2.3"
            assert payload["data"]["change_pwd_hint"] is False
            assert payload["data"]["md5_pwd_hint"] is False
            assert payload["data"]["password_upgrade_required"] is False

        response = await client.get("/api/v1/stats/versions")
        assert response.status_code == 200
        assert "runtime" not in response.json()["data"]

    which.assert_called_once_with("bwrap")
    assert platform.system.call_count == 2
    platform.machine.assert_called_once_with()
    assert factory.call_count == (0 if status == "missing" else 1)
    process_sandbox.get_process_sandbox_status.cache_clear()


@pytest.mark.asyncio
async def test_public_versions_route_uses_static_folder(
    fake_core_lifecycle,
    fake_db: FakeDb,
    tmp_path: Path,
):
    static_folder = tmp_path / "dist"
    assets_folder = static_folder / "assets"
    assets_folder.mkdir(parents=True)
    (static_folder / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (assets_folder / "version").write_text("v9.8.7", encoding="utf-8")

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
        response = await client.get("/api/v1/stats/versions")

    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "ok"
    assert data["data"]["webui_version"] == "v9.8.7"
    assert data["data"]["astrbot_version"]
    assert "astrbot_code_version" in data["data"]


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
    assert "/api/v1/file" in spec["paths"]

    bot_list = spec["paths"]["/api/v1/bots"]["get"]
    assert bot_list["x-astrbot-scope"] == "bot"
    assert "**Required scope:** `bot`" in bot_list["description"]

    conversation_list = spec["paths"]["/api/v1/conversations"]["get"]
    assert conversation_list["x-astrbot-scope"] == "data"
    assert "**Required scope:** `data`" in conversation_list["description"]

    chat_send = spec["paths"]["/api/v1/chat"]["post"]
    assert chat_send["x-astrbot-scope"] == "chat"
    assert chat_send["x-astrbot-sensitive-scopes"] == ["chat:admin"]
    assert "**Required scope:** `chat`" in chat_send["description"]
    assert "**Conditional sensitive scope:** `chat:admin`" in chat_send["description"]

    public_spec_path = (
        Path(__file__).resolve().parents[1] / "docs" / "public" / "openapi.json"
    )
    public_spec = json.loads(public_spec_path.read_text(encoding="utf-8"))
    runtime_scope_map = {
        (method, path): operation["x-astrbot-scope"]
        for path, methods in spec["paths"].items()
        for method, operation in methods.items()
        if isinstance(operation, dict) and "x-astrbot-scope" in operation
    }
    public_scope_map = {
        (method, path): operation["x-astrbot-scope"]
        for path, methods in public_spec["paths"].items()
        for method, operation in methods.items()
        if isinstance(operation, dict)
        and "x-astrbot-scope" in operation
        and not operation.get("x-websocket")
    }
    assert public_scope_map == runtime_scope_map


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
    (assets_folder / "index-AbCd1234.js").write_text(
        "window.__astrbotHashedStaticTest = true;",
        encoding="utf-8",
    )
    (assets_folder / "config-metadata.json").write_text("{}", encoding="utf-8")
    (assets_folder / "version").write_text("v4.27.4", encoding="utf-8")
    t2i_folder = static_folder / "t2i"
    t2i_folder.mkdir()
    (t2i_folder / "shiki_runtime.iife.js").write_text(
        "window.__astrbotShikiRuntimeTest = true;",
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
        hashed_asset_response = await client.get("/assets/index-AbCd1234.js")
        word_suffix_asset_response = await client.get("/assets/config-metadata.json")
        version_response = await client.get("/assets/version")
        unversioned_asset_response = await client.get("/t2i/shiki_runtime.iife.js")
        favicon_response = await client.get("/favicon.svg")
        root_response = await client.get("/")
        index_response = await client.get("/index.html")
        page_response = await client.get("/config")
        missing_response = await client.get("/assets/missing.js")
        traversal_response = await client.get("/assets/%2E%2E/%2E%2E/secret.txt")
        api_response = await client.get("/api/not-found")

    assert asset_response.status_code == 200
    assert "window.__astrbotStaticTest" in asset_response.text
    assert asset_response.headers["cache-control"] == "no-cache"
    assert hashed_asset_response.status_code == 200
    assert hashed_asset_response.headers["cache-control"] == "no-cache"
    assert word_suffix_asset_response.status_code == 200
    assert word_suffix_asset_response.headers["cache-control"] == "no-cache"
    assert version_response.status_code == 200
    assert version_response.headers["cache-control"] == "no-store"
    assert unversioned_asset_response.status_code == 200
    assert unversioned_asset_response.headers["cache-control"] == "no-cache"
    assert favicon_response.status_code == 200
    assert favicon_response.text == "<svg></svg>"
    assert root_response.headers["cache-control"] == "no-store"
    assert index_response.headers["cache-control"] == "no-store"
    assert page_response.status_code == 200
    assert page_response.headers["cache-control"] == "no-store"
    assert "/assets/index-demo.js" in page_response.text
    assert missing_response.status_code == 404
    assert missing_response.headers["content-type"].startswith("text/html")
    assert "请先尝试重启 AstrBot" in missing_response.text
    assert "<h2>手动安装</h2>" in missing_response.text
    assert "WebUI files are missing" in missing_response.text
    assert "Manual installation" in missing_response.text
    assert "AstrBot-vx.x.x-dashboard.zip" in missing_response.text
    assert "index.html" in missing_response.text
    assert traversal_response.status_code == 404
    assert api_response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("desktop_managed", "query", "should_clear_cache"),
    [
        (True, "?astrbot_bundle=desktop-4.27.5-core-4.27.5-webui-deadbeef", True),
        (True, "", False),
        (False, "?astrbot_bundle=desktop-4.27.5-core-4.27.5-webui-deadbeef", False),
    ],
)
async def test_dashboard_index_clears_legacy_cache_only_for_desktop_bundle(
    fake_core_lifecycle,
    fake_db: FakeDb,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    desktop_managed: bool,
    query: str,
    should_clear_cache: bool,
):
    static_folder = tmp_path / "dist"
    static_folder.mkdir()
    (static_folder / "index.html").write_text(
        "<!doctype html>",
        encoding="utf-8",
    )
    if desktop_managed:
        monkeypatch.setenv("ASTRBOT_DESKTOP_MANAGED", "1")
    else:
        monkeypatch.delenv("ASTRBOT_DESKTOP_MANAGED", raising=False)

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
        responses = [
            await client.get(f"/{query}"),
            await client.get(f"/index.html{query}"),
        ]

    for response in responses:
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        if should_clear_cache:
            assert response.headers["clear-site-data"] == '"cache"'
        else:
            assert "clear-site-data" not in response.headers


@pytest.mark.asyncio
async def test_v1_backup_download_accepts_bearer_token(
    tmp_path: Path,
):
    filename = "desktop-backup.zip"
    backup_path = tmp_path / filename
    backup_path.write_bytes(b"PK\x03\x04desktop-backup-content")
    prepare_download = Mock(
        return_value=BackupDownload(path=str(backup_path), filename=filename)
    )
    service = SimpleNamespace(
        config={"dashboard": {"jwt_secret": JWT_SECRET}},
        prepare_download=prepare_download,
    )
    request = Request(
        {
            "type": "http",
            "headers": [(b"authorization", b"bEaReR   desktop-session-token")],
        }
    )

    response = await download_backup_route(
        filename=filename,
        request=request,
        token=None,
        service=service,
    )

    assert isinstance(response, FileResponse)
    assert response.path == str(backup_path)
    prepare_download.assert_called_once_with(
        filename=filename,
        token="desktop-session-token",
        jwt_secret=JWT_SECRET,
    )


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

    open_api_file_upload = spec["paths"]["/api/v1/file"]["post"]
    assert open_api_file_upload["requestBody"]["content"]["multipart/form-data"][
        "schema"
    ]["$ref"].endswith("/Body_uploadOpenApiFile")
    assert open_api_file_upload["x-astrbot-scope"] == "file"


@pytest.mark.asyncio
async def test_v1_knowledge_base_create_validation_uses_api_error_shape(
    asgi_client: httpx.AsyncClient,
):
    headers = _jwt_headers()

    missing_name_response = await asgi_client.post(
        "/api/v1/knowledge-bases",
        json={"embedding_provider_id": "embedding-1"},
        headers=headers,
    )
    missing_provider_response = await asgi_client.post(
        "/api/v1/knowledge-bases",
        json={"name": "Docs"},
        headers=headers,
    )

    assert missing_name_response.status_code == 200
    assert missing_name_response.json()["status"] == "error"
    assert missing_name_response.json()["message"] == "知识库名称不能为空"
    assert missing_provider_response.status_code == 200
    assert missing_provider_response.json()["status"] == "error"
    assert (
        missing_provider_response.json()["message"] == "缺少参数 embedding_provider_id"
    )


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
async def test_v1_conversation_list_preserves_history_by_default(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    response = await asgi_client.get(
        "/api/v1/conversations",
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    conversation = payload["data"]["conversations"][0]
    assert conversation["cid"] == "conversation/with/slash"
    assert conversation["history"] == "[]"
    assert fake_core_lifecycle.conversation_manager.last_include_history is True


@pytest.mark.asyncio
async def test_v1_conversation_list_returns_summary_without_history(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    response = await asgi_client.get(
        "/api/v1/conversations",
        params={"include_history": "false"},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    conversation = payload["data"]["conversations"][0]
    assert conversation["cid"] == "conversation/with/slash"
    assert "history" not in conversation
    assert fake_core_lifecycle.conversation_manager.last_include_history is False


@pytest.mark.asyncio
async def test_legacy_conversation_list_preserves_history_by_default(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.get(
        "/api/conversation/list",
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["data"]["conversations"][0]["history"] == "[]"


@pytest.mark.asyncio
async def test_legacy_conversation_list_returns_summary_without_history(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.get(
        "/api/conversation/list",
        params={"include_history": "false"},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "history" not in payload["data"]["conversations"][0]


@pytest.mark.asyncio
async def test_conversation_list_normalizes_comma_separated_filters(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    response = await asgi_client.get(
        "/api/v1/conversations",
        params={
            "platforms": ", webchat-main ,",
            "message_types": ", FriendMessage ,",
            "exclude_ids": "astrbot, ,",
            "exclude_platforms": ", webchat ,",
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert fake_core_lifecycle.conversation_manager.last_filter_args == {
        "platforms": ["webchat-main"],
        "message_types": ["FriendMessage"],
        "exclude_ids": ["astrbot"],
        "exclude_platforms": ["webchat"],
    }


@pytest.mark.asyncio
async def test_conversation_workspace_filters_and_options(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    options_response = await asgi_client.get(
        "/api/v1/conversations/filter-options",
        headers=_jwt_headers(),
    )
    assert options_response.status_code == 200
    assert options_response.json()["data"]["bots"] == [
        {"id": "webchat-main", "type": "webchat"}
    ]

    list_response = await asgi_client.get(
        "/api/v1/conversations",
        params={
            "keyword": "Demo",
            "umo": "session-1",
            "sort_by": "updated_at",
            "sort_order": "asc",
            "group_by_session": "true",
        },
        headers=_jwt_headers(),
    )
    assert list_response.status_code == 200
    manager = fake_core_lifecycle.conversation_manager
    assert manager.last_keyword_query == "Demo"
    assert manager.last_umo_query == "session-1"
    assert manager.last_sort == ("updated_at", "asc")
    assert manager.last_group_by_session is True


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
async def test_v1_active_umos_filters_by_exact_platform_instance(
    asgi_client: httpx.AsyncClient, fake_db: FakeDb,
):
    """Return only the requested instance's sessions to platform editors."""
    fake_db.umo_ids = ["qq:GroupMessage:1", "qq-2:GroupMessage:2"]
    response = await asgi_client.get(
        "/api/v1/sessions/active-umos", params={"platform_id": "qq"}, headers=_jwt_headers(),
    )
    assert response.status_code == 200
    assert response.json()["data"]["umos"] == ["qq:GroupMessage:1"]


@pytest.mark.asyncio
async def test_v1_sender_lookup_requires_auth_and_returns_source(
    asgi_client: httpx.AsyncClient, fake_db: FakeDb,
):
    """Expose source session names without allowing unauthenticated lookup."""
    fake_db.get_umo_senders = AsyncMock(return_value=[(
        SimpleNamespace(umo="qq:GroupMessage:1000", sender_id="123", sender_name="Alice"),
        None,
    )])
    assert (await asgi_client.get("/api/v1/sessions/senders")).status_code == 401
    response = await asgi_client.get(
        "/api/v1/sessions/senders", params={"search": " Alice ", "limit": 10},
        headers=_jwt_headers(),
    )
    assert response.status_code == 200
    sender = response.json()["data"]["senders"][0]
    assert sender["sender_id"] == "123"
    assert sender["sender_name"] == "Alice"
    assert sender["platform"] == "qq"
    assert sender["display_name"] == "qq:GroupMessage:1000"
    assert response.json()["data"]["page"] == 1
    assert response.json()["data"]["has_more"] is False
    fake_db.get_umo_senders.assert_awaited_once_with("Alice", 11, None, offset=0)
    fake_db.get_umo_senders.reset_mock()
    response = await asgi_client.get(
        "/api/v1/sessions/senders",
        params=[("sender_ids", "123"), ("sender_ids", "456"), ("limit", "100")],
        headers=_jwt_headers(),
    )
    assert response.status_code == 200
    fake_db.get_umo_senders.assert_awaited_once_with("", 101, ["123", "456"], offset=0)
    for limit in (0, 101):
        response = await asgi_client.get(
            "/api/v1/sessions/senders", params={"limit": limit}, headers=_jwt_headers(),
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_v1_sender_lookup_pages_results_and_validates_page(
    asgi_client: httpx.AsyncClient, fake_db: FakeDb,
):
    """Pass page offsets through and hide the extra row used to detect the next page."""
    fake_db.get_umo_senders = AsyncMock(return_value=[
        (SimpleNamespace(umo="qq:GroupMessage:room", sender_id=str(index), sender_name=f"User {index}"), None)
        for index in range(3)
    ])
    response = await asgi_client.get(
        "/api/v1/sessions/senders", params={"page": 2, "limit": 2}, headers=_jwt_headers(),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["page"] == 2
    assert data["has_more"] is True
    assert [sender["sender_id"] for sender in data["senders"]] == ["0", "1"]
    fake_db.get_umo_senders.assert_awaited_once_with("", 3, None, offset=2)
    for page in (0, -1):
        response = await asgi_client.get(
            "/api/v1/sessions/senders", params={"page": page}, headers=_jwt_headers(),
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_v1_system_config_update_preserves_independent_bot_provider_sections(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_save_config(
        post_config: dict, config: FakeAstrBotConfig, is_core=False, *, runtime=None
    ):
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
@pytest.mark.parametrize("change", ["member_execution", "admin_removal"])
async def test_config_update_revokes_only_affected_shell_sessions(
    asgi_app, fake_core_lifecycle, monkeypatch, tmp_path, change
):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.booters.local import LocalBooter
    from astrbot.core.tools.computer_tools import shell as shell_tools

    config = fake_core_lifecycle.astrbot_config
    config["admins_id"] = ["creator", "other-admin"]
    config["agent_runner"] = {"runner_type": "local"}
    config["provider_settings"] = {
        "computer_use_runtime": "local",
        "computer_use_local_permissions": {
            role: {
                "allow_execution": True,
                "allow_network": True,
                "filesystem_scope": "host",
            }
            for role in ("admin", "member")
        },
    }
    other_config = copy.deepcopy(config)
    booter = LocalBooter()
    monkeypatch.setattr(computer_client, "local_booter", booter)
    monkeypatch.setattr(
        shell_tools, "workspace_root_for_context", AsyncMock(return_value=tmp_path)
    )
    sessions = []
    try:
        for role, profile, sender_id in (
            ("member", config, "member"),
            ("admin", config, "creator"),
            ("admin", other_config, "creator"),
            ("admin", config, "other-admin"),
        ):
            context = SimpleNamespace(
                context=SimpleNamespace(
                    context=SimpleNamespace(get_config=lambda umo, p=profile: p),
                    event=SimpleNamespace(
                        role=role,
                        unified_msg_origin="test:friend:revocation",
                        get_sender_id=lambda sender_id=sender_id: sender_id,
                    ),
                )
            )
            result = json.loads(
                await shell_tools.LocalExecuteShellTool().call(
                    context, command='python -u -c "input()"', yield_time_ms=0
                )
            )
            sessions.append(booter.shell._sessions[result["session_id"]])
            if profile is config and sender_id == "creator":
                admin_context = context

        service = asgi_app.state.services.config_profiles
        payload = copy.deepcopy(config)
        payload["wake_prefix"] = ["changed"]
        await service.update_profile("default", payload)
        assert all(session.process.returncode is None for session in sessions)

        payload = copy.deepcopy(config)
        if change == "admin_removal":
            payload["admins_id"] = ["other-admin"]
            revoked_index = 1
        else:
            payload["provider_settings"]["computer_use_local_permissions"]["member"][
                "allow_execution"
            ] = False
            revoked_index = 0
        await service.update_profile("default", payload)
        assert sessions[revoked_index].process.returncode is not None
        assert all(
            session.process.returncode is None
            for index, session in enumerate(sessions)
            if index != revoked_index
        )
        assert sessions[revoked_index].session_id not in booter.shell._sessions
        if change == "admin_removal":
            assert admin_context.context.event.role == "admin"
            result = await shell_tools.LocalExecuteShellTool().call(
                admin_context, command="echo unexpected", yield_time_ms=0
            )
            assert "permissions changed" in result
            assert len(booter.shell._sessions) == 3

        # Pre-upgrade sessions must not acquire a grant from the current config.
        sessions[2].permission_check = None
        payload = copy.deepcopy(config)
        payload["provider_settings"]["computer_use_runtime"] = "none"
        await service.update_profile("default", payload)
        assert all(session.process.returncode is not None for session in sessions)
        assert not booter.shell._sessions
    finally:
        await booter.shell.shutdown_sessions()


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["workspace", "host"])
@pytest.mark.parametrize(
    ("system", "backend", "status", "reason"),
    [
        ("windows", None, "unsupported", "windows"),
        ("linux", "bubblewrap", "missing", "bwrap"),
        ("darwin", "seatbelt", "missing", "sandbox-exec"),
        ("linux", "bubblewrap", "unavailable", "setting up uid map: Permission denied"),
        ("darwin", "seatbelt", "unavailable", "sandbox_apply: Operation not permitted"),
    ],
)
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/system-config",
        "/api/v1/config-profiles/default",
        "/api/config/astrbot/update",
    ],
)
async def test_config_api_saves_local_permissions_without_isolation(
    asgi_app,
    asgi_client,
    fake_core_lifecycle,
    path,
    scope,
    system,
    backend,
    status,
    reason,
):
    runtime = asgi_app.state.services.stats.runtime
    assert asgi_app.state.services.config_profiles.runtime is runtime
    runtime.update({"os": system, "sandbox": {"backend": backend, "status": status}})
    if status == "unavailable":
        runtime["sandbox"]["error"] = reason
    original = copy.deepcopy(fake_core_lifecycle.astrbot_config)
    payload = copy.deepcopy(original)
    payload["agent_runner"] = {"runner_type": "local"}
    payload["provider_settings"] = {
        "computer_use_runtime": "local",
        "computer_use_local_permissions": {
            "member": {
                "filesystem_scope": scope,
                "allow_execution": True,
                "allow_network": True,
            },
            "admin": {"filesystem_scope": "none"},
        },
    }
    legacy = path.startswith("/api/config/")
    response = await asgi_client.request(
        "POST" if legacy else "PUT",
        path,
        headers=_jwt_headers(),
        json={"conf_id": "default", "config": payload} if legacy else payload,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    payload["provider_settings"]["computer_use_local_permissions"]["admin"].update(
        allow_execution=False, allow_network=False
    )
    assert (
        fake_core_lifecycle.astrbot_config["provider_settings"]
        == payload["provider_settings"]
    )
    assert fake_core_lifecycle.reloaded_config_ids == ["default"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["missing", "unavailable", "unsupported"])
async def test_welcome_page_can_enable_local_computer_access_without_isolation(
    asgi_app, asgi_client, fake_core_lifecycle, status
):
    """Welcome setup only changes the runtime and retains default permissions."""
    from astrbot.core.config.default import get_local_permission_defaults

    runtime = asgi_app.state.services.stats.runtime
    runtime.update({"os": "linux", "sandbox": {"status": status}})
    config = fake_core_lifecycle.astrbot_config
    config["agent_runner"] = {"runner_type": "local"}
    config["provider_settings"] = {
        "computer_use_runtime": "none",
        "computer_use_local_permissions": get_local_permission_defaults("Linux"),
    }
    payload = copy.deepcopy(config)
    payload["provider_settings"]["computer_use_runtime"] = "local"

    response = await asgi_client.put(
        "/api/v1/config-profiles/default", headers=_jwt_headers(), json=payload
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"
    assert config["provider_settings"] == payload["provider_settings"]
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
async def test_v1_provider_schema_keeps_reasoning_in_model_metadata(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
    monkeypatch: pytest.MonkeyPatch,
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
    monkeypatch.setattr(
        llm_metadata,
        "LLM_METADATAS",
        {"gpt-4o-mini": model_metadata},
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
                "reasoning": True,
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
        "reasoning": True,
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
    config_schema = schema_response.json()["data"]["config_schema"]
    reasoning_effort_preset = config_schema["provider"]["items"]["custom_extra_body"][
        "template_schema"
    ]["reasoning_effort"]
    assert reasoning_effort_preset["type"] == "string"
    assert reasoning_effort_preset["default"] == "high"
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
async def test_v1_plugin_validate_repo_uses_service(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_service = asgi_app.state.services.plugins
    captured = {}

    async def fake_validate_plugin_repo(payload):
        captured["payload"] = payload
        return {
            "valid": True,
            "name": "astrbot_plugin_demo",
            "version": "1.2.3",
        }, "插件校验通过。"

    monkeypatch.setattr(
        plugin_service,
        "validate_plugin_repo",
        fake_validate_plugin_repo,
    )

    response = await asgi_client.post(
        "/api/v1/plugins/validate/repo",
        json={
            "url": "https://github.com/AstrBotDevs/astrbot-plugin-demo",
            "proxy": "https://proxy.example",
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["message"] == "插件校验通过。"
    assert data["data"]["version"] == "1.2.3"
    assert captured["payload"] == {
        "url": "https://github.com/AstrBotDevs/astrbot-plugin-demo",
        "proxy": "https://proxy.example",
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
            "install_method": "market",
            "registry_url": "https://example.com/plugins.json",
            "market_plugin_id": "AstrBotDevs/astrbot-plugin-demo",
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
        "install_method": "market",
        "registry_url": "https://example.com/plugins.json",
        "market_plugin_id": "AstrBotDevs/astrbot-plugin-demo",
    }
    assert empty_body_response.status_code == 200
    empty_body_data = empty_body_response.json()
    assert empty_body_data["status"] == "error"
    assert empty_body_data["message"] == "插件操作失败，请查看服务端日志。"
    assert "missing url" not in str(empty_body_data)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transport", "repository"),
    [
        ("github", "AstrBotDevs/astrbot-plugin-demo"),
        ("git", "https://gitee.com/AstrBotDevs/astrbot-plugin-demo.git"),
        ("git", "git@github.com:AstrBotDevs/astrbot-plugin-demo.git"),
    ],
)
async def test_v1_plugin_repository_install_uses_transport_route(
    transport: str,
    repository: str,
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_service = asgi_app.state.services.plugins
    captured = {}

    async def fake_install_plugin(payload):
        captured.update(payload)
        return {"name": "astrbot_plugin_demo"}, "安装成功。"

    monkeypatch.setattr(plugin_service, "install_plugin", fake_install_plugin)

    response = await asgi_client.post(
        f"/api/v1/plugins/install/{transport}",
        json={"repository": repository},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert captured["url"] == repository
    assert captured["repository_transport"] == transport


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
        fallback_method,
        repo_url,
        download_url,
    ):
        captured["persist_payload"] = payload
        captured["persist_fallback_method"] = fallback_method
        captured["persist_repo_url"] = repo_url
        captured["persist_download_url"] = download_url

    async def fake_sync_skills_after_plugin_change():
        captured["synced"] = True

    monkeypatch.setattr(plugin_service, "get_online_plugins", fake_get_online_plugins)
    monkeypatch.setattr(
        plugin_service.plugin_manager,
        "install_plugin",
        fake_install_plugin,
        raising=False,
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
    assert captured["persist_fallback_method"] == "repository"
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
async def test_plugin_service_validate_plugin_repo_fetches_metadata_file(
    asgi_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_service = asgi_app.state.services.plugins
    captured: dict[str, object] = {}

    async def fake_inspect_plugin_repository(repo_url: str, proxy: str):
        assert repo_url == "https://github.com/AstrBotDevs/astrbot-plugin-demo"
        captured["proxy"] = proxy
        return {
            "name": "astrbot_plugin_demo",
            "desc": "Demo plugin",
            "version": "2.0.0",
            "author": "AstrBotDevs",
            "repo": repo_url,
        }

    monkeypatch.setattr(
        plugin_service.plugin_manager,
        "inspect_plugin_repository",
        fake_inspect_plugin_repository,
        raising=False,
    )

    result, message = await plugin_service.validate_plugin_repo(
        {
            "url": "AstrBotDevs/astrbot-plugin-demo",
            "proxy": "https://proxy.example/",
        }
    )

    assert message == "插件校验通过。"
    assert result["desc"] == "Demo plugin"
    assert result["version"] == "2.0.0"
    assert captured["proxy"] == "https://proxy.example/"


@pytest.mark.asyncio
async def test_plugin_service_validate_plugin_repo_preserves_ssh_locator(
    asgi_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_service = asgi_app.state.services.plugins
    captured = {}

    async def fake_inspect_plugin_repository(repo_url: str, proxy: str):
        captured["repo_url"] = repo_url
        captured["proxy"] = proxy
        return {
            "name": "astrbot_plugin_demo",
            "desc": "Demo plugin",
            "version": "2.0.0",
            "author": "AstrBotDevs",
            "repo": repo_url,
        }

    monkeypatch.setattr(
        plugin_service.plugin_manager,
        "inspect_plugin_repository",
        fake_inspect_plugin_repository,
        raising=False,
    )

    await plugin_service.validate_plugin_repo(
        {"url": "git@github.com:AstrBotDevs/astrbot-plugin-demo.git"}
    )

    assert captured["repo_url"] == "git@github.com:AstrBotDevs/astrbot-plugin-demo.git"
    assert captured["proxy"] == ""


@pytest.mark.asyncio
async def test_plugin_service_enforces_repository_transport_route(
    asgi_app: FastAPI,
):
    plugin_service = asgi_app.state.services.plugins

    with pytest.raises(PluginServiceError, match="non-GitHub"):
        await plugin_service.install_plugin(
            {
                "url": "https://gitee.com/AstrBotDevs/demo.git",
                "repository_transport": "github",
            }
        )

    with pytest.raises(PluginServiceError, match="GitHub archive"):
        await plugin_service.install_plugin(
            {
                "url": "https://github.com/AstrBotDevs/demo",
                "repository_transport": "git",
            }
        )


@pytest.mark.asyncio
async def test_plugin_service_exposes_missing_git_error(
    asgi_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    from astrbot.core.repository import GitUnavailableError

    plugin_service = asgi_app.state.services.plugins

    async def fail_install(*_args, **_kwargs):
        raise GitUnavailableError("Git is required for this repository.")

    monkeypatch.setattr(
        plugin_service.plugin_manager,
        "install_plugin",
        fail_install,
        raising=False,
    )

    with pytest.raises(PluginServiceError) as exc_info:
        await plugin_service.install_plugin(
            {
                "url": "git@github.com:AstrBotDevs/demo.git",
                "repository_transport": "git",
            }
        )

    assert exc_info.value.public_message == "Git is required for this repository."


@pytest.mark.asyncio
async def test_plugin_service_validate_plugin_repo_rejects_large_metadata_file(
    asgi_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_service = asgi_app.state.services.plugins

    async def fake_inspect_plugin_repository(repo_url: str, proxy: str):  # noqa: ARG001
        raise ValueError("metadata.yaml 超过 1MB。")

    monkeypatch.setattr(
        plugin_service.plugin_manager,
        "inspect_plugin_repository",
        fake_inspect_plugin_repository,
        raising=False,
    )

    with pytest.raises(PluginServiceError, match="超过 1MB"):
        await plugin_service.validate_plugin_repo(
            {"url": "https://github.com/AstrBotDevs/astrbot-plugin-demo"}
        )


@pytest.mark.asyncio
async def test_plugin_service_validate_plugin_repo_hides_internal_errors(
    asgi_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_service = asgi_app.state.services.plugins

    async def fake_inspect_plugin_repository(repo_url: str, proxy: str):  # noqa: ARG001
        raise RuntimeError("secret stack trace")

    monkeypatch.setattr(
        plugin_service.plugin_manager,
        "inspect_plugin_repository",
        fake_inspect_plugin_repository,
        raising=False,
    )

    with pytest.raises(PluginServiceError) as exc_info:
        await plugin_service.validate_plugin_repo(
            {"url": "https://github.com/AstrBotDevs/astrbot-plugin-demo"}
        )

    assert exc_info.value.public_message == "插件校验失败，请查看服务端日志。"
    assert "secret stack trace" not in exc_info.value.public_message


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
            "install_method": "repository",
        }
    )

    assert message == "插件源已更新。"
    assert record["install_method"] == "repository"
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


def test_plugin_service_repo_identifier_accepts_gitee_url(
    asgi_app: FastAPI,
):
    plugin_service = asgi_app.state.services.plugins

    assert (
        plugin_service.repo_identifier_from_url(
            "https://gitee.com/AstrBotDevs/demo.git"
        )
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
        fallback_method="url",
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


def test_plugin_service_missing_install_source_is_implicit_for_display(
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

    assert record["install_method"] == "market"
    assert record["registry_url"] is None
    assert record["registry_name"] == "Default"
    assert record["repo"] == "https://github.com/AstrBotDevs/astrbot-plugin-demo"
    assert record["implicit"] is True
    assert record["name"] == "astrbot_plugin_demo"
    assert record["marketplace_name"] == "astrbot-plugin-demo"


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
                "install_method": "repository",
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
    assert update_info["record"]["install_method"] == "repository"


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


@pytest.fixture
def plugin_config_preview_files(asgi_app, monkeypatch, tmp_path):
    """Register a synthetic file field and its real uploaded image files."""
    root = tmp_path / "plugin_data"
    image_dir = root / "preview-demo" / "files" / "images"
    image_dir.mkdir(parents=True)
    PILImage.new("RGB", (1600, 800), "blue").save(image_dir / "landscape.png")
    PILImage.new("RGB", (40, 80), "orange").save(image_dir / "portrait.webp")
    (image_dir / "invalid.png").write_bytes(b"not an image")
    (image_dir / "active.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        encoding="utf-8",
    )
    other_dir = root / "preview-demo" / "files" / "other"
    other_dir.mkdir()
    PILImage.new("RGB", (10, 10), "red").save(other_dir / "private.png")
    config = SimpleNamespace(
        schema={
            "images": {"type": "file"},
            "other": {"type": "file"},
            "alias": {"type": "file"},
            "text": {"type": "string"},
        }
    )
    service = asgi_app.state.services.config_files
    monkeypatch.setattr(
        config_service, "get_astrbot_plugin_data_path", lambda: str(root)
    )
    monkeypatch.setattr(
        service,
        "get_plugin_metadata_by_name",
        lambda name: SimpleNamespace(config=config) if name == "preview-demo" else None,
    )
    return root, image_dir


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["landscape.png", "portrait.webp"])
async def test_v1_plugin_config_image_preview(
    asgi_client, plugin_config_preview_files, filename
):
    """Serve a bounded PNG preview without modifying or exposing the source."""
    _, image_dir = plugin_config_preview_files
    original = (image_dir / filename).read_bytes()
    response = await asgi_client.get(
        "/api/v1/plugins/config-files/preview",
        params={
            "plugin_id": "preview-demo",
            "config_key": "images",
            "path": f"files/images/{filename}",
        },
        headers=_jwt_headers(),
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    with PILImage.open(io.BytesIO(response.content)) as image:
        assert image.format == "PNG"
        assert max(image.size) <= 1024
        if filename == "landscape.png":
            assert image.size == (1024, 512)
    assert (image_dir / filename).read_bytes() == original


@pytest.mark.asyncio
async def test_v1_plugin_config_image_preview_requires_plugin_scope(
    asgi_client, fake_db, plugin_config_preview_files
):
    """Reuse plugin authentication rather than allowing public image URLs."""
    params = {
        "plugin_id": "preview-demo",
        "config_key": "images",
        "path": "files/images/landscape.png",
    }
    anonymous = await asgi_client.get(
        "/api/v1/plugins/config-files/preview", params=params
    )
    assert anonymous.status_code == 401
    fake_db.add_api_key("preview-wrong-scope", ["file"])
    denied = await asgi_client.get(
        "/api/v1/plugins/config-files/preview",
        params=params,
        headers={"Authorization": "Bearer preview-wrong-scope"},
    )
    assert denied.status_code == 403
    fake_db.add_api_key("preview-plugin-scope", ["plugin"])
    allowed = await asgi_client.get(
        "/api/v1/plugins/config-files/preview",
        params=params,
        headers={"Authorization": "Bearer preview-plugin-scope"},
    )
    assert allowed.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("plugin_id", "config_key", "path", "status"),
    [
        ("preview-demo", "images", "../private.png", 400),
        ("preview-demo", "images", "files/images/../other/private.png", 400),
        ("preview-demo", "images", "files/other/private.png", 400),
        ("preview-demo", "images", "files/images-other/private.png", 400),
        ("preview-demo", "images", "main.py", 400),
        ("preview-demo", "images", "/etc/passwd", 400),
        ("preview-demo", "images", "/files/images/landscape.png", 400),
        ("preview-demo", "images", "files/images/missing.png", 404),
        ("preview-demo", "images", "files/images", 400),
        ("preview-demo", "text", "files/images/landscape.png", 400),
        ("preview-demo", "unknown", "files/images/landscape.png", 400),
        ("unknown-plugin", "images", "files/images/landscape.png", 400),
        ("preview-demo", "images", "files/images/invalid.png", 415),
        ("preview-demo", "images", "files/images/active.svg", 415),
    ],
)
async def test_v1_plugin_config_image_preview_rejects_unsafe_inputs(
    asgi_client, plugin_config_preview_files, plugin_id, config_key, path, status
):
    """Reject paths outside the selected field and files that are not images."""
    response = await asgi_client.get(
        "/api/v1/plugins/config-files/preview",
        params={"plugin_id": plugin_id, "config_key": config_key, "path": path},
        headers=_jwt_headers(),
    )
    assert response.status_code == status
    assert response.json()["status"] == "error"
    assert str(plugin_config_preview_files[0]) not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("link_kind", ["file", "directory", "field-directory", "loop"])
async def test_v1_plugin_config_image_preview_rejects_symlink_escape(
    asgi_client, plugin_config_preview_files, require_symlink, link_kind
):
    """Resolve symlinks before enforcing the selected field's directory."""
    root, image_dir = plugin_config_preview_files
    if link_kind == "file":
        (image_dir / "linked.png").symlink_to(
            root / "preview-demo" / "files" / "other" / "private.png"
        )
        path = "files/images/linked.png"
    elif link_kind == "directory":
        (image_dir / "linked").symlink_to(image_dir.parent / "other")
        path = "files/images/linked/private.png"
    elif link_kind == "field-directory":
        alias = root / "preview-demo" / "files" / "alias"
        alias.symlink_to(image_dir)
        path = "files/alias/landscape.png"
    else:
        (image_dir / "loop.png").symlink_to(image_dir / "loop.png")
        path = "files/images/loop.png"
    response = await asgi_client.get(
        "/api/v1/plugins/config-files/preview",
        params={
            "plugin_id": "preview-demo",
            "config_key": "alias" if link_kind == "field-directory" else "images",
            "path": path,
        },
        headers=_jwt_headers(),
    )
    assert response.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", ["bytes", "pixels"])
async def test_v1_plugin_config_image_preview_is_bounded(
    asgi_client, plugin_config_preview_files, monkeypatch, limit
):
    """Bound compressed input and decoded dimensions independently."""
    monkeypatch.setattr(
        config_service,
        "MAX_PREVIEW_FILE_BYTES" if limit == "bytes" else "MAX_PREVIEW_PIXELS",
        32,
        raising=False,
    )
    response = await asgi_client.get(
        "/api/v1/plugins/config-files/preview",
        params={
            "plugin_id": "preview-demo",
            "config_key": "images",
            "path": "files/images/landscape.png",
        },
        headers=_jwt_headers(),
    )
    assert response.status_code == 413


@pytest.mark.asyncio
@pytest.mark.parametrize("format_", ["JPEG", "GIF", "BMP", "DIB", "TIFF", "ICO"])
async def test_v1_plugin_config_image_preview_supported_raster_formats(
    asgi_client, plugin_config_preview_files, format_
):
    """Decode supported raster formats rather than trusting the extension."""
    _, image_dir = plugin_config_preview_files
    path = image_dir / "sample.image"
    PILImage.new("RGB", (32, 32), "blue").save(path, format=format_)
    response = await asgi_client.get(
        "/api/v1/plugins/config-files/preview",
        params={
            "plugin_id": "preview-demo",
            "config_key": "images",
            "path": "files/images/sample.image",
        },
        headers=_jwt_headers(),
    )
    assert response.status_code == 200
    with PILImage.open(io.BytesIO(response.content)) as image:
        assert image.size == (32, 32)
        assert image.format == "PNG"


@pytest.mark.asyncio
async def test_v1_plugin_config_image_preview_applies_orientation_and_strips_metadata(
    asgi_client, plugin_config_preview_files
):
    """Apply EXIF orientation without returning private source metadata."""
    _, image_dir = plugin_config_preview_files
    image = PILImage.new("RGB", (80, 40), "blue")
    exif = image.getexif()
    exif[274] = 6
    exif[270] = "private fixture metadata"
    image.save(image_dir / "rotated.jpg", exif=exif)
    response = await asgi_client.get(
        "/api/v1/plugins/config-files/preview",
        params={
            "plugin_id": "preview-demo",
            "config_key": "images",
            "path": "files/images/rotated.jpg",
        },
        headers=_jwt_headers(),
    )
    assert response.status_code == 200
    with PILImage.open(io.BytesIO(response.content)) as preview:
        assert preview.size == (40, 80)
        assert not preview.getexif()
        assert not preview.info
    with PILImage.open(image_dir / "rotated.jpg") as original:
        assert original.size == (80, 40)
        assert original.getexif()[270] == "private fixture metadata"


@pytest.mark.asyncio
async def test_v1_plugin_config_image_preview_uses_first_animation_frame(
    asgi_client, plugin_config_preview_files
):
    """Keep animation previews bounded to one frame."""
    _, image_dir = plugin_config_preview_files
    PILImage.new("RGB", (32, 32), "blue").save(
        image_dir / "animated.gif",
        save_all=True,
        append_images=[PILImage.new("RGB", (32, 32), "red")],
        duration=100,
        loop=0,
    )
    response = await asgi_client.get(
        "/api/v1/plugins/config-files/preview",
        params={
            "plugin_id": "preview-demo",
            "config_key": "images",
            "path": "files/images/animated.gif",
        },
        headers=_jwt_headers(),
    )
    assert response.status_code == 200
    with PILImage.open(io.BytesIO(response.content)) as preview:
        assert not getattr(preview, "is_animated", False)
        assert preview.convert("RGB").getpixel((0, 0)) == (0, 0, 255)


@pytest.mark.asyncio
async def test_v1_plugin_config_image_preview_rejects_decompression_bombs(
    asgi_client, plugin_config_preview_files, monkeypatch
):
    """Handle Pillow's decoder guard without weakening its global limit."""
    monkeypatch.setattr(PILImage, "MAX_IMAGE_PIXELS", 100)
    response = await asgi_client.get(
        "/api/v1/plugins/config-files/preview",
        params={
            "plugin_id": "preview-demo",
            "config_key": "images",
            "path": "files/images/landscape.png",
        },
        headers=_jwt_headers(),
    )
    assert response.status_code == 413
    assert PILImage.MAX_IMAGE_PIXELS == 100


@pytest.mark.asyncio
@pytest.mark.parametrize("storage_error", [PermissionError, OSError])
async def test_v1_plugin_config_image_preview_distinguishes_storage_failure(
    asgi_client, plugin_config_preview_files, monkeypatch, storage_error
):
    """Report storage outages separately from corrupt or unsupported images."""
    _, image_dir = plugin_config_preview_files
    original_open = Path.open

    def failing_open(path, *args, **kwargs):
        if path == image_dir / "landscape.png":
            raise storage_error(f"Private storage failure: {image_dir}")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    response = await asgi_client.get(
        "/api/v1/plugins/config-files/preview",
        params={
            "plugin_id": "preview-demo",
            "config_key": "images",
            "path": "files/images/landscape.png",
        },
        headers=_jwt_headers(),
    )
    assert response.status_code == 503
    assert response.json()["message"] == "Image file cannot be read"
    assert str(image_dir) not in response.text


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
    config_response = await asgi_client.get(
        "/api/v1/plugins/config",
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
    assert config_response.status_code == 200
    assert config_response.json()["data"] == {
        "plugin_name": plugin_id,
        "log_level": None,
        "schema": {"name": plugin_id},
    }
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
@pytest.mark.parametrize(
    "permission", ["member", "admin", "group_admin", "shared_group_admin"]
)
async def test_v1_command_permission_patch_updates_service(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    permission: str,
):
    update = AsyncMock(return_value={"permission": permission})
    monkeypatch.setattr(asgi_app.state.services.commands, "update_permission", update)
    response = await asgi_client.patch(
        "/api/v1/commands/plugin.handler",
        json={"permission_group": permission},
        headers=_jwt_headers(),
    )
    assert response.status_code == 200
    assert response.json()["data"]["permission"] == permission
    update.assert_awaited_once_with("plugin.handler", permission)


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

    second_response = await asgi_client.get(f"/api/v1/files/tokens/{file_token}")

    assert second_response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("cached_token_state", ["valid", "expired", "consumed"])
async def test_v1_platform_logo_refreshes_stale_tokens_and_supports_repeated_reads(
    asgi_client: httpx.AsyncClient,
    asgi_app,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cached_token_state: str,
):
    """Exercise real config and image routes with reusable and stale logo tokens."""
    logo_file = tmp_path / "logo.png"
    PILImage.new("RGB", (1, 1), "red").save(logo_file)
    platform = SimpleNamespace(
        name="logo-test",
        logo_path=logo_file.name,
        default_config_tmpl={"type": "logo-test"},
        config_metadata=None,
    )
    monkeypatch.setattr(file_token_service, "staged_files", {})
    monkeypatch.setattr(config_service, "platform_registry", [platform])
    monkeypatch.setitem(config_service.platform_cls_map, platform.name, FakePlatform)
    monkeypatch.setattr(
        config_service,
        "inspect",
        SimpleNamespace(getfile=lambda _cls: str(tmp_path / "adapter.py")),
    )
    display_service = asgi_app.state.services.config_display
    cached_token = None
    if cached_token_state != "valid":
        cached_token = await file_token_service.register_file(
            str(logo_file), timeout=-1 if cached_token_state == "expired" else 60
        )
        if cached_token_state == "consumed":
            await file_token_service.handle_file(cached_token)
        display_service._logo_token_cache[f"{platform.name}:{platform.logo_path}"] = (
            cached_token
        )

    config_response = await asgi_client.get(
        "/api/v1/system-config/runtime", headers=_jwt_headers()
    )
    assert config_response.status_code == 200
    platform_metadata = config_response.json()["data"]["metadata"]["platform_group"][
        "metadata"
    ]["platform"]
    token = platform_metadata["config_template"][platform.name]["logo_token"]
    if cached_token is not None:
        assert token != cached_token
    logo_url = f"/api/v1/files/tokens/{token}"

    first_response = await asgi_client.get(logo_url)
    second_response = await asgi_client.get(logo_url)
    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.content == logo_file.read_bytes()
    assert second_response.headers["content-type"].startswith("image/png")

    responses = await asyncio.gather(*(asgi_client.get(logo_url) for _ in range(3)))
    assert all(response.status_code == 200 for response in responses)

    templates = {}
    await display_service.register_platform_logo(platform, templates)
    assert templates[platform.name]["logo_token"] == token


@pytest.mark.asyncio
async def test_v1_plugin_logo_supports_repeated_reads(
    asgi_client: httpx.AsyncClient,
    asgi_app,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    logo_file = tmp_path / "logo.png"
    PILImage.new("RGB", (1, 1), "red").save(logo_file)
    monkeypatch.setattr(file_token_service, "staged_files", {})
    plugin_service = asgi_app.state.services.plugins
    plugin = SimpleNamespace(logo_path=str(logo_file))
    logo_url = await plugin_service.resolve_plugin_logo_url(
        plugin, plugin_service.get_plugin_logo_token
    )

    first_response = await asgi_client.get(logo_url)
    second_response = await asgi_client.get(logo_url)
    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.content == logo_file.read_bytes()
    assert (
        await plugin_service.resolve_plugin_logo_url(
            plugin, plugin_service.get_plugin_logo_token
        )
        == logo_url
    )


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
    demo_server = next(
        server for server in data["data"] if server["name"] == "demo-server"
    )
    assert demo_server["connected"] is False


@pytest.mark.asyncio
async def test_v1_mcp_list_reports_connected_runtime(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    fake_tools = fake_core_lifecycle.provider_manager.llm_tools
    fake_tools.mcp_server_runtime_view["demo-server"] = SimpleNamespace(
        client=SimpleNamespace(
            tools=[SimpleNamespace(name="demo_tool")],
            server_errlogs=[],
        ),
    )

    response = await asgi_client.get(
        "/api/v1/mcp/servers",
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    demo_server = next(
        server for server in response.json()["data"] if server["name"] == "demo-server"
    )
    assert demo_server["connected"] is True
    assert demo_server["tools"] == ["demo_tool"]


@pytest.mark.asyncio
async def test_v1_skill_scope_accepts_api_key_and_rejects_plural_scope(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    fake_db: FakeDb,
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_get_skills():
        return {"skills": [{"name": "demo_skill"}]}

    monkeypatch.setattr(
        asgi_app.state.services.skills,
        "get_skills",
        fake_get_skills,
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

    by_name_response = await asgi_client.get(
        "/api/v1/skills/archive",
        params={"skill_name": "missing_skill"},
        headers=_jwt_headers(),
    )
    path_response = await asgi_client.get(
        "/api/v1/skills/missing_skill/archive",
        headers=_jwt_headers(),
    )

    assert by_name_response.status_code == 404
    assert by_name_response.headers["content-type"].startswith("application/json")
    assert by_name_response.json()["status"] == "error"
    assert by_name_response.json()["message"] == "Local skill not found"
    assert path_response.status_code == 404
    assert path_response.headers["content-type"].startswith("application/json")
    assert path_response.json()["message"] == "Local skill not found"

    def fake_prepare_skill_archive_400(_name: str):
        raise SkillsServiceError("Invalid skill name")

    monkeypatch.setattr(
        skill_service,
        "prepare_skill_archive",
        fake_prepare_skill_archive_400,
    )

    bad_request_response = await asgi_client.get(
        "/api/v1/skills/archive",
        params={"skill_name": "invalid_skill"},
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
        "/api/v1/skills/archive",
        params={"skill_name": "error_skill"},
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
async def test_v1_persona_create_preserves_explicit_empty_tools_and_skills(
    asgi_client: httpx.AsyncClient,
    fake_core_lifecycle,
):
    persona_id = "persona-empty-capabilities"

    response = await asgi_client.post(
        "/api/v1/personas",
        json={
            "persona_id": persona_id,
            "system_prompt": "A persona with no optional capabilities.",
            "tools": [],
            "skills": [],
        },
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    persona = fake_core_lifecycle.persona_mgr.personas[persona_id]
    assert persona.tools == []
    assert persona.skills == []


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
async def test_v1_log_export_packs_log_files_and_memory_logs(
    monkeypatch, tmp_path: Path, asgi_app, asgi_client: httpx.AsyncClient
):
    """The archive covers data/logs, configured log files elsewhere and memory logs."""
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    logs_dir = tmp_path / "data" / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "event_loop_watchdog.log").write_text("watchdog", encoding="utf-8")
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    (external_dir / "custom.log").write_text("current", encoding="utf-8")
    (external_dir / "custom.1.log").write_text("rotated", encoding="utf-8")
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    (other_dir / "custom.log").write_text("same name", encoding="utf-8")
    service = asgi_app.state.services.logs
    service.config["log_file_enable"] = True
    service.config["log_file_path"] = str(external_dir / "custom.log")
    service.config["trace_log_path"] = str(other_dir / "custom.log")
    service.log_broker.publish(
        {"level": "INFO", "time": 1.0, "data": "[INFO] hello", "category": "system"}
    )
    service.log_broker.publish(
        {
            "type": "trace",
            "level": "TRACE",
            "time": 2.0,
            "span_id": "span-1",
            "action": "start",
            "fields": {},
        }
    )

    response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "astrbot-diagnostics-" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert sorted(archive.namelist()) == [
            "config.json",
            "environment.json",
            "external/2/custom.log",
            "external/custom.1.log",
            "external/custom.log",
            "logs/astrbot.in-memory.log",
            "logs/event_loop_watchdog.log",
            "manifest.json",
            "plugins.json",
            "traces/history.in-memory.jsonl",
            "traces/history.jsonl",
        ]
        assert archive.read("external/custom.log") == b"current"
        assert archive.read("external/custom.1.log") == b"rotated"
        assert archive.read("external/2/custom.log") == b"same name"
        assert archive.read("logs/event_loop_watchdog.log") == b"watchdog"
        assert archive.read("logs/astrbot.in-memory.log").decode() == "[INFO] hello\n"
        traces = archive.read("traces/history.in-memory.jsonl").decode().splitlines()
        # Current LogBroker only retains ordinary logs; traces are persisted.
        assert traces == []
        manifest = json.loads(archive.read("manifest.json"))
    assert sorted(manifest["files"]) == [
        "external/2/custom.log",
        "external/custom.1.log",
        "external/custom.log",
        "logs/event_loop_watchdog.log",
    ]
    assert manifest["skipped"] == []
    assert (manifest["memory_logs"], manifest["memory_traces"]) == (1, 0)
    assert str(tmp_path) not in json.dumps(manifest)
    assert not any((tmp_path / "data" / "temp" / "log_exports").iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize("redact", [True, False])
async def test_diagnostic_export_time_range_filters_logs_and_persisted_traces(
    monkeypatch, tmp_path, asgi_app, asgi_client, redact
):
    from astrbot.core.utils.trace_store import TraceStore

    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    service = asgi_app.state.services.logs
    base = int(time.time()) - 3600
    logs_dir = tmp_path / "data" / "logs"
    logs_dir.mkdir(parents=True)
    selected = (
        f"[{datetime.fromtimestamp(base + 1).isoformat(sep=' ')}] token=private-range-value\n"
        "  selected traceback\n"
        f"[{datetime.fromtimestamp(base + 2).isoformat(sep=' ')}] last selected log\n"
    )
    (logs_dir / "astrbot.log").write_text(
        "undated preamble\n"
        f"[{datetime.fromtimestamp(base).isoformat(sep=' ')}] outside-before\n"
        + selected
        + f"[{datetime.fromtimestamp(base + 3).isoformat(sep=' ')}] outside-after\n"
        "  outside traceback\n",
        encoding="utf-8",
        newline="\n",
    )
    (logs_dir / "undated.log").write_text("unrelated undated log\n", encoding="utf-8")
    service.log_broker.publish({"time": base, "data": "outside-before"})
    service.log_broker.publish({"time": base + 1, "data": "selected memory log"})
    service.log_broker.publish({"time": base + 3, "data": "outside-after"})
    service.log_broker.log_cache.append({"type": "trace", "time": base, "data": "outside"})
    service.log_broker.log_cache.append({"type": "trace", "time": base + 1, "data": "selected"})
    path = logs_dir / "traces.db"
    service.config["trace_db_path"] = str(path)
    store = TraceStore(path, {"trace_db_max_mb": 8})
    monkeypatch.setattr(
        "astrbot.dashboard.services.log_service.get_trace_store", lambda *_: store
    )
    try:
        for index in range(60):
            trace_id = f"{index + 1:032x}"
            stamp = str((base + index) * 1_000_000_000)
            summary = {
                "trace_id": trace_id,
                "root_span_id": "b" * 16,
                "start_time_unix_nano": stamp,
                "end_time_unix_nano": stamp,
                "updated_time_unix_nano": stamp,
                "state": "completed",
                "has_errors": False,
                "has_models": False,
                "has_plugins": False,
                "has_commands": False,
                "span_count": 0,
                "attributes": {},
            }
            assert store.append({"trace": summary, "time_unix_nano": stamp})
        assert store.flush()
        response = await asgi_client.get(
            "/api/v1/logs/export",
            headers=_jwt_headers(),
            params={"redact": str(redact).lower(), "start_time": base + 1, "end_time": base + 2},
        )
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            disk_log = archive.read("logs/astrbot.log").decode()
            assert disk_log == (
                selected.replace("private-range-value", "[REDACTED]") if redact else selected
            )
            assert archive.read("logs/undated.log") == b""
            assert archive.read("logs/astrbot.in-memory.log") == b"selected memory log\n"
            assert json.loads(archive.read("traces/history.in-memory.jsonl"))["data"] == "selected"
            history = [json.loads(line) for line in archive.read("traces/history.jsonl").splitlines()]
            assert [item["trace"]["trace_id"] for item in history] == [f"{3:032x}", f"{2:032x}"]
            assert "config.json" in archive.namelist()
            assert "environment.json" in archive.namelist()
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["time_range"]["start_time"] == base + 1
            assert manifest["time_range"]["end_time"] == base + 2
            assert manifest["memory_logs"] == 1
            assert manifest["memory_traces"] == 1
            assert manifest["trace_history"]["count"] == 2
            assert manifest["trace_history"]["truncated"] is False
        assert store.list_traces(start_time=base + 58)["total"] == 2
        assert store.list_traces(end_time=base + 2)["total"] == 3
    finally:
        store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({"start_time": 20, "end_time": 10}, 400),
        ({"start_time": -1}, 422),
        ({"end_time": "invalid"}, 422),
    ],
)
async def test_diagnostic_export_rejects_invalid_time_ranges(asgi_client, params, status):
    response = await asgi_client.get(
        "/api/v1/logs/export", headers=_jwt_headers(), params=params
    )
    assert response.status_code == status


@pytest.mark.asyncio
@pytest.mark.parametrize("webui_version", ["v9.8.7", None])
async def test_diagnostic_export_includes_active_webui_version(
    monkeypatch, tmp_path, fake_core_lifecycle, fake_db, webui_version
):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    static_folder = tmp_path / "custom-webui"
    assets_folder = static_folder / "assets"
    assets_folder.mkdir(parents=True)
    if webui_version is not None:
        (assets_folder / "version").write_text(webui_version, encoding="utf-8")
    default_assets = tmp_path / "data" / "dist" / "assets"
    default_assets.mkdir(parents=True)
    (default_assets / "version").write_text("v0.0.1", encoding="utf-8")
    app = create_dashboard_asgi_app(
        core_lifecycle=fake_core_lifecycle,
        db=fake_db,
        jwt_secret=JWT_SECRET,
        static_folder=str(static_folder),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/logs/export", headers=_jwt_headers())
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        environment = json.loads(archive.read("environment.json"))
    assert environment["webui_version"] == webui_version


@pytest.mark.asyncio
async def test_v1_log_export_skips_files_that_are_not_regular(
    monkeypatch, tmp_path: Path, asgi_client: httpx.AsyncClient
):
    """A symlink in the log directory must not pull in a file from elsewhere."""
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    logs_dir = tmp_path / "data" / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "astrbot.log").write_text("ok", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("not a log", encoding="utf-8")
    link = logs_dir / "link.log"
    try:
        link.symlink_to(outside)
    except OSError:
        # No symlink privilege (e.g. Windows without developer mode): report a
        # regular file as a symlink instead, which takes the same code path.
        link.write_text("not a log", encoding="utf-8")
        real_lstat = Path.lstat

        def fake_lstat(self, *args, **kwargs):
            if self.name == "link.log":
                return os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 0, 0, 0, 0, 0, 0, 0))
            return real_lstat(self, *args, **kwargs)

        monkeypatch.setattr(Path, "lstat", fake_lstat)

    response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "logs/link.log" not in archive.namelist()
        assert archive.read("logs/astrbot.log") == b"ok"
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["skipped"] == [
        {"name": "logs/link.log", "reason": "not a regular file"}
    ]


@pytest.mark.asyncio
async def test_v1_log_export_keeps_archive_names_unique(
    monkeypatch, tmp_path: Path, asgi_app, asgi_client: httpx.AsyncClient
):
    """Log files never take the names of the generated entries."""
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    data_dir = tmp_path / "data"
    (data_dir / "logs").mkdir(parents=True)
    (data_dir / "logs" / "astrbot.in-memory.log").write_text("file log", encoding="utf-8")
    (data_dir / "traces").mkdir()
    (data_dir / "traces" / "history.in-memory.jsonl").write_text("file trace", encoding="utf-8")
    (data_dir / "manifest.json").write_text("trace log", encoding="utf-8")
    service = asgi_app.state.services.logs
    service.config["log_file_path"] = "manifest.json"
    service.config["trace_log_path"] = "traces/history.in-memory.jsonl"

    response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert archive.read("logs/2/astrbot.in-memory.log") == b"file log"
        assert archive.read("traces/2/history.in-memory.jsonl") == b"file trace"
        assert archive.read("2/manifest.json") == b"trace log"
        manifest = json.loads(archive.read("manifest.json"))
    assert sorted(manifest["files"]) == [
        "2/manifest.json",
        "logs/2/astrbot.in-memory.log",
        "traces/2/history.in-memory.jsonl",
    ]


@pytest.mark.asyncio
async def test_v1_log_export_refuses_when_disk_space_is_short(
    monkeypatch, tmp_path: Path, asgi_client: httpx.AsyncClient
):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    logs_dir = tmp_path / "data" / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "astrbot.log").write_text("x" * 1024, encoding="utf-8")
    monkeypatch.setattr(
        "astrbot.dashboard.services.log_service.shutil.disk_usage",
        lambda _path: SimpleNamespace(total=2048, used=2048, free=0),
    )

    response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())

    assert response.status_code == 400
    assert "disk space" in response.json()["message"]
    assert not any((tmp_path / "data" / "temp" / "log_exports").iterdir())


@pytest.mark.asyncio
async def test_v1_log_export_runs_one_export_at_a_time(
    monkeypatch, tmp_path: Path, asgi_app, asgi_client: httpx.AsyncClient
):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    lock = asgi_app.state.services.logs._export_lock
    lock.acquire()
    try:
        response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())
    finally:
        lock.release()

    assert response.status_code == 400
    assert "already running" in response.json()["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("redact", [True, False])
async def test_v1_log_export_requires_authentication(asgi_client, redact):
    response = await asgi_client.get("/api/v1/logs/export", params={"redact": redact})

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("redact", [True, False])
@pytest.mark.parametrize(
    "method", ["developer_header", "developer_bearer", "query", "expired"]
)
async def test_diagnostic_export_rejects_non_admin_auth(
    method, redact, fake_db, asgi_app, asgi_client
):
    from unittest.mock import Mock

    fake_db.add_api_key("diagnostic-developer-key", ["system", "config", "*"])
    export = Mock(
        side_effect=AssertionError("Export must not run before authentication")
    )
    asgi_app.state.services.logs.export_logs = export
    options = {
        "developer_header": {"headers": {"X-API-Key": "diagnostic-developer-key"}},
        "developer_bearer": {
            "headers": {"Authorization": "Bearer diagnostic-developer-key"}
        },
        "query": {"params": {"api_key": "diagnostic-developer-key"}},
        "expired": {
            "headers": {
                "Authorization": "Bearer "
                + jwt.encode(
                    {"username": "admin", "exp": 1}, JWT_SECRET, algorithm="HS256"
                )
            }
        },
    }
    options[method].setdefault("params", {})["redact"] = redact
    response = await asgi_client.get("/api/v1/logs/export", **options[method])
    assert response.status_code == 401
    export.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("redact", [True, False])
async def test_diagnostic_export_respects_redaction_for_every_section(
    monkeypatch, tmp_path, asgi_app, asgi_client, redact
):
    from urllib.parse import quote

    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    service = asgi_app.state.services.logs
    config = service.config
    config["trace_enable"] = False
    secret = "private/configured+credential"
    plugin_secret = "private-plugin-credential"
    trace_secret = "previous-provider-credential"
    aes_secret = "private-aes-credential"
    config["platform"] = [{"encoding_aes_key": aes_secret}]
    config["diagnostic_network"] = {
        "public_endpoint": "http://8.8.8.8:8080/v1",
        "public_ipv6": "https://[2606:4700:4700::1111]:443/v1",
        "local_endpoint": "http://192.168.1.2:6185/health",
    }
    config["provider_sources"] = [
        {"key": [secret], "api_base": "https://example.com/v1"}
    ]
    config.setdefault("dashboard", {}).update(
        password="private-password",
        jwt_secret="private-jwt-secret",
        password_storage_upgraded=True,
        password_change_required=False,
    )
    config["max_tokens"] = 4096
    plugin = service.core.plugin_manager.context.get_all_stars()[0]
    plugin.config = {"api_key": plugin_secret}
    logs = tmp_path / "data/logs"
    logs.mkdir(parents=True)
    (logs / "astrbot.log").write_text(
        f"{aes_secret}\n"
        f"{secret}\n{quote(secret, safe='')}\n{plugin_secret}\n{trace_secret}\nhttp://8.8.8.8:8080/v1 https://[2606:4700:4700::1111]:443/v1 http://192.168.1.2:6185/health\nAuthorization: Bearer unknown-header-token\nCookie: session=unknown; second=secret\n-----BEGIN PRIVATE KEY-----\nprivate-key-body\n-----END PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    (logs / "astrbot.1.log").write_text(plugin_secret, encoding="utf-8")
    (logs / "binary.log").write_bytes(b"\x00binary-private-data")
    service.log_broker.publish({"time": 1, "level": "INFO", "data": f"{secret} peer=8.8.8.8"})
    service.log_broker.publish(
        {"type": "trace", "time": 2, "fields": {"api_key": secret, "enabled": True}}
    )
    (logs / "traces.db").touch()

    class Store:
        def list_traces(self, **_kwargs):
            return {"traces": [{"trace_id": "a" * 32}], "total": 1}

        def get_trace(self, _trace_id):
            return {
                "trace": {"trace_id": "a" * 32},
                "spans": [
                    {"attributes": {"api_key": trace_secret, "message": plugin_secret, "peer": "::ffff:8.8.8.8", "ipv6": "2606:4700:4700:0:0:0:0:1111"}}
                ],
            }

    monkeypatch.setattr(
        "astrbot.dashboard.services.log_service.get_trace_store", lambda *_: Store()
    )
    response = await asgi_client.get(
        "/api/v1/logs/export",
        headers=_jwt_headers(),
        params={} if redact else {"redact": "false"},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert ("raw-" in response.headers["content-disposition"]) is (not redact)
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        all_text = "\n".join(archive.read(name).decode() for name in archive.namelist())
        for private in (
            secret,
            quote(secret, safe=""),
            plugin_secret,
            trace_secret,
            aes_secret,
            "private-password",
            "private-jwt-secret",
            "unknown-header-token",
            "session=unknown",
            "second=secret",
            "private-key-body",
        ):
            assert (private not in all_text) is redact
        assert "binary-private-data" not in all_text
        if not redact:
            assert archive.read("logs/astrbot.log") == (logs / "astrbot.log").read_bytes()
        exported = json.loads(archive.read("config.json"))["profiles"]["default"]
        if redact:
            assert exported["diagnostic_network"]["public_endpoint"] == "http://[PUBLIC_IP_1]:8080/v1"
            assert exported["diagnostic_network"]["public_ipv6"] == "https://[PUBLIC_IP_2]:443/v1"
            assert b"peer=[PUBLIC_IP_1]" in archive.read("logs/astrbot.in-memory.log")
            trace = json.loads(archive.read("traces/history.jsonl"))["spans"][0]["attributes"]
            assert trace["peer"] == "[PUBLIC_IP_1]"
            assert trace["ipv6"] == "[PUBLIC_IP_2]"
            assert "8.8.8.8" not in all_text
            assert "2606:4700:4700" not in all_text
        else:
            assert exported["diagnostic_network"] == config["diagnostic_network"]
            assert "::ffff:8.8.8.8" in all_text
        assert exported["diagnostic_network"]["local_endpoint"] == "http://192.168.1.2:6185/health"
        assert exported["dashboard"]["password_storage_upgraded"] is True
        assert exported["dashboard"]["password_change_required"] is False
        assert exported["max_tokens"] == 4096
        assert exported["provider_sources"][0]["key"] == ["[REDACTED]" if redact else secret]
        assert json.loads(archive.read("plugins.json"))["plugins"][0]["enabled"] is True
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["trace_history"]["count"] == 1
        assert manifest["trace_enabled"] is False
        assert manifest["redacted"] is redact
        assert "logs/traces.db" not in archive.namelist()
        assert "logs/binary.log" not in archive.namelist()
        assert archive.read("traces/history.in-memory.jsonl") == b""


@pytest.mark.asyncio
async def test_diagnostic_export_without_trace_does_not_create_or_enable_it(
    monkeypatch, tmp_path, asgi_app, asgi_client
):
    from unittest.mock import Mock

    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    asgi_app.state.services.logs.config["trace_enable"] = False
    getter = Mock(side_effect=AssertionError("No database should be opened"))
    monkeypatch.setattr(
        "astrbot.dashboard.services.log_service.get_trace_store", getter
    )
    response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["trace_enabled"] is False
        assert manifest["trace_history"]["status"] == "disabled_no_history"
        assert archive.read("traces/history.jsonl") == b""
    getter.assert_not_called()
    assert not (tmp_path / "data/logs/traces.db").exists()
    assert asgi_app.state.services.logs.config["trace_enable"] is False


@pytest.mark.asyncio
async def test_diagnostic_export_authenticates_dashboard_cookie(
    monkeypatch, tmp_path, asgi_client
):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    token = _jwt_headers()["Authorization"].removeprefix("Bearer ")
    asgi_client.cookies.set(DASHBOARD_JWT_COOKIE_NAME, token)
    response = await asgi_client.get("/api/v1/logs/export")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_diagnostic_export_redaction_failure_is_closed_and_unlocks(
    monkeypatch, tmp_path, asgi_app, asgi_client
):
    from unittest.mock import Mock

    from astrbot.dashboard.services import log_service

    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    original = log_service.collect_diagnostics
    monkeypatch.setattr(
        log_service,
        "collect_diagnostics",
        Mock(side_effect=RuntimeError("private-value-in-error")),
    )
    response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())
    assert response.status_code == 400
    assert "private-value-in-error" not in response.text
    assert not asgi_app.state.services.logs._export_lock.locked()
    assert not list((tmp_path / "data/temp/log_exports").glob("*.zip"))
    monkeypatch.setattr(log_service, "collect_diagnostics", original)
    response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_v1_persistent_trace_routes(asgi_client, asgi_app, monkeypatch, tmp_path):
    """Verify durable history/detail validation and dashboard authentication."""
    from astrbot.core.utils.trace_store import TraceStore
    from astrbot.dashboard.services import log_service

    store = TraceStore(tmp_path / "traces.db", {"trace_db_max_mb": 8})
    monkeypatch.setattr(log_service, "get_trace_store", lambda *_: store)
    stamp = str(time.time_ns())
    trace_id = "a" * 32
    span_id = "b" * 16
    summary = {
        "trace_id": trace_id,
        "root_span_id": span_id,
        "start_time_unix_nano": stamp,
        "end_time_unix_nano": stamp,
        "updated_time_unix_nano": stamp,
        "state": "completed",
        "has_errors": False,
        "has_models": False,
        "has_plugins": False,
        "span_count": 1,
        "attributes": {"astrbot.message_outline": "Hello"},
    }
    try:
        assert store.append(
            {
                "trace": summary,
                "time_unix_nano": stamp,
                "span": {
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "parent_span_id": None,
                    "name": "message",
                    "start_time_unix_nano": stamp,
                    "end_time_unix_nano": stamp,
                    "attributes": {},
                    "status": {"code": 1},
                },
            }
        )
        assert store.flush()
        response = await asgi_client.get("/api/v1/trace/history")
        assert response.status_code == 401
        token = jwt.encode(
            {"username": "astrbot", "exp": int(time.time()) + 600},
            JWT_SECRET,
            algorithm="HS256",
        )
        headers = {"Authorization": f"Bearer {token}"}
        response = await asgi_client.get(
            "/api/v1/trace/history",
            params={"limit": 1, "query": "Hello"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 1
        response = await asgi_client.get(
            "/api/v1/trace/history", params={"limit": 1, "page": 999}, headers=headers
        )
        assert response.json()["data"]["page"] == 1
        assert len(response.json()["data"]["traces"]) == 1
        assert (
            await asgi_client.get("/api/v1/trace/history?page=0", headers=headers)
        ).status_code == 422
        response = await asgi_client.get(f"/api/v1/trace/{trace_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["spans"][0]["span_id"] == span_id
        assert (
            await asgi_client.get("/api/v1/trace/history?limit=101", headers=headers)
        ).status_code == 422
        assert (
            await asgi_client.get("/api/v1/trace/invalid", headers=headers)
        ).status_code == 422
        assert (
            await asgi_client.get("/api/v1/trace/" + "c" * 32, headers=headers)
        ).status_code == 404
        assert (
            await asgi_client.get("/api/v1/trace/settings", headers=headers)
        ).status_code == 200
        monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
        asgi_app.state.services.logs.config.update(
            trace_enable=False, trace_db_path=str(tmp_path / "traces.db")
        )
        response = await asgi_client.get("/api/v1/logs/export", headers=headers)
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["trace_enabled"] is False
            assert manifest["trace_history"]["count"] == 1
            history = json.loads(archive.read("traces/history.jsonl"))
            assert history["trace"]["trace_id"] == trace_id
            assert history["spans"][0]["name"] == "message"
    finally:
        store.close()


@pytest.mark.asyncio
async def test_v1_trace_storage_cleanup_target(asgi_client, monkeypatch):
    """Validate trace cleanup requests without touching application data."""
    usage = {
        "logs": {"size_bytes": 10},
        "cache": {"size_bytes": 20},
        "traces": {"size_bytes": 30},
        "total_bytes": 60,
    }
    cleanup = AsyncMock(return_value={"removed_traces": 3, "status": usage})
    monkeypatch.setattr(stat_service.StatService, "cleanup_storage", cleanup)
    monkeypatch.setattr(
        stat_service.StatService, "get_storage_status", AsyncMock(return_value=usage)
    )
    token = jwt.encode(
        {"username": "astrbot", "exp": int(time.time()) + 600},
        JWT_SECRET,
        algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {token}"}
    assert (
        await asgi_client.post(
            "/api/v1/stats/storage/cleanup", json={"target": "traces"}
        )
    ).status_code == 401
    response = await asgi_client.post(
        "/api/v1/stats/storage/cleanup",
        json={"target": "traces"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["removed_traces"] == 3
    cleanup.assert_awaited_once_with("traces")
    response = await asgi_client.get("/api/v1/stats/storage", headers=headers)
    assert response.json()["data"]["total_bytes"] == 60
    assert response.json()["data"]["traces"]["size_bytes"] == 30
    assert (
        await asgi_client.post(
            "/api/v1/stats/storage/cleanup", json={"target": "invalid"}, headers=headers
        )
    ).status_code == 422
