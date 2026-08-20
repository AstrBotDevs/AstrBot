from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import SpooledTemporaryFile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import jwt
import pytest
import pytest_asyncio
from fastapi import FastAPI, Request

import astrbot.dashboard.api.app as dashboard_api_app
import astrbot.dashboard.api.backups as dashboard_backups_api
import astrbot.dashboard.api.knowledge_bases as dashboard_knowledge_bases_api
import astrbot.dashboard.api.memory as dashboard_memory_api
import astrbot.dashboard.api.sessions as dashboard_sessions_api
import astrbot.dashboard.api.skills as dashboard_skills_api
import astrbot.dashboard.services.config_service as config_service
from astrbot.core.auth.registry import dashboard_api_capability_specs
from astrbot.core.file_token_service import FileTokenService
from astrbot.core.log import LogBroker
from astrbot.core.platform.send_result import PlatformSendResult
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.star.dashboard_extension import DashboardExtensionRegistry
from astrbot.core.star.plugin_catalog import PluginCatalog
from astrbot.core.star.plugin_extension_coordinator import PluginExtensionCoordinator
from astrbot.core.utils.active_event_registry import ActiveEventRegistry
from astrbot.core.utils.llm_metadata import LLMMetadataCatalog
from astrbot.core.utils.totp import TotpRuntimeState
from astrbot.core.webchat.queue_manager import WebChatQueueManager
from astrbot.core.webchat.run_coordinator import WebChatRunCoordinator
from astrbot.dashboard.api.app import create_dashboard_asgi_app
from astrbot.dashboard.services.api_key_scopes import SCOPE_INCLUDES
from astrbot.dashboard.services.api_key_service import ApiKeyService
from astrbot.dashboard.services.auth_service import (
    DASHBOARD_JWT_COOKIE_NAME,
    DashboardTokenValidator,
)
from astrbot.dashboard.services.backup_service import BackupServiceError
from astrbot.dashboard.services.chat_service import ChatServiceError
from astrbot.dashboard.services.knowledge_base_service import KnowledgeBaseServiceError
from astrbot.dashboard.services.memory_service import MemoryServiceError
from astrbot.dashboard.services.open_api_service import OpenApiServiceError
from astrbot.dashboard.services.platform_service import PlatformServiceError
from astrbot.dashboard.services.plugin_service import (
    PLUGIN_UPDATE_SOURCE_REQUIRED_MESSAGE,
    PluginServiceError,
)
from astrbot.dashboard.services.session_management_service import (
    SessionManagementServiceError,
)
from astrbot.dashboard.services.skills_service import SkillArchive, SkillsServiceError

JWT_SECRET = "fastapi-v1-test-secret-with-32-bytes"

TEST_DASHBOARD_ACCOUNT_ID = "fastapi-v1-dashboard-account"


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
    def __init__(self, db: FakeDb) -> None:
        self.db = db

    def fetchall(self) -> list[tuple[str]]:
        return [(umo,) for umo in self.db.umo_ids]

    def scalars(self) -> _FakeScalarResult:
        return _FakeScalarResult(self.db.preferences)


class _FakeDbSession:
    def __init__(self, db: FakeDb) -> None:
        self.db = db

    async def execute(self, _statement) -> _FakeDbResult:
        return _FakeDbResult(self.db)


class _FakeDbContext:
    def __init__(self, db: FakeDb) -> None:
        self.db = db

    async def __aenter__(self) -> _FakeDbSession:
        return _FakeDbSession(self.db)

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class FakeDb:
    def __init__(self) -> None:
        self.api_keys: dict[str, FakeApiKey] = {}
        self.capabilities: set[tuple[str, str, str, str]] = set()
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
        key_id = f"key-{raw_key}"
        self.api_keys[ApiKeyService.hash_key(raw_key)] = FakeApiKey(
            key_id=key_id,
            scopes=scopes,
        )
        subject_id = f"api-key:{key_id}"
        expanded = list(scopes)
        for scope in scopes:
            expanded.extend(SCOPE_INCLUDES.get(scope, ()))
        for action, resource_type, resource_id in dashboard_api_capability_specs(
            expanded
        ):
            self.capabilities.add((subject_id, action, resource_type, resource_id))

    def capability_allows(self, subject_id: str, action: str, resource) -> bool:
        return (
            subject_id,
            action,
            resource.type,
            resource.id,
        ) in self.capabilities


class FakeLlmTools:
    def __init__(self) -> None:
        self.config = {
            "mcpServers": {
                "demo-server": {
                    "active": True,
                    "url": "https://93.184.216.34/demo-server",
                    "transport": "streamable_http",
                },
                "modelscope/demo": {
                    "active": True,
                    "url": "https://93.184.216.34/modelscope-demo",
                    "transport": "streamable_http",
                },
            }
        }
        self.mcp_server_runtime_view = {}
        self.func_list = []
        self.enabled_servers: list[tuple[str, dict]] = []
        self.disabled_servers: list[str] = []
        self.tested_configs: list[dict] = []
        self.synced_modelscope_tokens: list[str] = []
        self.activated_tools: list[str] = []
        self.deactivated_tools: list[str] = []

    def load_mcp_config(self) -> dict:
        return copy.deepcopy(self.config)

    def bind_plugin_lookup(self, _plugin_catalog) -> None:
        return None

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
        timeout_seconds: int,
    ) -> None:
        _ = timeout_seconds
        self.enabled_servers.append((name, copy.deepcopy(config)))

    async def disable_mcp_server(self, name: str, *, timeout_seconds: int) -> None:
        _ = timeout_seconds
        self.disabled_servers.append(name)

    def iter_builtin_tools(self) -> list:
        return []

    def is_builtin_tool(self, _tool_name: str) -> bool:
        return False

    async def activate_llm_tool(self, _tool_name: str) -> bool:
        self.activated_tools.append(_tool_name)
        return True

    async def deactivate_llm_tool(self, _tool_name: str) -> bool:
        self.deactivated_tools.append(_tool_name)
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
        self.cleared_provider_calls: list[dict] = []
        self.cleared_all_provider_calls: list[str] = []
        self.tool_manager = FakeLlmTools()

    def dynamic_import_provider(self, provider_type: str) -> None:
        raise ImportError(provider_type)

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

    async def clear_provider_override(self, umo: str, provider_type) -> None:
        self.cleared_provider_calls.append({"umo": umo, "provider_type": provider_type})

    async def clear_all_provider_overrides(self, umo: str) -> None:
        self.cleared_all_provider_calls.append(umo)


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

    async def send_by_session(self, session, message_chain) -> PlatformSendResult:
        self.sent_messages.append((session, message_chain))
        return PlatformSendResult(
            platform_id=self.platform_id,
            success=True,
            target=session.session_id,
            message_count=len(message_chain.chain),
        )

    async def send_to_session(self, session, message_chain) -> PlatformSendResult:
        self.sent_messages.append((session, message_chain))
        return PlatformSendResult(
            platform_id=self.platform_id,
            success=True,
            target=session.session_id,
            message_count=len(message_chain.chain),
        )


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

    def get_conf_id_for_umop(self, umo: str) -> str | None:
        return self.umop_to_conf_id.get(umo)


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
    def save_config(self, post_config: dict | None = None, *, indent: int = 2) -> None:
        _ = indent
        if post_config is None:
            post_config = dict(self)
        self.clear()
        self.update(copy.deepcopy(post_config))

    async def save_config_async(
        self,
        post_config: dict | None = None,
        *,
        indent: int = 2,
    ) -> bool:
        self.save_config(post_config, indent=indent)
        return True


class FakeAuthorizationService:
    """Dashboard allow-all double that still enforces API-key capabilities."""

    def __init__(self, db: FakeDb) -> None:
        self.db = db

    async def authorize(self, subject, action, resource, context):
        if getattr(subject, "kind", None) == "api-key":
            allowed = self.db.capability_allows(subject.id, action, resource)
            return SimpleNamespace(allowed=allowed, requires_step_up=False)
        return SimpleNamespace(allowed=True, requires_step_up=False)


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
                    "type": "openai_chat_completions",
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


@pytest.fixture
def fake_db() -> FakeDb:
    return FakeDb()


@pytest.fixture
def fake_core_lifecycle(fake_db: FakeDb):
    config = _build_fake_config()
    provider_manager = FakeProviderManager(config)
    catalogs = RuntimeCatalogs()
    catalogs.tools = provider_manager.tool_manager
    webchat_run_coordinator = WebChatRunCoordinator(WebChatQueueManager())
    platform = FakePlatform("webchat-main")
    umop_config_router = FakeUmopConfigRouter()
    reloaded_config_ids = []
    platform_reload_configs = []
    terminated_platform_ids = []

    async def reload_pipeline_scheduler(config_id: str) -> None:
        reloaded_config_ids.append(config_id)

    async def remove_pipeline_scheduler(config_id: str) -> None:
        reloaded_config_ids.remove(config_id)

    async def restart() -> None:
        return None

    async def reload_platform(config: dict) -> None:
        platform_reload_configs.append(copy.deepcopy(config))

    async def load_platform(config: dict) -> None:
        platform_reload_configs.append(copy.deepcopy(config))

    async def terminate_platform(platform_id: str) -> None:
        terminated_platform_ids.append(platform_id)

    demo_plugin = SimpleNamespace(
        name="astrbot_plugin_demo",
        module_path="tests.fastapi.dashboard.demo_plugin",
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
        config=None,
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

    catalogs.plugins.publish(demo_plugin)
    plugin_catalog = PluginCatalog(catalogs)
    extension_registry = DashboardExtensionRegistry()
    plugin_extensions = PluginExtensionCoordinator(extension_registry)

    class FakePreferences:
        def __init__(self) -> None:
            self.values: dict[str, object] = {}

        async def global_get(self, key: str, default: object = None) -> object:
            return self.values.get(key, default)

        async def global_put(self, key: str, value: object) -> None:
            self.values[key] = value

        async def session_get(self, *_args, **_kwargs) -> list:
            return []

        async def session_put(self, *_args, **_kwargs) -> None:
            return None

    plugin_lifecycle = SimpleNamespace(
        reload_failed_plugin=reload_plugin,
        reload=reload_plugin,
        install_plugin=AsyncMock(),
        install_plugin_from_file=AsyncMock(),
        update_plugin=AsyncMock(),
        uninstall_plugin=AsyncMock(),
        uninstall_failed_plugin=AsyncMock(),
        turn_off_plugin=turn_off_plugin,
        turn_on_plugin=turn_on_plugin,
    )
    plugin_loader = SimpleNamespace(
        bundled_store_path="",
        failure_info=None,
        failed_plugins=lambda: {},
    )
    plugin_packages = SimpleNamespace(store_path="")

    return SimpleNamespace(
        astrbot_config=config,
        log_broker=LogBroker(),
        services=SimpleNamespace(
            demo_mode=False,
            authorization=FakeAuthorizationService(fake_db),
            preferences=FakePreferences(),
            file_token_service=FileTokenService(),
            pip_installer=SimpleNamespace(install=lambda *_args, **_kwargs: None),
            computer_runtime=SimpleNamespace(
                sync_skills_to_active_sandboxes=AsyncMock(),
            ),
            html_renderer=SimpleNamespace(),
            llm_metadata_catalog=LLMMetadataCatalog(),
            totp_runtime_state=TotpRuntimeState(),
        ),
        updater=FakeAstrBotUpdator(),
        catalogs=catalogs,
        webchat_run_coordinator=webchat_run_coordinator,
        start_time=1234567890,
        astrbot_config_mgr=SimpleNamespace(
            confs={"default": config},
            default_conf=config,
            get_conf_list=lambda: [{"id": "default", "name": "default"}],
        ),
        reload_pipeline_scheduler=reload_pipeline_scheduler,
        remove_pipeline_scheduler=remove_pipeline_scheduler,
        restart=restart,
        reloaded_config_ids=reloaded_config_ids,
        platform_reload_configs=platform_reload_configs,
        terminated_platform_ids=terminated_platform_ids,
        umop_config_router=umop_config_router,
        platform_manager=SimpleNamespace(
            fake_platform=platform,
            find_inst_by_webhook_uuid=(
                lambda webhook_uuid: (
                    platform
                    if webhook_uuid == platform.config["webhook_uuid"]
                    else None
                )
            ),
            send_to_session=platform.send_to_session,
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
            catalog=plugin_catalog,
            extensions=plugin_extensions,
            lifecycle=plugin_lifecycle,
            loader=plugin_loader,
            packages=plugin_packages,
        ),
        execution_context=SimpleNamespace(
            active_event_registry=ActiveEventRegistry(),
        ),
        star_context=SimpleNamespace(),
        knowledge_base_manager=None,
        memory_manager=SimpleNamespace(),
        cron_manager=SimpleNamespace(),
        subagent_orchestrator=SimpleNamespace(reload_from_config=AsyncMock()),
    )


@pytest.fixture
def asgi_app(fake_core_lifecycle, fake_db: FakeDb):
    app = create_dashboard_asgi_app(
        runtime=fake_core_lifecycle,
        core_control=fake_core_lifecycle,
        db=fake_db,
        jwt_secret=JWT_SECRET,
    )

    async def validate_dashboard_principal(principal) -> bool:
        return principal.account_id == TEST_DASHBOARD_ACCOUNT_ID

    app.state.services.auth.validate_dashboard_principal = validate_dashboard_principal
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
    token = DashboardTokenValidator(JWT_SECRET).issue(
        "fastapi-v1-test",
        account_id=TEST_DASHBOARD_ACCOUNT_ID,
    )
    return {"Authorization": f"Bearer {token}"}


class _RecordingErrorLogger:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def error(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))


_SENSITIVE_INTERNAL_ERROR = (
    "api_key=api-key-12345 "
    "Authorization: Bearer bearer-token-12345 "
    "password=dashboard-password "
    "https://internal.example.test/control?api_key=internal-api-key "
    r"C:\AstrBot\data\secrets.json "
    "/srv/astrbot/data/secret.txt"
)

_SENSITIVE_ERROR_FRAGMENTS = (
    "api-key-12345",
    "bearer-token-12345",
    "dashboard-password",
    "internal.example.test",
    r"C:\AstrBot\data\secrets.json",
    "/srv/astrbot/data/secret.txt",
)

_DASHBOARD_API_ERROR_CASES = (
    pytest.param(
        "sessions",
        "sessions",
        "list_all_umos_with_status",
        "GET",
        "/api/v1/sessions",
        None,
        SessionManagementServiceError,
        200,
        dashboard_sessions_api,
        id="sessions",
    ),
    pytest.param(
        "backups",
        "backups",
        "list_backups",
        "GET",
        "/api/v1/backups",
        None,
        BackupServiceError,
        200,
        dashboard_backups_api,
        id="backups",
    ),
    pytest.param(
        "knowledge_bases",
        "knowledge_bases",
        "list_kbs",
        "GET",
        "/api/v1/knowledge-bases",
        None,
        KnowledgeBaseServiceError,
        200,
        dashboard_knowledge_bases_api,
        id="knowledge_bases",
    ),
    pytest.param(
        "memory",
        "memory",
        "list_facts",
        "GET",
        "/api/v1/memory/facts",
        None,
        MemoryServiceError,
        200,
        dashboard_memory_api,
        id="memory",
    ),
    pytest.param(
        "skills",
        "skills",
        "get_skills",
        "GET",
        "/api/v1/skills",
        None,
        SkillsServiceError,
        200,
        dashboard_skills_api,
        id="skills",
    ),
    pytest.param(
        "files",
        "chat",
        "resolve_webchat_file",
        "GET",
        "/api/v1/files/content",
        None,
        ChatServiceError,
        200,
        dashboard_api_app,
        id="files",
    ),
    pytest.param(
        "chat",
        "chat",
        "new_session",
        "GET",
        "/api/v1/chat/sessions/new",
        None,
        ChatServiceError,
        200,
        dashboard_api_app,
        id="chat",
    ),
    pytest.param(
        "open_api",
        "open_api",
        "send_message",
        "POST",
        "/api/v1/im/messages",
        {
            "umo": "webchat-main:FriendMessage:test-session",
            "message": "hello",
        },
        OpenApiServiceError,
        400,
        dashboard_api_app,
        id="open_api",
    ),
)


async def _request_api_error_case(
    client: httpx.AsyncClient,
    *,
    method: str,
    path: str,
    payload: dict | None,
) -> httpx.Response:
    request_kwargs: dict[str, object] = {"headers": _jwt_headers()}
    if payload is not None:
        request_kwargs["json"] = payload
    return await client.request(method, path, **request_kwargs)


def _assert_error_log_is_redacted(logger: _RecordingErrorLogger) -> None:
    assert logger.calls
    for args, kwargs in logger.calls:
        assert "exc_info" not in kwargs
        rendered = " ".join(str(arg) for arg in args)
        for fragment in _SENSITIVE_ERROR_FRAGMENTS:
            assert fragment not in rendered


__all__ = [name for name in globals() if not name.startswith("__")]
