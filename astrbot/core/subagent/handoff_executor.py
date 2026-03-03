from __future__ import annotations

import json
import typing as T
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import TYPE_CHECKING

import mcp

from astrbot import logger
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.message import Message
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.cron.events import CronMessageEvent
from astrbot.core.message.components import Image
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.provider.register import llm_tools
from astrbot.core.subagent.background_notifier import (
    wake_main_agent_for_background_result,
)
from astrbot.core.subagent.models import SubagentTaskData
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.image_ref_utils import is_supported_image_ref
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings

if TYPE_CHECKING:
    from astrbot.core.astr_agent_context import AstrAgentContext


@dataclass(slots=True)
class _HandoffExecutionSettings:
    runtime: str
    max_nested_depth: int
    default_max_steps: int
    streaming_response: bool


class HandoffExecutor:
    @staticmethod
    def _safe_int(value: T.Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _get_provider_settings(
        cls, run_context: ContextWrapper[AstrAgentContext]
    ) -> dict[str, T.Any]:
        ctx = run_context.context.context
        event = run_context.context.event
        cfg = ctx.get_config(umo=event.unified_msg_origin)
        provider_settings = cfg.get("provider_settings", {})
        if not isinstance(provider_settings, dict):
            return {}
        return provider_settings

    @classmethod
    def _get_orchestrator(
        cls, run_context: ContextWrapper[AstrAgentContext]
    ) -> T.Any | None:
        return getattr(run_context.context.context, "subagent_orchestrator", None)

    @classmethod
    def _resolve_max_nested_depth(
        cls, run_context: ContextWrapper[AstrAgentContext]
    ) -> int:
        orchestrator = cls._get_orchestrator(run_context)
        orchestrator_depth_getter = getattr(orchestrator, "get_max_nested_depth", None)
        if callable(orchestrator_depth_getter):
            depth = cls._safe_int(orchestrator_depth_getter(), 2)
            return min(8, max(1, depth))

        ctx = run_context.context.context
        event = run_context.context.event
        cfg = ctx.get_config(umo=event.unified_msg_origin)
        orchestrator_cfg = cfg.get("subagent_orchestrator", {})
        raw_depth = (
            orchestrator_cfg.get("max_nested_depth", 2)
            if isinstance(orchestrator_cfg, dict)
            else 2
        )
        depth = cls._safe_int(raw_depth, 2)
        return min(8, max(1, depth))

    @classmethod
    def _resolve_execution_settings(
        cls, run_context: ContextWrapper[AstrAgentContext]
    ) -> _HandoffExecutionSettings:
        provider_settings = cls._get_provider_settings(run_context)
        return _HandoffExecutionSettings(
            runtime=str(provider_settings.get("computer_use_runtime", "none")),
            max_nested_depth=cls._resolve_max_nested_depth(run_context),
            default_max_steps=cls._safe_int(
                provider_settings.get("max_agent_step", 30), 30
            ),
            streaming_response=bool(provider_settings.get("streaming_response", False)),
        )

    @classmethod
    def _resolve_agent_max_steps(cls, tool: HandoffTool, default_max_steps: int) -> int:
        configured_max_step = getattr(tool, "max_steps", None)
        if isinstance(configured_max_step, int) and configured_max_step > 0:
            return configured_max_step
        return default_max_steps

    @classmethod
    def collect_image_urls_from_args(cls, image_urls_raw: T.Any) -> list[str]:
        if image_urls_raw is None:
            return []

        if isinstance(image_urls_raw, str):
            return [image_urls_raw]

        if isinstance(image_urls_raw, (Sequence, AbstractSet)) and not isinstance(
            image_urls_raw, (str, bytes, bytearray)
        ):
            return [item for item in image_urls_raw if isinstance(item, str)]

        logger.debug(
            "Unsupported image_urls type in handoff tool args: %s",
            type(image_urls_raw).__name__,
        )
        return []

    @classmethod
    async def collect_image_urls_from_message(
        cls, run_context: ContextWrapper[AstrAgentContext]
    ) -> list[str]:
        urls: list[str] = []
        event = getattr(run_context.context, "event", None)
        message_obj = getattr(event, "message_obj", None)
        message = getattr(message_obj, "message", None)
        if message:
            for idx, component in enumerate(message):
                if not isinstance(component, Image):
                    continue
                try:
                    path = await component.convert_to_file_path()
                    if path:
                        urls.append(path)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Failed to convert handoff image component at index %d: %s",
                        idx,
                        exc,
                        exc_info=True,
                    )
        return urls

    @classmethod
    async def collect_handoff_image_urls(
        cls,
        run_context: ContextWrapper[AstrAgentContext],
        image_urls_raw: T.Any,
    ) -> list[str]:
        candidates: list[str] = []
        candidates.extend(cls.collect_image_urls_from_args(image_urls_raw))
        candidates.extend(await cls.collect_image_urls_from_message(run_context))

        normalized = normalize_and_dedupe_strings(candidates)
        extensionless_local_roots = (get_astrbot_temp_path(),)
        sanitized = [
            item
            for item in normalized
            if is_supported_image_ref(
                item,
                allow_extensionless_existing_local_file=True,
                extensionless_local_roots=extensionless_local_roots,
            )
        ]
        dropped_count = len(normalized) - len(sanitized)
        if dropped_count > 0:
            logger.debug(
                "Dropped %d invalid image_urls entries in handoff image inputs.",
                dropped_count,
            )
        return sanitized

    @classmethod
    def _get_runtime_computer_tools(cls, runtime: str) -> dict[str, FunctionTool]:
        from astrbot.core.astr_main_agent_resources import (
            EXECUTE_SHELL_TOOL,
            FILE_DOWNLOAD_TOOL,
            FILE_UPLOAD_TOOL,
            LOCAL_EXECUTE_SHELL_TOOL,
            LOCAL_PYTHON_TOOL,
            PYTHON_TOOL,
        )

        if runtime == "sandbox":
            return {
                EXECUTE_SHELL_TOOL.name: EXECUTE_SHELL_TOOL,
                PYTHON_TOOL.name: PYTHON_TOOL,
                FILE_UPLOAD_TOOL.name: FILE_UPLOAD_TOOL,
                FILE_DOWNLOAD_TOOL.name: FILE_DOWNLOAD_TOOL,
            }
        if runtime == "local":
            return {
                LOCAL_EXECUTE_SHELL_TOOL.name: LOCAL_EXECUTE_SHELL_TOOL,
                LOCAL_PYTHON_TOOL.name: LOCAL_PYTHON_TOOL,
            }
        return {}

    @classmethod
    def build_handoff_toolset(
        cls,
        run_context: ContextWrapper[AstrAgentContext],
        tools: list[str | FunctionTool] | None,
    ) -> ToolSet | None:
        provider_settings = cls._get_provider_settings(run_context)
        runtime = str(provider_settings.get("computer_use_runtime", "none"))
        runtime_computer_tools = cls._get_runtime_computer_tools(runtime)

        if tools is None:
            toolset = ToolSet()
            for registered_tool in llm_tools.func_list:
                if isinstance(registered_tool, HandoffTool):
                    continue
                if registered_tool.active:
                    toolset.add_tool(registered_tool)
            for runtime_tool in runtime_computer_tools.values():
                toolset.add_tool(runtime_tool)
            return None if toolset.empty() else toolset

        if not tools:
            return None

        toolset = ToolSet()
        for tool_name_or_obj in tools:
            if isinstance(tool_name_or_obj, str):
                registered_tool = llm_tools.get_func(tool_name_or_obj)
                if (
                    registered_tool
                    and registered_tool.active
                    and not isinstance(registered_tool, HandoffTool)
                ):
                    toolset.add_tool(registered_tool)
                    continue
                runtime_tool = runtime_computer_tools.get(tool_name_or_obj)
                if runtime_tool:
                    toolset.add_tool(runtime_tool)
            elif isinstance(tool_name_or_obj, FunctionTool) and not isinstance(
                tool_name_or_obj, HandoffTool
            ):
                toolset.add_tool(tool_name_or_obj)
        return None if toolset.empty() else toolset

    @classmethod
    async def execute_foreground(
        cls,
        tool: HandoffTool,
        run_context: ContextWrapper[AstrAgentContext],
        *,
        image_urls_prepared: bool = False,
        **tool_args: T.Any,
    ):
        args = dict(tool_args)
        input_ = args.get("input")
        if image_urls_prepared:
            prepared_image_urls = args.get("image_urls")
            if isinstance(prepared_image_urls, list):
                image_urls = prepared_image_urls
            else:
                logger.debug(
                    "Expected prepared handoff image_urls as list[str], got %s.",
                    type(prepared_image_urls).__name__,
                )
                image_urls = []
        else:
            image_urls = await cls.collect_handoff_image_urls(
                run_context,
                args.get("image_urls"),
            )
        args["image_urls"] = image_urls

        toolset = cls.build_handoff_toolset(run_context, tool.agent.tools)
        execution_settings = cls._resolve_execution_settings(run_context)

        ctx = run_context.context.context
        event = run_context.context.event
        umo = event.unified_msg_origin
        event_get_extra = getattr(event, "get_extra", None)
        current_depth = (
            cls._safe_int(event_get_extra("subagent_handoff_depth"), 0)
            if callable(event_get_extra)
            else 0
        )
        max_depth = execution_settings.max_nested_depth
        if current_depth >= max_depth:
            yield mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(
                        type="text",
                        text=(
                            f"error: nested subagent handoff depth limit reached ({max_depth}). "
                            "Please continue in current agent."
                        ),
                    )
                ]
            )
            return

        prov_id = getattr(
            tool, "provider_id", None
        ) or await ctx.get_current_chat_provider_id(umo)

        contexts = None
        dialogs = tool.agent.begin_dialogs
        if dialogs:
            contexts = []
            for dialog in dialogs:
                try:
                    contexts.append(
                        dialog
                        if isinstance(dialog, Message)
                        else Message.model_validate(dialog)
                    )
                except Exception:  # noqa: BLE001
                    continue

        agent_max_step = cls._resolve_agent_max_steps(
            tool, execution_settings.default_max_steps
        )
        stream = execution_settings.streaming_response
        event_set_extra = getattr(event, "set_extra", None)
        if callable(event_set_extra):
            event_set_extra("subagent_handoff_depth", current_depth + 1)
        try:
            llm_resp = await ctx.tool_loop_agent(
                event=event,
                chat_provider_id=prov_id,
                prompt=input_,
                image_urls=image_urls,
                system_prompt=tool.agent.instructions,
                tools=toolset,
                contexts=contexts,
                max_steps=agent_max_step,
                stream=stream,
            )
        finally:
            if callable(event_set_extra):
                event_set_extra("subagent_handoff_depth", current_depth)
        yield mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text=llm_resp.completion_text)]
        )

    @classmethod
    async def submit_background(
        cls,
        tool: HandoffTool,
        run_context: ContextWrapper[AstrAgentContext],
        *,
        tool_call_id: str | None = None,
        **tool_args: T.Any,
    ):
        prepared_tool_args = dict(tool_args)
        prepared_tool_args["image_urls"] = await cls.collect_handoff_image_urls(
            run_context,
            prepared_tool_args.get("image_urls"),
        )
        orchestrator = getattr(
            run_context.context.context, "subagent_orchestrator", None
        )
        if orchestrator is None:
            yield mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(
                        type="text",
                        text=(
                            "error: subagent orchestrator is not available, "
                            "background handoff cannot be submitted."
                        ),
                    )
                ]
            )
            return

        try:
            task_id = await orchestrator.submit_handoff(
                handoff=tool,
                run_context=run_context,
                payload=prepared_tool_args,
                background=True,
                tool_call_id=tool_call_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to submit handoff to subagent orchestrator runtime: %s",
                exc,
                exc_info=True,
            )
            yield mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(
                        type="text",
                        text="error: failed to submit subagent background task to orchestrator.",
                    )
                ]
            )
            return

        if not task_id:
            yield mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(
                        type="text",
                        text=(
                            "error: failed to submit subagent background task "
                            "because orchestrator returned no task id."
                        ),
                    )
                ]
            )
            return

        yield mcp.types.CallToolResult(
            content=[
                mcp.types.TextContent(
                    type="text",
                    text=(
                        f"Background task dedicated to subagent '{tool.agent.name}' submitted. "
                        f"task_id={task_id}. You will be notified when it finishes."
                    ),
                )
            ]
        )

    @classmethod
    async def execute_queued_task(
        cls,
        *,
        task: SubagentTaskData,
        plugin_context: T.Any,
        handoff: HandoffTool | None,
    ) -> str:
        if handoff is None:
            raise ValueError(f"Handoff tool `{task.handoff_tool_name}` not found.")

        payload = json.loads(task.payload_json)
        if not isinstance(payload, dict):
            raise ValueError("Invalid task payload.")
        tool_args = payload.get("tool_args", {})
        if not isinstance(tool_args, dict):
            raise ValueError("Invalid task tool_args payload.")
        meta = payload.get("_meta", {})
        if not isinstance(meta, dict):
            meta = {}

        session = MessageSession.from_str(task.umo)
        cron_event = CronMessageEvent(
            context=plugin_context,
            session=session,
            message=str(
                tool_args.get("input") or f"[SubagentTask] {task.subagent_name}"
            ),
            extras={
                "background_note": meta.get("background_note")
                or f"Background task for subagent '{task.subagent_name}' finished."
            },
            message_type=session.message_type,
        )
        if role := meta.get("role"):
            cron_event.role = role

        from astrbot.core.astr_agent_context import (
            AgentContextWrapper,
            AstrAgentContext,
        )

        agent_ctx = AstrAgentContext(context=plugin_context, event=cron_event)
        wrapper = AgentContextWrapper(
            context=agent_ctx,
            tool_call_timeout=int(meta.get("tool_call_timeout", 3600)),
        )

        handoff_args = dict(tool_args)
        handoff_args["image_urls"] = await cls.collect_handoff_image_urls(
            wrapper,
            handoff_args.get("image_urls"),
        )
        result_text = ""
        async for result in cls.execute_foreground(
            handoff,
            wrapper,
            image_urls_prepared=True,
            **handoff_args,
        ):
            if isinstance(result, mcp.types.CallToolResult):
                for content in result.content:
                    if isinstance(content, mcp.types.TextContent):
                        result_text += content.text + "\n"

        await wake_main_agent_for_background_result(
            run_context=wrapper,
            task_id=task.task_id,
            tool_name=handoff.name,
            result_text=result_text,
            tool_args=handoff_args,
            note=meta.get("background_note")
            or f"Background task for subagent '{task.subagent_name}' finished.",
            summary_name=f"Dedicated to subagent `{task.subagent_name}`",
            extra_result_fields={"subagent_name": task.subagent_name},
        )
        return result_text or "ok"
