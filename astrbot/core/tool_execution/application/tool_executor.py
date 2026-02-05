"""工具执行编排器

组合各组件，编排工具执行流程。
"""

import asyncio
from typing import Any, AsyncGenerator

import mcp.types

from astrbot.core.tool_execution.domain.config import BACKGROUND_TOOL_NAMES
from astrbot.core.tool_execution.interfaces import (
    IMethodResolver,
    IResultProcessor,
    ITimeoutStrategy,
    ITimeoutHandler,
)


class ToolExecutor:
    """工具执行编排器"""

    def __init__(
        self,
        method_resolver: IMethodResolver = None,
        result_processor: IResultProcessor = None,
        timeout_strategy: ITimeoutStrategy = None,
        timeout_handler: ITimeoutHandler = None,
    ):
        self._method_resolver = method_resolver
        self._result_processor = result_processor
        self._timeout_strategy = timeout_strategy
        self._timeout_handler = timeout_handler

    @property
    def method_resolver(self) -> IMethodResolver:
        if self._method_resolver is None:
            from astrbot.core.tool_execution.infrastructure.handler import (
                MethodResolver,
            )

            self._method_resolver = MethodResolver()
        return self._method_resolver

    @property
    def result_processor(self) -> IResultProcessor:
        if self._result_processor is None:
            from astrbot.core.tool_execution.infrastructure.handler import (
                ResultProcessor,
            )

            self._result_processor = ResultProcessor()
        return self._result_processor

    @property
    def timeout_strategy(self) -> ITimeoutStrategy:
        if self._timeout_strategy is None:
            from astrbot.core.tool_execution.infrastructure.timeout import (
                TimeoutStrategy,
            )

            self._timeout_strategy = TimeoutStrategy()
        return self._timeout_strategy

    @property
    def timeout_handler(self) -> ITimeoutHandler:
        if self._timeout_handler is None:
            from astrbot.core.tool_execution.infrastructure.timeout import (
                BackgroundHandler,
            )

            self._timeout_handler = BackgroundHandler()
        return self._timeout_handler

    async def execute(
        self, tool: Any, run_context: Any, **tool_args
    ) -> AsyncGenerator[mcp.types.CallToolResult, None]:
        """执行工具"""
        handler, method_name = self.method_resolver.resolve(tool)

        timeout_enabled = self._should_enable_timeout(
            run_context.tool_call_timeout, tool.name
        )

        async for result in self._execute_with_timeout(
            tool, run_context, handler, method_name, timeout_enabled, **tool_args
        ):
            yield result

    def _should_enable_timeout(self, timeout: float, tool_name: str) -> bool:
        """判断是否启用超时"""
        return timeout > 0 and tool_name not in BACKGROUND_TOOL_NAMES

    async def _execute_with_timeout(
        self, tool, run_context, handler, method_name, timeout_enabled, **tool_args
    ) -> AsyncGenerator[mcp.types.CallToolResult, None]:
        """带超时控制的执行"""
        from astrbot.core.astr_agent_tool_exec import call_local_llm_tool
        from astrbot.core.tool_execution.infrastructure.handler import ResultProcessor

        wrapper = call_local_llm_tool(
            context=run_context,
            handler=handler,
            method_name=method_name,
            **tool_args,
        )

        # 创建带上下文的结果处理器
        result_processor = ResultProcessor(run_context)

        while True:
            try:
                if timeout_enabled:
                    resp = await self.timeout_strategy.execute(
                        anext(wrapper), run_context.tool_call_timeout
                    )
                else:
                    resp = await anext(wrapper)

                processed = await result_processor.process(resp)
                if processed:
                    yield processed

            except asyncio.TimeoutError:
                ctx = self._build_timeout_context(tool, run_context, handler, tool_args)
                result = await self.timeout_handler.handle_timeout(ctx)
                yield result
                return
            except StopAsyncIteration:
                break

    def _build_timeout_context(self, tool, run_context, handler, tool_args) -> dict:
        """构建超时上下文"""
        event = run_context.context.event
        return {
            "tool_name": tool.name,
            "tool_args": tool_args,
            "session_id": event.unified_msg_origin,
            "handler": handler,
            "event": event,
            "event_queue": run_context.context.context.get_event_queue(),
        }
