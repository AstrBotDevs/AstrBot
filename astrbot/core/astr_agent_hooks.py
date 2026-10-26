from typing import Any

from mcp.types import CallToolResult

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.pipeline.context_utils import call_event_hook
from astrbot.core.star.star_handler import EventType, star_handlers_registry


class MainAgentHooks(BaseAgentRunHooks[AstrAgentContext]):
    def should_buffer_streaming_response(
        self, run_context: ContextWrapper[AstrAgentContext]
    ) -> bool:
        event = run_context.context.event
        return bool(
            star_handlers_registry.get_handlers_by_event_type(
                EventType.OnLLMResponseEvent,
                plugins_name=event.plugins_name,
            )
        )

    async def on_agent_begin(
        self, run_context: ContextWrapper[AstrAgentContext]
    ) -> None:
        await call_event_hook(
            run_context.context.event,
            EventType.OnAgentBeginEvent,
            run_context,
        )

    async def on_agent_done(self, run_context, llm_response) -> None:
        # 执行事件钩子
        if llm_response and llm_response.reasoning_content:
            # we will use this in result_decorate stage to inject reasoning content to chain
            run_context.context.event.set_extra(
                "_llm_reasoning_content", llm_response.reasoning_content
            )

        await call_event_hook(
            run_context.context.event,
            EventType.OnLLMResponseEvent,
            llm_response,
        )
        await call_event_hook(
            run_context.context.event,
            EventType.OnAgentDoneEvent,
            run_context,
            llm_response,
        )

    async def on_agent_response(self, run_context, llm_response) -> None:
        await call_event_hook(
            run_context.context.event,
            EventType.OnLLMResponseEvent,
            llm_response,
        )

    async def on_tool_start(
        self,
        run_context: ContextWrapper[AstrAgentContext],
        tool: FunctionTool[Any],
        tool_args: dict | None,
    ) -> None:
        await call_event_hook(
            run_context.context.event,
            EventType.OnUsingLLMToolEvent,
            tool,
            tool_args,
        )

    async def on_tool_end(
        self,
        run_context: ContextWrapper[AstrAgentContext],
        tool: FunctionTool[Any],
        tool_args: dict | None,
        tool_result: CallToolResult | None,
    ) -> None:
        run_context.context.event.clear_result()
        await call_event_hook(
            run_context.context.event,
            EventType.OnLLMToolRespondEvent,
            tool,
            tool_args,
            tool_result,
        )


class EmptyAgentHooks(BaseAgentRunHooks[AstrAgentContext]):
    def should_buffer_streaming_response(
        self, run_context: ContextWrapper[AstrAgentContext]
    ) -> bool:
        return False


MAIN_AGENT_HOOKS = MainAgentHooks()
