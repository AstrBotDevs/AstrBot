"""Real-Core E2E tests for legacy patterns uncovered by popular marketplace plugins."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.api.provider import Provider
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config import AstrBotConfig
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.cron.manager import CronJobManager
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.pipeline.context_utils import call_handler
from astrbot.core.platform.astrbot_message import Group
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.platform.platform import PlatformStatus
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.core.provider.entities import LLMResponse, ProviderMeta, ProviderType
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.provider.register import llm_tools
from astrbot.core.star.context import Context
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.sdk_bridge import SDKPluginManager
from astrbot.core.star.sdk_bridge.services import sessions as bridge_sessions
from astrbot.core.star.star import star_map, star_registry
from astrbot.core.star.star_handler import EventType, star_handlers_registry
from astrbot.core.umop_config_router import UmopConfigRouter
from astrbot.core.utils.shared_preferences import SharedPreferences


class _StubChatProvider(Provider):
    """Minimal chat provider used for fallback/image provider resolution checks."""

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

    async def text_chat(self, prompt=None, **kwargs) -> LLMResponse:
        _ = kwargs
        return LLMResponse(role="assistant", completion_text=str(prompt or ""))

    async def text_chat_stream(
        self, prompt=None, **kwargs
    ) -> AsyncGenerator[LLMResponse, None]:
        _ = (prompt, kwargs)
        yield LLMResponse(role="assistant", completion_text="ok", is_chunk=False)


class _StubPlatform(Platform):
    """Platform stub recording proactive deliveries and raw OneBot actions."""

    def __init__(self, name: str, config: dict, event_queue: asyncio.Queue) -> None:
        super().__init__(config, event_queue)
        self._name = name
        self.status = PlatformStatus.RUNNING
        self.sent_sessions: list[tuple[str, object]] = []
        self.raw_actions: list[tuple[str, dict]] = []
        outer = self

        class _BotApi:
            async def call_action(self, action: str, **params):
                outer.raw_actions.append((action, dict(params)))
                if action == "get_group_list":
                    return [
                        {"group_id": 1001, "group_name": "Alpha"},
                        {"group_id": 1002, "group_name": "Beta"},
                    ]
                return {"action": action, **params}

        self.bot = SimpleNamespace(api=_BotApi())

    async def run(self) -> None:
        return None

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name=self._name,
            description=f"Stub {self._name}",
            id=self._name,
        )

    def get_client(self) -> object:
        return self.bot

    async def send_by_session(self, session, message_chain) -> None:
        self.sent_sessions.append((str(session), message_chain))


class _StubMessageEvent(AstrMessageEvent):
    """Concrete inbound event for arbitrary platform adapters."""

    def __init__(self, text: str, platform_name: str = "aiocqhttp") -> None:
        platform_meta = PlatformMetadata(
            name=platform_name,
            description=f"Stub {platform_name}",
            id=platform_name,
        )
        msg = AstrBotMessage()
        msg.type = MessageType.FRIEND_MESSAGE
        msg.self_id = "bot-1"
        msg.session_id = "user-1"
        msg.message_id = f"msg-{abs(hash((platform_name, text)))}"
        msg.sender = MessageMember(user_id="user-1", nickname="Tester")
        msg.message = [Plain(text)]
        msg.message_str = text
        msg.raw_message = {"text": text}
        super().__init__(
            message_str=text,
            message_obj=msg,
            platform_meta=platform_meta,
            session_id="user-1",
        )
        self.role = "admin"
        self.is_wake = True
        self.is_at_or_wake_command = True

    async def send(self, message) -> None:
        self._has_send_oper = True

    async def get_group(self, group_id: str | None = None) -> Group:
        return Group(group_id=group_id or "grp-1", group_name="Stub Group")


async def _dispatch(config: AstrBotConfig, module_path: str, event: _StubMessageEvent):
    candidates = [
        h
        for h in star_handlers_registry.get_handlers_by_module_name(module_path)
        if h.event_type == EventType.AdapterMessageEvent
        and not any(isinstance(f, CommandGroupFilter) for f in h.event_filters)
        and all(f.filter(event, config) for f in h.event_filters)
    ]
    outputs: list[str] = []
    for handler in candidates:
        parsed = event.get_extra("parsed_params") or {}
        async for _item in call_handler(event, handler.handler, **parsed):
            res = event.get_result()
            if res is not None:
                outputs.append(res.get_plain_text())
                event.clear_result()
    return [h.handler_name for h in candidates], outputs


@pytest.mark.asyncio
async def test_popular_plugin_compat_patterns_e2e(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify package/__init__ & <dir>.py entrypoints, priorities, multi-word aliases, OR platforms, raw bot unwrap, PlatformFacade.status, and agent provider helpers."""
    baseline_star_paths = {m.module_path for m in star_registry if m.module_path}
    baseline_map_keys = set(star_map.keys())
    baseline_handler_names = set(star_handlers_registry.star_handlers_map.keys())
    baseline_tool_names = {t.name for t in llm_tools.func_list}
    baseline_web_routes = list(Context.registered_web_apis)

    astrbot_root = tmp_path / "astrbot_root"
    store_dir = tmp_path / "plugins"
    store_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ASTRBOT_ROOT", str(astrbot_root))
    monkeypatch.setenv("ASTRBOT_SDK_DATA_DIR", str(tmp_path / "sdk_data"))

    # Plugin 1: __init__.py package entrypoint covering on_message(priority=-10),
    # sys.maxsize priority, PlatformAdapterType.ALL, multi-word space alias,
    # LegacyBotApiProxy result unwrapping, PlatformFacade.status & send_by_session.
    pkg_dir = store_dir / "pop_pkg_entry"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "metadata.yaml").write_text(
        "name: pop_pkg_entry\ndesc: pkg entry\nauthor: AstrBot\nversion: '1.0.0'\n",
        encoding="utf-8",
    )
    (pkg_dir / "__init__.py").write_text(
        '''
import json
import sys
from astrbot.api.all import *
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core.platform.astr_message_event import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform import PlatformStatus
from astrbot.core.star.filter.platform_adapter_type import PlatformAdapterType

@register("pop_pkg_entry", "AstrBot", "pkg entry", "1.0.0")
class PopPkgPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context, config)
        self.seen_priorities: list[str] = []

    @filter.platform_adapter_type(PlatformAdapterType.ALL, priority=sys.maxsize - 20)
    async def on_all_platforms(self, event):
        if event.message_str == "check-platform-all":
            self.seen_priorities.append("all-max")
            yield event.plain_result("all-platform-ok")

    @filter.on_message(priority=-10)
    async def on_msg_hook(self, event):
        if event.message_str == "check-on-msg":
            groups = await event.bot.api.call_action("get_group_list", no_cache=False)
            gids = [item["group_id"] for item in groups]
            plats = self.context.platform_manager.get_insts()
            aiocq = next(p for p in plats if p.meta().id == "aiocqhttp")
            assert aiocq.status == PlatformStatus.RUNNING
            sess = MessageSession("aiocqhttp", MessageType.FRIEND_MESSAGE, "user-1")
            assert str(sess) == "aiocqhttp:FriendMessage:user-1"
            await aiocq.send_by_session(sess, MessageChain([Plain("facade-send-ok")]))
            yield event.plain_result(json.dumps({"gids": gids, "status": aiocq.status.value}))

    @filter.command("重启AstrBot", alias={"重启 AstrBot"})
    async def restart_cmd(self, event):
        yield event.plain_result("alias-space-ok")
''',
        encoding="utf-8",
    )

    # Plugin 2: <dir>.py entrypoint covering bitwise OR platform filters and
    # astrbot.core.astr_main_agent.providers helpers.
    named_dir = store_dir / "pop_named_entry"
    named_dir.mkdir(parents=True)
    (named_dir / "metadata.yaml").write_text(
        "name: pop_named_entry\ndesc: named entry\nauthor: AstrBot\nversion: '1.0.0'\n",
        encoding="utf-8",
    )
    (named_dir / "pop_named_entry.py").write_text(
        '''
import json
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core.astr_main_agent import (
    _get_fallback_chat_providers,
    _select_image_chat_provider,
)
from astrbot.core.astr_main_agent.providers import (
    resolve_fallback_providers,
    select_image_provider,
)
from astrbot.core.star.filter.platform_adapter_type import PlatformAdapterType

@register("pop_named_entry", "AstrBot", "named entry", "1.0.0")
class PopNamedPlugin(Star):
    @filter.platform_adapter_type(
        PlatformAdapterType.AIOCQHTTP | PlatformAdapterType.WEBCHAT,
        priority=5,
    )
    async def on_multi_plat(self, event):
        if event.message_str == "hi":
            yield event.plain_result(f"or-match:{event.get_platform_name()}")

    @filter.command("check_providers")
    async def check_providers(self, event):
        primary = self.context.get_provider_by_id("chat-main")
        fallbacks = resolve_fallback_providers(primary, self.context, ["chat-main", "chat-fallback"])
        img_p = select_image_provider(primary, None, fallbacks)
        assert len(_get_fallback_chat_providers(primary, self.context, ["chat-fallback"])) == 1
        assert _select_image_chat_provider(primary) is primary
        yield event.plain_result(
            json.dumps(
                {
                    "fallbacks": [p.meta().id for p in fallbacks],
                    "selected": img_p.meta().id,
                },
                sort_keys=True,
            )
        )
''',
        encoding="utf-8",
    )

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
    config.save_config()

    ucr = UmopConfigRouter(sp=real_sp)
    await ucr.initialize()
    acm = AstrBotConfigManager(default_config=config, ucr=ucr, sp=real_sp)
    await acm.initialize()
    persona_mgr = PersonaManager(db, acm)
    await persona_mgr.initialize()
    conv_mgr = ConversationManager(db, acm)
    history_mgr = PlatformMessageHistoryManager(db)
    cron_mgr = CronJobManager(db)

    provider_mgr = ProviderManager(acm, db, persona_mgr)
    chat_main = _StubChatProvider(
        {"id": "chat-main", "model": "mock-main", "type": "openai_chat_completion"},
        {},
    )
    chat_fb = _StubChatProvider(
        {"id": "chat-fallback", "model": "mock-fb", "type": "openai_chat_completion"},
        {},
    )
    provider_mgr.provider_insts = [chat_main, chat_fb]
    provider_mgr.curr_provider_inst = chat_main
    provider_mgr.inst_map = {"chat-main": chat_main, "chat-fallback": chat_fb}

    kb_mgr = KnowledgeBaseManager(provider_mgr)
    await kb_mgr.initialize()

    event_queue: asyncio.Queue = asyncio.Queue()
    platform_mgr = PlatformManager(config, event_queue)
    aiocq_plat = _StubPlatform("aiocqhttp", {}, event_queue)
    webchat_plat = _StubPlatform("webchat", {}, event_queue)
    telegram_plat = _StubPlatform("telegram", {}, event_queue)
    platform_mgr.platform_insts.extend([aiocq_plat, webchat_plat, telegram_plat])

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
    await cron_mgr.start(context)
    sdk_mgr = SDKPluginManager(context, store_dir)

    try:
        loaded = await sdk_mgr.load_all(
            runtime_overrides={
                "pop_pkg_entry": "isolated",
                "pop_named_entry": "isolated",
            }
        )
        assert set(loaded) == {"pop_pkg_entry", "pop_named_entry"}

        pkg_bridge = sdk_mgr.find_bridge("pop_pkg_entry")
        named_bridge = sdk_mgr.find_bridge("pop_named_entry")
        assert pkg_bridge is not None and named_bridge is not None

        # Verify handler priority extras survived Worker -> Host registration.
        pkg_handlers = {
            h.handler_name: h
            for h in star_handlers_registry.get_handlers_by_module_name(pkg_bridge.module_path)
        }
        assert pkg_handlers["on_msg_hook"].extras_configs["priority"] == -10
        assert pkg_handlers["on_all_platforms"].extras_configs["priority"] == sys.maxsize - 20

        # 1. @filter.on_message + LegacyBotApiProxy unwrap + PlatformFacade.status + send_by_session.
        matched, out = await _dispatch(
            config, pkg_bridge.module_path, _StubMessageEvent("check-on-msg", "aiocqhttp")
        )
        assert "on_msg_hook" in matched
        payload = json.loads(out[0])
        assert payload == {"gids": [1001, 1002], "status": "running"}
        assert ("get_group_list", {"no_cache": False}) in aiocq_plat.raw_actions
        assert any(
            isinstance(seg, Plain) and seg.text == "facade-send-ok"
            for _sess, chain in aiocq_plat.sent_sessions
            for seg in chain.chain
        )

        # 2. PlatformAdapterType.ALL matches any platform (including telegram).
        matched_all, out_all = await _dispatch(
            config, pkg_bridge.module_path, _StubMessageEvent("check-platform-all", "telegram")
        )
        assert "on_all_platforms" in matched_all
        assert "all-platform-ok" in out_all

        # 3. Top-level multi-word alias containing spaces.
        matched_alias, out_alias = await _dispatch(
            config, pkg_bridge.module_path, _StubMessageEvent("重启 AstrBot", "webchat")
        )
        assert "restart_cmd" in matched_alias
        assert out_alias == ["alias-space-ok"]

        # 4. Bitwise OR PlatformAdapterType filter matches AIOCQHTTP and WEBCHAT, skips TELEGRAM.
        m_acq, o_acq = await _dispatch(
            config, named_bridge.module_path, _StubMessageEvent("hi", "aiocqhttp")
        )
        m_web, o_web = await _dispatch(
            config, named_bridge.module_path, _StubMessageEvent("hi", "webchat")
        )
        m_tg, o_tg = await _dispatch(
            config, named_bridge.module_path, _StubMessageEvent("hi", "telegram")
        )
        assert "on_multi_plat" in m_acq and o_acq == ["or-match:aiocqhttp"]
        assert "on_multi_plat" in m_web and o_web == ["or-match:webchat"]
        assert "on_multi_plat" not in m_tg and o_tg == []

        # 5. astrbot.core.astr_main_agent.providers helpers resolve fallbacks & image provider.
        m_prov, o_prov = await _dispatch(
            config, named_bridge.module_path, _StubMessageEvent("check_providers", "webchat")
        )
        assert "check_providers" in m_prov
        assert json.loads(o_prov[0]) == {
            "fallbacks": ["chat-fallback"],
            "selected": "chat-main",
        }
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
