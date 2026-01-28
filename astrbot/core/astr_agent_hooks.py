from typing import Any

from mcp.types import CallToolResult

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.message import Message
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.pipeline.context_utils import call_event_hook
from astrbot.core.star.star_handler import EventType


class MainAgentHooks(BaseAgentRunHooks[AstrAgentContext]):
    async def on_agent_done(self, run_context, llm_response):
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

    async def on_tool_start(
        self,
        run_context: ContextWrapper[AstrAgentContext],
        tool: FunctionTool[Any],
        tool_args: dict | None,
    ):
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
    ):
        run_context.context.event.clear_result()
        await call_event_hook(
            run_context.context.event,
            EventType.OnLLMToolRespondEvent,
            tool,
            tool_args,
            tool_result,
        )

        # special handle web_search_tavily
        platform_name = run_context.context.event.get_platform_name()
        if (
            platform_name == "webchat"
            and tool.name == "web_search_tavily"
            and len(run_context.messages) > 0
            and tool_result
            and len(tool_result.content)
        ):
            # inject system prompt
            first_part = run_context.messages[0]
            if (
                isinstance(first_part, Message)
                and first_part.role == "system"
                and first_part.content
                and isinstance(first_part.content, str)
            ):
                # we assume system part is str
                first_part.content += (
                    "Always cite web search results you rely on. "
                    "Index is a unique identifier for each search result. "
                    "Use the exact citation format <ref>index</ref> (e.g. <ref>abcd.3</ref>) "
                    "after the sentence that uses the information. Do not invent citations."
                )


class EmptyAgentHooks(BaseAgentRunHooks[AstrAgentContext]):
    pass


MAIN_AGENT_HOOKS = MainAgentHooks()
