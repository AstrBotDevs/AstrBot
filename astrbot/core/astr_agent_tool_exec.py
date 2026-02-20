import asyncio
import inspect
import json
import traceback
import typing as T
import uuid

import mcp

from astrbot import logger
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.message import Message
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.astr_main_agent_resources import (
    BACKGROUND_TASK_RESULT_WOKE_SYSTEM_PROMPT,
    SEND_MESSAGE_TO_USER_TOOL,
)
from astrbot.core.cron.events import CronMessageEvent
from astrbot.core.message.message_event_result import (
    CommandResult,
    MessageChain,
    MessageEventResult,
)
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.provider.entites import ProviderRequest
from astrbot.core.provider.register import llm_tools
from astrbot.core.utils.history_saver import persist_agent_history
from astrbot.core import t


class FunctionToolExecutor(BaseFunctionToolExecutor[AstrAgentContext]):
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
                except Exception as e:  # noqa: BLE001
                    logger.error(
                        t("background-task-failed", task_id=task_id, error=str(e)),
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
            async for r in cls._execute_local(tool, run_context, **tool_args):
                yield r
            return

    @classmethod
    async def _execute_handoff(
        cls,
        tool: HandoffTool,
        run_context: ContextWrapper[AstrAgentContext],
        **tool_args,
    ):
        input_ = tool_args.get("input")

        # make toolset for the agent
        tools = tool.agent.tools
        if tools:
            toolset = ToolSet()
            for t in tools:
                if isinstance(t, str):
                    _t = llm_tools.get_func(t)
                    if _t:
                        toolset.add_tool(_t)
                elif isinstance(t, FunctionTool):
                    toolset.add_tool(t)
        else:
            toolset = None

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

        llm_resp = await ctx.tool_loop_agent(
            event=event,
            chat_provider_id=prov_id,
            prompt=input_,
            system_prompt=tool.agent.instructions,
            tools=toolset,
            contexts=contexts,
            max_steps=30,
            run_hooks=tool.agent.run_hooks,
        )
        yield mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text=llm_resp.completion_text)]
        )

    @classmethod
    async def _execute_background(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[AstrAgentContext],
        task_id: str,
        **tool_args,
    ) -> None:
        from astrbot.core.astr_main_agent import (
            MainAgentBuildConfig,
            _get_session_conv,
            build_main_agent,
        )

        # run the tool
        result_text = ""
        try:
            async for r in cls._execute_local(
                tool, run_context, tool_call_timeout=3600, **tool_args
            ):
                # collect results, currently we just collect the text results
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
        ctx = run_context.context.context

        note = (
            event.get_extra("background_note")
            or f"Background task {tool.name} finished."
        )
        extras = {
            "background_task_result": {
                "task_id": task_id,
                "tool_name": tool.name,
                "result": result_text or "",
                "tool_args": tool_args,
            }
        }
        session = MessageSession.from_str(event.unified_msg_origin)
        cron_event = CronMessageEvent(
            context=ctx,
            session=session,
            message=note,
            extras=extras,
            message_type=session.message_type,
        )
        cron_event.role = event.role
        config = MainAgentBuildConfig(tool_call_timeout=3600)

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
            "Output using same language as previous conversation."
            " After completing your task, summarize and output your actions and results."
        )
        if not req.func_tool:
            req.func_tool = ToolSet()
        req.func_tool.add_tool(SEND_MESSAGE_TO_USER_TOOL)

        result = await build_main_agent(
            event=cron_event, plugin_context=ctx, config=config, req=req
        )
        if not result:
            logger.error(t("background-task-build-failed"))
            return

        runner = result.agent_runner
        async for _ in runner.step_until_done(30):
            # agent will send message to user via using tools
            pass
        llm_resp = runner.get_final_llm_resp()
        task_meta = extras.get("background_task_result", {})
        summary_note = (
            f"[BackgroundTask] {task_meta.get('tool_name', tool.name)} "
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
            logger.warning(t("background-task-no-response"))
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
                    # NOTE: Tool 在这里直接请求发送消息给用户
                    # TODO: 是否需要判断 event.get_result() 是否为空?
                    # 如果为空,则说明没有发送消息给用户,并且返回值为空,将返回一个特殊的 TextContent,其内容如"工具没有返回内容"
                    if res := run_context.context.event.get_result():
                        if res.chain:
                            try:
                                await event.send(
                                    MessageChain(
                                        chain=res.chain,
                                        type="tool_direct_result",
                                    )
                                )
                            except Exception as e:
                                logger.error(
                                    t("tool-send-message-failed", error=str(e), traceback=traceback.format_exc()),
                                    exc_info=True,
                                )
                    yield None
            except asyncio.TimeoutError:
                raise Exception(
                    t("tool-execution-timeout",tool_name=tool.name,timeout=tool_call_timeout or run_context.tool_call_timeout)
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
        res = await tool.call(run_context, **tool_args)
        if not res:
            return
        yield res


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
            raise ValueError(t("unknown-method-name", method_name=method_name))
    except ValueError as e:
        raise Exception(t("tool-execution-value-error", error=str(e))) from e
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
            t("tool-parameter-mismatch", handler_param_str=handler_param_str)
        ) from e
    except Exception as e:
        trace_ = traceback.format_exc()
        raise Exception(
            t("tool-execution-error", error=str(e), traceback=trace_)
        ) from e

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
            logger.error(t("previous-error", traceback=trace_))
            raise e
    elif inspect.iscoroutine(ready_to_call):
        # 如果只是一个协程, 直接执行
        ret = await ready_to_call
        if isinstance(ret, MessageEventResult | CommandResult):
            event.set_result(ret)
            yield
        else:
            yield ret
