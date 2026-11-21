"""Full-API isolated legacy Star showcase plugin exercising AstrBot main Core APIs."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from apscheduler.triggers.date import DateTrigger
from astrbot.api import (
    AstrBotConfig,
    FunctionTool,
    ToolSet,
    html_renderer,
    logger,
    sp,
)
from astrbot.api.all import MessageChain, Plain
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderType
from astrbot.api.star import Context, Star, StarTools
from astrbot.api.web import request
from astrbot.core.utils.session_waiter import SessionController, session_waiter


@dataclass
class LegacyDynTool(FunctionTool):
    """Dynamically registered FunctionTool subclass using the Core signature."""

    name: str = "legacy_dyn_tool"
    description: str = "Multiply an integer by 3 dynamically"
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {"x": {"type": "integer", "description": "Input integer"}},
            "required": ["x"],
        }
    )

    async def call(self, context: Any, x: int = 1) -> str:
        """Multiply x by 3."""
        _ = context
        return f"dyn-mul:{int(x) * 3}"


class LegacyMainApiShowcasePlugin(Star):
    """Exercise AstrBot's classic `astrbot.api` / `Context` surface in isolated mode."""

    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context, config)
        self.config = config
        self._cron_fired = asyncio.Event()
        self._cron_payload: dict[str, Any] = {}
        self._hook_counts: dict[str, int] = {}
        self._terminated = False
        self.context.register_web_api(
            "/legacy/ping",
            self._web_ping,
            ["GET"],
            "Legacy showcase ping route",
        )

    async def _web_ping(self) -> dict[str, Any]:
        """Handle `/legacy/ping` using `astrbot.api.web.request`."""
        return {
            "ok": True,
            "plugin": "legacy_main_api_showcase",
            "q": request.query.get("q", ""),
        }

    async def _on_cron_tick(self, tag: str = "") -> None:
        """Cron callback invoked inside the isolated Runner from Host APScheduler."""
        self._cron_payload = {"tag": tag}
        self._cron_fired.set()

    async def terminate(self) -> None:
        """Mark plugin termination on shutdown/unload."""
        self._terminated = True

    @filter.command_group("lg")
    def lg(self) -> None:
        """Legacy command group root."""

    @lg.command("ping")
    async def lg_ping(self, event: AstrMessageEvent):
        """Respond inside a legacy sub-command."""
        yield event.plain_result("lg-pong")

    @filter.regex(r"^#legacy-ping$")
    async def legacy_regex(self, event: AstrMessageEvent):
        """Handle regex pattern using legacy filter."""
        banner = (self.config or {}).get("banner", "MAIN")
        yield event.plain_result(f"{banner}:regex-pong")

    @filter.llm_tool(name="legacy_mul")
    async def legacy_mul(self, event: AstrMessageEvent, a: int, b: int) -> str:
        """Multiply two integers via @filter.llm_tool.

        Args:
            a(int): First factor.
            b(int): Second factor.
        """
        _ = event
        return str(a * b)

    @filter.on_llm_request()
    async def on_llm_req(self, event: AstrMessageEvent, req: Any) -> None:
        _ = (event, req)
        self._hook_counts["on_llm_request"] = (
            self._hook_counts.get("on_llm_request", 0) + 1
        )

    @filter.on_decorating_result()
    async def on_decorating_res(self, event: AstrMessageEvent) -> None:
        self._hook_counts["on_decorating_result"] = (
            self._hook_counts.get("on_decorating_result", 0) + 1
        )
        res = event.get_result()
        if res and any("[legacy-hook]" in getattr(c, "text", "") for c in res.chain):
            res.chain.append(Plain(" [legacy-decorated]"))

    @filter.after_message_sent()
    async def on_after_sent(self, event: AstrMessageEvent) -> None:
        _ = event
        self._hook_counts["after_message_sent"] = (
            self._hook_counts.get("after_message_sent", 0) + 1
        )

    @filter.command("legacy_wait")
    async def legacy_wait(self, event: AstrMessageEvent):
        """Exercise `@session_waiter` multi-turn session capture."""
        yield event.plain_result("legacy-ask")

        @session_waiter(timeout=10)
        async def _waiter(controller: SessionController, evt: AstrMessageEvent):
            await evt.send(evt.plain_result(f"legacy-got:{evt.message_str.strip()}"))
            controller.stop()

        await _waiter(event)

    @filter.command("legacy_suite")
    async def legacy_suite(self, event: AstrMessageEvent):
        """Exercise every supported AstrBot Main Core API in isolated legacy mode."""
        logger.info("Running legacy_main_api_showcase full suite")
        umo = event.unified_msg_origin

        # 1. Config, locale & save_config_async
        global_cfg = self.context.get_config(umo)
        locale_val = self.context.locale(umo)
        cfg_saved = False
        if self.config is not None:
            self.config["counter"] = 7
            cfg_saved = await self.config.save_config_async()
        config_ok = bool(global_cfg) and bool(locale_val) and cfg_saved

        # 2. Star registry & StarTools
        stars = await self.context.get_all_stars_async()
        self_meta = self.context.get_registered_star("legacy_main_api_showcase")
        data_dir = Path(StarTools.get_data_dir())
        marker = data_dir / "legacy_marker.txt"
        marker.write_text("legacy-dir-ok", encoding="utf-8")
        stars_ok = (
            len(stars) >= 1
            and self_meta is not None
            and marker.read_text(encoding="utf-8") == "legacy-dir-ok"
        )

        # 3. SharedPreferences (`sp`)
        await sp.put_async("plugin", "legacy_demo", "k1", {"v": 42})
        sp_val = await sp.get_async("plugin", "legacy_demo", "k1")
        sp_range = await sp.range_get_async("plugin", "legacy_demo")
        await sp.remove_async("plugin", "legacy_demo", "k1")
        sp_after = await sp.get_async("plugin", "legacy_demo", "k1", "gone")
        sp_ok = (
            sp_val == {"v": 42}
            and any(
                entry.key == "k1" and entry.value.get("val") == {"v": 42}
                for entry in sp_range
            )
            and sp_after == "gone"
        )

        # 4. Providers, llm_generate, & tool_loop_agent
        chat_provs = self.context.get_all_providers()
        tts_provs = self.context.get_all_tts_providers()
        stt_provs = self.context.get_all_stt_providers()
        emb_provs = self.context.get_all_embedding_providers()
        using_prov = self.context.get_using_provider(umo)
        await self.context.provider_manager.set_provider(
            chat_provs[0].meta().id,
            ProviderType.CHAT_COMPLETION,
            umo=umo,
        )
        llm_resp = await self.context.llm_generate(
            chat_provider_id=chat_provs[0].meta().id,
            prompt="legacy ping",
        )
        agent_resp = await self.context.tool_loop_agent(
            event=event,
            chat_provider_id=chat_provs[0].meta().id,
            prompt="compute legacy_mul(3, 4)",
            tools=ToolSet([LegacyDynTool()]),
        )
        tts_audio = await tts_provs[0].get_audio("hello legacy tts")
        stt_text = await stt_provs[0].get_text(tts_audio)
        emb_vec = await emb_provs[0].get_embedding("hello embed")
        providers_ok = (
            len(chat_provs) >= 1
            and len(tts_provs) >= 1
            and len(stt_provs) >= 1
            and len(emb_provs) >= 1
            and using_prov is not None
            and bool(llm_resp.completion_text)
            and bool(agent_resp.completion_text)
            and bool(tts_audio)
            and bool(stt_text)
            and bool(emb_vec)
        )

        # 5. ConversationManager + PlatformMessageHistoryManager
        cid = await self.context.conversation_manager.new_conversation(
            umo,
            title="legacy-conv",
        )
        conv_obj = await self.context.conversation_manager.get_conversation(umo, cid)
        convs = await self.context.conversation_manager.get_conversations(umo)
        await self.context.conversation_manager.add_message_pair(
            cid,
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
        )
        await self.context.conversation_manager.update_conversation(
            umo,
            cid,
            title="legacy-conv-2",
        )
        updated_conv = await self.context.conversation_manager.get_conversation(
            umo, cid
        )
        await self.context.conversation_manager.delete_conversation(umo, cid)

        hist_rec = await self.context.message_history_manager.insert(
            platform_id="webchat",
            user_id=umo,
            content={"role": "user", "text": "hist-1"},
            sender_id="user-1",
            sender_name="Moon",
        )
        await self.context.message_history_manager.insert_message_chain(
            platform_id="webchat",
            user_id=umo,
            message_chain=MessageChain().message("hist-2"),
            role="bot",
        )
        hist_cnt = await self.context.message_history_manager.count(
            platform_id="webchat",
            user_id=umo,
        )
        hist_rows = await self.context.message_history_manager.get(
            platform_id="webchat",
            user_id=umo,
        )
        await self.context.message_history_manager.update(
            hist_rec.id,
            content={"role": "user", "text": "hist-1-updated"},
            llm_checkpoint_id="turn-99",
        )
        await self.context.message_history_manager.delete_by_id(hist_rec.id)
        conv_history_ok = (
            conv_obj is not None
            and any(c.cid == cid for c in convs)
            and updated_conv is not None
            and len(json.loads(updated_conv.history)) == 2
            and hist_cnt >= 2
            and len(hist_rows) >= 2
        )

        # 6. Persona live write + UmopConfigRouter
        persona_ok = False
        if self.context.persona_manager.personas_v3:
            self.context.persona_manager.personas_v3[0]["prompt"] = (
                "Updated via isolated legacy plugin"
            )
            await asyncio.sleep(0.05)
            persona_ok = True
        await self.context.astrbot_config_mgr.ucr.update_route(
            "webchat:FriendMessage:legacy_routed",
            "default",
        )
        await self.context.astrbot_config_mgr.ucr.delete_route(
            "webchat:FriendMessage:legacy_routed",
        )

        # 7. KnowledgeBaseManager
        kb_helper = await self.context.kb_manager.create_kb(
            "sdk_demo_kb",
            embedding_provider_id=emb_provs[0].get_provider_id(),
        )
        kb_list = await self.context.kb_manager.list_kbs()
        kb_found = await self.context.kb_manager.get_kb_by_name("sdk_demo_kb")
        kb_deleted = await self.context.kb_manager.delete_kb(kb_helper.kb.kb_id)
        kb_ok = (
            any(k.kb_name == "sdk_demo_kb" for k in kb_list)
            and kb_found is not None
            and bool(kb_deleted)
        )

        # 8. CronJobManager (basic job CRUD + live APScheduler firing back)
        basic_job = await self.context.cron_manager.add_basic_job(
            name="demo_basic_cron",
            cron_expression="*/5 * * * *",
            handler=self._on_cron_tick,
        )
        listed_jobs = await self.context.cron_manager.list_jobs()
        await self.context.cron_manager.delete_job(basic_job.job_id)

        run_at = datetime.now(timezone.utc) + timedelta(seconds=0.15)
        self.context.cron_manager.scheduler.add_job(
            self._on_cron_tick,
            DateTrigger(run_date=run_at),
            kwargs={"tag": "live-fire"},
            id="legacy_live_date_job",
            name="Legacy live date job",
            replace_existing=True,
        )
        await asyncio.wait_for(self._cron_fired.wait(), timeout=5.0)
        cron_ok = (
            any(j.job_id == basic_job.job_id for j in listed_jobs)
            and self._cron_payload.get("tag") == "live-fire"
        )

        # 9. Dynamic FunctionTool + toggle + pending Web API settle
        self.context.register_llm_tool(LegacyDynTool)
        pending = list(getattr(self.context, "_pending", []))
        if pending:
            await asyncio.gather(*pending)
            self.context._pending.clear()
        deact_ok = await self.context.deactivate_llm_tool_async("legacy_dyn_tool")
        act_ok = await self.context.activate_llm_tool_async("legacy_dyn_tool")
        dyn_tools_ok = deact_ok and act_ok

        # 10. HTML T2I, proactive send_message, event actions, and call_action
        img_path = await html_renderer.render_t2i("legacy render")
        await self.context.send_message(
            umo,
            MessageChain().message("legacy-proactive-ok"),
        )
        await event.send_typing()
        await event.react("thumbsup")
        bot_info = await event.bot.api.call_action("get_login_info", echo="ok")
        platform_ok = (
            bool(img_path)
            and isinstance(bot_info, dict)
            and bot_info.get("result", {}).get("echo") == "ok"
        )

        # 11. Isolation boundary check for host-internal deprecated APIs
        isolation_guarded = True
        for forbidden_call in (
            lambda: self.context.register_commands(
                "legacy_main_api_showcase",
                "bad",
                "desc",
                1,
                self.lg_ping,
            ),
            lambda: self.context.get_db(),
        ):
            try:
                forbidden_call()
                isolation_guarded = False
            except Exception as exc:
                if "unavailable in isolated legacy mode" not in str(exc):
                    isolation_guarded = False

        report = {
            "config_ok": config_ok,
            "stars_ok": stars_ok,
            "sp_ok": sp_ok,
            "providers_ok": providers_ok,
            "conv_history_ok": conv_history_ok,
            "persona_ok": persona_ok,
            "kb_ok": kb_ok,
            "cron_ok": cron_ok,
            "dyn_tools_ok": dyn_tools_ok,
            "platform_ok": platform_ok,
            "isolation_guarded": isolation_guarded,
        }
        report["all_passed"] = all(report.values())
        yield event.plain_result(json.dumps(report, sort_keys=True))
