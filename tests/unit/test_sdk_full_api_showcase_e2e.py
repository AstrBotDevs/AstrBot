"""Real-Core end-to-end tests exercising modern SDK and isolated legacy showcase plugins."""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

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
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config import AstrBotConfig
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.cron.manager import CronJobManager
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.platform.manager import PlatformManager
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

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "sdk_showcase"


class _ShowcaseChatProvider(Provider):
    """Deterministic chat provider supporting single-turn, stream, and tool loops."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.set_model(str(provider_config.get("model") or "mock-gpt"))

    def meta(self) -> ProviderMeta:
        """Return explicit ProviderMeta without requiring global provider registration."""
        return ProviderMeta(
            id=str(self.provider_config["id"]),
            model=self.get_model(),
            type=str(self.provider_config["type"]),
            provider_type=ProviderType.CHAT_COMPLETION,
        )

    def get_current_key(self) -> str:
        """Return dummy key."""
        return "mock-key"

    def set_key(self, key: str) -> None:
        """Accept key updates."""
        _ = key

    async def get_models(self) -> list[str]:
        """Return available mock model IDs."""
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
        """Execute a deterministic chat turn and drive Agent tool calls when offered."""
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
        if "showcase_add" in tool_names and not has_tool_results:
            return LLMResponse(
                role="assistant",
                tools_call_name=["showcase_add"],
                tools_call_args=[{"a": 6, "b": 7}],
                tools_call_ids=["call_add_1"],
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

        joined_tools = ",".join(tool_outputs)
        return LLMResponse(
            role="assistant",
            completion_text=f"chat-ok:{prompt or ''}:{joined_tools}:{system_prompt or ''}",
        )

    async def text_chat_stream(
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
        tool_choice: str = "auto",
        request_max_retries: int | None = None,
        **kwargs,
    ) -> AsyncGenerator[LLMResponse, None]:
        """Yield deterministic incremental chunks followed by a final response."""
        _ = (
            prompt,
            session_id,
            image_urls,
            audio_urls,
            func_tool,
            contexts,
            system_prompt,
            tool_calls_result,
            model,
            tool_choice,
            request_max_retries,
            kwargs,
        )
        yield LLMResponse(role="assistant", completion_text="chunk-1", is_chunk=True)
        yield LLMResponse(role="assistant", completion_text="-2", is_chunk=True)
        yield LLMResponse(role="assistant", completion_text="chunk-1-2", is_chunk=False)


class _ShowcaseTTSProvider(TTSProvider):
    """Local TTS provider writing deterministic audio bytes under temp storage."""

    def __init__(self, provider_config: dict, provider_settings: dict, tmp_dir: Path):
        super().__init__(provider_config, provider_settings)
        self._tmp_dir = tmp_dir
        self.set_model("mock-tts")

    def meta(self) -> ProviderMeta:
        """Return TTS provider metadata."""
        return ProviderMeta(
            id=str(self.provider_config["id"]),
            model=self.get_model(),
            type=str(self.provider_config["type"]),
            provider_type=ProviderType.TEXT_TO_SPEECH,
        )

    async def get_audio(self, text: str) -> str:
        """Write deterministic WAV payload bytes and return the output file path."""
        out_path = self._tmp_dir / "tts_out.wav"
        out_path.write_bytes(f"RIFF-MOCK:{text}".encode())
        return str(out_path)


class _ShowcaseSTTProvider(STTProvider):
    """Local STT provider verifying local audio files resolve cleanly."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.set_model("mock-stt")

    def meta(self) -> ProviderMeta:
        """Return STT provider metadata."""
        return ProviderMeta(
            id=str(self.provider_config["id"]),
            model=self.get_model(),
            type=str(self.provider_config["type"]),
            provider_type=ProviderType.SPEECH_TO_TEXT,
        )

    async def get_text(self, audio_url: str) -> str:
        """Verify local file accessibility and return deterministic transcription."""
        candidate = Path(audio_url)
        if not candidate.exists() or candidate.stat().st_size == 0:
            raise FileNotFoundError(f"Expected audio file for STT: {audio_url}")
        return "transcribed-ok"


class _ShowcaseEmbeddingProvider(EmbeddingProvider):
    """Deterministic embedding provider for vector and KB creation paths."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.set_model("mock-embed")

    def meta(self) -> ProviderMeta:
        """Return embedding provider metadata."""
        return ProviderMeta(
            id=str(self.provider_config["id"]),
            model=self.get_model(),
            type=str(self.provider_config["type"]),
            provider_type=ProviderType.EMBEDDING,
        )

    async def get_embedding(self, text: str) -> list[float]:
        """Return a fixed 4-dimensional embedding."""
        _ = text
        return [0.1, 0.2, 0.3, 0.4]

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        """Return fixed 4-dimensional embeddings for every input string."""
        return [[0.1, 0.2, 0.3, 0.4] for _ in text]

    def get_dim(self) -> int:
        """Return embedding dimension."""
        return 4


class _ShowcasePlatform(Platform):
    """Platform adapter recording proactive messages and raw bot API actions."""

    def __init__(self, config: dict, event_queue: asyncio.Queue) -> None:
        super().__init__(config, event_queue)
        self.sent_sessions: list[tuple[str, object]] = []
        self.raw_actions: list[tuple[str, dict]] = []
        outer = self

        class _BotApi:
            async def call_action(self, action: str, **params):
                outer.raw_actions.append((action, dict(params)))
                return {"action": action, **params}

        self.bot = SimpleNamespace(api=_BotApi())

    async def run(self) -> None:
        """No-op background loop for unit testing."""
        return None

    def meta(self) -> PlatformMetadata:
        """Return platform metadata matching webchat events."""
        return PlatformMetadata(name="webchat", description="E2E WebChat", id="webchat")

    def get_client(self) -> object:
        """Return the mock bot client."""
        return self.bot

    async def send_by_session(self, session, message_chain) -> None:
        """Record proactive messages routed through Context.send_message."""
        self.sent_sessions.append((str(session), message_chain))


class _ShowcaseMessageEvent(AstrMessageEvent):
    """Concrete AstrMessageEvent recording outbound sends, typing, and reactions."""

    def __init__(self, text: str, umo_session_id: str = "user-1") -> None:
        platform_meta = PlatformMetadata(
            name="webchat",
            description="E2E WebChat",
            id="webchat",
        )
        msg = AstrBotMessage()
        msg.type = MessageType.FRIEND_MESSAGE
        msg.self_id = "bot-self"
        msg.session_id = umo_session_id
        msg.message_id = f"msg-{umo_session_id}-{abs(hash(text))}"
        msg.sender = MessageMember(user_id="user-1", nickname="Moon")
        msg.message = [Plain(text)]
        msg.message_str = text
        msg.raw_message = {"text": text}
        super().__init__(
            message_str=text,
            message_obj=msg,
            platform_meta=platform_meta,
            session_id=umo_session_id,
        )
        self.is_wake = True
        self.is_at_or_wake_command = True
        self.sent_messages: list[object] = []
        self.typing_count = 0
        self.reactions: list[str] = []

    async def send(self, message) -> None:
        """Record reply deliveries triggered by the event."""
        self.sent_messages.append(message)
        self._has_send_oper = True

    async def send_typing(self) -> None:
        """Record typing indicator forwarding."""
        self.typing_count += 1

    async def react(self, emoji: str) -> None:
        """Record emoji reaction forwarding."""
        self.reactions.append(emoji)


class _LocalHtmlRenderer:
    """Offline HTML/text renderer writing PNG bytes into the test temp directory."""

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
        """Render an HTML template to a local PNG path."""
        _ = (return_url, options)
        self._counter += 1
        out_path = self._out_dir / f"render_html_{self._counter}.png"
        out_path.write_bytes(f"PNG-HTML:{tmpl}:{json.dumps(data)}".encode())
        return str(out_path)

    async def render_t2i(
        self,
        text: str,
        return_url: bool = False,
        use_network: bool | None = None,
        template_name: str | None = None,
    ) -> str:
        """Render plain text to a local PNG path."""
        _ = (return_url, use_network, template_name)
        self._counter += 1
        out_path = self._out_dir / f"render_t2i_{self._counter}.png"
        out_path.write_bytes(f"PNG-T2I:{text}".encode())
        return str(out_path)


class _WebRequestDouble:
    """Minimal Starlette Request stand-in for invoking PluginRequest handlers."""

    def __init__(
        self,
        method: str,
        path: str,
        *,
        query_items: list[tuple[str, str]] | None = None,
        body_bytes: bytes = b"",
    ) -> None:
        self.method = method
        self.headers: dict[str, str] = {}
        self.cookies: dict[str, str] = {}
        query_str = "&".join(f"{k}={v}" for k, v in (query_items or ()))
        self.url = SimpleNamespace(path=path, query=query_str)
        self.client = None
        self._query_items = list(query_items or ())
        self.query_params = self
        self._body_bytes = body_bytes

    def multi_items(self) -> list[tuple[str, str]]:
        """Return multi-value query items."""
        return list(self._query_items)

    async def body(self) -> bytes:
        """Return raw HTTP body bytes."""
        return self._body_bytes


async def _dispatch_matching_handler(
    config: AstrBotConfig,
    module_path: str,
    event: _ShowcaseMessageEvent,
    *,
    handler_name: str | None = None,
) -> list[MessageEventResult]:
    """Find and execute the matching pipeline handler for an inbound event.

    Args:
        config: Host AstrBotConfig passed to handler filters.
        module_path: Bridge module_path owning the target handlers.
        event: Inbound concrete AstrMessageEvent.
        handler_name: Optional explicit handler name to disambiguate.

    Returns:
        List of MessageEventResult yields emitted during handler execution.
    """
    candidates = [
        handler
        for handler in star_handlers_registry.get_handlers_by_module_name(module_path)
        if handler.event_type == EventType.AdapterMessageEvent
        and (handler_name is None or handler.handler_name == handler_name)
        # Mirror waking_check: CommandGroupFilter wakes the pipeline but is never activated.
        and not (
            handler_name is None
            and any(isinstance(f, CommandGroupFilter) for f in handler.event_filters)
        )
        and all(f.filter(event, config) for f in handler.event_filters)
    ]
    assert len(candidates) == 1, (
        f"Expected 1 handler match for {event.message_str!r} ({handler_name}), "
        f"got {[h.handler_name for h in candidates]}"
    )
    handler = candidates[0]
    parsed = event.get_extra("parsed_params") or {}
    results: list[MessageEventResult] = []
    async for _ in handler.handler(event, **parsed):
        res = event.get_result()
        if res is not None:
            results.append(res)
            event.clear_result()
    return results


async def _invoke_web_route(
    context: Context,
    method: str,
    path: str,
    *,
    plugin_name: str,
    query_items: list[tuple[str, str]] | None = None,
    body_bytes: bytes = b"",
) -> dict:
    """Resolve and invoke one registered plugin web route in a PluginRequest context.

    Args:
        context: Host Context holding registered_web_apis.
        method: HTTP verb (e.g. GET, POST).
        path: Request subpath matching the registered route.
        plugin_name: Owning plugin name passed in PluginRequest.
        query_items: Optional query parameter pairs.
        body_bytes: Optional raw request body.

    Returns:
        Decoded JSON dict from the ASGI Response returned by the bridge view handler.
    """
    matched = _match_registered_web_api(context.registered_web_apis, path, method)
    assert matched is not None, f"Web route {method} {path} not registered"
    view_handler, path_values = matched
    req = _WebRequestDouble(method, path, query_items=query_items, body_bytes=body_bytes)
    plugin_request = PluginRequest(
        req,
        path_params=path_values,
        plugin_name=plugin_name,
        username="admin",
    )
    with bind_request_context(plugin_request):
        response = await view_handler(**path_values)
    assert response.status_code == 200
    raw = b""
    async for chunk in response.body_iterator:
        raw += chunk
    return json.loads(raw)


async def _setup_real_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    plugin_names: tuple[str, ...],
) -> SimpleNamespace:
    """Boot real AstrBot SQLite, SharedPreferences, Managers, Context, and SDKPluginManager.

    Args:
        tmp_path: Pytest temporary directory isolating all files and databases.
        monkeypatch: Pytest MonkeyPatch fixture for env vars and module-level globals.
        plugin_names: Fixture plugin directories under tests/fixtures/sdk_showcase to stage.

    Returns:
        Namespace holding all initialized managers, Context, SDKPluginManager, and cleanup data.
    """
    baseline_star_paths = {m.module_path for m in star_registry if m.module_path}
    baseline_map_keys = set(star_map.keys())
    baseline_handler_names = set(star_handlers_registry.star_handlers_map.keys())
    baseline_tool_names = {t.name for t in llm_tools.func_list}
    baseline_web_routes = list(Context.registered_web_apis)

    astrbot_root = tmp_path / "astrbot_root"
    store_dir = tmp_path / "plugins"
    store_dir.mkdir(parents=True, exist_ok=True)
    for name in plugin_names:
        shutil.copytree(_FIXTURES_DIR / name, store_dir / name)

    monkeypatch.setenv("ASTRBOT_ROOT", str(astrbot_root))
    monkeypatch.setenv("ASTRBOT_SDK_DATA_DIR", str(tmp_path / "sdk_data"))

    kb_files = tmp_path / "kb" / "files"
    kb_db_path = tmp_path / "kb" / "kb.db"
    kb_files.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("astrbot.core.knowledge_base.kb_mgr.FILES_PATH", kb_files)
    monkeypatch.setattr("astrbot.core.knowledge_base.kb_mgr.DB_PATH", kb_db_path)

    db = SQLiteDatabase(str(tmp_path / "data_v4.db"))
    await db.initialize()
    real_sp = SharedPreferences(
        db_helper=db,
        json_storage_path=str(tmp_path / "shared_preferences.json"),
    )
    await real_sp.initialize()

    # Wire every module-level `sp` reference onto this isolated SharedPreferences instance.
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

    config_path = astrbot_root / "data" / "cmd_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = AstrBotConfig(config_path=str(config_path))
    config["dashboard"] = {**dict(config.get("dashboard") or {}), "jwt_secret": "showcase-jwt-secret"}
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
        await persona_mgr.create_persona("showcase_default", "Initial system prompt")

    conv_mgr = ConversationManager(db, acm)
    history_mgr = PlatformMessageHistoryManager(db)
    cron_mgr = CronJobManager(db)

    provider_mgr = ProviderManager(acm, db, persona_mgr)
    chat_prov = _ShowcaseChatProvider(
        {
            "id": "chat-main",
            "model": "mock-gpt",
            "type": "openai_chat_completion",
            "provider_type": "chat_completion",
        },
        {},
    )
    tts_prov = _ShowcaseTTSProvider(
        {
            "id": "tts-main",
            "model": "mock-tts",
            "type": "openai_tts",
            "provider_type": "text_to_speech",
        },
        {},
        tmp_path,
    )
    stt_prov = _ShowcaseSTTProvider(
        {
            "id": "stt-main",
            "model": "mock-stt",
            "type": "openai_whisper_api",
            "provider_type": "speech_to_text",
        },
        {},
    )
    emb_prov = _ShowcaseEmbeddingProvider(
        {
            "id": "emb-main",
            "model": "mock-embed",
            "type": "openai_embedding",
            "provider_type": "embedding",
        },
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
    platform = _ShowcasePlatform({}, event_queue)
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
    context.html_renderer = _LocalHtmlRenderer(tmp_path)  # type: ignore[assignment]
    await cron_mgr.start(context)
    sdk_mgr = SDKPluginManager(context, store_dir)
    pm_stub = SimpleNamespace(
        context=context,
        _sdk_plugin_manager=sdk_mgr,
        plugin_store_path=str(store_dir),
        reload=AsyncMock(return_value=(True, None)),
    )
    context._star_manager = pm_stub  # type: ignore[assignment]
    core_lifecycle = SimpleNamespace(
        astrbot_config=config,
        plugin_manager=pm_stub,
        astrbot_config_mgr=acm,
        umop_config_router=ucr,
    )
    return SimpleNamespace(
        astrbot_root=astrbot_root,
        store_dir=store_dir,
        db=db,
        real_sp=real_sp,
        config=config,
        ucr=ucr,
        acm=acm,
        persona_mgr=persona_mgr,
        conv_mgr=conv_mgr,
        history_mgr=history_mgr,
        cron_mgr=cron_mgr,
        provider_mgr=provider_mgr,
        kb_mgr=kb_mgr,
        platform=platform,
        context=context,
        sdk_mgr=sdk_mgr,
        pm_stub=pm_stub,
        core_lifecycle=core_lifecycle,
        baseline_star_paths=baseline_star_paths,
        baseline_map_keys=baseline_map_keys,
        baseline_handler_names=baseline_handler_names,
        baseline_tool_names=baseline_tool_names,
        baseline_web_routes=baseline_web_routes,
    )


async def _teardown_real_core(env: SimpleNamespace) -> None:
    """Stop bridges, close pools/schedulers, and restore global Star registries."""
    try:
        await env.sdk_mgr.stop_all()
    finally:
        for entry in list(bridge_sessions._REGISTRY.values()):
            if entry.deadline is not None:
                entry.deadline.cancel()
        bridge_sessions._REGISTRY.clear()
        await env.cron_mgr.shutdown()
        if env.cron_mgr.scheduler.running:
            env.cron_mgr.scheduler.shutdown(wait=False)
        if getattr(env.kb_mgr, "kb_db", None) is not None:
            await env.kb_mgr.kb_db.engine.dispose()
        await env.real_sp.close()
        await env.db.engine.dispose()
        star_registry[:] = [
            m for m in star_registry if m.module_path in env.baseline_star_paths
        ]
        for key in list(star_map.keys()):
            if key not in env.baseline_map_keys:
                star_map.pop(key, None)
        for name in list(star_handlers_registry.star_handlers_map.keys()):
            if name not in env.baseline_handler_names:
                star_handlers_registry.star_handlers_map.pop(name, None)
        star_handlers_registry._handlers[:] = [
            h
            for h in star_handlers_registry._handlers
            if h.handler_full_name in env.baseline_handler_names
        ]
        llm_tools.func_list[:] = [
            t for t in llm_tools.func_list if t.name in env.baseline_tool_names
        ]
        Context.registered_web_apis = list(env.baseline_web_routes)


@pytest.mark.asyncio
async def test_new_sdk_full_api_showcase_against_real_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify full_api_peer + full_api_showcase against real Core managers & dashboard."""
    env = await _setup_real_core(
        tmp_path,
        monkeypatch,
        ("full_api_peer", "full_api_showcase"),
    )
    try:
        loaded = await env.sdk_mgr.load_all()
        assert loaded == ["full_api_peer", "full_api_showcase"]

        bridge = env.sdk_mgr.bridges["full_api_showcase"]
        initial_pid = bridge.runner_pid
        assert initial_pid is not None and initial_pid > 0

        # Ping probe triggers @lifecycle.health in the running Worker.
        await bridge._require_client().ping()

        # Dashboard PluginPageService: view discovery, HTML serving, and i18n context.
        page_svc = PluginPageService(env.pm_stub, env.core_lifecycle, env.config)
        entry = await page_svc.get_plugin_page_entry_config(
            plugin_name="full_api_showcase",
            view_name="dashboard",
            jwt_secret="showcase-jwt-secret",
            username="admin",
            locale="zh-CN",
        )
        assert entry["name"] == "dashboard"
        assert "/api/v1/plugins/full_api_showcase/views/dashboard/" in entry["content_path"]

        served_html = await page_svc.serve_page_content(
            plugin_name="full_api_showcase",
            view_name="dashboard",
            asset_path="",
            asset_token="",
            jwt_secret="showcase-jwt-secret",
            username="admin",
            locale="zh-CN",
            theme=None,
        )
        assert "AstrBot SDK Full API Showcase" in served_html.content

        token = page_svc.issue_plugin_page_asset_token(
            plugin_name="full_api_showcase",
            view_name="dashboard",
            jwt_secret="showcase-jwt-secret",
            username="admin",
            locale="zh-CN",
        )
        assert token is not None
        initial_ctx = page_svc.build_initial_context(
            asset_token=token,
            jwt_secret="showcase-jwt-secret",
            locale="zh-CN",
            theme="dark",
        )
        assert initial_ctx is not None
        assert initial_ctx["i18n"]["zh-CN"]["title"] == "全接口演示插件"
        assert initial_ctx["i18n"]["en-US"]["title"] == "Full API Showcase"

        # ConfigFileService live reconfiguration + writeOnly masking + validation rejection.
        display_svc = ConfigDisplayService(env.core_lifecycle)
        file_svc = ConfigFileService(env.core_lifecycle)

        await file_svc.save_plugin_configs(
            {
                "api_token": "super-secret-123",
                "greeting_prefix": "LIVE",
                "max_items": 12,
            },
            bridge.plugin_name,
        )
        env.pm_stub.reload.assert_not_awaited()
        assert bridge.runner_pid == initial_pid

        displayed = display_svc.get_plugin_config("full_api_showcase")
        assert displayed["config"]["api_token"] == ""
        assert displayed["config"]["greeting_prefix"] == "LIVE"
        assert displayed["config"]["max_items"] == 12

        with pytest.raises(ValueError, match="49"):
            await file_svc.save_plugin_configs(
                {
                    "api_token": "super-secret-123",
                    "greeting_prefix": "BAD",
                    "max_items": 49,
                },
                bridge.plugin_name,
            )
        assert display_svc.get_plugin_config("full_api_showcase")["config"]["max_items"] == 12

        # Regex message handler reflects live-configured prefix and max_items.
        ping_results = await _dispatch_matching_handler(
            env.config,
            bridge.module_path,
            _ShowcaseMessageEvent("#sdk-ping"),
        )
        assert len(ping_results) == 1
        assert ping_results[0].chain[0].text == "LIVE:pong:12"

        # Full capability showcase suite command.
        suite_results = await _dispatch_matching_handler(
            env.config,
            bridge.module_path,
            _ShowcaseMessageEvent("showcase suite"),
        )
        assert len(suite_results) == 1
        report = json.loads(suite_results[0].chain[0].text)
        assert report["all_passed"] is True, f"Showcase suite failed: {report}"
        assert report["storage_ok"] is True
        assert report["assets_ok"] is True
        assert report["convs_ok"] is True
        assert report["plugins_ok"] is True
        assert report["render_ok"] is True
        assert report["tools_ok"] is True
        assert report["llm_ok"] is True
        assert "13" in report["agent_text"]
        assert report["config_reloaded"] >= 1
        assert report["hooks"].get("plugin_loaded", 0) >= 1

        # Verify side effects on Host registries & PlatformAdapter.
        assert any(
            isinstance(seg, Plain) and seg.text == "proactive-sdk-ok"
            and any(isinstance(other, Image) for other in chain.chain)
            for _umo, chain in env.platform.sent_sessions
            for seg in chain.chain
        )
        runtime_tool = llm_tools.get_func("runtime_echo")
        discovered_tool = llm_tools.get_func("discovered_ping")
        assert runtime_tool is not None
        assert discovered_tool is not None
        assert llm_tools.get_func("dyn_temp") is None
        assert await runtime_tool.handler(_ShowcaseMessageEvent("t"), tag="e2e") == "runtime-echo:e2e"
        assert await discovered_tool.handler(_ShowcaseMessageEvent("d"), note="hi") == "discovered:hi"

        # Multi-turn session wait dialog via real SessionWaitService interceptor.
        sent_before = len(env.platform.sent_sessions)
        dialog_event = _ShowcaseMessageEvent("showcase dialog")
        dialog_task = asyncio.create_task(
            _dispatch_matching_handler(env.config, bridge.module_path, dialog_event)
        )
        try:
            for _ in range(100):
                if (
                    any(
                        entry.umo_str == "webchat:FriendMessage:user-1"
                        for entry in bridge_sessions._REGISTRY.values()
                    )
                    and len(env.platform.sent_sessions) > sent_before
                ):
                    break
                await asyncio.sleep(0.05)
            assert any(
                entry.umo_str == "webchat:FriendMessage:user-1"
                for entry in bridge_sessions._REGISTRY.values()
            )

            followup_event = _ShowcaseMessageEvent("turn-two")
            await bridge_sessions._session_wait_interceptor(followup_event)
            assert followup_event.is_stopped()
            dialog_results = await asyncio.wait_for(dialog_task, timeout=5.0)
            assert dialog_results[0].chain[0].text == "dialog:turn-two"
        finally:
            if not dialog_task.done():
                dialog_task.cancel()
                await asyncio.gather(dialog_task, return_exceptions=True)

        # Web route GET and POST through PluginRequest bridge wrapper.
        get_body = await _invoke_web_route(
            env.context,
            "GET",
            "/showcase/echo/demo",
            plugin_name="full_api_showcase",
            query_items=[("q", "hello")],
        )
        assert get_body == {
            "topic": "demo",
            "q": "hello",
            "method": "GET",
            "body": "",
            "prefix": "LIVE",
        }
        post_body = await _invoke_web_route(
            env.context,
            "POST",
            "/showcase/echo/demo",
            plugin_name="full_api_showcase",
            query_items=[("q", "hello")],
            body_bytes=b"body-bytes",
        )
        assert post_body == {
            "topic": "demo",
            "q": "hello",
            "method": "POST",
            "body": "body-bytes",
            "prefix": "LIVE",
        }

        # Pipeline hooks mutate LLMRequest and MessageResult when authorized.
        hook_handlers = star_handlers_registry.get_handlers_by_module_name(bridge.module_path)
        llm_req_hook = next(
            h for h in hook_handlers if h.event_type == EventType.OnLLMRequestEvent
        )
        msg_res_hook = next(
            h for h in hook_handlers if h.event_type == EventType.OnDecoratingResultEvent
        )
        msg_sent_hook = next(
            h for h in hook_handlers if h.event_type == EventType.OnAfterMessageSentEvent
        )

        hook_ev = _ShowcaseMessageEvent("hook")
        req = ProviderRequest(prompt="[hook-test] hi", system_prompt="base")
        await llm_req_hook.handler(hook_ev, req)
        assert "[hook-llm-req]" in req.system_prompt

        hook_ev.set_result(MessageEventResult().message("[hook-test] out"))
        await msg_res_hook.handler(hook_ev)
        assert "".join(c.text for c in hook_ev.get_result().chain if isinstance(c, Plain)) == (
            "[hook-test] out [hook-msg-res]"
        )
        await msg_sent_hook.handler(hook_ev)
    finally:
        await _teardown_real_core(env)


@pytest.mark.asyncio
async def test_legacy_main_api_showcase_against_real_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify legacy_main_api_showcase against real Core managers in isolated mode."""
    env = await _setup_real_core(
        tmp_path,
        monkeypatch,
        ("legacy_main_api_showcase",),
    )
    try:
        loaded = await env.sdk_mgr.load_all()
        assert loaded == ["legacy_main_api_showcase"]

        bridge = env.sdk_mgr.bridges["legacy_main_api_showcase"]

        # Full isolated legacy API suite.
        suite_event = _ShowcaseMessageEvent("legacy_suite")
        suite_results = await _dispatch_matching_handler(
            env.config,
            bridge.module_path,
            suite_event,
        )
        assert len(suite_results) == 1
        report = json.loads(suite_results[0].chain[0].text)
        assert report["all_passed"] is True, f"Legacy suite failed: {report}"
        for flag in (
            "config_ok",
            "stars_ok",
            "sp_ok",
            "providers_ok",
            "conv_history_ok",
            "persona_ok",
            "kb_ok",
            "cron_ok",
            "dyn_tools_ok",
            "platform_ok",
            "isolation_guarded",
        ):
            assert report[flag] is True, f"Expected {flag} to pass: {report}"

        # Assert persisted plugin config, live Host persona mutation, and platform effects.
        cfg_file = env.astrbot_root / "data" / "config" / "legacy_main_api_showcase_config.json"
        assert json.loads(cfg_file.read_text(encoding="utf-8-sig"))["counter"] == 7
        assert env.persona_mgr.personas_v3[0]["prompt"] == "Updated via isolated legacy plugin"
        assert any(
            isinstance(seg, Plain) and seg.text == "legacy-proactive-ok"
            for _umo, chain in env.platform.sent_sessions
            for seg in chain.chain
        )
        assert suite_event.typing_count >= 1
        assert "thumbsup" in suite_event.reactions
        assert ("get_login_info", {"echo": "ok"}) in env.platform.raw_actions

        # Verify both decorator-registered and dynamic FunctionTool execute cleanly.
        legacy_mul = llm_tools.get_func("legacy_mul")
        legacy_dyn = llm_tools.get_func("legacy_dyn_tool")
        assert legacy_mul is not None
        assert legacy_dyn is not None
        assert await legacy_mul.handler(_ShowcaseMessageEvent("m"), a=3, b=4) == "12"
        assert await legacy_dyn.handler(_ShowcaseMessageEvent("d"), x=5) == "dyn-mul:15"

        # Verify command group subcommand, regex filter, and legacy web route.
        lg_res = await _dispatch_matching_handler(
            env.config,
            bridge.module_path,
            _ShowcaseMessageEvent("lg ping"),
        )
        assert lg_res[0].chain[0].text == "lg-pong"

        regex_res = await _dispatch_matching_handler(
            env.config,
            bridge.module_path,
            _ShowcaseMessageEvent("#legacy-ping"),
        )
        assert regex_res[0].chain[0].text == "MAIN:regex-pong"

        web_body = await _invoke_web_route(
            env.context,
            "GET",
            "/legacy/ping",
            plugin_name="legacy_main_api_showcase",
            query_items=[("q", "ok")],
        )
        assert web_body == {
            "ok": True,
            "plugin": "legacy_main_api_showcase",
            "q": "ok",
        }

        # Multi-turn @session_waiter flow.
        wait_event = _ShowcaseMessageEvent("legacy_wait")
        wait_task = asyncio.create_task(
            _dispatch_matching_handler(env.config, bridge.module_path, wait_event)
        )
        try:
            for _ in range(100):
                if any(
                    entry.umo_str == "webchat:FriendMessage:user-1"
                    for entry in bridge_sessions._REGISTRY.values()
                ):
                    break
                await asyncio.sleep(0.05)
            assert any(
                entry.umo_str == "webchat:FriendMessage:user-1"
                for entry in bridge_sessions._REGISTRY.values()
            )

            followup_event = _ShowcaseMessageEvent("hello-waiter")
            await bridge_sessions._session_wait_interceptor(followup_event)
            assert followup_event.is_stopped()
            wait_results = await asyncio.wait_for(wait_task, timeout=5.0)
            assert wait_results[0].chain[0].text == "legacy-ask"
            assert any(
                isinstance(seg, Plain) and seg.text == "legacy-got:hello-waiter"
                for _umo, chain in env.platform.sent_sessions
                for seg in chain.chain
            )
        finally:
            if not wait_task.done():
                wait_task.cancel()
                await asyncio.gather(wait_task, return_exceptions=True)

        # Pipeline hook @filter.on_decorating_result appends decorator suffix.
        hook_handlers = star_handlers_registry.get_handlers_by_module_name(bridge.module_path)
        dec_hook = next(
            h for h in hook_handlers if h.event_type == EventType.OnDecoratingResultEvent
        )
        dec_ev = _ShowcaseMessageEvent("hook")
        dec_ev.set_result(MessageEventResult().message("[legacy-hook] reply"))
        await dec_hook.handler(dec_ev)
        assert "".join(c.text for c in dec_ev.get_result().chain if isinstance(c, Plain)) == (
            "[legacy-hook] reply [legacy-decorated]"
        )
    finally:
        await _teardown_real_core(env)
