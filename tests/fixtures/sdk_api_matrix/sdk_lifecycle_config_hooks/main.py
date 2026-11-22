"""Dedicated new-SDK plugin covering config, lifecycle, tasks, cron, and hooks."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import Field

from astrbot_sdk import (
    DirectContext,
    MessageEvent,
    Plugin,
    PluginConfig,
    TaskGroup,
    Worker,
    has_native_runtime,
    hooks,
    lifecycle,
    on,
)
from astrbot_sdk.capabilities import CapabilitySet
from astrbot_sdk.config import (
    export_config_schema,
    reject_external_schema_refs,
    schema_has_sensitive_fields,
    validate_config_against_model,
)
from astrbot_sdk.errors import CallScopeRetired
from astrbot_sdk.hooks import (
    LLMRequest,
    LLMResponse,
    MessageResult,
    PluginError,
    ToolCall,
    ToolResult,
)
from astrbot_sdk.message_components import Plain


class LchConfig(PluginConfig):
    """Typed configuration for the lifecycle/config/hooks matrix plugin."""

    secret_key: str = Field(
        default="",
        description="Write-only secret token masked by Host display APIs.",
        json_schema_extra={"writeOnly": True},
    )
    tag: str = Field(default="init", description="Live tag echoed in commands.")
    limit: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Numeric limit validated live.",
    )


class SdkLifecycleConfigHooksPlugin(Plugin[LchConfig]):
    """Exercise Config, Lifecycle, Tasks, Cron, Plugins, DirectContext, and Hooks."""

    config_model = LchConfig

    def __init__(self, context: Any) -> None:
        super().__init__(context)
        self._startup_ok = asyncio.Event()
        self._health_ok = False
        self._shutdown_reason: str | None = None
        self._config_reloads = 0
        self._cron_hits: list[str] = []
        self._cron_done = asyncio.Event()
        self._hook_counts: dict[str, int] = {}
        self._last_error: str | None = None
        self._detached_retired = asyncio.Event()
        self._detached_retired_ok = False

    def _bump(self, name: str) -> None:
        self._hook_counts[name] = self._hook_counts.get(name, 0) + 1

    @lifecycle.startup
    async def on_startup(self) -> None:
        """Exercise ctx.tasks.{spawn, is_shutdown, check_health} and direct_view."""

        async def _boot_task() -> None:
            await asyncio.sleep(0)
            self._startup_ok.set()

        self.ctx.tasks.spawn("lch_boot", _boot_task())
        self.ctx.tasks.check_health()
        assert self.ctx.tasks.is_shutdown is False

    @lifecycle.validate_config
    async def on_validate_config(self, candidate: LchConfig) -> None:
        """Reject limit == 42 to test pre-save Worker config validation."""
        if candidate.limit == 42:
            raise ValueError("limit=42 is rejected by lch validate_config")

    @lifecycle.config_changed
    async def on_config_changed(
        self,
        event: lifecycle.ConfigChangedEvent[LchConfig],
    ) -> None:
        """Track confirmed live configuration changes."""
        _ = event
        self._config_reloads += 1

    @lifecycle.health
    async def on_health(self) -> None:
        """Record health check execution."""
        self._health_ok = True

    @lifecycle.shutdown
    async def on_shutdown(self, event: lifecycle.ShutdownEvent) -> None:
        """Record shutdown event."""
        self._shutdown_reason = event.reason

    @on.service("lch_svc", description="Host-scoped service")
    async def handle_svc(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Serve Host-scoped plugin service calls using Plugin.config property."""
        return {"echo": payload.get("msg"), "tag": self.config.tag}

    @on.direct_service("lch_direct", description="Direct zero-authority service")
    async def handle_direct(
        self,
        payload: dict[str, Any],
        dctx: DirectContext[LchConfig],
    ) -> dict[str, Any]:
        """Serve direct P2P service calls with DirectContext.current_config()."""
        return {
            "direct": payload.get("v"),
            "tag": dctx.current_config().tag,
            "plugin": dctx.plugin.name,
        }

    @hooks.plugin_loaded()
    async def h_loaded(self, info: Any) -> None:
        _ = info
        self._bump("plugin_loaded")

    @hooks.plugin_unloaded()
    async def h_unloaded(self, info: Any) -> None:
        _ = info
        self._bump("plugin_unloaded")

    @hooks.waiting_llm_request()
    async def h_waiting(self, event: MessageEvent | None) -> None:
        _ = event
        self._bump("waiting_llm_request")

    @hooks.llm_request()
    async def h_llm_req(self, event: MessageEvent | None, req: LLMRequest) -> None:
        _ = event
        self._bump("llm_request")
        if "[lch-track]" in (req.prompt or ""):
            req.contexts.clear()
            req.contexts.append({"role": "system", "content": "sys-a"})
            req.contexts.extend(
                [
                    {"role": "user", "content": "usr-b"},
                    {"role": "assistant", "content": "drop"},
                ]
            )
            req.contexts.pop()
            req.contexts.insert(0, {"role": "system", "content": "tmp"})
            req.contexts.remove({"role": "system", "content": "tmp"})
            req.system_prompt = f"{req.system_prompt or ''} [lch-sys]".strip()

    @hooks.llm_response()
    async def h_llm_res(self, event: MessageEvent | None, res: LLMResponse) -> None:
        _ = event
        self._bump("llm_response")
        if "lch-resp" in (res.content or ""):
            res.content = f"{res.content} [lch-resp-mut]"

    @hooks.tool_call()
    async def h_tool_call(self, event: MessageEvent | None, call: ToolCall) -> None:
        _ = event
        self._bump("tool_call")
        if "lch-call" in str(call.args):
            call.args = {**call.args, "mutated": True}

    @hooks.tool_result()
    async def h_tool_res(
        self,
        event: MessageEvent | None,
        result: ToolResult,
    ) -> None:
        _ = event
        self._bump("tool_result")
        if "lch-tool" in (result.content or ""):
            result.content = f"{result.content} [lch-tool-mut]"

    @hooks.agent_start()
    async def h_agent_start(self, event: MessageEvent | None) -> None:
        _ = event
        self._bump("agent_start")

    @hooks.agent_end()
    async def h_agent_end(self, event: MessageEvent | None) -> None:
        _ = event
        self._bump("agent_end")

    @hooks.plugin_error()
    async def h_plugin_error(
        self,
        event: MessageEvent | None,
        err: PluginError,
    ) -> None:
        _ = event
        self._bump("plugin_error")
        self._last_error = f"{err.plugin_name}:{err.handler_name}:{err.error}"

    @hooks.message_result()
    async def h_msg_res(
        self,
        event: MessageEvent | None,
        res: MessageResult,
    ) -> None:
        _ = event
        self._bump("message_result")
        if any("lch-msg" in getattr(seg, "text", "") for seg in res.chain):
            res.chain.append(Plain(" [lch-msg-mut]"))

    @hooks.message_sent()
    async def h_msg_sent(self, event: MessageEvent | None) -> None:
        _ = event
        self._bump("message_sent")

    @on.command("lch retire", description="Verify CallScopeRetired on detached task")
    async def lch_retire(self, event: MessageEvent):
        """Verify captured invocation context retires after handler completes."""
        _ = event
        scoped_ctx = self.ctx

        async def _late_probe() -> None:
            await asyncio.sleep(0.05)
            try:
                await scoped_ctx.plugins.list()
            except CallScopeRetired:
                self._detached_retired_ok = True
            finally:
                self._detached_retired.set()

        asyncio.create_task(_late_probe())
        yield event.reply("retire-scheduled")

    @on.command("lch run", description="Run lifecycle, config, TaskGroup, and cron")
    async def lch_run(self, event: MessageEvent):
        """Exercise Config helpers, TaskGroup, CronClient, Plugins, and Caps."""
        await asyncio.wait_for(self._startup_ok.wait(), timeout=5.0)
        await asyncio.wait_for(self._detached_retired.wait(), timeout=5.0)

        # Config helpers + TaskGroup
        import os

        tmp_pkg = Path(self.ctx.storage.data_dir) / "lch_schema_export"
        os.makedirs(tmp_pkg, exist_ok=True)
        exported = export_config_schema(LchConfig, tmp_pkg)
        schema_obj = json.loads(exported.read_text(encoding="utf-8"))
        reject_external_schema_refs(schema_obj)
        sensitive_ok = schema_has_sensitive_fields(schema_obj) is True
        validated = validate_config_against_model(LchConfig, {"tag": "val", "limit": 9})

        tg = TaskGroup()
        done_val = await tg.run_to_completion(
            "local-commit", asyncio.sleep(0, result="tg-ok")
        )
        await tg.shutdown()

        # CapabilitySet methods & native helper
        cap_set = CapabilitySet.from_ids("storage.kv", "cron.schedule")
        caps_ok = (
            cap_set.has("cron.schedule")
            and cap_set.get("storage.kv") is not None
            and sorted(cap_set.keys()) == ["cron.schedule", "storage.kv"]
            and len(list(cap_set.values())) == 2
            and len(list(cap_set.items())) == 2
        )
        native_flag = has_native_runtime()
        worker_ref_ok = callable(Worker.from_dir)

        # DirectContext + CurrentConfig
        d_view = self.ctx.direct_view()
        cur_cfg = self.ctx.current_config()

        # CronClient full API including remove_scheduler_job
        async def _tick(tag: str = "") -> None:
            self._cron_hits.append(tag)
            if tag == "once-fire":
                self._cron_done.set()

        b_job = await self.ctx.cron.add_basic_job("lch_basic", "*/5 * * * *", _tick)
        listed = await self.ctx.cron.list_jobs()
        await self.ctx.cron.delete_job(str(b_job["job_id"]))

        rem_id = await self.ctx.cron.add_once_job(
            "lch_removed_once",
            datetime.now(UTC) + timedelta(hours=1),
            _tick,
            args=("never",),
        )
        await self.ctx.cron.remove_scheduler_job(rem_id)

        await self.ctx.cron.add_once_job(
            "lch_fire_once",
            datetime.now(UTC) + timedelta(seconds=0.12),
            _tick,
            kwargs={"tag": "once-fire"},
            replace_existing=True,
        )
        await asyncio.wait_for(self._cron_done.wait(), timeout=5.0)

        # PluginRegistryService
        all_plugins = await self.ctx.plugins.list()
        peer = await self.ctx.plugins.get("astrbot/full_api_peer")
        peer_svc = await self.ctx.plugins.call_service(
            "astrbot/full_api_peer",
            "summarize",
            {"topic": "matrix"},
        )
        self.logger.info("lch suite checked %d plugins", len(all_plugins))

        yield event.reply(
            json.dumps(
                {
                    "tag": cur_cfg.tag,
                    "limit": cur_cfg.limit,
                    "direct_tag": d_view.current_config().tag,
                    "reloads": self._config_reloads,
                    "health_ok": self._health_ok,
                    "sensitive_ok": sensitive_ok,
                    "validated_tag": validated.tag,
                    "tg_ok": done_val == "tg-ok" and tg.is_shutdown,
                    "caps_ok": caps_ok,
                    "native_bool": isinstance(native_flag, bool),
                    "worker_ref_ok": worker_ref_ok,
                    "detached_retired_ok": self._detached_retired_ok,
                    "cron_ok": (
                        any(j.get("job_id") == b_job.get("job_id") for j in listed)
                        and self._cron_hits == ["once-fire"]
                    ),
                    "peer_ok": (
                        peer is not None and peer_svc.get("summary") == "peer:matrix"
                    ),
                    "plugin_meta_name": self.ctx.plugin.name,
                    "hooks": dict(self._hook_counts),
                    "last_error": self._last_error,
                },
                sort_keys=True,
            )
        )
