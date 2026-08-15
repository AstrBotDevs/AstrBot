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
    """Allow-all authorization double for route-focused Dashboard tests."""

    async def authorize(self, *_args, **_kwargs):
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
def fake_core_lifecycle():
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
            authorization=FakeAuthorizationService(),
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


def test_dashboard_uses_the_runtime_log_broker(
    fake_core_lifecycle,
    fake_db: FakeDb,
):
    """Dashboard logs must use the explicit completed-runtime dependency."""
    app = create_dashboard_asgi_app(
        runtime=fake_core_lifecycle,
        core_control=SimpleNamespace(),
        db=fake_db,
        jwt_secret=JWT_SECRET,
    )

    assert app.state.services.logs.log_broker is fake_core_lifecycle.log_broker


@pytest_asyncio.fixture
async def asgi_client(asgi_app):
    transport = httpx.ASGITransport(app=asgi_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_dashboard_shutdown_owns_update_service(asgi_app: FastAPI, monkeypatch):
    update_shutdown = AsyncMock()
    page_shutdown = AsyncMock()
    ticket_shutdown = AsyncMock()
    monkeypatch.setattr(asgi_app.state.services.updates, "shutdown", update_shutdown)
    monkeypatch.setattr(
        asgi_app.state.services.plugin_page_sessions,
        "shutdown",
        page_shutdown,
    )
    monkeypatch.setattr(
        asgi_app.state.services.plugin_file_tickets,
        "shutdown",
        ticket_shutdown,
    )

    for handler in asgi_app.router.on_shutdown:
        await handler()

    update_shutdown.assert_awaited_once()
    page_shutdown.assert_awaited_once()
    ticket_shutdown.assert_awaited_once()


def _jwt_headers() -> dict[str, str]:
    token = DashboardTokenValidator(JWT_SECRET).issue(
        "fastapi-v1-test",
        account_id=TEST_DASHBOARD_ACCOUNT_ID,
    )
    return {"Authorization": f"Bearer {token}"}


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
        runtime=fake_core_lifecycle,
        core_control=fake_core_lifecycle,
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


@pytest.mark.asyncio
async def test_dashboard_unhandled_errors_use_the_standard_error_envelope(
    asgi_app: FastAPI,
):
    handler = asgi_app.exception_handlers[Exception]
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/test-unhandled-error",
            "headers": [],
        }
    )
    response = await handler(request, RuntimeError("api_key=secret-value"))

    assert response.status_code == 500
    assert json.loads(response.body) == {
        "status": "error",
        "message": "Internal server error",
    }


@pytest.mark.asyncio
async def test_v1_scope_dependencies_accept_dashboard_cookie(
    asgi_client: httpx.AsyncClient,
):
    token = DashboardTokenValidator(JWT_SECRET).issue(
        "fastapi-v1-cookie-test",
        account_id=TEST_DASHBOARD_ACCOUNT_ID,
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
async def test_accountless_dashboard_session_is_rejected(
    asgi_client: httpx.AsyncClient,
):
    token = DashboardTokenValidator(JWT_SECRET).issue("legacy-dashboard-user")

    response = await asgi_client.get(
        "/api/v1/bots",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_legacy_dashboard_token_without_required_claims_is_rejected(
    asgi_client: httpx.AsyncClient,
):
    token = jwt.encode(
        {"username": "legacy-dashboard-user"},
        JWT_SECRET,
        algorithm="HS256",
    )

    response = await asgi_client.get(
        "/api/v1/bots",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("token_type", "wrong-token-type"),
        ("aud", "wrong-audience"),
        ("iss", "urn:astrbot:dashboard:wrong-instance"),
        ("sid", ""),
        ("jti", ""),
        ("sub", "different-user"),
    ],
)
async def test_dashboard_session_claim_mismatch_is_rejected(
    asgi_client: httpx.AsyncClient,
    claim: str,
    value: str,
):
    validator = DashboardTokenValidator(JWT_SECRET)
    payload = jwt.decode(
        validator.issue("fastapi-v1-test", account_id=TEST_DASHBOARD_ACCOUNT_ID),
        options={"verify_signature": False},
    )
    payload[claim] = value
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    response = await asgi_client.get(
        "/api/v1/bots",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing_claim",
    ["exp", "iat", "iss", "aud", "sub", "username", "sid", "jti", "token_type"],
)
async def test_dashboard_session_missing_required_claim_is_rejected(
    asgi_client: httpx.AsyncClient,
    missing_claim: str,
):
    validator = DashboardTokenValidator(JWT_SECRET)
    payload = jwt.decode(
        validator.issue("fastapi-v1-test", account_id=TEST_DASHBOARD_ACCOUNT_ID),
        options={"verify_signature": False},
    )
    del payload[missing_claim]
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    response = await asgi_client.get(
        "/api/v1/bots",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_each_dashboard_login_token_has_a_distinct_session_id(asgi_app: FastAPI):
    validator = asgi_app.state.dashboard_token_validator

    first = validator.validate(
        validator.issue("dashboard-user", account_id=TEST_DASHBOARD_ACCOUNT_ID)
    )
    second = validator.validate(
        validator.issue("dashboard-user", account_id=TEST_DASHBOARD_ACCOUNT_ID)
    )

    assert first.sid != second.sid
    assert first.jti != second.jti


@pytest.mark.asyncio
async def test_cookie_authenticated_mutation_rejects_untrusted_origins(
    asgi_client: httpx.AsyncClient,
):
    token = DashboardTokenValidator(JWT_SECRET).issue(
        "cookie-user",
        account_id=TEST_DASHBOARD_ACCOUNT_ID,
    )
    cookie = {"Cookie": f"{DASHBOARD_JWT_COOKIE_NAME}={token}"}

    missing = await asgi_client.post("/api/v1/auth/logout", headers=cookie)
    opaque = await asgi_client.post(
        "/api/v1/auth/logout",
        headers={**cookie, "Origin": "null"},
    )
    cross_site = await asgi_client.post(
        "/api/v1/auth/logout",
        headers={**cookie, "Origin": "https://attacker.example"},
    )
    same_origin = await asgi_client.post(
        "/api/v1/auth/logout",
        headers={**cookie, "Origin": "http://testserver"},
    )

    assert missing.status_code == 403
    assert opaque.status_code == 403
    assert cross_site.status_code == 403
    assert same_origin.status_code == 200
    set_cookie_headers = same_origin.headers.get_list("set-cookie")
    assert any("Path=/api/v1" in header for header in set_cookie_headers)
    assert any("Path=/" in header for header in set_cookie_headers)


@pytest.mark.asyncio
async def test_logout_ignores_invalid_cookie_and_still_clears_it(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.post(
        "/api/v1/auth/logout",
        headers={"Cookie": f"{DASHBOARD_JWT_COOKIE_NAME}=invalid"},
    )

    assert response.status_code == 200
    assert len(response.headers.get_list("set-cookie")) == 2


@pytest.mark.asyncio
async def test_cookie_csrf_uses_trusted_proxy_external_origin(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
):
    astrbot_config = asgi_app.state.astrbot_config
    previous_dashboard_config = astrbot_config.get("dashboard")
    astrbot_config["dashboard"] = {"trust_proxy_headers": True}
    token = DashboardTokenValidator(JWT_SECRET).issue(
        "proxy-user",
        account_id=TEST_DASHBOARD_ACCOUNT_ID,
    )
    try:
        response = await asgi_client.post(
            "/api/v1/auth/logout",
            headers={
                "Cookie": f"{DASHBOARD_JWT_COOKIE_NAME}={token}",
                "Origin": "https://dashboard.example",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "dashboard.example",
            },
        )
    finally:
        if previous_dashboard_config is None:
            del astrbot_config["dashboard"]
        else:
            astrbot_config["dashboard"] = previous_dashboard_config

    assert response.status_code == 200


@pytest.mark.integration
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
    plugin_dashboard_paths = [
        "/api/v1/plugins/{extension_id}/dashboard",
        "/api/v1/plugins/{extension_id}/dashboard/pages/{page_id}/session",
        "/api/v1/plugins/{extension_id}/dashboard/actions/{action_id}",
        "/api/v1/plugins/{extension_id}/dashboard/uploads/{action_id}",
        "/api/v1/plugins/{extension_id}/dashboard/files/{action_id}",
    ]
    for path in plugin_dashboard_paths:
        assert path in spec["paths"]
        operation = next(iter(spec["paths"][path].values()))
        assert operation["security"] == [
            {"DashboardBearerAuth": [], "DashboardCookieAuth": []}
        ]
    assert (
        spec["components"]["securitySchemes"]["DashboardBearerAuth"]["scheme"]
        == "bearer"
    )
    assert spec["components"]["securitySchemes"]["DashboardCookieAuth"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": "astrbot_dashboard_jwt",
    }
    assert not any("/api/plugin-pages/" in path for path in spec["paths"])
    assert not any("/api/plugin-files/" in path for path in spec["paths"])
    session_operation = spec["paths"][plugin_dashboard_paths[1]]["post"]
    file_operation = spec["paths"][plugin_dashboard_paths[4]]["post"]
    assert "Set-Cookie" in session_operation["responses"]["200"]["headers"]
    assert "Set-Cookie" in file_operation["responses"]["200"]["headers"]
    upload_operation = spec["paths"][plugin_dashboard_paths[3]]["post"]
    upload_schema = upload_operation["requestBody"]["content"]["multipart/form-data"][
        "schema"
    ]
    assert upload_schema["required"] == ["metadata", "file"]
    assert "/api/v1/conversations" in spec["paths"]
    assert "/api/v1/mcp/servers" in spec["paths"]
    assert "/api/v1/skills" in spec["paths"]
    assert "/api/v1/file" in spec["paths"]
    assert "/api/v1/plugins/by-id" not in spec["paths"]
    assert "/api/v1/plugins/config" not in spec["paths"]
    assert "/api/v1/plugins/config/schema" not in spec["paths"]
    assert "/api/v1/plugins/config-files" not in spec["paths"]
    assert "/api/v1/plugins/readme" not in spec["paths"]
    assert "/api/v1/plugins/changelog" not in spec["paths"]
    assert "/api/v1/plugins/reload" not in spec["paths"]
    assert "/api/v1/plugins/enabled" not in spec["paths"]
    assert "/api/v1/plugins/version-support/check" not in spec["paths"]
    assert "/api/v1/plugins/validate/repo" not in spec["paths"]
    assert "/api/v1/plugin-sources/by-id" not in spec["paths"]
    assert "/api/v1/mcp/servers/by-name" not in spec["paths"]
    assert "/api/v1/mcp/servers/enabled" not in spec["paths"]
    assert "/api/v1/mcp/servers/test" not in spec["paths"]
    assert "/api/v1/skills/by-name" not in spec["paths"]
    assert "/api/v1/skills/archive" not in spec["paths"]
    assert "/api/v1/skills/files" not in spec["paths"]
    assert "/api/v1/skills/file" not in spec["paths"]
    assert "/api/v1/personas/by-id" not in spec["paths"]


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
        runtime=fake_core_lifecycle,
        core_control=fake_core_lifecycle,
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
        headers=_jwt_headers(),
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
async def test_v1_backup_download_requires_authorized_dashboard_bearer(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    tmp_path: Path,
):
    service = asgi_app.state.services.backups
    service.backup_dir = str(tmp_path)
    (tmp_path / "backup.zip").write_bytes(b"backup")
    valid_token = DashboardTokenValidator(JWT_SECRET).issue(
        "backup-user",
        account_id=TEST_DASHBOARD_ACCOUNT_ID,
    )

    bearer = await asgi_client.get(
        "/api/v1/backups/backup.zip",
        headers={"Authorization": f"bEaReR    {valid_token}"},
    )
    query_token = await asgi_client.get(
        "/api/v1/backups/backup.zip",
        params={"token": valid_token},
    )

    assert bearer.status_code == 200
    assert bearer.content == b"backup"
    assert query_token.status_code == 401


@pytest.mark.asyncio
async def test_v1_backup_download_rejects_non_dashboard_credentials(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    tmp_path: Path,
):
    service = asgi_app.state.services.backups
    service.backup_dir = str(tmp_path)
    (tmp_path / "backup.zip").write_bytes(b"backup")
    valid_token = DashboardTokenValidator(JWT_SECRET).issue(
        "backup-user",
        account_id=TEST_DASHBOARD_ACCOUNT_ID,
    )
    expired_payload = jwt.decode(valid_token, options={"verify_signature": False})
    expired_payload["exp"] = 0
    expired_token = jwt.encode(expired_payload, JWT_SECRET, algorithm="HS256")

    empty_credentials = await asgi_client.get(
        "/api/v1/backups/backup.zip",
        headers={"Authorization": "Bearer    "},
    )
    wrong_scheme = await asgi_client.get(
        "/api/v1/backups/backup.zip",
        headers={"Authorization": f"ApiKey {valid_token}"},
    )
    expired = await asgi_client.get(
        "/api/v1/backups/backup.zip",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    forged = await asgi_client.get(
        "/api/v1/backups/backup.zip",
        headers={"Authorization": f"Bearer {valid_token}forged"},
    )

    assert empty_credentials.status_code == 401
    assert expired.status_code == 401
    # A malformed Dashboard bearer is checked as a legacy raw API-key input
    # only after JWT validation fails. Neither it nor an explicit API Key can
    # carry the Dashboard-only `system` capability.
    assert forged.status_code == 403
    assert wrong_scheme.status_code == 403


@pytest.mark.asyncio
async def test_v1_backup_download_rejects_missing_authorization_service(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    tmp_path: Path,
):
    """Backup archives cannot bypass an unavailable authorization runtime."""

    service = asgi_app.state.services.backups
    service.backup_dir = str(tmp_path)
    (tmp_path / "backup.zip").write_bytes(b"backup")
    asgi_app.state.runtime.services.authorization = None

    response = await asgi_client.get(
        "/api/v1/backups/backup.zip",
        headers=_jwt_headers(),
    )

    assert response.status_code == 503
    assert response.json()["message"] == "Authorization unavailable"


@pytest.mark.asyncio
async def test_v1_openapi_uses_pydantic_request_bodies(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    spec = response.json()
    schemas = spec["components"]["schemas"]
    assert "BotRegistrationRequest" in schemas
    assert "BotActionRequest" in schemas
    assert "ConfigContentRequest" in schemas

    bot_registration = spec["paths"]["/api/v1/bot-types/{bot_type}/registration"][
        "post"
    ]
    assert bot_registration["parameters"][0]["name"] == "bot_type"
    assert bot_registration["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/BotRegistrationRequest")

    bot_action = spec["paths"]["/api/v1/bots/{bot_id}/actions"]["post"]
    assert bot_action["parameters"][0]["name"] == "bot_id"
    assert bot_action["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/BotActionRequest")

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
async def test_v1_conversation_detail_requires_user_id(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.get(
        "/api/v1/conversations/conversation%2Fwith%2Fslash",
        headers=_jwt_headers(),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_conversation_export_rejects_missing_authorization_service(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
):
    """A valid Dashboard JWT must not bypass unavailable authorization."""

    asgi_app.state.runtime.services.authorization = None

    response = await asgi_client.post(
        "/api/v1/conversations/export",
        json={"conversations": []},
        headers=_jwt_headers(),
    )

    assert response.status_code == 503
    assert response.json()["message"] == "Authorization unavailable"


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
    assert fake_db.touched_key_ids == ["config-key", "config-key", "config-key"]


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
