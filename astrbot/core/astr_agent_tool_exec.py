import inspect
import traceback
import typing as T

import mcp

from astrbot import logger
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.message.message_event_result import (
    CommandResult,
    MessageEventResult,
)
from astrbot.core.provider.register import llm_tools
from astrbot.core.tool_execution.application.tool_executor import ToolExecutor
from astrbot.core.tool_execution.errors import MethodResolutionError


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
        prov_id = await ctx.get_current_chat_provider_id(umo)
        llm_resp = await ctx.tool_loop_agent(
            event=event,
            chat_provider_id=prov_id,
            prompt=input_,
            system_prompt=tool.agent.instructions,
            tools=toolset,
            max_steps=30,
            run_hooks=tool.agent.run_hooks,
        )
        yield mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text=llm_resp.completion_text)]
        )

    @classmethod
    async def _execute_local(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[AstrAgentContext],
        **tool_args,
    ):
        """执行本地工具

        使用 ToolExecutor 编排组件完成工具执行。
        """
        event = run_context.context.event
        if not event:
            raise ValueError("Event must be provided for local function tools.")

        executor = ToolExecutor()

        try:
            async for result in executor.execute(tool, run_context, **tool_args):
                yield result
        except MethodResolutionError as e:
            raise ValueError(str(e)) from e

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
