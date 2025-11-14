import asyncio
import inspect
import traceback
import typing as T

import mcp

from astrbot import logger
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.message.message_event_result import (
    CommandResult,
    MessageChain,
    MessageEventResult,
)
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.provider.register import llm_tools

from .astr_agent_context import AgentContextWrapper
from .astr_agent_run_util import AgentRunner, run_agent


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
        input_ = tool_args.get("input", "agent")
        agent_runner = AgentRunner()

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

        request = ProviderRequest(
            prompt=input_,
            system_prompt=tool.description or "",
            image_urls=[],  # 暂时不传递原始 agent 的上下文
            contexts=[],  # 暂时不传递原始 agent 的上下文
            func_tool=toolset,
        )
        astr_agent_ctx = AstrAgentContext(
            provider=run_context.context.provider,
            event=run_context.context.event,
        )

        event = run_context.context.event

        logger.debug(f"正在将任务委托给 Agent: {tool.agent.name}, input: {input_}")
        await event.send(
            MessageChain().message("✨ 正在将任务委托给 Agent: " + tool.agent.name),
        )

        await agent_runner.reset(
            provider=run_context.context.provider,
            request=request,
            run_context=AgentContextWrapper(
                context=astr_agent_ctx,
                tool_call_timeout=run_context.tool_call_timeout,
            ),
            tool_executor=FunctionToolExecutor(),
            agent_hooks=tool.agent.run_hooks or BaseAgentRunHooks[AstrAgentContext](),
        )

        async for _ in run_agent(agent_runner, 15, True):
            pass

        if agent_runner.done():
            llm_response = agent_runner.get_final_llm_resp()

            if not llm_response:
                text_content = mcp.types.TextContent(
                    type="text",
                    text=f"error when deligate task to {tool.agent.name}",
                )
                yield mcp.types.CallToolResult(content=[text_content])
                return

            logger.debug(
                f"Agent  {tool.agent.name} 任务完成, response: {llm_response.completion_text}",
            )

            result = (
                f"Agent {tool.agent.name} respond with: {llm_response.completion_text}\n\n"
                "Note: If the result is error or need user provide more information, please provide more information to the agent(you can ask user for more information first)."
            )

            text_content = mcp.types.TextContent(
                type="text",
                text=result,
            )
            yield mcp.types.CallToolResult(content=[text_content])
        else:
            text_content = mcp.types.TextContent(
                type="text",
                text=f"error when deligate task to {tool.agent.name}",
            )
            yield mcp.types.CallToolResult(content=[text_content])
        return

    @classmethod
    async def _execute_local(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[AstrAgentContext],
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
                    timeout=run_context.tool_call_timeout,
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
                                    f"Tool 直接发送消息失败: {e}",
                                    exc_info=True,
                                )
                    yield None
            except asyncio.TimeoutError:
                raise Exception(
                    f"tool {tool.name} execution timeout after {run_context.tool_call_timeout} seconds.",
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
    handler: T.Callable[..., T.Awaitable[T.Any]],
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
        logger.error(f"调用本地 LLM 工具时出错: {e}", exc_info=True)
    except TypeError:
        logger.error("处理函数参数不匹配，请检查 handler 的定义。", exc_info=True)
    except Exception as e:
        trace_ = traceback.format_exc()
        logger.error(f"调用本地 LLM 工具时出错: {e}\n{trace_}")

    if not ready_to_call:
        return

    if inspect.isasyncgen(ready_to_call):
        _has_yielded = False
        try:
            async for ret in ready_to_call:
                # 这里逐步执行异步生成器, 对于每个 yield 返回的 ret, 执行下面的代码
                # 返回值只能是 MessageEventResult 或者 None（无返回值）
                _has_yielded = True
                if isinstance(ret, (MessageEventResult, CommandResult)):
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
        if isinstance(ret, (MessageEventResult, CommandResult)):
            event.set_result(ret)
            yield
        else:
            yield ret
