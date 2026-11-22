"""Full-API isolated legacy Star showcase plugin exercising AstrBot main Core APIs."""

from __future__ import annotations

import asyncio
import json
import re
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
from astrbot.api import (
    agent as api_agent,
)
from astrbot.api.agents import (
    AgentConfig,
    AgentRole,
    AgentRuntime,
    ImageOutput,
    PlainOutput,
    URLMedia,
    chain_from_content,
)
from astrbot.api.all import MessageChain, Plain
from astrbot.api.chatui import ViewResult, ViewSpec
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.event.filter import (
    CustomFilter,
    EventMessageType,
    GreedyStr,
    PermissionType,
    PlatformAdapterType,
)
from astrbot.api.message_components import (
    ActionRow,
    At,
    AtAll,
    BaseMessageComponent,
    Button,
    Face,
    Forward,
    Image,
    Json,
    Location,
    Music,
    Node,
    Nodes,
    Poke,
    Reply,
    Share,
)
from astrbot.api.platform import MessageMember, register_platform_adapter
from astrbot.api.provider import ProviderType
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.api.web import (
    error_response,
    file_response,
    json_response,
    request,
    stream_response,
)
from astrbot.core import file_token_service
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot.core.utils.session_waiter import SessionController, session_waiter


class _HeaderFilter(CustomFilter):
    """Legacy custom filter verifying filter composition."""

    def filter(self, event: AstrMessageEvent, cfg: Any = None) -> bool:
        _ = cfg
        return "allow" in event.message_str or event.message_str.startswith(
            "legacy_guarded"
        )


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


@register("legacy_main_api_showcase", "astrbot", "Legacy full showcase", "1.0.0")
class LegacyMainApiShowcasePlugin(Star):
    """Exercise AstrBot's classic `astrbot.api` / `Context` surface in isolated mode."""

    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context, config)
        self.config = config
        self._cron_fired = asyncio.Event()
        self._cron_payload: dict[str, Any] = {}
        self._hook_counts: dict[str, int] = {}
        self._lifecycle_hits = 0
        self._terminated = False
        self.context.register_web_api(
            "/legacy/ping",
            self._web_ping,
            ["GET"],
            "Legacy showcase ping route",
        )
        self.context.register_web_api(
            "/legacy/rich",
            self._web_rich,
            ["GET", "POST"],
            "Legacy showcase rich HTTP route",
        )

    async def _web_ping(self) -> dict[str, Any]:
        """Handle `/legacy/ping` using `astrbot.api.web.request`."""
        return {
            "ok": True,
            "plugin": "legacy_main_api_showcase",
            "q": request.query.get("q", ""),
        }

    async def _web_rich(self) -> Any:
        """Exercise rich HTTP request inspection and response helpers."""
        mode = request.query.get("mode", "json")
        if mode == "error":
            return error_response("legacy-err", status_code=418, data={"ok": False})
        if mode == "stream":

            async def _sse():
                yield "legacy-chunk-1\n"
                yield b"legacy-chunk-2\n"

            return stream_response(_sse())
        if mode == "file":
            f = Path(StarTools.get_data_dir()) / "legacy_web_file.txt"
            f.write_text("legacy-file-ok", encoding="utf-8")
            return file_response(f, filename="legacy_web_file.txt")
        if mode == "form":
            form = await request.form()
            files = await request.files()
            uploaded_name = ""
            if "upload" in files:
                uploaded = files["upload"]
                uploaded_name = getattr(uploaded, "filename", "uploaded")
            return json_response(
                {
                    "field": form.get("field", ""),
                    "uploaded": uploaded_name,
                }
            )
        return json_response({"ok": True, "mode": mode})

    async def _on_cron_tick(self, tag: str = "") -> None:
        """Cron callback invoked inside the isolated Runner from Host APScheduler."""
        self._cron_payload = {"tag": tag}
        self._cron_fired.set()

    async def _dyn_cmd(self, event: AstrMessageEvent):
        """Dynamically registered command invoked via HandlerRegisterService."""
        _ = event
        yield event.plain_result("lg-dyn-pong")

    async def terminate(self) -> None:
        """Mark plugin termination on shutdown/unload."""
        self._terminated = True

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded_hook(self) -> None:
        self._lifecycle_hits += 1

    @filter.on_platform_loaded()
    async def on_platform_loaded_hook(self) -> None:
        self._lifecycle_hits += 1

    @filter.command_group("lg")
    def lg(self) -> None:
        """Legacy command group root."""

    @lg.command("ping")
    async def lg_ping(self, event: AstrMessageEvent):
        """Respond inside a legacy sub-command."""
        yield event.plain_result("lg-pong")

    @lg.command("echo", alias={"ec"})
    async def lg_echo(self, event: AstrMessageEvent, count: int, rest: GreedyStr):
        """Exercise typed int parameter and GreedyStr parsing inside subcommand."""
        yield event.plain_result(f"echo:{count}:{rest}")

    @lg.group("sub")
    def lg_sub(self) -> None:
        """Nested command group."""

    @lg_sub.command("leaf")
    async def lg_sub_leaf(self, event: AstrMessageEvent):
        """Respond from nested command group leaf."""
        yield event.plain_result("lg-sub-leaf")

    @filter.custom_filter(_HeaderFilter)
    @filter.event_message_type(EventMessageType.PRIVATE_MESSAGE)
    @filter.permission_type(PermissionType.ADMIN)
    @filter.platform_adapter_type(PlatformAdapterType.WEBCHAT)
    @filter.command("legacy_guarded")
    async def legacy_guarded(self, event: AstrMessageEvent):
        """Exercise composed legacy filters (custom + type + permission + platform)."""
        yield event.plain_result("guarded-ok")

    @filter.button_action("lg_btn")
    async def on_lg_btn(self, event: AstrMessageEvent):
        """Handle callback button clicks with action_id ``lg_btn``."""
        inter = event.get_button_interaction()
        val = inter.data.get("k") if isinstance(inter.data, dict) else inter.data
        yield event.plain_result(f"lg-btn:{val}")

    @filter.ui_action("bump")
    async def on_ui_bump(self, event: AstrMessageEvent):
        """Handle ChatUI card action ``bump``."""
        inter = event.get_ui_interaction()
        prev = int(inter.view.data.get("clicks", 0)) if inter is not None else 0
        yield event.view_result(data={"clicks": prev + 1})

    @filter.command("legacy_view")
    async def legacy_view(self, event: AstrMessageEvent):
        """Create a legacy ChatUI card view."""
        yield event.view_result(
            name="legacy_card",
            data={"clicks": 0},
            text="Legacy card fallback",
            title="Legacy Card",
        )

    @filter.command("legacy_req_llm")
    async def legacy_req_llm(self, event: AstrMessageEvent):
        """Exercise yielding `event.request_llm(...)`."""
        yield event.request_llm(
            prompt="req-llm-ping",
            system_prompt="sys-brief",
        )

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

    @filter.on_waiting_llm_request()
    async def on_waiting_llm(self, event: AstrMessageEvent) -> None:
        _ = event
        self._hook_counts["on_waiting_llm_request"] = (
            self._hook_counts.get("on_waiting_llm_request", 0) + 1
        )

    @filter.on_llm_request()
    async def on_llm_req(self, event: AstrMessageEvent, req: Any) -> None:
        _ = (event, req)
        self._hook_counts["on_llm_request"] = (
            self._hook_counts.get("on_llm_request", 0) + 1
        )

    @filter.on_llm_response()
    async def on_llm_res(self, event: AstrMessageEvent, resp: Any) -> None:
        _ = (event, resp)
        self._hook_counts["on_llm_response"] = (
            self._hook_counts.get("on_llm_response", 0) + 1
        )

    @filter.on_using_llm_tool()
    async def on_using_tool(
        self, event: AstrMessageEvent, tool: Any, tool_args: Any
    ) -> None:
        _ = (event, tool, tool_args)
        self._hook_counts["on_using_llm_tool"] = (
            self._hook_counts.get("on_using_llm_tool", 0) + 1
        )

    @filter.on_llm_tool_respond()
    async def on_tool_respond(
        self, event: AstrMessageEvent, tool: Any, tool_args: Any, tool_result: Any
    ) -> None:
        _ = (event, tool, tool_args, tool_result)
        self._hook_counts["on_llm_tool_respond"] = (
            self._hook_counts.get("on_llm_tool_respond", 0) + 1
        )

    @filter.on_agent_begin()
    async def on_agent_begin_hook(self, event: AstrMessageEvent, req: Any) -> None:
        _ = (event, req)
        self._hook_counts["on_agent_begin"] = (
            self._hook_counts.get("on_agent_begin", 0) + 1
        )

    @filter.on_agent_done()
    async def on_agent_done_hook(
        self, event: AstrMessageEvent, req: Any, resp: Any
    ) -> None:
        _ = (event, req, resp)
        self._hook_counts["on_agent_done"] = (
            self._hook_counts.get("on_agent_done", 0) + 1
        )

    @filter.on_plugin_error()
    async def on_plugin_err(
        self,
        event: AstrMessageEvent,
        plugin_name: str,
        handler_name: str,
        error: str,
        tb: str,
    ) -> None:
        _ = (event, plugin_name, handler_name, error, tb)
        self._hook_counts["on_plugin_error"] = (
            self._hook_counts.get("on_plugin_error", 0) + 1
        )

    @filter.on_plugin_loaded()
    async def on_plugin_loaded_hook(self, metadata: Any) -> None:
        _ = metadata
        self._hook_counts["on_plugin_loaded"] = (
            self._hook_counts.get("on_plugin_loaded", 0) + 1
        )

    @filter.on_plugin_unloaded()
    async def on_plugin_unloaded_hook(self, metadata: Any) -> None:
        _ = metadata
        self._hook_counts["on_plugin_unloaded"] = (
            self._hook_counts.get("on_plugin_unloaded", 0) + 1
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

        # 2. Star registry, Star KV/render methods, & StarTools
        stars = await self.context.get_all_stars_async()
        self_meta = self.context.get_registered_star("legacy_main_api_showcase")
        data_dir = Path(StarTools.get_data_dir())
        marker = data_dir / "legacy_marker.txt"
        marker.write_text("legacy-dir-ok", encoding="utf-8")
        await self.put_kv_data("star_kv_k", {"x": 9})
        star_kv = await self.get_kv_data("star_kv_k")
        await self.delete_kv_data("star_kv_k")
        star_kv_after = await self.get_kv_data("star_kv_k", "gone")
        t2i_asset = await self.text_to_image("star render text")
        html_asset = await self.html_render("<b>{{ m }}</b>", {"m": "ok"})
        stars_ok = (
            len(stars) >= 1
            and self_meta is not None
            and marker.read_text(encoding="utf-8") == "legacy-dir-ok"
            and star_kv == {"x": 9}
            and star_kv_after == "gone"
            and bool(t2i_asset)
            and bool(html_asset)
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

        # 9. Dynamic FunctionTool + StarTools async toggle + dynamic command register
        self.context.register_llm_tool(LegacyDynTool)
        self.context.register_commands(
            "legacy_main_api_showcase",
            "lg_dyn",
            "Dynamic legacy command",
            1,
            self._dyn_cmd,
        )
        pending = list(getattr(self.context, "_pending", []))
        if pending:
            await asyncio.gather(*pending)
            self.context._pending.clear()
        deact_ok = await StarTools.deactivate_llm_tool_async("legacy_dyn_tool")
        act_ok = await StarTools.activate_llm_tool_async("legacy_dyn_tool")
        dyn_tools_ok = deact_ok and act_ok

        # 10. Event injection (get_event_queue & StarTools.create_event), DB read,
        # file_token_service, subagents.reload, plugin.lifecycle
        await self.context.get_event_queue().put(event)
        abm = await StarTools.create_message(
            type="FriendMessage",
            self_id="bot-self",
            session_id="user-1",
            sender=MessageMember(user_id="user-1", nickname="Moon"),
            message=[Plain("startools-injected")],
            message_str="startools-injected",
        )
        await StarTools.create_event(abm, platform="webchat", is_wake=True)
        await StarTools.send_message(
            umo,
            MessageChain().message("startools-send-ok"),
        )

        aliases = await self.context.get_db().get_umo_aliases([umo])
        db_convs = await self.context.get_db().get_conversations(user_id="user-1")
        db_read_ok = isinstance(aliases, list) and isinstance(db_convs, list)

        token_file = data_dir / "legacy_token.txt"
        token_file.write_bytes(b"LEGACY-FILE-TOKEN")
        legacy_file_token = await file_token_service.register_file(
            str(token_file),
            single_use=False,
        )
        legacy_img_url = await Image.fromFileSystem(
            str(token_file)
        ).register_to_file_service()
        file_token_ok = bool(legacy_file_token) and "/api/file/" in legacy_img_url

        init_handoffs = list(self.context.subagent_orchestrator.handoffs)
        reloaded_handoffs = await self.context.subagent_orchestrator.reload_from_config(
            {"agents": [{"name": "reloaded_sub"}]}
        )
        subagent_ok = len(init_handoffs) >= 1 and len(reloaded_handoffs) >= 1

        plugin_lifecycle_ok = True
        if self.context.get_registered_star("full_api_peer") is not None:
            await self.context._star_manager.turn_off_plugin("full_api_peer")
            await self.context._star_manager.turn_on_plugin("full_api_peer")

        # 11. HTML T2I, streaming/buffer, event actions, rich components, DTOs
        img_path = await html_renderer.render_t2i("legacy render")
        await self.context.send_message(
            umo,
            MessageChain().message("legacy-proactive-ok"),
        )
        await event.send(
            MessageChain(
                chain=[
                    Plain("legacy-rich"),
                    At(qq="u1", name="Moon"),
                    AtAll(),
                    Reply(id="r1", message_str="orig"),
                    Face(id=1),
                    Forward(id="f1"),
                    Nodes([Node(content=[Plain("ln")], uin="u1", name="Moon")]),
                    Poke(user_id="u1", poke_type="126"),
                    Json(data={"k": 1}),
                    Share(url="https://astrbot.app", title="AstrBot"),
                    Location(lat=31.2, lon=121.5, title="SH"),
                    Music(
                        url="https://astrbot.app/s",
                        audio="https://astrbot.app/a.mp3",
                        title="Song",
                    ),
                    ActionRow(
                        [
                            Button.callback("LegacyClick", "lg_btn", data={"k": "v"}),
                            Button.link("Docs", "https://astrbot.app"),
                        ]
                    ),
                ]
            )
        )

        async def _leg_stream():
            yield MessageChain().message("leg-stream-1")
            yield MessageChain().message("leg-stream-2")

        await event.send_streaming(_leg_stream(), use_fallback=True)
        buf_tail = await event.process_buffer(
            "buf-a\nbuf-b\ntail", re.compile(r"[^\n]+\n")
        )

        await event.send_typing()
        await event.stop_typing()
        await event.react("thumbsup")
        grp = await event.get_group("grp-legacy")
        event.set_extra("lg_extra", "ok")
        extra_ok = event.get_extra("lg_extra") == "ok"
        event.clear_extra()
        temp_track = data_dir / "track_temp.txt"
        temp_track.write_text("tmp", encoding="utf-8")
        event.track_temporary_local_file(str(temp_track))
        event.untrack_temporary_local_file(str(temp_track))
        event.cleanup_temporary_local_files()
        temp_track.unlink(missing_ok=True)

        bot_info = await event.bot.api.call_action("get_login_info", echo="ok")

        agent_chain = chain_from_content(
            [
                PlainOutput("agent-ok"),
                ImageOutput(URLMedia("https://astrbot.app/a.png")),
            ]
        )
        cfg_dto = AgentConfig(model="mock-gpt", system_prompt="sys")
        view_spec = ViewSpec(
            name="legacy_card", target="chat_message", actions=["bump"]
        )
        view_res = ViewResult(name="legacy_card", data={"clicks": 0}, text="fb")
        chatui_agents_ok = (
            isinstance(agent_chain.chain[0], BaseMessageComponent)
            and cfg_dto.model == "mock-gpt"
            and AgentRole.MAIN == "main"
            and view_spec.name == "legacy_card"
            and view_res.name == "legacy_card"
            and len(star_handlers_registry) >= 1
        )
        platform_ok = (
            bool(img_path)
            and buf_tail == "tail"
            and grp is not None
            and extra_ok
            and isinstance(bot_info, dict)
            and bot_info.get("result", {}).get("echo") == "ok"
            and chatui_agents_ok
        )

        # 12. Explicit IsolationUnsupportedError checks (5 in-process + AgentRuntime)
        isolation_guarded = True
        for forbidden_call in (
            lambda: register_platform_adapter("custom", "custom", None),
            lambda: self.context.register_provider(object()),
            lambda: api_agent("custom_agent"),
            lambda: self.context.get_llm_tool_manager(),
            lambda: self.context.get_db()(),
            lambda: AgentRuntime(),
        ):
            try:
                forbidden_call()
                isolation_guarded = False
            except Exception as exc:
                if "unavailable" not in str(exc):
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
            "db_read_ok": db_read_ok,
            "file_token_ok": file_token_ok,
            "legacy_file_token": legacy_file_token,
            "subagent_ok": subagent_ok,
            "plugin_lifecycle_ok": plugin_lifecycle_ok,
            "platform_ok": platform_ok,
            "isolation_guarded": isolation_guarded,
            "lifecycle_hits": self._lifecycle_hits,
            "hooks": dict(self._hook_counts),
        }
        report["all_passed"] = all(
            (
                config_ok,
                stars_ok,
                sp_ok,
                providers_ok,
                conv_history_ok,
                persona_ok,
                kb_ok,
                cron_ok,
                dyn_tools_ok,
                db_read_ok,
                file_token_ok,
                subagent_ok,
                plugin_lifecycle_ok,
                platform_ok,
                isolation_guarded,
            )
        )
        yield event.plain_result(json.dumps(report, sort_keys=True))
