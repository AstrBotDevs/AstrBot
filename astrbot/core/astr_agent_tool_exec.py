import asyncio
import inspect
import json
import traceback
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from collections.abc import Set as AbstractSet
from typing import Any

import mcp

from astrbot import logger
from astrbot.core import astrbot_config as _astrbot_config
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.message import Message
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolSchema, ToolSet
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.astr_main_agent_resources import (
    BACKGROUND_TASK_RESULT_WOKE_SYSTEM_PROMPT,
    BACKGROUND_TASK_WOKE_USER_PROMPT,
    CONVERSATION_HISTORY_INJECT_PREFIX,
)
from astrbot.core.config.default import DEFAULT_MAX_HANDOFF_CALLS_PER_RUN
from astrbot.core.cron.events import CronMessageEvent
from astrbot.core.message.components import Image
from astrbot.core.message.message_event_result import (
    CommandResult,
    MessageChain,
    MessageEventResult,
)
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.provider.entites import ProviderRequest
from astrbot.core.provider.register import llm_tools
from astrbot.core.star.session_plugin_manager import SessionPluginManager
from astrbot.core.star.star import star_map
from astrbot.core.tools.computer_tools import (
    CuaKeyboardTypeTool,
    CuaMouseClickTool,
    CuaScreenshotTool,
    ExecuteShellTool,
    FileDownloadTool,
    FileEditTool,
    FileReadTool,
    FileUploadTool,
    FileWriteTool,
    GrepTool,
    LocalPythonTool,
    PythonTool,
)
from astrbot.core.tools.message_tools import SendMessageToUserTool
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.history_saver import persist_agent_history
from astrbot.core.utils.image_ref_utils import is_supported_image_ref
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings
from astrbot.core.utils.trace import _current_span as _trace_current_span


class FunctionToolExecutor(BaseFunctionToolExecutor[AstrAgentContext]):
    _HANDOFF_CALL_COUNT_EXTRA_KEY = "_subagent_handoff_call_count"
    _DEFAULT_MAX_HANDOFF_CALLS_PER_RUN = DEFAULT_MAX_HANDOFF_CALLS_PER_RUN
    _MAX_HANDOFF_CALL_COUNT_SANITY_LIMIT = 10_000

    @classmethod
    def _build_handoff_error_result(
        cls,
        *,
        tool_name: str,
        error_type: str,
        fix_hint: str,
        action_hint: str,
    ) -> mcp.types.CallToolResult:
        guidance = (
            "[handoff CALL FAILED - IMMEDIATE RETRY REQUIRED]\n"
            f"error_type: {error_type}\n"
            f"fix: {fix_hint}\n"
            f"action: {action_hint}\n"
            "example:\n"
            "{\n"
            '  "input": "Summarize the user request, constraints, and expected output.",\n'
            '  "background_task": false\n'
            "}"
        )
        return mcp.types.CallToolResult(
            content=[
                mcp.types.TextContent(
                    type="text",
                    text=f"error: {tool_name} rejected invalid handoff request.\n{guidance}",
                )
            ]
        )

    @classmethod
    def _parse_background_task_arg(
        cls,
        tool_name: str,
        value: T.Any,
    ) -> tuple[bool, mcp.types.CallToolResult | None]:
        if value is None:
            return False, None
        if isinstance(value, bool):
            return value, None
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True, None
            if normalized in {"false", "0", "no", "off", ""}:
                return False, None

        return False, cls._build_handoff_error_result(
            tool_name=tool_name,
            error_type="invalid_background_task",
            fix_hint=(
                "`background_task` must be a boolean (`true` or `false`) or a string "
                'equivalent such as `"1"`/`"0"`, `"yes"`/`"no"`, or '
                '`"on"`/`"off"`.'
            ),
            action_hint=(
                "Retry the same handoff with `background_task` set to a boolean or one "
                'of the supported string equivalents (`"true"`, `"false"`, '
                '`"1"`, `"0"`, `"yes"`, `"no"`, `"on"`, `"off"`).'
            ),
        )

    @classmethod
    def _normalize_handoff_input(
        cls,
        tool_name: str,
        input_value: T.Any,
    ) -> tuple[str | None, mcp.types.CallToolResult | None]:
        if not isinstance(input_value, str) or not input_value.strip():
            return None, cls._build_handoff_error_result(
                tool_name=tool_name,
                error_type="missing_or_empty_input",
                fix_hint=(
                    "Provide a non-empty `input` string that clearly describes the delegated task."
                ),
                action_hint=("Retry now with a concise task statement in `input`."),
            )
        return input_value.strip(), None

    @classmethod
    async def _resolve_handoff_provider_id(
        cls,
        tool: HandoffTool,
        *,
        ctx: T.Any,
        umo: str,
    ) -> str:
        configured_provider_id = str(getattr(tool, "provider_id", "") or "").strip()
        if not configured_provider_id:
            return await ctx.get_current_chat_provider_id(umo)

        provider_mgr = getattr(ctx, "provider_manager", None)
        if provider_mgr is None or not hasattr(provider_mgr, "get_provider_by_id"):
            return configured_provider_id

        provider_inst = await provider_mgr.get_provider_by_id(configured_provider_id)
        if provider_inst is not None:
            return configured_provider_id

        fallback_provider_id = await ctx.get_current_chat_provider_id(umo)
        logger.warning(
            "Subagent %s configured provider `%s` not found, fallback to `%s`.",
            tool.name,
            configured_provider_id,
            fallback_provider_id,
        )
        return fallback_provider_id

    @classmethod
    def _tool_enabled_for_session(
        cls,
        tool: FunctionTool,
        session_config: dict | None,
    ) -> bool:
        mp = tool.handler_module_path
        if not mp:
            return True

        plugin = star_map.get(mp)
        if not plugin:
            return True

        return SessionPluginManager.is_plugin_enabled_for_session_config(
            plugin.name,
            session_config,
            reserved=plugin.reserved,
        )

    @classmethod
    def _collect_image_urls_from_args(cls, image_urls_raw: T.Any) -> list[str]:
        if image_urls_raw is None:
            return []
        if isinstance(image_urls_raw, str):
            return [image_urls_raw]
        if isinstance(image_urls_raw, (Sequence, AbstractSet)) and (
            not isinstance(image_urls_raw, (str, bytes, bytearray))
        ):
            return [item for item in image_urls_raw if isinstance(item, str)]
        logger.debug(
            "Unsupported image_urls type in handoff tool args: %s",
            type(image_urls_raw).__name__,
        )
        return []

    @classmethod
    async def _collect_image_urls_from_message(
        cls,
        run_context: ContextWrapper[AstrAgentContext],
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
                except Exception as e:
                    logger.error(
                        "Failed to convert handoff image component at index %d: %s",
                        idx,
                        e,
                        exc_info=True,
                    )
        return urls

    @classmethod
    async def _collect_handoff_image_urls(
        cls,
        run_context: ContextWrapper[AstrAgentContext],
        image_urls_raw: Any,
    ) -> list[str]:
        candidates: list[str] = []
        candidates.extend(cls._collect_image_urls_from_args(image_urls_raw))
        candidates.extend(await cls._collect_image_urls_from_message(run_context))
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
    async def execute(cls, tool, run_context, **tool_args):
        """执行函数调用｡

        Args:
            tool: The tool to execute.
            run_context: The run context.
            **tool_args: Tool-specific arguments.
            **kwargs: 函数调用的参数｡

        Returns:
            AsyncGenerator[None | mcp.types.CallToolResult, None]

        """
        if isinstance(tool, HandoffTool):
            is_bg, bg_error = cls._parse_background_task_arg(
                tool.name,
                tool_args.pop("background_task", None),
            )
            if bg_error is not None:
                yield bg_error
                return
            if is_bg:
                async for r in cls._execute_handoff_background(
                    tool,
                    run_context,
                    **tool_args,
                ):
                    yield r
                return
            async for r in cls._execute_handoff(tool, run_context, **tool_args):
                yield r
            return
        elif isinstance(tool, MCPTool):
            async for r in cls._execute_mcp(tool, run_context, **tool_args):
                yield r
            return
        elif tool.is_background_task:
            task_id = uuid.uuid4().hex

            async def _run_in_background() -> None:
                try:
                    await cls._execute_background(
                        tool=tool,
                        run_context=run_context,
                        task_id=task_id,
                        **tool_args,
                    )
                except Exception as e:
                    logger.error(
                        f"Background task {task_id} failed: {e!s}",
                        exc_info=True,
                    )

            asyncio.create_task(_run_in_background())
            text_content = mcp.types.TextContent(
                type="text",
                text=f"Background task submitted. task_id={task_id}",
            )
            yield mcp.types.CallToolResult(content=[text_content])
            return
        else:
            rejection = cls._check_sandbox_capability(tool, run_context)
            if rejection is not None:
                yield rejection
                return
            async for r in cls._execute_local(tool, run_context, **tool_args):
                yield r
            return

    _BROWSER_TOOL_NAMES: frozenset[str] = frozenset(
        {
            "astrbot_execute_browser",
            "astrbot_execute_browser_batch",
            "astrbot_run_browser_skill",
        },
    )

    @classmethod
    def _check_sandbox_capability(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[AstrAgentContext],
    ) -> mcp.types.CallToolResult | None:
        """Return a rejection result if the tool requires a sandbox capability
        that is not available, or None if the tool may proceed.
        """
        if tool.name not in cls._BROWSER_TOOL_NAMES:
            return None
        from astrbot.core.computer.computer_client import get_sandbox_capabilities

        session_id = run_context.context.event.unified_msg_origin
        caps = get_sandbox_capabilities(session_id)
        if caps is None:
            return None
        if "browser" not in caps:
            msg = f"Tool '{tool.name}' requires browser capability, but the current sandbox profile does not include it (capabilities: {list(caps)}). Please ask the administrator to switch to a sandbox profile with browser support, or use shell/python tools instead."
            logger.warning(
                "[ToolExec] capability_rejected tool=%s caps=%s",
                tool.name,
                list(caps),
            )
            return mcp.types.CallToolResult(
                content=[mcp.types.TextContent(type="text", text=msg)],
                isError=True,
            )
        return None

    @classmethod
    def _get_runtime_computer_tools(
        cls,
        runtime: str,
        tool_mgr: Any = None,
        booter: str | None = None,
        session_id: str = "",
        sandbox_cfg: dict | None = None,
    ) -> dict[str, ToolSchema]:
        """Get computer runtime tools via ComputerToolProvider.

        Delegates tool discovery to ComputerToolProvider for decoupled
        sandbox / local tool injection.  The *tool_mgr* parameter is kept
        for backward compatibility but is no longer used.

        Args:
            runtime: ``'sandbox'``, ``'local'``, or ``'none'``.
            tool_mgr: Kept for backward compatibility (unused).
            booter: Short-form booter type (e.g. ``'shipyard_neo'``).
            session_id: Session identifier.
            sandbox_cfg: Full sandbox configuration dict (preferred over
                *booter* when both are provided).

        Returns:
            Dict mapping tool name to FunctionTool instance.

        """
        from astrbot.core.computer.computer_tool_provider import (
            ComputerToolProvider,
        )
        from astrbot.core.tool_provider import ToolProviderContext

        cfg: dict = {}
        if sandbox_cfg is not None:
            cfg = sandbox_cfg
        elif booter:
            cfg["booter"] = booter

        ctx = ToolProviderContext(
            computer_use_runtime=runtime,
            sandbox_cfg=cfg,
            session_id=session_id,
        )
        tools = ComputerToolProvider().get_tools(ctx)
        return {t.name: t for t in tools}

    @classmethod
    async def _build_handoff_toolset(
        cls,
        run_context: ContextWrapper[AstrAgentContext],
        tools: list[str | FunctionTool] | None,
    ) -> ToolSet | None:
        ctx = run_context.context.context
        event = run_context.context.event
        cfg = ctx.get_config(umo=event.unified_msg_origin)
        session_config = await SessionPluginManager.get_session_plugin_config(
            event.unified_msg_origin
        )
        provider_settings = cfg.get("provider_settings", {})
        runtime = str(provider_settings.get("computer_use_runtime", "local"))
        tool_mgr = ctx.get_llm_tool_manager()
        runtime_computer_tools = cls._get_runtime_computer_tools(
            runtime,
            session_id=event.unified_msg_origin,
            sandbox_cfg=sandbox_cfg,
        )
        if tools is None:
            toolset = ToolSet()
            for registered_tool in llm_tools.func_list:
                if isinstance(registered_tool, HandoffTool):
                    continue
                if registered_tool.active and cls._tool_enabled_for_session(
                    registered_tool,
                    session_config,
                ):
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
                    and cls._tool_enabled_for_session(registered_tool, session_config)
                ):
                    toolset.add_tool(registered_tool)
                    continue
                runtime_tool = runtime_computer_tools.get(tool_name_or_obj)
                if runtime_tool:
                    toolset.add_tool(runtime_tool)
            elif isinstance(tool_name_or_obj, FunctionTool):
                if cls._tool_enabled_for_session(tool_name_or_obj, session_config):
                    toolset.add_tool(tool_name_or_obj)
        return None if toolset.empty() else toolset

    @classmethod
    async def _execute_handoff(
        cls,
        tool: HandoffTool[Any],
        run_context: ContextWrapper[Any],
        *,
        image_urls_prepared: bool = False,
        **tool_args: Any,
    ):
        tool_args = dict(tool_args)
        input_, input_error = cls._normalize_handoff_input(
            tool.name,
            tool_args.get("input"),
        )
        if input_error is not None:
            yield input_error
            return
        tool_args["input"] = input_
        if image_urls_prepared:
            prepared_image_urls = tool_args.get("image_urls")
            if isinstance(prepared_image_urls, list):
                image_urls = prepared_image_urls
            else:
                logger.debug(
                    "Expected prepared handoff image_urls as list[str], got %s.",
                    type(prepared_image_urls).__name__,
                )
                image_urls = []
        else:
            image_urls = await cls._collect_handoff_image_urls(
                run_context,
                tool_args.get("image_urls"),
            )
        tool_args["image_urls"] = image_urls

        # Build handoff toolset from registered tools plus runtime computer tools.
        toolset = await cls._build_handoff_toolset(run_context, tool.agent.tools)

        umo = event.unified_msg_origin

        # Use per-subagent provider override if configured; otherwise fall back
        # to the current/default provider resolution.
        prov_id = await cls._resolve_handoff_provider_id(
            tool,
            ctx=ctx,
            umo=umo,
        )

        # prepare begin dialogs
        contexts = None
        dialogs = tool.agent.begin_dialogs
        if dialogs:
            contexts = []
            for dialog in dialogs:
                try:
                    contexts.append(
                        dialog
                        if isinstance(dialog, Message)
                        else Message.model_validate(dialog),
                    )
                except Exception:
                    continue
        prov_settings: dict = ctx.get_config(umo=umo).get("provider_settings", {})
        agent_max_step = int(prov_settings.get("max_agent_step", 3))
        stream = prov_settings.get("streaming_response", False)
        # ── Trace: create a dedicated llm_agent span for this subagent ──────
        _subagent_span = None
        _subagent_token = None
        if _astrbot_config.get("trace_enable", False):
            _span_parent = _trace_current_span.get()
            if _span_parent is not None:
                _subagent_span = _span_parent.child(
                    f"LLMAgent [{tool.agent.name}]",
                    span_type="llm_agent",
                )
                _subagent_span.set_input(
                    subagent=tool.agent.name,
                    prompt=(input_ or "")[:500],
                    system_prompt=(tool.agent.instructions or "")[:300],
                )
                _subagent_token = _trace_current_span.set(_subagent_span)
        # ─────────────────────────────────────────────────────────────────────
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
                tool_call_timeout=run_context.tool_call_timeout,
                stream=stream,
            )
            if _subagent_span is not None and _subagent_span.finished_at is None:
                _subagent_span.set_output(
                    response=(llm_resp.completion_text or "")[:2000]
                    if llm_resp
                    else "",
                )
                _subagent_span.finish()
        except Exception:
            if _subagent_span is not None and _subagent_span.finished_at is None:
                _subagent_span.finish(status="error")
            raise
        finally:
            if _subagent_token is not None:
                _trace_current_span.reset(_subagent_token)
        # ─────────────────────────────────────────────────────────────────────
        yield mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text=llm_resp.completion_text)],
        )

    @classmethod
    async def _execute_handoff_background(
        cls,
        tool: HandoffTool,
        run_context: ContextWrapper[AstrAgentContext],
        **tool_args,
    ):
        """Execute a handoff as a background task.

        Immediately yields a success response with a task_id, then runs
        the subagent asynchronously.  When the subagent finishes, a
        ``CronMessageEvent`` is created so the main LLM can inform the
        user of the result – the same pattern used by
        ``_execute_background`` for regular background tasks.
        """
        task_id = uuid.uuid4().hex

        async def _run_handoff_in_background() -> None:
            try:
                await cls._do_handoff_background(
                    tool=tool,
                    run_context=run_context,
                    task_id=task_id,
                    **tool_args,
                )
            except Exception as e:
                logger.error(
                    f"Background handoff {task_id} ({tool.name}) failed: {e!s}",
                    exc_info=True,
                )

        asyncio.create_task(_run_handoff_in_background())
        text_content = mcp.types.TextContent(
            type="text",
            text=f"Background task dedicated to subagent '{tool.agent.name}' submitted. task_id={task_id}. The subagent '{tool.agent.name}' is working on the task on behalf of you. You will be notified when it finishes.",
        )
        yield mcp.types.CallToolResult(content=[text_content])

    @classmethod
    async def _do_handoff_background(
        cls,
        tool: HandoffTool,
        run_context: ContextWrapper[AstrAgentContext],
        task_id: str,
        **tool_args,
    ) -> None:
        """Run the subagent handoff and, on completion, wake the main agent."""
        result_text = ""
        tool_args = dict(tool_args)
        tool_args["image_urls"] = await cls._collect_handoff_image_urls(
            run_context,
            tool_args.get("image_urls"),
        )
        try:
            async for r in cls._execute_handoff(
                tool,
                run_context,
                image_urls_prepared=True,
                **tool_args,
            ):
                if isinstance(r, mcp.types.CallToolResult):
                    for content in r.content:
                        if isinstance(content, mcp.types.TextContent):
                            result_text += content.text + "\n"
        except Exception as e:
            result_text = (
                f"error: Background task execution failed, internal error: {e!s}"
            )
        event = run_context.context.event
        await cls._wake_main_agent_for_background_result(
            run_context=run_context,
            task_id=task_id,
            tool_name=tool.name,
            result_text=result_text,
            tool_args=tool_args,
            note=event.get_extra("background_note")
            or f"Background task for subagent '{tool.agent.name}' finished.",
            summary_name=f"Dedicated to subagent `{tool.agent.name}`",
            extra_result_fields={"subagent_name": tool.agent.name},
        )

    @classmethod
    async def _execute_background(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[AstrAgentContext],
        task_id: str,
        **tool_args,
    ) -> None:
        result_text = ""
        try:
            async for r in cls._execute_local(
                tool,
                run_context,
                tool_call_timeout=3600,
                **tool_args,
            ):
                if isinstance(r, mcp.types.CallToolResult):
                    result_text = ""
                    for content in r.content:
                        if isinstance(content, mcp.types.TextContent):
                            result_text += content.text + "\n"
        except Exception as e:
            result_text = (
                f"error: Background task execution failed, internal error: {e!s}"
            )
        event = run_context.context.event
        await cls._wake_main_agent_for_background_result(
            run_context=run_context,
            task_id=task_id,
            tool_name=tool.name,
            result_text=result_text,
            tool_args=tool_args,
            note=event.get_extra("background_note")
            or f"Background task {tool.name} finished.",
            summary_name=tool.name,
        )

    @classmethod
    async def _wake_main_agent_for_background_result(
        cls,
        run_context: ContextWrapper[AstrAgentContext],
        *,
        task_id: str,
        tool_name: str,
        result_text: str,
        tool_args: dict[str, Any],
        note: str,
        summary_name: str,
        extra_result_fields: dict[str, Any] | None = None,
    ) -> None:
        from astrbot.core.astr_main_agent import (
            MainAgentBuildConfig,
            _get_session_conv,
            build_main_agent,
        )

        event = run_context.context.event
        ctx = run_context.context.context
        task_result = {
            "task_id": task_id,
            "tool_name": tool_name,
            "result": result_text or "",
            "tool_args": tool_args,
        }
        if extra_result_fields:
            task_result.update(extra_result_fields)
        extras = {"background_task_result": task_result}
        session = MessageSession.from_str(event.unified_msg_origin)
        cron_event = CronMessageEvent(
            context=ctx,
            session=session,
            message=note,
            extras=extras,
            message_type=session.message_type,
        )
        cron_event.role = event.role

        config = MainAgentBuildConfig(
            tool_call_timeout=run_context.tool_call_timeout,
            streaming_response=ctx.get_config()
            .get("provider_settings", {})
            .get("stream", False),
        )
        req = ProviderRequest()
        req.system_prompt = ""
        conv = await _get_session_conv(event=cron_event, plugin_context=ctx)
        req.conversation = conv
        context = json.loads(conv.history)
        if context:
            req.contexts = context
            context_dump = req._print_friendly_context()
            req.contexts = []
            req.system_prompt += CONVERSATION_HISTORY_INJECT_PREFIX + context_dump
        bg = json.dumps(extras["background_task_result"], ensure_ascii=False)
        req.system_prompt += BACKGROUND_TASK_RESULT_WOKE_SYSTEM_PROMPT.format(
            background_task_result=bg,
        )
        req.prompt = BACKGROUND_TASK_WOKE_USER_PROMPT
        if not req.func_tool:
            req.func_tool = ToolSet()
        req.func_tool.add_tool(SEND_MESSAGE_TO_USER_TOOL)
        result = await build_main_agent(
            event=cron_event,
            plugin_context=ctx,
            config=config,
            req=req,
        )
        if not result:
            logger.error(f"Failed to build main agent for background task {tool_name}.")
            return
        runner = result.agent_runner
        async for _ in runner.step_until_done(3):
            pass
        llm_resp = runner.get_final_llm_resp()
        task_meta = extras.get("background_task_result", {})
        summary_note = f"[BackgroundTask] {summary_name} (task_id={task_meta.get('task_id', task_id)}) finished. Result: {task_meta.get('result') or result_text or 'no content'}"
        if llm_resp and llm_resp.completion_text:
            summary_note += (
                f"I finished the task, here is the result: {llm_resp.completion_text}"
            )
        await persist_agent_history(
            ctx.conversation_manager,
            event=cron_event,
            req=req,
            summary_note=summary_note,
        )
        if not llm_resp:
            logger.warning("background task agent got no response")
            return

    @classmethod
    async def _execute_local(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[AstrAgentContext],
        *,
        tool_call_timeout: int | None = None,
        **tool_args,
    ):
        event = run_context.context.event
        if not event:
            raise ValueError("Event must be provided for local function tools.")
        is_override_call = False
        for ty in type(tool).mro():
            if "call" in ty.__dict__ and ty.__dict__["call"] is not FunctionTool.call:
                is_override_call = True
                break
        if not tool.handler and (not hasattr(tool, "run")) and (not is_override_call):
            raise ValueError("Tool must have a valid handler or override 'run' method.")
        awaitable = None
        method_name = ""
        if tool.handler:
            awaitable = tool.handler
            method_name = "decorator_handler"
        elif is_override_call:
            awaitable = tool.call
            method_name = "call"
        else:
            awaitable = getattr(tool, "run", None)
            if awaitable is not None:
                method_name = "run"
        if awaitable is None:
            raise ValueError("Tool must have a valid handler or override 'run' method.")
        sdk_plugin_bridge = getattr(
            run_context.context.context,
            "sdk_plugin_bridge",
            None,
        )
        if sdk_plugin_bridge is not None:
            try:
                await sdk_plugin_bridge.dispatch_message_event(
                    "calling_func_tool",
                    event,
                    {
                        "tool_name": tool.name,
                        "tool_args": json.loads(
                            json.dumps(tool_args, ensure_ascii=False, default=str),
                        ),
                    },
                )
            except Exception as exc:
                logger.warning("SDK calling_func_tool dispatch failed: %s", exc)
        _HandlerType = Callable[
            ...,
            Awaitable[MessageEventResult | mcp.types.CallToolResult | str | None]
            | AsyncGenerator[MessageEventResult | CommandResult | str | None, None],
        ]
        wrapper = call_local_llm_tool(
            context=run_context,
            handler=awaitable,
            method_name=method_name,
            **tool_args,
        )
        while True:
            try:
                resp = await asyncio.wait_for(
                    anext(wrapper),
                    timeout=tool_call_timeout or run_context.tool_call_timeout,
                )
                if resp is not None:
                    if isinstance(resp, mcp.types.CallToolResult):
                        yield resp
                    else:
                        text_content = mcp.types.TextContent(
                            type="text",
                            text=str(resp),
                        )
                        yield mcp.types.CallToolResult(content=[text_content])
                else:
                    res = run_context.context.event.get_result()
                    if res and res.chain:
                        try:
                            await event.send(
                                MessageChain(
                                    chain=res.chain,
                                    type="tool_direct_result",
                                ),
                            )
                        except Exception as e:
                            logger.error(f"Tool 直接发送消息失败: {e}", exc_info=True)
                        yield None
                    else:
                        yield mcp.types.CallToolResult(
                            content=[
                                mcp.types.TextContent(
                                    type="text",
                                    text="Tool executed successfully with no output.",
                                ),
                            ],
                        )
            except TimeoutError:
                raise Exception(
                    f"tool {tool.name} execution timeout after {tool_call_timeout or run_context.tool_call_timeout} seconds.",
                ) from None
            except StopAsyncIteration:
                break

    @classmethod
    async def _execute_mcp(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[AstrAgentContext],
        **tool_args,
    ):
        res = await tool.call(run_context, **tool_args)
        if not res:
            return
        yield res


async def call_local_llm_tool(
    context: ContextWrapper[AstrAgentContext],
    handler: Callable[
        ...,
        Awaitable[MessageEventResult | mcp.types.CallToolResult | str | None]
        | AsyncGenerator[MessageEventResult | CommandResult | str | None, None],
    ],
    method_name: str,
    *args,
    **kwargs,
) -> AsyncGenerator[Any, None]:
    """执行本地 LLM 工具的处理函数并处理其返回结果"""
    ready_to_call = None
    trace_ = None
    event = context.context.event
    try:
        if method_name == "run" or method_name == "decorator_handler":
            ready_to_call = handler(event, *args, **kwargs)
        elif method_name == "call":
            ready_to_call = handler(context, *args, **kwargs)
        else:
            raise ValueError(f"未知的方法名: {method_name}")
    except ValueError as e:
        raise Exception(f"Tool execution ValueError: {e}") from e
    except TypeError as e:
        try:
            sig = inspect.signature(handler)
            params = list(sig.parameters.values())
            if params:
                params = params[1:]
            param_strs = []
            for param in params:
                param_str = param.name
                if param.annotation != inspect.Parameter.empty:
                    if isinstance(param.annotation, type):
                        type_str = param.annotation.__name__
                    else:
                        type_str = str(param.annotation)
                    param_str += f": {type_str}"
                if param.default != inspect.Parameter.empty:
                    param_str += f" = {param.default!r}"
                param_strs.append(param_str)
            handler_param_str = (
                ", ".join(param_strs) if param_strs else "(no additional parameters)"
            )
        except Exception:
            handler_param_str = "(unable to inspect signature)"
        raise Exception(
            f"Tool handler parameter mismatch, please check the handler definition. Handler parameters: {handler_param_str}",
        ) from e
    except Exception as e:
        trace_ = traceback.format_exc()
        raise Exception(f"Tool execution error: {e}. Traceback: {trace_}") from e
    if not ready_to_call:
        return
    if inspect.isasyncgen(ready_to_call):
        _has_yielded = False
        try:
            async for ret in ready_to_call:
                _has_yielded = True
                if isinstance(ret, MessageEventResult | CommandResult):
                    event.set_result(ret)
                    yield
                else:
                    yield ret
            if not _has_yielded:
                yield
        except Exception as e:
            logger.error(f"Previous Error: {trace_}")
            raise e
    elif inspect.iscoroutine(ready_to_call):
        ret = await ready_to_call
        if isinstance(ret, MessageEventResult | CommandResult):
            event.set_result(ret)
            yield
        else:
            yield ret
