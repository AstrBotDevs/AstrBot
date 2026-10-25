"""Asynchronous delegation implemented with the public plugin lifecycle."""

from __future__ import annotations

import asyncio
import copy

from pydantic import TypeAdapter, ValidationError

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.api.web import error_response, json_response, request
from astrbot.core.agent.message import dump_messages_with_checkpoints
from astrbot.core.agent.tool import ToolSet
from astrbot.core.utils.active_event_registry import active_event_registry

from .context import SubAgentContext
from .execution import SubAgentExecutor
from .templates import ExpertDefinition, SubAgentOrchestrator
from .tools import (
    SUBAGENT_TOOL_NAMES,
    CancelAgentTool,
    GetAgentResultTool,
    ListAgentsTool,
    SendAgentMessageTool,
    SpawnAgentTool,
    WaitAgentTool,
)

if not hasattr(filter, "on_agent_step_end"):
    raise RuntimeError("This plugin requires the Agent lifecycle SDK update.")


class Main(Star):
    """Own expert settings, worker scheduling, persistence, and monitoring."""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context, config)
        self.config = config
        self._expert_settings_lock = asyncio.Lock()
        self.orchestrator = SubAgentOrchestrator(
            context.get_llm_tool_manager(), context.persona_manager, context.get_db()
        )
        self.spawn_tool = SpawnAgentTool([])
        # Register before the loader restores per-tool activation on reload.
        self.context.add_llm_tools(
            self.spawn_tool,
            ListAgentsTool(),
            WaitAgentTool(),
            GetAgentResultTool(),
            SendAgentMessageTool(),
            CancelAgentTool(),
        )

    def _refresh_spawn_tool(self) -> None:
        """Refresh expert and provider choices while retaining tool activation."""
        configured = SpawnAgentTool(
            self.orchestrator.templates, providers=self.context.get_all_providers()
        )
        self.spawn_tool.templates = configured.templates
        self.spawn_tool.description = configured.description
        self.spawn_tool.parameters = configured.parameters

    async def initialize(self):
        """Load templates and recover persisted workers after tool binding."""
        await self.orchestrator.reload_from_config(self.config)
        self._refresh_spawn_tool()
        self.context.register_web_api(
            "/astrbot_plugin_subagent/runtime",
            self.runtime_view,
            ["GET"],
            "Read-only worker progress",
        )
        self.context.register_web_api(
            "/astrbot_plugin_subagent/experts",
            self.expert_settings,
            ["GET", "POST"],
            "Manage expert templates",
        )
        store = self.orchestrator.store
        store.settings = self.config
        store.scheduler = self.orchestrator.scheduler
        await store.recover(self.context)

    @filter.on_llm_request()
    async def prepare_request(self, event, req):
        """Expose delegation controls without removing any of main's tools."""
        wakeup = event.get_extra("_subagent_wakeup")
        if wakeup is not None:
            scope = (
                event.unified_msg_origin,
                getattr(req.conversation, "cid", None),
                str(event.get_sender_id()),
            )
            runtime = self.orchestrator.store.runtimes.get(tuple(wakeup))
            if runtime is not None:
                runtime.wakeup_queued = False
            if (
                tuple(wakeup) != scope
                or runtime is None
                or not runtime._pending_results
                or active_event_registry.get_background_stop_signal(event).is_set()
                or not self.config.get("enabled", True)
                or await self.context.conversation_manager.get_curr_conversation_id(
                    event.unified_msg_origin
                )
                != scope[1]
            ):
                event.stop_event()
                return
        if req.func_tool is None:
            req.func_tool = ToolSet()
        if not self.config.get("enabled", True):
            for name in SUBAGENT_TOOL_NAMES:
                req.func_tool.remove_tool(name)
            return
        self._refresh_spawn_tool()
        # Use the manager's wrappers so per-tool permissions still apply.
        registered = self.context.get_llm_tool_manager().get_full_tool_set()
        for name in SUBAGENT_TOOL_NAMES:
            tool = registered.get_tool(name)
            if tool is not None and tool.active:
                req.func_tool.add_tool(tool)

    @filter.on_agent_begin()
    async def begin(self, event, run_context):
        """Bind main's request to a sender-owned conversation runtime."""
        if not self.config.get("enabled", True) or run_context.runner is None:
            return
        conversation = run_context.runner.req.conversation
        if conversation is None:
            return
        original = run_context.context
        parent = SubAgentContext(
            context=original.context,
            event=original.event,
            extra=original.extra,
            conversation_id=conversation.cid,
        )
        await self.orchestrator.store.bind(parent)
        run_context.context = parent
        tools = run_context.runner.req.func_tool
        parent.delegable_tools = (
            ToolSet(
                tools=[
                    tool for tool in tools.tools if tool.name not in SUBAGENT_TOOL_NAMES
                ]
            )
            if tools is not None
            else ToolSet()
        )
        parent.subagent_runtime.begin_parent(run_context, run_context.runner)

    @filter.on_agent_step_start()
    async def receive(self, event, run_context):
        """Deliver completed worker turns at a complete tool-pair boundary."""
        if isinstance(run_context.context, SubAgentContext):
            run_context.context.subagent_runtime.receive_results(run_context)

    @filter.on_agent_step_end()
    async def checkpoint(self, event, run_context):
        """Checkpoint private worker progress after a complete step."""
        if isinstance(run_context.context, SubAgentContext):
            await run_context.context.subagent_runtime.checkpoint(run_context)

    @filter.on_agent_done()
    async def done(self, event, run_context, response):
        """Release main and reconcile receipts after normal history persistence."""
        if not isinstance(run_context.context, SubAgentContext):
            return
        runtime = run_context.context.subagent_runtime
        runtime.end_parent(run_context)
        await runtime.checkpoint()
        if runtime.wakeup_task is None or runtime.wakeup_task.done():
            task = asyncio.create_task(
                SubAgentExecutor._dispatch_subagent_results(run_context)
            )
            runtime.wakeup_task = task
            self.context.register_background_task(event, task)

    async def expert_settings(self):
        """Read or save expert templates through the standard plugin API.

        Returns:
            Expert definitions and selector options, or a save/error response.
        """
        if request.method == "GET":
            providers = [
                {
                    "id": provider.provider_config["id"],
                    "model": provider.get_model(),
                }
                for provider in self.context.get_all_providers()
            ]
            personas = [
                {
                    "id": persona["name"],
                    "prompt": persona.get("prompt", ""),
                    "tools": persona.get("tools"),
                }
                for persona in self.context.persona_manager.personas_v3
            ]
            tools = [
                {"name": tool.name, "description": tool.description}
                for tool in self.context.get_llm_tool_manager().get_full_tool_set()
                if tool.active
                and tool.name not in SUBAGENT_TOOL_NAMES
                and not tool.name.startswith("transfer_to_")
            ]
            return json_response(
                {
                    "status": "ok",
                    "data": {
                        "agents": copy.deepcopy(self.config.get("agents", [])),
                        "providers": providers,
                        "personas": personas,
                        "tools": tools,
                    },
                }
            )

        payload = await request.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("agents"), list):
            return error_response("An agents list is required.")
        try:
            definitions = TypeAdapter(list[ExpertDefinition]).validate_python(
                payload["agents"]
            )
        except ValidationError as exc:
            return error_response(
                f"Invalid expert definition: {exc.errors()[0]['msg']}"
            )
        if len({item.name for item in definitions}) != len(definitions):
            return error_response("Expert names must be unique.")
        agents = [
            {**item.model_dump(), "__template_key": "expert"} for item in definitions
        ]
        async with self._expert_settings_lock:
            old_agents = copy.deepcopy(self.config.get("agents", []))
            old_templates = self.orchestrator.templates
            try:
                await self.orchestrator.reload_from_config({"agents": agents})
                await self.config.save_config_async(replace_config={"agents": agents})
            except Exception:
                self.config["agents"] = old_agents
                self.orchestrator.templates = old_templates
                logger.exception("Could not save subagent expert settings")
                return error_response(
                    "Could not save expert settings.", status_code=500
                )
            self._refresh_spawn_tool()
        return json_response({"status": "ok", "data": {"agents": agents}})

    async def runtime_view(self):
        """Return runtime metadata and history through the standard plugin API."""
        agent_id = request.query.get("agent_id")
        records = []
        for scope, runtime in self.orchestrator.store.runtimes.items():
            for worker in runtime._instances.values():
                if agent_id and worker.agent_id != agent_id:
                    continue
                data = worker.to_dict(include_result=True)
                data.update(session=scope[0], conversation_id=scope[1], sender=scope[2])
                if agent_id:
                    data["messages"] = dump_messages_with_checkpoints(
                        worker.run_context.messages
                    )
                records.append(data)
        return json_response({"status": "ok", "data": {"agents": records}})

    async def terminate(self):
        """Stop workers and persist their interrupted state before unloading."""
        await self.orchestrator.store.close()
