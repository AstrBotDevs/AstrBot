"""Real-Core E2E and public-surface coverage audit across the 7-plugin SDK API matrix."""

from __future__ import annotations

import ast
import asyncio
import json
import shutil
from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.datastructures import Headers

from astrbot_sdk import capabilities as sdk_capabilities
from astrbot_sdk import lifecycle as sdk_lifecycle
from astrbot_sdk import message_components as sdk_components
from astrbot_sdk import on as sdk_on
from astrbot_sdk import services as sdk_services
from astrbot_sdk import tasks as sdk_tasks
from astrbot_sdk.context import PluginContext
from astrbot_sdk.conversations import ConversationService
from astrbot_sdk.llm import LLMService
from astrbot_sdk.plugins import PluginRegistryService
from astrbot_sdk.render import RenderService
from astrbot_sdk.tools import ToolService
from astrbot_sdk.web import INLINE_BODY_LIMIT, WebService

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.api.provider import Provider
from astrbot.api.web import PluginRequest, bind_request_context
from astrbot.core import file_token_service
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.chatui import ViewResult as CoreViewResult
from astrbot.core.chatui import resolve_view, view_store
from astrbot.core.config import AstrBotConfig
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.cron.manager import CronJobManager
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.message.components import (
    ActionRow,
    ButtonInteraction,
    Json,
    Node,
    Nodes,
    UIInteraction,
    ViewContext,
)
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.pipeline.context_utils import call_handler
from astrbot.core.platform.astrbot_message import Group
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.platform.platform import PlatformStatus
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.core.provider.entities import (
    LLMResponse,
    ProviderMeta,
    ProviderRequest,
    ProviderType,
)
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.provider.provider import EmbeddingProvider, STTProvider, TTSProvider
from astrbot.core.provider.register import llm_tools
from astrbot.core.star.context import Context
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.sdk_bridge import SDKPluginManager
from astrbot.core.star.sdk_bridge.services import sessions as bridge_sessions
from astrbot.core.star.star import star_map, star_registry
from astrbot.core.star.star_handler import EventType, star_handlers_registry
from astrbot.core.umop_config_router import UmopConfigRouter
from astrbot.core.utils.shared_preferences import SharedPreferences
from astrbot.dashboard.api.plugins import _match_registered_web_api
from astrbot.dashboard.services.config_service import (
    ConfigDisplayService,
    ConfigFileService,
)
from astrbot.dashboard.services.plugin_page_service import PluginPageService

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MATRIX_DIR = _REPO_ROOT / "tests" / "fixtures" / "sdk_api_matrix"
_PEER_DIR = _REPO_ROOT / "tests" / "fixtures" / "sdk_showcase" / "full_api_peer"

_MATRIX_PLUGINS = (
    "sdk_commands_messages",
    "sdk_events_sessions",
    "sdk_storage_assets_render",
    "sdk_conversations_kb_history",
    "sdk_llm_tools_agent",
    "sdk_web_views",
    "sdk_lifecycle_config_hooks",
)


def _public_methods(cls: type) -> list[str]:
    """Return non-underscore callable attributes declared directly or inherited cleanly."""
    return [
        name
        for name, value in cls.__dict__.items()
        if not name.startswith("_") and callable(value)
    ]


def test_sdk_api_matrix_public_surface_coverage() -> None:
    """Assert every public decorator, service method, and user-facing SDK symbol appears in the API matrix."""
    refs: set[str] = set()
    plugin_mains = sorted(_MATRIX_DIR.glob("*/main.py"))
    assert len(plugin_mains) == len(_MATRIX_PLUGINS)
    for path in plugin_mains:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                refs.add(node.id)
            elif isinstance(node, ast.Attribute):
                refs.add(node.attr)
            elif isinstance(node, ast.alias):
                refs.add(node.name.split(".")[0])
                if node.asname:
                    refs.add(node.asname)

    required_symbols = {
        # Top-level decorators & namespaces
        *sdk_on.__all__,
        *sdk_lifecycle.__all__,
        "llm_request",
        "llm_response",
        "tool_call",
        "tool_result",
        "message_result",
        "message_sent",
        "agent_start",
        "agent_end",
        "waiting_llm_request",
        "plugin_error",
        "plugin_loaded",
        "plugin_unloaded",
        # Hook DTOs & message components
        "LLMRequest",
        "LLMResponse",
        "ToolCall",
        "ToolResult",
        "MessageResult",
        "PluginError",
        "ActionRow",
        "At",
        "AtAll",
        "Button",
        "Face",
        "File",
        "Forward",
        "Image",
        "Json",
        "Location",
        "Music",
        "Node",
        "Nodes",
        "Plain",
        "Poke",
        "Record",
        "Reply",
        "Share",
        "Video",
        "MessageChain",
        "to_message_chain",
        # Results & events & sessions & views & config & tools & llm & conv & render & web & worker
        "Propagation",
        "ViewResult",
        "ViewSpec",
        "MessageEvent",
        "MessageType",
        "SenderRole",
        "DefaultSessionFilter",
        "SenderSessionFilter",
        "SessionFilter",
        "prepare_outbound_chain",
        "DirectContext",
        "Plugin",
        "PluginConfig",
        "Worker",
        "has_native_runtime",
        "CallScopeRetired",
        "AssetRef",
        "RenderOptions",
        "TextRenderOptions",
        "WebRequest",
        "WebResponse",
        "WebRouteRegistration",
        "json_response",
        "error_response",
        "file_response",
        "stream_response",
        "normalize_web_result",
        "scan_views",
        "load_i18n",
        "read_view_file",
        "export_config_schema",
        "reject_external_schema_refs",
        "schema_has_sensitive_fields",
        "validate_config_against_model",
        "Tool",
        "ToolCallContext",
        "ToolDefinition",
        "ToolParam",
        "ToolRef",
        "is_tool_context_param",
        "tool_params_schema",
        "AgentRequest",
        "AgentResponse",
        "AgentStep",
        "ChatChunk",
        "ChatResponse",
        "EmbeddingResponse",
        "ProviderInfo",
        "ProviderKind",
        "Transcript",
        "Conversation",
        "ConversationPage",
        "ConversationPatch",
        "Message",
        "TextPart",
        "ImagePart",
        "AudioPart",
        "CapabilitySet",
    }
    missing_symbols = sorted(sym for sym in required_symbols if sym not in refs)
    assert not missing_symbols, f"Missing public SDK symbols in api_matrix: {missing_symbols}"

    # Verify every public method on PluginContext and every service/client class is called/referenced.
    service_classes: tuple[type, ...] = (
        PluginContext,
        sdk_services.PluginStorage,
        sdk_services.AssetService,
        sdk_services.MessageService,
        sdk_services.EventStateClient,
        sdk_services.PlatformClient,
        sdk_services.SessionService,
        sdk_services.SessionWait,
        sdk_services.CronClient,
        sdk_services.KnowledgeBaseClient,
        sdk_services.MessageHistoryClient,
        ConversationService,
        LLMService,
        ToolService,
        RenderService,
        WebService,
        PluginRegistryService,
        sdk_tasks.TaskGroup,
        sdk_capabilities.CapabilitySet,
    )
    missing_methods: list[str] = []
    # Low-level internal helpers tested explicitly outside plugin handlers or optional convenience aliases.
    allowed_uncalled = {
        "PluginContext.build",
        "PluginContext.scoped_for_invocation",
        "PluginContext.retire_invocation_scope",
        "PluginContext.handle_event",
        "PluginContext.handle_tool",
        "PluginContext.handle_hook",
        "PluginContext.handle_service",
        "PluginContext.handle_ui_action",
        "PluginContext.handle_button_action",
        "PluginContext.handle_cron",
        "PluginContext.validate_config",
        "PluginContext.notify_config_changed",
        "PluginContext.notify_shutdown",
        "PluginContext.run_startup",
        "PluginContext.run_health",
        "PluginContext.deliver_session",
        "PluginContext.expire_session",
        "PluginContext.invoke_web",
        "PluginContext.set_granted_capabilities",
        "PluginContext.check_tool_discovery",
        "SessionService.consider",
        "WebService.dispatch",
        "TaskGroup.background_errors",
        "TaskGroup.drain_errors",
        "TaskGroup.task_count",
        "CapabilitySet.empty",
    }
    for cls in service_classes:
        for method_name in _public_methods(cls):
            qual = f"{cls.__name__}.{method_name}"
            if qual in allowed_uncalled:
                continue
            if method_name not in refs:
                missing_methods.append(qual)
    assert not missing_methods, f"Uncovered service/context methods in api_matrix: {missing_methods}"
    assert set(sdk_components.__all__) >= {
        "ActionRow",
        "Button",
        "Image",
        "Plain",
        "Node",
        "Nodes",
    }


class _MatrixChatProvider(Provider):
    """Deterministic chat provider supporting single-turn, stream, and lta_add tool calls."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.set_model(str(provider_config.get("model") or "mock-gpt"))

    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id=str(self.provider_config["id"]),
            model=self.get_model(),
            type=str(self.provider_config["type"]),
            provider_type=ProviderType.CHAT_COMPLETION,
        )

    def get_current_key(self) -> str:
        return "mock-key"

    def set_key(self, key: str) -> None:
        _ = key

    async def get_models(self) -> list[str]:
        return [self.get_model()]

    async def text_chat(
        self,
        prompt: str | None = None,
        session_id: str | None = None,
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
        func_tool=None,
        contexts=None,
        system_prompt: str | None = None,
        tool_calls_result=None,
        model: str | None = None,
        extra_user_content_parts=None,
        tool_choice: str = "auto",
        request_max_retries: int | None = None,
        **kwargs,
    ) -> LLMResponse:
        _ = (
            session_id,
            image_urls,
            audio_urls,
            model,
            extra_user_content_parts,
            tool_choice,
            request_max_retries,
            kwargs,
        )
        tool_names = [tool.name for tool in getattr(func_tool, "tools", []) or []]
        has_tool_results = bool(tool_calls_result) or any(
            (msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None))
            == "tool"
            for msg in (contexts or [])
        )
        if "lta_add" in tool_names and not has_tool_results:
            return LLMResponse(
                role="assistant",
                tools_call_name=["lta_add"],
                tools_call_args=[{"a": 3, "b": 5}],
                tools_call_ids=["call_lta_1"],
            )

        tool_outputs: list[str] = []
        result_items = (
            tool_calls_result
            if isinstance(tool_calls_result, list)
            else ([tool_calls_result] if tool_calls_result else [])
        )
        for item in result_items:
            for block in getattr(item, "tool_calls_result", []) or []:
                tool_outputs.append(str(getattr(block, "content", "")))
        for msg in contexts or []:
            role = (
                msg.get("role")
                if isinstance(msg, dict)
                else getattr(msg, "role", None)
            )
            if role == "tool":
                content = (
                    msg.get("content", "")
                    if isinstance(msg, dict)
                    else getattr(msg, "content", "")
                )
                tool_outputs.append(str(content))
        effective_prompt = prompt or ""
        if not effective_prompt:
            for msg in reversed(contexts or []):
                role = (
                    msg.get("role")
                    if isinstance(msg, dict)
                    else getattr(msg, "role", None)
                )
                if role == "user":
                    effective_prompt = str(
                        msg.get("content", "")
                        if isinstance(msg, dict)
                        else getattr(msg, "content", "")
                    )
                    break
        return LLMResponse(
            role="assistant",
            completion_text=f"chat-ok:{effective_prompt}:{','.join(tool_outputs)}:{system_prompt or ''}",
        )

    async def text_chat_stream(
        self,
        prompt: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[LLMResponse, None]:
        _ = (prompt, kwargs)
        yield LLMResponse(role="assistant", completion_text="chunk-1", is_chunk=True)
        yield LLMResponse(role="assistant", completion_text="-2", is_chunk=True)
        yield LLMResponse(role="assistant", completion_text="chunk-1-2", is_chunk=False)


class _MatrixTTSProvider(TTSProvider):
    def __init__(self, provider_config: dict, provider_settings: dict, tmp_dir: Path):
        super().__init__(provider_config, provider_settings)
        self._tmp_dir = tmp_dir
        self.set_model("mock-tts")

    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id=str(self.provider_config["id"]),
            model=self.get_model(),
            type=str(self.provider_config["type"]),
            provider_type=ProviderType.TEXT_TO_SPEECH,
        )

    async def get_audio(self, text: str) -> str:
        out_path = self._tmp_dir / "matrix_tts.wav"
        out_path.write_bytes(f"RIFF-MATRIX:{text}".encode())
        return str(out_path)


class _MatrixSTTProvider(STTProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.set_model("mock-stt")

    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id=str(self.provider_config["id"]),
            model=self.get_model(),
            type=str(self.provider_config["type"]),
            provider_type=ProviderType.SPEECH_TO_TEXT,
        )

    async def get_text(self, audio_url: str) -> str:
        candidate = Path(audio_url)
        if not candidate.exists() or candidate.stat().st_size == 0:
            raise FileNotFoundError(f"Expected audio file for STT: {audio_url}")
        return "transcribed-ok"


class _MatrixEmbeddingProvider(EmbeddingProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.set_model("mock-embed")

    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id=str(self.provider_config["id"]),
            model=self.get_model(),
            type=str(self.provider_config["type"]),
            provider_type=ProviderType.EMBEDDING,
        )

    async def get_embedding(self, text: str) -> list[float]:
        _ = text
        return [0.1, 0.2, 0.3, 0.4]

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3, 0.4] for _ in text]

    def get_dim(self) -> int:
        return 4


class _MatrixPlatform(Platform):
    def __init__(self, config: dict, event_queue: asyncio.Queue) -> None:
        super().__init__(config, event_queue)
        self.status = PlatformStatus.RUNNING
        self.sent_sessions: list[tuple[str, object]] = []
        self.raw_actions: list[tuple[str, dict]] = []
        outer = self

        class _BotApi:
            async def call_action(self, action: str, **params):
                outer.raw_actions.append((action, dict(params)))
                return {"action": action, **params}

        self.bot = SimpleNamespace(api=_BotApi())

    async def run(self) -> None:
        return None

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="webchat",
            description="Matrix WebChat",
            id="webchat",
            support_ui_interaction=True,
        )

    def get_client(self) -> object:
        return self.bot

    async def send_by_session(self, session, message_chain) -> None:
        self.sent_sessions.append((str(session), message_chain))


class _MatrixMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        text: str,
        umo_session_id: str = "user-1",
        *,
        platform_name: str = "webchat",
        message_type: MessageType = MessageType.FRIEND_MESSAGE,
        role: str = "admin",
        extra_components: list | None = None,
    ) -> None:
        platform_meta = PlatformMetadata(
            name=platform_name,
            description=f"Matrix {platform_name}",
            id=platform_name,
            support_ui_interaction=True,
        )
        msg = AstrBotMessage()
        msg.type = message_type
        msg.self_id = "bot-self"
        msg.session_id = umo_session_id
        msg.message_id = f"msg-{umo_session_id}-{abs(hash((platform_name, text)))}"
        msg.sender = MessageMember(user_id="user-1", nickname="Moon")
        msg.message = [Plain(text), *(extra_components or [])]
        msg.message_str = text
        msg.raw_message = (
            role,
            umo_session_id,
            {"text": text, "_platform_history_id": platform_name},
        )
        super().__init__(
            message_str=text,
            message_obj=msg,
            platform_meta=platform_meta,
            session_id=umo_session_id,
        )
        self.role = role
        self.is_wake = True
        self.is_at_or_wake_command = True
        self.sent_messages: list[object] = []
        self.streamed_chunks: list[list[object]] = []
        self.typing_count = 0
        self.stop_typing_count = 0
        self.reactions: list[str] = []

    async def send(self, message) -> None:
        self.sent_messages.append(message)
        self._has_send_oper = True

    async def send_streaming(
        self,
        generator: AsyncGenerator,
        use_fallback: bool = False,
    ) -> None:
        _ = use_fallback
        chunks = [chain async for chain in generator]
        self.streamed_chunks.append(chunks)
        self._has_send_oper = True

    async def send_typing(self) -> None:
        self.typing_count += 1

    async def stop_typing(self) -> None:
        self.stop_typing_count += 1

    async def react(self, emoji: str) -> None:
        self.reactions.append(emoji)

    async def get_group(self, group_id: str | None = None) -> Group:
        return Group(group_id=group_id or "grp-default", group_name="Matrix Group")


class _MatrixRenderer:
    def __init__(self, out_dir: Path) -> None:
        self._out_dir = out_dir
        self._counter = 0

    async def render_custom_template(
        self,
        tmpl: str,
        data: dict,
        return_url: bool = False,
        options: dict | None = None,
    ) -> str:
        _ = (return_url, options)
        self._counter += 1
        out_path = self._out_dir / f"matrix_html_{self._counter}.png"
        out_path.write_bytes(f"PNG-HTML:{tmpl}:{json.dumps(data)}".encode())
        return str(out_path)

    async def render_t2i(
        self,
        text: str,
        return_url: bool = False,
        use_network: bool | None = None,
        template_name: str | None = None,
    ) -> str:
        _ = (return_url, use_network, template_name)
        self._counter += 1
        out_path = self._out_dir / f"matrix_t2i_{self._counter}.png"
        out_path.write_bytes(f"PNG-T2I:{text}".encode())
        return str(out_path)


def _matching_handlers(
    config: AstrBotConfig,
    module_path: str,
    event: _MatrixMessageEvent,
):
    return [
        h
        for h in star_handlers_registry.get_handlers_by_module_name(module_path)
        if h.event_type == EventType.AdapterMessageEvent
        and not any(isinstance(f, CommandGroupFilter) for f in h.event_filters)
        and all(f.filter(event, config) for f in h.event_filters)
    ]


async def _dispatch_matrix(
    config: AstrBotConfig,
    module_path: str,
    event: _MatrixMessageEvent,
    *,
    handler_name: str | None = None,
) -> list[MessageEventResult]:
    candidates = [
        h
        for h in _matching_handlers(config, module_path, event)
        if handler_name is None or h.handler_name == handler_name
    ]
    assert len(candidates) == 1, (
        f"Expected 1 handler match for {event.message_str!r} ({handler_name}), "
        f"got {[h.handler_name for h in candidates]}"
    )
    handler = candidates[0]
    parsed = event.get_extra("parsed_params") or {}
    results: list[MessageEventResult] = []
    yielded_items: list[object] = []
    async for item in call_handler(event, handler.handler, **parsed):
        if item is not None:
            yielded_items.append(item)
        res = event.get_result()
        if res is not None:
            results.append(res)
            event.clear_result()
    event.set_extra("_yielded_items", yielded_items)
    return results


async def _invoke_matrix_web(
    context: Context,
    method: str,
    path: str,
    *,
    plugin_name: str,
    query_items: list[tuple[str, str]] | None = None,
    body_bytes: bytes = b"",
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    matched = _match_registered_web_api(context.registered_web_apis, path, method)
    assert matched is not None, f"Web route {method} {path} not registered"
    view_handler, path_values = matched
    req = SimpleNamespace(
        method=method,
        headers=Headers(headers or {}),
        cookies={},
        url=SimpleNamespace(
            path=path,
            query="&".join(f"{k}={v}" for k, v in (query_items or ())),
        ),
        client=SimpleNamespace(host="127.0.0.1"),
        query_params=SimpleNamespace(multi_items=lambda: list(query_items or ())),
        body=AsyncMock(return_value=body_bytes),
    )
    plugin_request = PluginRequest(
        req,  # type: ignore[arg-type]
        path_params=path_values,
        plugin_name=plugin_name,
        username="admin",
    )
    with bind_request_context(plugin_request):
        response = await view_handler(**path_values)
    raw = b""
    if hasattr(response, "body_iterator") and response.body_iterator is not None:
        async for chunk in response.body_iterator:
            raw += chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8")
    elif getattr(response, "body", None):
        raw = bytes(response.body)
    resp_headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
    return int(response.status_code), resp_headers, raw


@pytest.mark.asyncio
async def test_every_sdk_api_plugin_against_real_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Load full_api_peer plus all 7 sdk_api_matrix plugins and exercise every API end-to-end."""
    baseline_star_paths = {m.module_path for m in star_registry if m.module_path}
    baseline_map_keys = set(star_map.keys())
    baseline_handler_names = set(star_handlers_registry.star_handlers_map.keys())
    baseline_tool_names = {t.name for t in llm_tools.func_list}
    baseline_web_routes = list(Context.registered_web_apis)

    astrbot_root = tmp_path / "astrbot_root"
    store_dir = tmp_path / "plugins"
    store_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_PEER_DIR, store_dir / "full_api_peer")
    for name in _MATRIX_PLUGINS:
        shutil.copytree(_MATRIX_DIR / name, store_dir / name)

    monkeypatch.setenv("ASTRBOT_ROOT", str(astrbot_root))
    monkeypatch.setenv("ASTRBOT_SDK_DATA_DIR", str(tmp_path / "sdk_data"))

    kb_files = tmp_path / "kb" / "files"
    kb_files.mkdir(parents=True)
    monkeypatch.setattr("astrbot.core.knowledge_base.kb_mgr.FILES_PATH", kb_files)
    monkeypatch.setattr("astrbot.core.knowledge_base.kb_mgr.DB_PATH", tmp_path / "kb" / "kb.db")

    db = SQLiteDatabase(str(tmp_path / "data_v4.db"))
    await db.initialize()
    real_sp = SharedPreferences(db_helper=db, json_storage_path=str(tmp_path / "sp.json"))
    await real_sp.initialize()
    for target in (
        "astrbot.core.sp",
        "astrbot.api.sp",
        "astrbot.core.session_overrides.sp",
        "astrbot.core.provider.manager.sp",
        "astrbot.core.provider.func_tool_manager.sp",
        "astrbot.core.conversation_mgr.sp",
        "astrbot.core.star.sdk_bridge.bridge.sp",
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        "astrbot.core.star.sdk_bridge.services.sp.sp",
    ):
        monkeypatch.setattr(target, real_sp)

    cfg_path = astrbot_root / "data" / "cmd_config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    config = AstrBotConfig(config_path=str(cfg_path))
    config["callback_api_base"] = "http://127.0.0.1:6185"
    config["dashboard"] = {**dict(config.get("dashboard") or {}), "jwt_secret": "matrix-jwt-secret"}
    config["provider_stt_settings"] = {"enable": True, "provider_id": "stt-main"}
    config["provider_tts_settings"] = {"enable": True, "provider_id": "tts-main"}
    config["agent"] = {
        "runtime": "astrbot",
        "config": {"model": {"provider_id": "chat-main"}},
    }
    config.save_config()

    ucr = UmopConfigRouter(sp=real_sp)
    await ucr.initialize()
    acm = AstrBotConfigManager(default_config=config, ucr=ucr, sp=real_sp)
    await acm.initialize()
    persona_mgr = PersonaManager(db, acm)
    await persona_mgr.initialize()
    if not persona_mgr.personas_v3:
        await persona_mgr.create_persona("matrix_default", "Matrix default prompt")

    conv_mgr = ConversationManager(db, acm)
    history_mgr = PlatformMessageHistoryManager(db)
    cron_mgr = CronJobManager(db)

    provider_mgr = ProviderManager(acm, db, persona_mgr)
    chat_prov = _MatrixChatProvider(
        {"id": "chat-main", "model": "mock-gpt", "type": "openai_chat_completion", "provider_type": "chat_completion"},
        {},
    )
    tts_prov = _MatrixTTSProvider(
        {"id": "tts-main", "model": "mock-tts", "type": "openai_tts", "provider_type": "text_to_speech"},
        {},
        tmp_path,
    )
    stt_prov = _MatrixSTTProvider(
        {"id": "stt-main", "model": "mock-stt", "type": "openai_whisper_api", "provider_type": "speech_to_text"},
        {},
    )
    emb_prov = _MatrixEmbeddingProvider(
        {"id": "emb-main", "model": "mock-embed", "type": "openai_embedding", "provider_type": "embedding"},
        {},
    )
    provider_mgr.provider_insts = [chat_prov]
    provider_mgr.curr_provider_inst = chat_prov
    provider_mgr.stt_provider_insts = [stt_prov]
    provider_mgr.curr_stt_provider_inst = stt_prov
    provider_mgr.tts_provider_insts = [tts_prov]
    provider_mgr.curr_tts_provider_inst = tts_prov
    provider_mgr.embedding_provider_insts = [emb_prov]
    provider_mgr.inst_map = {
        "chat-main": chat_prov,
        "tts-main": tts_prov,
        "stt-main": stt_prov,
        "emb-main": emb_prov,
    }

    kb_mgr = KnowledgeBaseManager(provider_mgr)
    await kb_mgr.initialize()

    event_queue: asyncio.Queue = asyncio.Queue()
    platform_mgr = PlatformManager(config, event_queue)
    platform = _MatrixPlatform({}, event_queue)
    platform_mgr.platform_insts.append(platform)

    Context.registered_web_apis = list(baseline_web_routes)
    context = Context(
        event_queue=event_queue,
        config=config,
        db=db,
        provider_manager=provider_mgr,
        platform_manager=platform_mgr,
        conversation_manager=conv_mgr,
        message_history_manager=history_mgr,
        persona_manager=persona_mgr,
        astrbot_config_mgr=acm,
        knowledge_base_manager=kb_mgr,
        cron_manager=cron_mgr,
        agent_runtimes={},
    )
    context.html_renderer = _MatrixRenderer(tmp_path)  # type: ignore[assignment]
    await cron_mgr.start(context)
    sdk_mgr = SDKPluginManager(context, store_dir)
    pm_stub = SimpleNamespace(
        context=context,
        _sdk_plugin_manager=sdk_mgr,
        plugin_store_path=str(store_dir),
        reload=AsyncMock(return_value=(True, None)),
        turn_off_plugin=AsyncMock(return_value=None),
        turn_on_plugin=AsyncMock(return_value=None),
    )
    context._star_manager = pm_stub  # type: ignore[assignment]
    core_lifecycle = SimpleNamespace(
        astrbot_config=config,
        plugin_manager=pm_stub,
        astrbot_config_mgr=acm,
        umop_config_router=ucr,
    )

    try:
        loaded = await sdk_mgr.load_all()
        assert set(loaded) == {"full_api_peer", *_MATRIX_PLUGINS}
        bridges = {name: sdk_mgr.bridges[name] for name in _MATRIX_PLUGINS}

        # 1. sdk_commands_messages
        cm_mod = bridges["sdk_commands_messages"].module_path
        cm_calc_ev = _MatrixMessageEvent("cm compute 4 2.5 true bonus")
        cm_calc_res = await _dispatch_matrix(config, cm_mod, cm_calc_ev)
        assert cm_calc_res[0].chain[0].text == "calc:10:bonus"
        assert cm_calc_ev.is_stopped()
        assert not _matching_handlers(config, cm_mod, _MatrixMessageEvent("cm compute 4 2.5", role="member"))
        assert not _matching_handlers(
            config,
            cm_mod,
            _MatrixMessageEvent("cm compute 4 2.5", message_type=MessageType.GROUP_MESSAGE),
        )
        assert not _matching_handlers(config, cm_mod, _MatrixMessageEvent("cm compute 4 2.5", platform_name="discord"))

        assert (await _dispatch_matrix(config, cm_mod, _MatrixMessageEvent("cm top space")))[0].chain[0].text == "alias-top-ok"
        assert (await _dispatch_matrix(config, cm_mod, _MatrixMessageEvent("cm grp")))[0].chain[0].text == "grp-root-ok"
        assert (
            await _dispatch_matrix(
                config,
                cm_mod,
                _MatrixMessageEvent("cm grp leaf"),
                handler_name="cm_grp_leaf",
            )
        )[0].chain[0].text == "grp-leaf-ok"
        regex_ev = _MatrixMessageEvent("#CM-HI")
        regex_res = await _dispatch_matrix(config, cm_mod, regex_ev)
        assert regex_res[0].chain[0].text == "regex-hi:#CM-HI"
        assert regex_ev.is_stopped()

        btn_ev = _MatrixMessageEvent(
            "",
            extra_components=[ButtonInteraction(action_id="cm_btn", interaction_id="b1", data={"v": 7})],
        )
        btn_res = await _dispatch_matrix(config, cm_mod, btn_ev)
        assert json.loads(btn_res[0].chain[0].text) == {"action": "cm_btn", "data": {"v": 7}}

        media_res = await _dispatch_matrix(config, cm_mod, _MatrixMessageEvent("cm media_rich"))
        media_report = json.loads(media_res[0].chain[0].text)
        assert media_report["ok"] is True
        assert media_report["rich_count"] == 15
        assert media_report["media_count"] == 12
        assert media_report["props"]["is_private"] is True
        assert any(
            isinstance(seg, Node) or isinstance(seg, Nodes) or isinstance(seg, ActionRow)
            for _umo, chain in platform.sent_sessions
            for seg in chain.chain
        )

        # 2. sdk_events_sessions
        es_mod = bridges["sdk_events_sessions"].module_path
        es_ev = _MatrixMessageEvent("es act")
        es_res = await _dispatch_matrix(config, es_mod, es_ev)
        es_report = json.loads(es_res[0].chain[0].text)
        assert es_report["receipt_ok"] is True
        assert es_report["group"]["group_id"] == "es-grp"
        assert es_report["raw"] == {"action": "es_ping", "val": 9}
        assert es_ev.typing_count >= 1
        assert es_ev.stop_typing_count >= 1
        assert "star" in es_ev.reactions
        assert len(es_ev.streamed_chunks) >= 2
        assert ("es_ping", {"val": 9}) in platform.raw_actions

        for trigger, reply_text, non_match, expected in (
            ("es wait_default", "ans-def", None, "wait-default:ans-def"),
            ("es wait_sender", "ans-snd", None, "wait-sender:ans-snd"),
            ("es wait_custom", "PASS:ok", "NOPE", "wait-custom:PASS:ok"),
        ):
            wait_task = asyncio.create_task(
                _dispatch_matrix(config, es_mod, _MatrixMessageEvent(trigger))
            )
            try:
                for _ in range(100):
                    if wait_task.done():
                        await wait_task
                    if bridge_sessions._REGISTRY:
                        break
                    await asyncio.sleep(0.05)
                assert bridge_sessions._REGISTRY
                if non_match is not None:
                    miss_ev = _MatrixMessageEvent(non_match)
                    await bridge_sessions._session_wait_interceptor(miss_ev)
                    assert not miss_ev.is_stopped()
                hit_ev = _MatrixMessageEvent(reply_text)
                await bridge_sessions._session_wait_interceptor(hit_ev)
                assert hit_ev.is_stopped()
                wait_out = await asyncio.wait_for(wait_task, timeout=5.0)
                assert wait_out[0].chain[0].text == expected
            finally:
                if not wait_task.done():
                    wait_task.cancel()
                    await asyncio.gather(wait_task, return_exceptions=True)

        # 3. sdk_storage_assets_render
        sar_mod = bridges["sdk_storage_assets_render"].module_path
        sar_res = await _dispatch_matrix(config, sar_mod, _MatrixMessageEvent("sar run"))
        sar_report = json.loads(sar_res[0].chain[0].text)
        for key in ("kv_ok", "local_ok", "asset_ok", "prepared_ok", "render_ok"):
            assert sar_report[key] is True, f"sar failed on {key}: {sar_report}"
        sar_tok_path = await file_token_service.handle_file(sar_report["token"])
        assert Path(sar_tok_path).read_bytes() == b"SAR-TOKEN-DATA"

        # 4. sdk_conversations_kb_history
        ckh_mod = bridges["sdk_conversations_kb_history"].module_path
        ckh_res = await _dispatch_matrix(config, ckh_mod, _MatrixMessageEvent("ckh run"))
        ckh_report = json.loads(ckh_res[0].chain[0].text)
        assert ckh_report == {"conv_ok": True, "kb_ok": True, "history_ok": True}

        # 5. sdk_llm_tools_agent
        lta_mod = bridges["sdk_llm_tools_agent"].module_path
        lta_res = await _dispatch_matrix(config, lta_mod, _MatrixMessageEvent("lta run"))
        lta_report = json.loads(lta_res[0].chain[0].text)
        assert lta_report["runtime_tools"] == ["lta_runtime"]
        assert lta_report["provs"] == 1
        assert lta_report["cur_id"] == "chat-main"
        assert "lta-chat" in lta_report["gen"]
        assert lta_report["stream"] == "chunk-1-2chunk-1-2"
        assert lta_report["embed_dims"] == 2
        assert lta_report["transcript"] == "transcribed-ok"
        assert "8" in lta_report["agent_text"]
        assert lta_report["step_ok"] is True

        for tname, kwargs, expected_substr in (
            ("lta_add", {"a": 11, "b": 4}, "15"),
            ("lta_stream", {"text": "yo"}, "lta-stream:yo"),
            ("lta_discovered", {"tag": "z"}, "disc:z"),
            ("lta_runtime", {"note": "hi"}, "LTA:HI"),
        ):
            t = llm_tools.get_func(tname)
            assert t is not None, f"Missing tool {tname}"
            assert expected_substr in str(await t.handler(_MatrixMessageEvent("t"), **kwargs))
        assert llm_tools.get_func("_temp_tool") is None

        # 6. sdk_web_views
        wv_mod = bridges["sdk_web_views"].module_path
        page_svc = PluginPageService(pm_stub, core_lifecycle, config)
        panel_html = await page_svc.serve_page_content(
            plugin_name="sdk_web_views",
            view_name="panel",
            asset_path="",
            asset_token="",
            jwt_secret="matrix-jwt-secret",
            username="admin",
            locale="en-US",
            theme=None,
        )
        assert "Web Views Panel" in panel_html.content
        _pm, mini_spec, mini_entry = resolve_view(wv_mod, "mini_card")
        assert mini_spec.name == "mini_card" and mini_entry.is_file()
        tok = page_svc.issue_plugin_page_asset_token(
            plugin_name="sdk_web_views",
            view_name="panel",
            jwt_secret="matrix-jwt-secret",
            username="admin",
            locale="zh-CN",
        )
        init_ctx = page_svc.build_initial_context(
            asset_token=tok,
            jwt_secret="matrix-jwt-secret",
            locale="zh-CN",
            theme="dark",
        )
        assert init_ctx is not None
        assert "zh-CN" in init_ctx["i18n"] and "en-US" in init_ctx["i18n"]

        wv_open_ev = _MatrixMessageEvent("wv open")
        await _dispatch_matrix(config, wv_mod, wv_open_ev)
        wv_payload = next(
            seg.data for chain in wv_open_ev.sent_messages for seg in chain.chain if isinstance(seg, Json)
        )
        wv_id = str(wv_payload["id"])
        assert view_store.get(wv_id)["data"] == {"clicks": 10}

        ui_ev = _MatrixMessageEvent(
            "",
            extra_components=[
                UIInteraction(
                    action_id="wv_inc",
                    interaction_id="ui-wv",
                    data={},
                    view=ViewContext(id=wv_id, name="mini_card", version=1, revision=1, data={"clicks": 10}),
                )
            ],
        )
        await _dispatch_matrix(config, wv_mod, ui_ev)
        assert any(
            isinstance(item, CoreViewResult) and item.data == {"clicks": 11}
            for item in (ui_ev.get_extra("_yielded_items") or [])
        )
        wv_meta_res = await _dispatch_matrix(config, wv_mod, _MatrixMessageEvent("wv meta"))
        assert set(json.loads(wv_meta_res[0].chain[0].text)["pages"]) == {"mini_card", "panel"}

        st_j, _h_j, raw_j = await _invoke_matrix_web(
            context, "GET", "/wv/inspect/alpha", plugin_name="sdk_web_views"
        )
        assert st_j == 200 and json.loads(raw_j) == {"item": "alpha", "mode": "json"}

        st_t, _h_t, raw_t = await _invoke_matrix_web(
            context,
            "GET",
            "/wv/inspect/alpha",
            plugin_name="sdk_web_views",
            query_items=[("mode", "text"), ("q", "hi")],
        )
        assert st_t == 201 and raw_t == b"text:alpha:hi"

        st_r, hdr_r, _raw_r = await _invoke_matrix_web(
            context,
            "GET",
            "/wv/inspect/alpha",
            plugin_name="sdk_web_views",
            query_items=[("mode", "redirect")],
        )
        assert st_r == 307 and hdr_r.get("location") == "/next/alpha"

        st_p, _h_p, raw_p = await _invoke_matrix_web(
            context,
            "POST",
            "/wv/inspect/alpha",
            plugin_name="sdk_web_views",
            query_items=[("mode", "response_json")],
            body_bytes=b'{"x": 42}',
            headers={"x-test": "hdr-val"},
        )
        assert st_p == 200
        resp_p = json.loads(raw_p)
        assert resp_p["method"] == "POST"
        assert resp_p["header_x"] == "hdr-val"
        assert resp_p["body_json"] == {"x": 42}
        assert resp_p["username"] == "admin"

        st_e, _h_e, raw_e = await _invoke_matrix_web(
            context,
            "GET",
            "/wv/inspect/alpha",
            plugin_name="sdk_web_views",
            query_items=[("mode", "error")],
        )
        assert st_e == 418 and json.loads(raw_e)["data"] == {"item": "alpha"}

        st_s, hdr_s, raw_s = await _invoke_matrix_web(
            context,
            "GET",
            "/wv/inspect/alpha",
            plugin_name="sdk_web_views",
            query_items=[("mode", "stream")],
        )
        assert st_s == 200 and hdr_s.get("x-stream") == "1" and raw_s == b"wv-s1\nwv-s2\n"

        st_f, _h_f, raw_f = await _invoke_matrix_web(
            context,
            "GET",
            "/wv/inspect/alpha",
            plugin_name="sdk_web_views",
            query_items=[("mode", "file")],
        )
        assert st_f == 200 and raw_f == b"FILE:alpha"

        st_vh, _h_vh, raw_vh = await _invoke_matrix_web(
            context,
            "GET",
            "/wv/inspect/alpha",
            plugin_name="sdk_web_views",
            query_items=[("mode", "view_helpers")],
        )
        assert st_vh == 200
        vh = json.loads(raw_vh)
        assert vh["view_has_title"] is True
        assert vh["view_meta_len"] > 0
        assert vh["route_registered"] is True
        assert vh["i18n_locales"] == ["en-US", "zh-CN"]

        large_size = INLINE_BODY_LIMIT + 512
        st_big, _h_big, raw_big = await _invoke_matrix_web(
            context,
            "POST",
            "/wv/inspect/alpha",
            plugin_name="sdk_web_views",
            query_items=[("mode", "stream_in")],
            body_bytes=b"X" * large_size,
        )
        assert st_big == 200
        big_json = json.loads(raw_big)
        assert big_json["total"] == large_size
        assert big_json["chunks"] >= 5

        # 7. sdk_lifecycle_config_hooks
        lch_bridge = bridges["sdk_lifecycle_config_hooks"]
        lch_mod = lch_bridge.module_path
        initial_lch_pid = lch_bridge.runner_pid
        assert initial_lch_pid and initial_lch_pid > 0
        await lch_bridge._require_client().ping()

        display_svc = ConfigDisplayService(core_lifecycle)
        file_svc = ConfigFileService(core_lifecycle)
        await file_svc.save_plugin_configs(
            {"secret_key": "top-secret", "tag": "live-tag", "limit": 15},
            lch_bridge.plugin_name,
        )
        assert lch_bridge.runner_pid == initial_lch_pid
        shown_cfg = display_svc.get_plugin_config("sdk_lifecycle_config_hooks")
        assert shown_cfg["config"]["secret_key"] == ""
        assert shown_cfg["config"]["tag"] == "live-tag"
        assert shown_cfg["config"]["limit"] == 15

        with pytest.raises(ValueError, match="42"):
            await file_svc.save_plugin_configs(
                {"secret_key": "top-secret", "tag": "bad", "limit": 42},
                lch_bridge.plugin_name,
            )
        assert display_svc.get_plugin_config("sdk_lifecycle_config_hooks")["config"]["limit"] == 15

        assert await lch_bridge.invoke_service("lch_svc", {"msg": "hi"}) == {
            "echo": "hi",
            "tag": "live-tag",
        }
        assert await lch_bridge.invoke_service("lch_direct", {"v": 7}) == {
            "direct": 7,
            "tag": "live-tag",
            "plugin": "sdk_lifecycle_config_hooks",
        }

        lch_handlers = star_handlers_registry.get_handlers_by_module_name(lch_mod)
        lch_meta = next(m for m in star_registry if m.module_path == lch_mod)
        hook_ev = _MatrixMessageEvent("lch-hook")

        await next(h for h in lch_handlers if h.event_type == EventType.OnPluginLoadedEvent).handler(lch_meta)
        await next(h for h in lch_handlers if h.event_type == EventType.OnPluginUnloadedEvent).handler(lch_meta)
        await next(h for h in lch_handlers if h.event_type == EventType.OnWaitingLLMRequestEvent).handler(hook_ev)

        req = ProviderRequest(prompt="[lch-track] go", system_prompt="base")
        await next(h for h in lch_handlers if h.event_type == EventType.OnLLMRequestEvent).handler(hook_ev, req)
        assert req.contexts == [
            {"role": "system", "content": "sys-a"},
            {"role": "user", "content": "usr-b"},
        ]
        assert "[lch-sys]" in req.system_prompt

        llm_resp = LLMResponse(role="assistant", completion_text="lch-resp")
        await next(h for h in lch_handlers if h.event_type == EventType.OnLLMResponseEvent).handler(hook_ev, llm_resp)
        assert llm_resp.completion_text == "lch-resp [lch-resp-mut]"

        tool_stub = SimpleNamespace(name="lta_add", description="Add")
        tool_args = {"k": "lch-call"}
        await next(h for h in lch_handlers if h.event_type == EventType.OnUsingLLMToolEvent).handler(
            hook_ev, tool_stub, tool_args
        )
        assert tool_args == {"k": "lch-call", "mutated": True}

        tool_res_obj = SimpleNamespace(content=[SimpleNamespace(text="lch-tool")])
        await next(h for h in lch_handlers if h.event_type == EventType.OnLLMToolRespondEvent).handler(
            hook_ev, tool_stub, tool_args, tool_res_obj
        )
        assert "lch-tool [lch-tool-mut]" in str(tool_res_obj.content[0].text)

        await next(h for h in lch_handlers if h.event_type == EventType.OnAgentBeginEvent).handler(hook_ev)
        await next(h for h in lch_handlers if h.event_type == EventType.OnAgentDoneEvent).handler(hook_ev)
        await next(h for h in lch_handlers if h.event_type == EventType.OnPluginErrorEvent).handler(
            hook_ev, "sdk_lifecycle_config_hooks", "lch_fn", RuntimeError("boom"), "tb"
        )

        hook_ev.set_result(MessageEventResult().message("lch-msg"))
        await next(h for h in lch_handlers if h.event_type == EventType.OnDecoratingResultEvent).handler(hook_ev)
        assert "".join(
            c.text for c in hook_ev.get_result().chain if isinstance(c, Plain)
        ) == "lch-msg [lch-msg-mut]"
        await next(h for h in lch_handlers if h.event_type == EventType.OnAfterMessageSentEvent).handler(hook_ev)

        retire_res = await _dispatch_matrix(config, lch_mod, _MatrixMessageEvent("lch retire"))
        assert retire_res[0].chain[0].text == "retire-scheduled"
        lch_run_res = await _dispatch_matrix(config, lch_mod, _MatrixMessageEvent("lch run"))
        lch_report = json.loads(lch_run_res[0].chain[0].text)
        for flag in (
            "health_ok",
            "sensitive_ok",
            "tg_ok",
            "caps_ok",
            "native_bool",
            "worker_ref_ok",
            "detached_retired_ok",
            "cron_ok",
            "peer_ok",
        ):
            assert lch_report[flag] is True, f"lch failed on {flag}: {lch_report}"
        assert lch_report["tag"] == "live-tag"
        assert lch_report["limit"] == 15
        assert lch_report["direct_tag"] == "live-tag"
        assert lch_report["reloads"] >= 1
        assert lch_report["validated_tag"] == "val"
        assert "boom" in (lch_report["last_error"] or "")
        for hook_key in (
            "plugin_loaded",
            "plugin_unloaded",
            "waiting_llm_request",
            "llm_request",
            "llm_response",
            "tool_call",
            "tool_result",
            "agent_start",
            "agent_end",
            "plugin_error",
            "message_result",
            "message_sent",
        ):
            assert lch_report["hooks"].get(hook_key, 0) >= 1, f"Missing hook {hook_key}: {lch_report['hooks']}"
    finally:
        try:
            await sdk_mgr.stop_all()
        finally:
            for entry in list(bridge_sessions._REGISTRY.values()):
                if entry.deadline is not None:
                    entry.deadline.cancel()
            bridge_sessions._REGISTRY.clear()
            await cron_mgr.shutdown()
            if cron_mgr.scheduler.running:
                cron_mgr.scheduler.shutdown(wait=False)
            if getattr(kb_mgr, "kb_db", None) is not None:
                await kb_mgr.kb_db.engine.dispose()
            await real_sp.close()
            await db.engine.dispose()
            star_registry[:] = [
                m for m in star_registry if m.module_path in baseline_star_paths
            ]
            for key in list(star_map.keys()):
                if key not in baseline_map_keys:
                    star_map.pop(key, None)
            for name in list(star_handlers_registry.star_handlers_map.keys()):
                if name not in baseline_handler_names:
                    star_handlers_registry.star_handlers_map.pop(name, None)
            star_handlers_registry._handlers[:] = [
                h
                for h in star_handlers_registry._handlers
                if h.handler_full_name in baseline_handler_names
            ]
            llm_tools.func_list[:] = [
                t for t in llm_tools.func_list if t.name in baseline_tool_names
            ]
            Context.registered_web_apis = list(baseline_web_routes)
