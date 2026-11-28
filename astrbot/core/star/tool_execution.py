"""Invoke plugin tools through their existing event and result contract."""

import inspect
import traceback
import typing as T
from contextlib import aclosing

import mcp

from astrbot import logger
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.message.message_event_result import CommandResult, MessageEventResult
from astrbot.core.utils.async_generator import iterate_in_task


async def call_local_llm_tool(
    context: ContextWrapper[AstrAgentContext],
    handler: T.Callable[
        ...,
        T.Awaitable[MessageEventResult | mcp.types.CallToolResult | str | None]
        | T.AsyncGenerator[MessageEventResult | CommandResult | str | None, None],
    ],
    method_name: str,
    *args,
    tool: FunctionTool | None = None,
    **kwargs,
) -> T.AsyncGenerator[T.Any, None]:
    """执行本地 LLM 工具的处理函数并处理其返回结果"""
    ready_to_call = None  # 一个协程或者异步生成器

    trace_ = None

    event = context.context.event

    def check_availability() -> None:
        if tool is not None and not context.is_tool_available(tool):
            raise ValueError(f"Tool {tool.name} is no longer available.")

    check_availability()
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

    is_awaitable = inspect.isawaitable(ready_to_call)
    if is_awaitable:
        ready_to_call = await ready_to_call

    if inspect.isasyncgen(ready_to_call):

        async def checked_results():
            async with aclosing(ready_to_call):
                # Async generators actually start in the iterator's separate task.
                check_availability()
                async for item in ready_to_call:
                    yield item

        _has_yielded = False
        try:
            async with aclosing(iterate_in_task(checked_results())) as results:
                async for ret in results:
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
    elif is_awaitable:
        ret = ready_to_call
        if isinstance(ret, MessageEventResult | CommandResult):
            event.set_result(ret)
            yield
        else:
            yield ret
