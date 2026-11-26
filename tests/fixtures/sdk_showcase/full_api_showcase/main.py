"""Full-API modern SDK showcase exercising `astrbot_sdk` capabilities and hooks."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from astrbot_sdk import (
    MessageEvent,
    Plugin,
    PluginConfig,
    SenderSessionFilter,
    hooks,
    lifecycle,
    on,
)
from astrbot_sdk.conversations import (
    AudioPart,
    ConversationPatch,
    ImagePart,
    Message,
    TextPart,
)
from astrbot_sdk.hooks import (
    LLMRequest,
    LLMResponse,
    MessageResult,
    ToolCall,
    ToolResult,
)
from astrbot_sdk.llm import AgentRequest, ProviderKind
from astrbot_sdk.message_components import (
    ActionRow,
    At,
    AtAll,
    Button,
    Face,
    Forward,
    Image,
    Json,
    Location,
    Music,
    Node,
    Nodes,
    Plain,
    Poke,
    Reply,
    Share,
)
from astrbot_sdk.messages import MessageChain
from astrbot_sdk.tools import Tool, ToolCallContext, ToolDefinition
from astrbot_sdk.web import (
    error_response,
    file_response,
    json_response,
    stream_response,
)


class ShowcaseConfig(PluginConfig):
    """Typed configuration for the full API showcase plugin."""

    api_token: str = Field(
        default="",
        description="Write-only secret token",
        json_schema_extra={"writeOnly": True},
    )
    greeting_prefix: str = Field(
        default="SDK",
        description="Prefix returned by handlers",
    )
    max_items: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Upper limit validated by schema and hook",
    )


class RuntimeEchoTool(Tool):
    """Self-contained dynamic tool registered via `ctx.tools.update_runtime_tools`."""

    name = "runtime_echo"
    description = "Echo a tag from runtime tool"

    async def call(self, tag: Annotated[str, "Tag string"] = "ok") -> str:
        """Return an echoed tag string."""
        return f"runtime-echo:{tag}"


class FullApiShowcasePlugin(Plugin[ShowcaseConfig]):
    """Exercise every capability, web, view, tool, and hook API in `astrbot_sdk`."""

    config_model = ShowcaseConfig

    def __init__(self, context: Any) -> None:
        super().__init__(context)
        self._startup_task_done = asyncio.Event()
        self._health_checked = False
        self._shutdown_reason: str | None = None
        self._config_reloaded_count = 0
        self._hook_counts: dict[str, int] = {}
        self._cron_fired = asyncio.Event()
        self._cron_tag = ""

        @self.ctx.web.route(
            "/showcase/echo/<topic>",
            methods=["GET", "POST"],
            description="Echo showcase web route",
        )
        async def echo_route(req: Any, topic: str) -> Any:
            body = (await req.body()).decode("utf-8")
            mode = req.query.get("mode", "json")
            if mode == "error":
                return error_response(
                    "showcase-err", status_code=418, data={"topic": topic}
                )
            if mode == "stream":

                async def _sse():
                    yield "data: part-1\n\n"
                    yield b"data: part-2\n\n"

                return stream_response(_sse())
            if mode == "file":
                sample_file = Path(self.ctx.storage.data_dir) / "web_sample.txt"
                sample_file.parent.mkdir(parents=True, exist_ok=True)
                sample_file.write_text("file-route-ok", encoding="utf-8")
                return file_response(sample_file, filename="web_sample.txt")
            return json_response(
                {
                    "topic": topic,
                    "q": req.query.get("q", ""),
                    "method": req.method,
                    "body": body,
                    "prefix": self.ctx.current_config().greeting_prefix,
                }
            )

    def _bump_hook(self, stage: str) -> None:
        self._hook_counts[stage] = self._hook_counts.get(stage, 0) + 1

    @lifecycle.startup
    async def on_startup(self) -> None:
        """Spawn a background task via `ctx.tasks.spawn` during startup."""

        async def _bg_job() -> None:
            await asyncio.sleep(0)
            self._startup_task_done.set()

        self.ctx.tasks.spawn("showcase_startup_bg", _bg_job())

    @lifecycle.validate_config
    async def on_validate_config(self, candidate: ShowcaseConfig) -> None:
        """Reject reserved `max_items == 49` before persisting config."""
        if candidate.max_items == 49:
            raise ValueError("max_items=49 is reserved by plugin policy")

    @lifecycle.config_changed
    async def on_config_changed(
        self,
        event: lifecycle.ConfigChangedEvent[ShowcaseConfig],
    ) -> None:
        """Track live reconfigurations."""
        _ = event
        self._config_reloaded_count += 1

    @lifecycle.health
    async def on_health(self) -> None:
        """Record health check execution."""
        self._health_checked = True

    @lifecycle.shutdown
    async def on_shutdown(self, event: lifecycle.ShutdownEvent) -> None:
        """Record shutdown reason for diagnostics."""
        self._shutdown_reason = event.reason

    @on.tool(name="showcase_add", description="Add two integers")
    async def showcase_add(
        self,
        call: ToolCallContext,
        a: Annotated[int, "First operand"],
        b: Annotated[int, "Second operand"],
    ) -> str:
        """Add two integers within an authorized ToolCallContext."""
        _ = call
        return str(a + b)

    @on.streaming_tool(
        name="showcase_stream_echo",
        description="Streaming-input echo tool",
    )
    async def showcase_stream_echo(
        self,
        call: ToolCallContext,
        text: Annotated[str, "Text payload"],
    ) -> str:
        """Echo streamed input arguments."""
        _ = call
        return f"stream-tool:{text}"

    @on.tool_discovery
    async def discover_tools(self) -> list[ToolDefinition]:
        """Expose a discovered dynamic tool catalog."""

        async def _discovered(call: ToolCallContext, note: str = "hi") -> str:
            _ = call
            return f"discovered:{note}"

        self.ctx._register_dynamic_tool("tool:discovered_ping", _discovered)
        return [
            ToolDefinition(
                name="discovered_ping",
                description="Discovered dynamic showcase tool",
            )
        ]

    @hooks.plugin_loaded()
    async def on_plugin_loaded(self, info: Any) -> None:
        _ = info
        self._bump_hook("plugin_loaded")

    @hooks.plugin_unloaded()
    async def on_plugin_unloaded(self, info: Any) -> None:
        _ = info
        self._bump_hook("plugin_unloaded")

    @hooks.waiting_llm_request()
    async def on_waiting_llm_request(self, event: MessageEvent | None) -> None:
        _ = event
        self._bump_hook("waiting_llm_request")

    @hooks.llm_request()
    async def on_llm_request(self, event: MessageEvent | None, req: LLMRequest) -> None:
        _ = event
        self._bump_hook("llm_request")
        if "[hook-test]" in (req.prompt or "") or "[hook-test]" in (
            req.system_prompt or ""
        ):
            req.system_prompt = f"{req.system_prompt or ''} [hook-llm-req]".strip()

    @hooks.llm_response()
    async def on_llm_response(
        self,
        event: MessageEvent | None,
        res: LLMResponse,
    ) -> None:
        _ = (event, res)
        self._bump_hook("llm_response")

    @hooks.tool_call()
    async def on_tool_call(self, event: MessageEvent | None, call: ToolCall) -> None:
        _ = (event, call)
        self._bump_hook("tool_call")

    @hooks.tool_result()
    async def on_tool_result(
        self,
        event: MessageEvent | None,
        result: ToolResult,
    ) -> None:
        _ = (event, result)
        self._bump_hook("tool_result")

    @hooks.agent_start()
    async def on_agent_start(self, event: MessageEvent | None) -> None:
        _ = event
        self._bump_hook("agent_start")

    @hooks.agent_end()
    async def on_agent_end(self, event: MessageEvent | None) -> None:
        _ = event
        self._bump_hook("agent_end")

    @hooks.plugin_error()
    async def on_plugin_error(
        self,
        event: MessageEvent | None,
        error: Any,
    ) -> None:
        _ = (event, error)
        self._bump_hook("plugin_error")

    @hooks.message_result()
    async def on_message_result(
        self,
        event: MessageEvent | None,
        res: MessageResult,
    ) -> None:
        _ = event
        self._bump_hook("message_result")
        if any("[hook-test]" in getattr(seg, "text", "") for seg in res.chain):
            res.chain.append(Plain(" [hook-msg-res]"))

    @hooks.message_sent()
    async def on_message_sent(self, event: MessageEvent | None) -> None:
        _ = event
        self._bump_hook("message_sent")

    @on.message(regex=r"^#sdk-ping$", priority=5)
    async def regex_ping(self, event: MessageEvent):
        """Respond to regex trigger using confirmed live config."""
        cfg = self.ctx.current_config()
        yield event.reply(f"{cfg.greeting_prefix}:pong:{cfg.max_items}")

    @on.button_action("sdk_approve")
    async def on_sdk_approve(self, event: MessageEvent):
        """Handle callback button clicks matching action_id ``sdk_approve``."""
        inter = event.button_interaction
        item = inter.data.get("item") if isinstance(inter.data, dict) else inter.data
        yield event.reply(f"btn-approved:{item}")

    @on.ui_action("refresh")
    async def on_refresh_card(self, event: MessageEvent):
        """Handle authenticated ChatUI card refresh interactions."""
        inter = event.ui_interaction
        prev = int(inter.view.data.get("count", 0)) if inter is not None else 0
        yield event.view_result(data={"count": prev + 1})

    @on.command("showcase view")
    async def showcase_view(self, event: MessageEvent):
        """Create an interactive ChatUI message card view."""
        yield event.view_result(
            name="card",
            data={"count": 1},
            text="SDK card fallback",
            title="SDK Card",
        )

    @on.command("showcase dialog")
    async def showcase_dialog(self, event: MessageEvent):
        """Exercise multi-turn `ctx.sessions.wait` with SenderSessionFilter."""
        async with self.ctx.sessions.wait(
            event,
            filter=SenderSessionFilter(),
            timeout=10.0,
        ) as wait:
            reply_ev = await wait.ask("ask-next")
            yield event.reply(f"dialog:{reply_ev.text}")

    @on.command("showcase suite")
    async def showcase_suite(self, event: MessageEvent):
        """Exercise every capability family against AstrBot Host services."""
        await asyncio.wait_for(self._startup_task_done.wait(), timeout=5.0)
        cfg = self.ctx.current_config()

        # 1. Storage KV + runner data_dir
        await self.ctx.storage.set("showcase_key", {"n": 42})
        kv_val = await self.ctx.storage.get("showcase_key")
        await self.ctx.storage.delete("showcase_key")
        kv_after_del = await self.ctx.storage.get("showcase_key", "missing")
        note_path = Path(self.ctx.storage.data_dir) / "showcase_note.txt"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text("local-ok", encoding="utf-8")
        storage_ok = (
            kv_val == {"n": 42}
            and kv_after_del == "missing"
            and note_path.read_text(encoding="utf-8") == "local-ok"
        )

        # 2. Assets upload, download & file_token_service download token
        payload_bytes = b"PNG-SHOWCASE-PAYLOAD"
        uploaded = await self.ctx.assets.upload(
            payload_bytes,
            filename="showcase.png",
            media_type="image/png",
        )
        downloaded_path = await self.ctx.assets.download(uploaded)
        file_token = await self.ctx.assets.issue_download_token(
            b"TOKEN-PAYLOAD",
            filename="token.txt",
            single_use=False,
        )
        try:
            assets_ok = downloaded_path.read_bytes() == payload_bytes
        finally:
            downloaded_path.unlink(missing_ok=True)

        # 3. Proactive outbound messages (media + all rich segments)
        await self.ctx.messages.send(
            event.umo,
            MessageChain(Plain("proactive-sdk-ok"), Image(source=uploaded)),
        )
        await self.ctx.messages.send(
            event.umo,
            MessageChain(
                Plain("rich-sdk"),
                At(user_id="u1", name="Moon"),
                AtAll(),
                Reply(id="m1", text="q"),
                Face(id=1),
                Forward(id="f1"),
                Nodes([Node(sender_id="u1", content=[Plain("n")])]),
                Poke(poke_type="126", user_id="u1"),
                Json(data={"k": 1}),
                Share(url="https://astrbot.app", title="AstrBot"),
                Location(lat=31.2, lon=121.5, title="SH"),
                Music(
                    music_type="custom",
                    url="https://astrbot.app/s",
                    audio="https://astrbot.app/a.mp3",
                    title="Song",
                ),
                ActionRow(
                    [
                        Button.callback("Approve", "sdk_approve", data={"item": "x"}),
                        Button.link("Docs", "https://astrbot.app"),
                    ]
                ),
            ),
        )

        # 4. Conversations full CRUD + multimodal parts
        created = await self.ctx.conversations.create(
            event.umo,
            title="t1",
            messages=(
                Message(
                    role="user",
                    content=(
                        TextPart("hello"),
                        ImagePart(source="https://astrbot.app/a.png"),
                        AudioPart(source="https://astrbot.app/a.wav"),
                    ),
                ),
            ),
        )
        cur = await self.ctx.conversations.current(event.umo)
        fetched = await self.ctx.conversations.get(event.umo, created.id)
        listed = await self.ctx.conversations.list(event.umo)
        await self.ctx.conversations.append(
            event.umo,
            created.id,
            (Message(role="assistant", content="world"),),
        )
        updated = await self.ctx.conversations.update(
            event.umo,
            created.id,
            ConversationPatch(title="t2"),
        )
        await self.ctx.conversations.set_current(event.umo, created.id)
        await self.ctx.conversations.delete(event.umo, created.id)
        after_del = await self.ctx.conversations.get(event.umo, created.id)
        convs_ok = (
            cur is not None
            and cur.id == created.id
            and fetched is not None
            and any(item.id == created.id for item in listed.items)
            and updated.title == "t2"
            and len(updated.messages) == 2
            and after_del is None
        )

        # 5. Event state, typing/react/group/call_llm, streaming & raw platform action
        await self.ctx.events.set_call_llm(event, False)
        await self.ctx.events.send_typing(event)
        await self.ctx.events.stop_typing(event)
        await self.ctx.events.react(event, "rocket")
        grp_info = await self.ctx.events.get_group(event, group_id="grp-1")

        async def _sdk_stream():
            yield "sdk-stream-1"
            yield Plain("sdk-stream-2")

        await self.ctx.messages.send_streaming(event, _sdk_stream(), use_fallback=True)
        raw_res = await self.ctx.platforms.call_action(
            "webchat", "sdk_raw_ping", ping=1
        )
        events_platform_ok = (
            grp_info is not None
            and grp_info.get("group_id") == "grp-1"
            and isinstance(raw_res, dict)
            and raw_res.get("ping") == 1
        )

        # 6. Cron, KnowledgeBase, & MessageHistory Host services
        async def _sdk_cron_cb(tag: str = "") -> None:
            self._cron_tag = tag
            self._cron_fired.set()

        basic_job = await self.ctx.cron.add_basic_job(
            "sdk_basic_job",
            "*/5 * * * *",
            _sdk_cron_cb,
        )
        listed_jobs = await self.ctx.cron.list_jobs()
        await self.ctx.cron.delete_job(str(basic_job["job_id"]))
        await self.ctx.cron.add_once_job(
            "sdk_once_job",
            datetime.now(UTC) + timedelta(seconds=0.15),
            _sdk_cron_cb,
            kwargs={"tag": "sdk-cron-ok"},
            replace_existing=True,
        )
        await asyncio.wait_for(self._cron_fired.wait(), timeout=5.0)
        cron_ok = (
            any(j.get("job_id") == basic_job.get("job_id") for j in listed_jobs)
            and self._cron_tag == "sdk-cron-ok"
        )

        emb_provs = await self.ctx.llm.list_providers(ProviderKind.EMBEDDING)
        kb_rec = await self.ctx.kb.create(
            "sdk_modern_kb",
            embedding_provider_id=emb_provs[0].id,
        )
        kb_list = await self.ctx.kb.list()
        kb_by_id = await self.ctx.kb.get(str(kb_rec["kb_id"]))
        kb_by_name = await self.ctx.kb.get_by_name("sdk_modern_kb")
        kb_del = await self.ctx.kb.delete(str(kb_rec["kb_id"]))
        kb_ok = (
            any(k.get("kb_id") == kb_rec.get("kb_id") for k in kb_list)
            and kb_by_id is not None
            and kb_by_name is not None
            and kb_del is True
        )

        hist_rec = await self.ctx.history.insert(
            "webchat",
            "sdk_hist_u1",
            {"role": "user", "text": "sdk-h1"},
            sender_id="sdk_hist_u1",
        )
        await self.ctx.history.insert_chain(
            "webchat",
            "sdk_hist_u1",
            "sdk-h2",
            role="bot",
        )
        hist_cnt = await self.ctx.history.count("webchat", "sdk_hist_u1")
        hist_rows = await self.ctx.history.get("webchat", "sdk_hist_u1")
        await self.ctx.history.update(
            int(hist_rec["id"]),
            content={"role": "user", "text": "sdk-h1-upd"},
        )
        await self.ctx.history.delete_by_id(int(hist_rec["id"]))
        history_ok = hist_cnt >= 2 and len(hist_rows) >= 2

        # 7. Plugin inspection + host-scoped & direct peer services
        all_plugins = await self.ctx.plugins.list()
        peer_info = await self.ctx.plugins.get("astrbot/full_api_peer")
        svc_res = await self.ctx.plugins.call_service(
            "astrbot/full_api_peer",
            "summarize",
            {"topic": "all-apis"},
        )
        direct_res = await self.ctx.plugins.call_service(
            "astrbot/full_api_peer",
            "fast_tag",
            {"text": "clean"},
        )
        plugins_ok = (
            len(all_plugins) >= 2
            and peer_info is not None
            and svc_res.get("summary") == "peer:all-apis"
            and direct_res.get("tag") == "[full_api_peer] clean"
        )

        # 8. Render HTML & text to image assets
        html_asset = await self.ctx.render.html(
            "<h1>{{ title }}</h1>",
            {"title": "Hi"},
        )
        text_asset = await self.ctx.render.text("hello render")
        html_dl = await self.ctx.assets.download(html_asset)
        text_dl = await self.ctx.assets.download(text_asset)
        try:
            render_ok = len(html_dl.read_bytes()) > 0 and len(text_dl.read_bytes()) > 0
        finally:
            html_dl.unlink(missing_ok=True)
            text_dl.unlink(missing_ok=True)

        # 9. Dynamic tools: register/unregister + update_runtime_tools
        async def dyn_temp(call: ToolCallContext, item: str = "x") -> str:
            _ = call
            return f"temp:{item}"

        temp_ref = await self.ctx.tools.register(dyn_temp)
        await self.ctx.tools.unregister(temp_ref)
        runtime_refs = await self.ctx.tools.update_runtime_tools([RuntimeEchoTool()])
        tools_ok = [ref.name for ref in runtime_refs] == ["runtime_echo"]

        # 10. LLM providers, generate, stream, embed, TTS/STT, and agent loop
        chat_providers = await self.ctx.llm.list_providers(ProviderKind.CHAT)
        cur_provider = await self.ctx.llm.current_provider(ProviderKind.CHAT)
        gen_res = await self.ctx.llm.generate("ping-chat", system_prompt="be brief")
        stream_chunks = [
            chunk.delta async for chunk in self.ctx.llm.stream("ping-stream")
        ]
        embed_res = await self.ctx.llm.embed(("alpha", "beta"))
        audio_ref = await self.ctx.llm.synthesize("hello tts")
        transcript = await self.ctx.llm.transcribe(audio_ref)
        agent_res = await self.ctx.llm.run_agent(
            AgentRequest(
                input="compute showcase_add(6, 7)",
                tools=("showcase_add", "runtime_echo"),
            )
        )
        llm_ok = (
            len(chat_providers) >= 1
            and cur_provider is not None
            and bool(gen_res.content)
            and "".join(stream_chunks) != ""
            and len(embed_res.embeddings) == 2
            and bool(transcript.text)
            and bool(agent_res.text)
        )

        report = {
            "pid": os.getpid(),
            "prefix": cfg.greeting_prefix,
            "max_items": cfg.max_items,
            "config_reloaded": self._config_reloaded_count,
            "storage_ok": storage_ok,
            "assets_ok": assets_ok,
            "file_token": file_token,
            "file_token_ok": bool(file_token),
            "convs_ok": convs_ok,
            "events_platform_ok": events_platform_ok,
            "cron_ok": cron_ok,
            "kb_ok": kb_ok,
            "history_ok": history_ok,
            "plugins_ok": plugins_ok,
            "render_ok": render_ok,
            "tools_ok": tools_ok,
            "llm_ok": llm_ok,
            "agent_text": agent_res.text,
            "hooks": dict(self._hook_counts),
        }
        report["all_passed"] = all(
            (
                storage_ok,
                assets_ok,
                bool(file_token),
                convs_ok,
                events_platform_ok,
                cron_ok,
                kb_ok,
                history_ok,
                plugins_ok,
                render_ok,
                tools_ok,
                llm_ok,
            )
        )
        yield event.reply(json.dumps(report, sort_keys=True))
