from typing import Any

from mcp.types import CallToolResult

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.pipeline.context_utils import call_event_hook
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.star.star_handler import EventType


def _event_requests_agent_stop(event) -> bool:
    get_extra = getattr(event, "get_extra", None)
    is_stopped = getattr(event, "is_stopped", None)
    return (
        (bool(get_extra("agent_user_aborted")) if callable(get_extra) else False)
        or (bool(get_extra("agent_stop_requested")) if callable(get_extra) else False)
        or (bool(is_stopped()) if callable(is_stopped) else False)
    )


def _build_aborted_llm_response(llm_response) -> LLMResponse:
    return LLMResponse(
        role="assistant",
        completion_text="",
        id=getattr(llm_response, "id", None) if llm_response else None,
        usage=getattr(llm_response, "usage", None) if llm_response else None,
    )


class MainAgentHooks(BaseAgentRunHooks[AstrAgentContext]):
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
        event = run_context.context.event
        suppress_llm_response = _event_requests_agent_stop(event)

        if (
            not suppress_llm_response
            and llm_response
            and llm_response.reasoning_content
        ):
            # we will use this in result_decorate stage to inject reasoning content to chain
            set_extra = getattr(event, "set_extra", None)
            if callable(set_extra):
                set_extra("_llm_reasoning_content", llm_response.reasoning_content)

        if not suppress_llm_response:
            await call_event_hook(
                event,
                EventType.OnLLMResponseEvent,
                llm_response,
            )

        if _event_requests_agent_stop(event):
            set_extra = getattr(event, "set_extra", None)
            if callable(set_extra):
                set_extra("_llm_reasoning_content", None)
            llm_response = _build_aborted_llm_response(llm_response)

        await call_event_hook(
            event,
            EventType.OnAgentDoneEvent,
            run_context,
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
    pass


MAIN_AGENT_HOOKS = MainAgentHooks()
