import asyncio
import inspect
import json
import traceback
import typing as T
import uuid
from collections.abc import Sequence
from collections.abc import Set as AbstractSet

import mcp

from astrbot import logger
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.job_manager import AgentJob, get_agent_job_manager
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.message import Message
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolOutcome, ToolSet
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
from astrbot.core.agent.tool_gateway import ToolGateway
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.astr_main_agent_resources import (
    BACKGROUND_TASK_RESULT_WOKE_SYSTEM_PROMPT,
)
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


class FunctionToolExecutor(BaseFunctionToolExecutor[AstrAgentContext]):
    @classmethod
    def _collect_image_urls_from_args(cls, image_urls_raw: T.Any) -> list[str]:
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
    async def _collect_image_urls_from_message(
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
        image_urls_raw: T.Any,
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
        """执行函数调用。

        Args:
            event (AstrMessageEvent): 事件对象, 当 origin 为 local 时必须提供。
            **kwargs: 函数调用的参数。

        Returns:
            AsyncGenerator[None | mcp.types.CallToolResult, None]

        """
        if isinstance(tool, HandoffTool):
            is_bg = tool_args.pop("background_task", False)
            if is_bg:
                async for r in cls._execute_handoff_background(
                    tool, run_context, **tool_args
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
            event = run_context.context.event
            requester_id = (
                f"{event.get_platform_id() or event.get_platform_name() or 'unknown'}:"
                f"{event.get_sender_id() or 'unknown'}"
            )

            async def _run_in_background() -> ToolOutcome:
                return await cls._execute_background(
                    tool=tool,
                    run_context=run_context,
                    **tool_args,
                )

            async def _notify_completion(
                completed: AgentJob, outcome: ToolOutcome
            ) -> None:
                if not bool(getattr(tool, "background_notify", True)):
                    return
                if outcome.status == "direct_sent":
                    return
                if completed.status == "succeeded":
                    result_text = completed.result.strip()
                    if not result_text:
                        return
                    message = (
                        f"后台任务 {completed.job_id} 已完成：\n{result_text[:4000]}"
                    )
                else:
                    detail = completed.error_summary or completed.error_code
                    message = (
                        f"后台任务 {completed.job_id} 未能完成："
                        f"{detail[:500] or completed.status}"
                    )
                await event.send(MessageChain().message(message))

            job = await get_agent_job_manager().submit(
                tool_name=tool.name,
                requester_id=requester_id,
                umo=event.unified_msg_origin,
                arguments=tool_args,
                runner=_run_in_background,
                timeout_seconds=int(
                    getattr(tool, "background_timeout_seconds", 120) or 120
                ),
                cancellable=bool(getattr(tool, "background_cancellable", True)),
                on_complete=_notify_completion,
            )
            text_content = mcp.types.TextContent(
                type="text",
                text=(
                    f"Background task submitted. job_id={job.job_id}. "
                    "Use agent_job_status or agent_job_result to inspect it."
                ),
            )
            yield mcp.types.CallToolResult(content=[text_content])

            return
        else:
            async for r in cls._execute_local(tool, run_context, **tool_args):
                yield r
            return

    @classmethod
    def _get_runtime_computer_tools(
        cls,
        runtime: str,
        tool_mgr,
        booter: str | None = None,
    ) -> dict[str, FunctionTool]:
        booter = "" if booter is None else str(booter).lower()
        if runtime == "sandbox":
            shell_tool = tool_mgr.get_builtin_tool(ExecuteShellTool)
            python_tool = tool_mgr.get_builtin_tool(PythonTool)
            upload_tool = tool_mgr.get_builtin_tool(FileUploadTool)
            download_tool = tool_mgr.get_builtin_tool(FileDownloadTool)
            read_tool = tool_mgr.get_builtin_tool(FileReadTool)
            write_tool = tool_mgr.get_builtin_tool(FileWriteTool)
            edit_tool = tool_mgr.get_builtin_tool(FileEditTool)
            grep_tool = tool_mgr.get_builtin_tool(GrepTool)
            tools = {
                shell_tool.name: shell_tool,
                python_tool.name: python_tool,
                upload_tool.name: upload_tool,
                download_tool.name: download_tool,
                read_tool.name: read_tool,
                write_tool.name: write_tool,
                edit_tool.name: edit_tool,
                grep_tool.name: grep_tool,
            }
            if booter == "cua":
                screenshot_tool = tool_mgr.get_builtin_tool(CuaScreenshotTool)
                mouse_click_tool = tool_mgr.get_builtin_tool(CuaMouseClickTool)
                keyboard_type_tool = tool_mgr.get_builtin_tool(CuaKeyboardTypeTool)
                tools.update(
                    {
                        screenshot_tool.name: screenshot_tool,
                        mouse_click_tool.name: mouse_click_tool,
                        keyboard_type_tool.name: keyboard_type_tool,
                    }
                )
            return tools
        if runtime == "local":
            shell_tool = tool_mgr.get_builtin_tool(ExecuteShellTool)
            python_tool = tool_mgr.get_builtin_tool(LocalPythonTool)
            read_tool = tool_mgr.get_builtin_tool(FileReadTool)
            write_tool = tool_mgr.get_builtin_tool(FileWriteTool)
            edit_tool = tool_mgr.get_builtin_tool(FileEditTool)
            grep_tool = tool_mgr.get_builtin_tool(GrepTool)
            return {
                shell_tool.name: shell_tool,
                python_tool.name: python_tool,
                read_tool.name: read_tool,
                write_tool.name: write_tool,
                edit_tool.name: edit_tool,
                grep_tool.name: grep_tool,
            }
        return {}

    @classmethod
    def _build_handoff_toolset(
        cls,
        run_context: ContextWrapper[AstrAgentContext],
        tools: list[str | FunctionTool] | None,
    ) -> ToolSet | None:
        ctx = run_context.context.context
        event = run_context.context.event
        cfg = ctx.get_config(umo=event.unified_msg_origin)
        provider_settings = cfg.get("provider_settings", {})
        runtime = str(provider_settings.get("computer_use_runtime", "local"))
        tool_mgr = (
            ctx.get_llm_tool_manager()
            if hasattr(ctx, "get_llm_tool_manager")
            else llm_tools
        )
        runtime_computer_tools = cls._get_runtime_computer_tools(
            runtime,
            tool_mgr,
            provider_settings.get("sandbox", {}).get("booter"),
        )

        # Keep persona semantics aligned with the main agent: tools=None means
        # "all tools", including runtime computer-use tools.
        if tools is None:
            toolset = ToolSet()
            handoff_names = {
                tool.name
                for tool in tool_mgr.func_list
                if isinstance(tool, HandoffTool)
            }
            for registered_tool in tool_mgr.get_full_tool_set():
                if registered_tool.name in handoff_names:
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
                if registered_tool and registered_tool.active:
                    toolset.add_tool(registered_tool)
                    continue
                runtime_tool = runtime_computer_tools.get(tool_name_or_obj)
                if runtime_tool:
                    toolset.add_tool(runtime_tool)
            elif isinstance(tool_name_or_obj, FunctionTool):
                toolset.add_tool(tool_name_or_obj)
        return None if toolset.empty() else toolset

    @classmethod
    async def _execute_handoff(
        cls,
        tool: HandoffTool,
        run_context: ContextWrapper[AstrAgentContext],
        *,
        image_urls_prepared: bool = False,
        **tool_args: T.Any,
    ):
        tool_args = dict(tool_args)
        input_ = tool_args.get("input")
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
        toolset = cls._build_handoff_toolset(run_context, tool.agent.tools)

        ctx = run_context.context.context
        event = run_context.context.event
        umo = event.unified_msg_origin

        # Use per-subagent provider override if configured; otherwise fall back
        # to the current/default provider resolution.
        prov_id = getattr(
            tool, "provider_id", None
        ) or await ctx.get_current_chat_provider_id(umo)

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
                        else Message.model_validate(dialog)
                    )
                except Exception:
                    continue

        prov_settings: dict = ctx.get_config(umo=umo).get("provider_settings", {})
        agent_max_step = int(prov_settings.get("max_agent_step", 30))
        stream = prov_settings.get("streaming_response", False)
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
        yield mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text=llm_resp.completion_text)]
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
            except Exception as e:  # noqa: BLE001
                logger.error(
                    f"Background handoff {task_id} ({tool.name}) failed: {e!s}",
                    exc_info=True,
                )

        asyncio.create_task(_run_handoff_in_background())

        text_content = mcp.types.TextContent(
            type="text",
            text=(
                f"Background task dedicated to subagent '{tool.agent.name}' submitted. task_id={task_id}. "
                f"The subagent '{tool.agent.name}' is working on the task on hehalf you. "
                f"You will be notified when it finishes."
            ),
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
            note=(
                event.get_extra("background_note")
                or f"Background task for subagent '{tool.agent.name}' finished."
            ),
            summary_name=f"Dedicated to subagent `{tool.agent.name}`",
            extra_result_fields={"subagent_name": tool.agent.name},
        )

    @classmethod
    async def _execute_background(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[AstrAgentContext],
        **tool_args,
    ) -> ToolOutcome:
        """Execute one background tool without starting a second Agent loop.

        Args:
            tool: Registered local function tool.
            run_context: Original authenticated Agent context.
            **tool_args: Schema-validated tool arguments.

        Returns:
            Last normalized tool outcome, or an explicit empty outcome.
        """

        final_outcome: ToolOutcome | None = None
        try:

            async def local_executor(current_tool, current_context, **kwargs):
                async for item in cls._execute_local(
                    current_tool,
                    current_context,
                    tool_call_timeout=int(
                        getattr(current_tool, "background_timeout_seconds", 120) or 120
                    ),
                    **kwargs,
                ):
                    yield item

            async for r in ToolGateway.invoke(
                local_executor,
                tool,
                run_context,
                **tool_args,
            ):
                if isinstance(r, ToolOutcome):
                    final_outcome = r
                elif isinstance(r, mcp.types.CallToolResult):
                    final_outcome = ToolOutcome(
                        status=(
                            "failed"
                            if r.isError
                            else "success"
                            if r.content or r.structuredContent
                            else "empty"
                        ),
                        result=r,
                        retryable=bool(
                            r.isError or not (r.content or r.structuredContent)
                        ),
                        error_code="tool_error" if r.isError else "",
                    )
        except Exception as e:
            return ToolOutcome(
                status="failed",
                retryable=True,
                error_code="background_execution_failed",
                diagnostics=str(e)[:1000],
                result=mcp.types.CallToolResult(
                    content=[
                        mcp.types.TextContent(
                            type="text",
                            text=f"Background task execution failed: {e!s}",
                        )
                    ],
                    isError=True,
                ),
            )
        return final_outcome or ToolOutcome(
            status="empty",
            retryable=True,
            error_code="empty_result",
            diagnostics="Background tool produced no normalized result.",
        )

    @classmethod
    async def _wake_main_agent_for_background_result(
        cls,
        run_context: ContextWrapper[AstrAgentContext],
        *,
        task_id: str,
        tool_name: str,
        result_text: str,
        tool_args: dict[str, T.Any],
        note: str,
        summary_name: str,
        extra_result_fields: dict[str, T.Any] | None = None,
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
        conv = await _get_session_conv(event=cron_event, plugin_context=ctx)
        req.conversation = conv
        context = json.loads(conv.history)
        if context:
            req.contexts = context
            context_dump = req._print_friendly_context()
            req.contexts = []
            req.system_prompt += (
                "\n\nBellow is you and user previous conversation history:\n"
                f"{context_dump}"
            )

        bg = json.dumps(extras["background_task_result"], ensure_ascii=False)
        req.system_prompt += BACKGROUND_TASK_RESULT_WOKE_SYSTEM_PROMPT.format(
            background_task_result=bg
        )
        req.prompt = (
            "Proceed according to your system instructions. "
            "Output using same language as previous conversation. "
            "If you need to deliver the result to the user immediately, "
            "you MUST use `send_message_to_user` tool to send the message directly to the user, "
            "otherwise the user will not see the result. "
            "After completing your task, summarize and output your actions and results. "
        )
        if not req.func_tool:
            req.func_tool = ToolSet()
        req.func_tool.add_tool(
            ctx.get_llm_tool_manager().get_builtin_tool(SendMessageToUserTool)
        )

        result = await build_main_agent(
            event=cron_event, plugin_context=ctx, config=config, req=req
        )
        if not result:
            logger.error(f"Failed to build main agent for background task {tool_name}.")
            return

        runner = result.agent_runner
        async for _ in runner.step_until_done(30):
            # agent will send message to user via using tools
            pass
        llm_resp = runner.get_final_llm_resp()
        task_meta = extras.get("background_task_result", {})
        summary_note = (
            f"[BackgroundTask] {summary_name} "
            f"(task_id={task_meta.get('task_id', task_id)}) finished. "
            f"Result: {task_meta.get('result') or result_text or 'no content'}"
        )
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

        # 检查 tool 下有没有 run 方法
        if not tool.handler and not hasattr(tool, "run") and not is_override_call:
            raise ValueError("Tool must have a valid handler or override 'run' method.")

        awaitable = None
        method_name = ""
        if tool.handler:
            awaitable = tool.handler
            method_name = "decorator_handler"
        elif is_override_call:
            awaitable = tool.call
            method_name = "call"
        elif hasattr(tool, "run"):
            awaitable = getattr(tool, "run")
            method_name = "run"
        if awaitable is None:
            raise ValueError("Tool must have a valid handler or override 'run' method.")

        send_count_before = int(getattr(event, "_send_oper_count", 0) or 0)
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
                        has_content = bool(resp.content or resp.structuredContent)
                        yield ToolOutcome(
                            status=(
                                "failed"
                                if resp.isError
                                else "success"
                                if has_content
                                else "empty"
                            ),
                            result=resp,
                            retryable=bool(resp.isError or not has_content),
                            error_code=(
                                "tool_error"
                                if resp.isError
                                else "empty_result"
                                if not has_content
                                else ""
                            ),
                        )
                    else:
                        text = str(resp).strip()
                        text_content = mcp.types.TextContent(
                            type="text",
                            text=text or "The tool returned an empty result.",
                        )
                        yield ToolOutcome(
                            status="success" if text else "empty",
                            result=mcp.types.CallToolResult(
                                content=[text_content], isError=not bool(text)
                            ),
                            retryable=not bool(text),
                            error_code="" if text else "empty_result",
                        )
                else:
                    direct_sent = (
                        int(getattr(event, "_send_oper_count", 0) or 0)
                        > send_count_before
                    )
                    if hasattr(event, "get_extra"):
                        try:
                            terminal_marker = event.get_extra(
                                "agent_control_terminal_sent", False
                            )
                        except TypeError:
                            terminal_marker = event.get_extra(
                                "agent_control_terminal_sent"
                            )
                        direct_sent = direct_sent or bool(terminal_marker)
                    if res := run_context.context.event.get_result():
                        if res.chain:
                            try:
                                await event.send(
                                    MessageChain(
                                        chain=res.chain,
                                        type="tool_direct_result",
                                    )
                                )
                                direct_sent = True
                            except Exception as e:
                                logger.error(
                                    f"Tool 直接发送消息失败: {e}",
                                    exc_info=True,
                                )
                    if direct_sent:
                        # Mark the event before the normalized outcome reaches
                        # the Agent loop. The response stage uses this terminal
                        # flag to suppress a second plain-text reply after a
                        # plugin has already delivered a message chain.
                        if hasattr(event, "set_extra"):
                            event.set_extra("agent_control_terminal_sent", True)
                        yield ToolOutcome(
                            status="direct_sent",
                            result=mcp.types.CallToolResult(
                                content=[
                                    mcp.types.TextContent(
                                        type="text",
                                        text="The tool sent its result directly to the user.",
                                    )
                                ]
                            ),
                            terminal=True,
                            side_effect_performed=True,
                        )
                    else:
                        yield ToolOutcome(
                            status="empty",
                            result=mcp.types.CallToolResult(
                                content=[
                                    mcp.types.TextContent(
                                        type="text",
                                        text=(
                                            "Tool execution produced no result and did not "
                                            "send a message. Use an approved fallback or tell "
                                            "the user that the capability failed."
                                        ),
                                    )
                                ],
                                isError=True,
                            ),
                            retryable=True,
                            error_code="empty_result",
                        )
            except asyncio.TimeoutError:
                raise Exception(
                    f"tool {tool.name} execution timeout after {tool_call_timeout or run_context.tool_call_timeout} seconds.",
                )
            except StopAsyncIteration:
                break

    @classmethod
    async def _execute_mcp(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[AstrAgentContext],
        **tool_args,
    ):
        """Execute an MCP-style tool and always emit a normalized outcome.

        MCP adapters in the wild return ``CallToolResult``, plain text, or
        ``None``.  Previously ``None`` silently ended the tool stream, which
        made the Agent treat an unexecuted tool as a completed turn.

        Args:
            tool: Registered MCP-compatible tool.
            run_context: Authenticated Agent context.
            **tool_args: Schema-validated arguments.
        """

        try:
            res = await tool.call(run_context, **tool_args)
        except asyncio.TimeoutError:
            yield ToolOutcome(
                status="failed",
                retryable=True,
                error_code="timeout",
                diagnostics=f"MCP tool {tool.name} timed out.",
                result=mcp.types.CallToolResult(
                    content=[
                        mcp.types.TextContent(
                            type="text", text="error: MCP tool execution timed out."
                        )
                    ],
                    isError=True,
                ),
            )
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("MCP tool %s failed", tool.name)
            message = str(exc)[:1000]
            yield ToolOutcome(
                status="failed",
                retryable=True,
                error_code="mcp_error",
                diagnostics=message,
                result=mcp.types.CallToolResult(
                    content=[
                        mcp.types.TextContent(
                            type="text", text=f"error: MCP tool failed: {message}"
                        )
                    ],
                    isError=True,
                ),
            )
            return

        if isinstance(res, ToolOutcome):
            yield res
            return
        if isinstance(res, mcp.types.CallToolResult):
            has_content = bool(res.content or res.structuredContent)
            yield ToolOutcome(
                status="failed"
                if res.isError
                else "success"
                if has_content
                else "empty",
                result=res,
                retryable=bool(res.isError or not has_content),
                error_code=(
                    "mcp_error"
                    if res.isError
                    else "empty_result"
                    if not has_content
                    else ""
                ),
            )
            return

        text = str(res or "").strip()
        result = mcp.types.CallToolResult(
            content=[
                mcp.types.TextContent(
                    type="text", text=text or "error: MCP tool returned no content."
                )
            ],
            isError=not bool(text),
        )
        yield ToolOutcome(
            status="success" if text else "empty",
            result=result,
            retryable=not bool(text),
            error_code="" if text else "empty_result",
        )


async def call_local_llm_tool(
    context: ContextWrapper[AstrAgentContext],
    handler: T.Callable[
        ...,
        T.Awaitable[MessageEventResult | mcp.types.CallToolResult | str | None]
        | T.AsyncGenerator[MessageEventResult | CommandResult | str | None, None],
    ],
    method_name: str,
    *args,
    **kwargs,
) -> T.AsyncGenerator[T.Any, None]:
    """执行本地 LLM 工具的处理函数并处理其返回结果"""
    ready_to_call = None  # 一个协程或者异步生成器

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
        # 获取函数的签名（包括类型），除了第一个 event/context 参数。
        try:
            sig = inspect.signature(handler)
            params = list(sig.parameters.values())
            # 跳过第一个参数（event 或 context）
            if params:
                params = params[1:]

            param_strs = []
            for param in params:
                param_str = param.name
                if param.annotation != inspect.Parameter.empty:
                    # 获取类型注解的字符串表示
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
            f"Tool handler parameter mismatch, please check the handler definition. Handler parameters: {handler_param_str}"
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
                # 这里逐步执行异步生成器, 对于每个 yield 返回的 ret, 执行下面的代码
                # 返回值只能是 MessageEventResult 或者 None（无返回值）
                _has_yielded = True
                if isinstance(ret, MessageEventResult | CommandResult):
                    # 如果返回值是 MessageEventResult, 设置结果并继续
                    event.set_result(ret)
                    yield
                else:
                    # 如果返回值是 None, 则不设置结果并继续
                    # 继续执行后续阶段
                    yield ret
            if not _has_yielded:
                # 如果这个异步生成器没有执行到 yield 分支
                yield
        except Exception as e:
            logger.error(f"Previous Error: {trace_}")
            raise e
    elif inspect.iscoroutine(ready_to_call):
        # 如果只是一个协程, 直接执行
        ret = await ready_to_call
        if isinstance(ret, MessageEventResult | CommandResult):
            event.set_result(ret)
            yield
        else:
            yield ret
