from typing import TYPE_CHECKING, Any

from mcp.types import CallToolResult

from astrbot.core import logger
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_runtime.context import AstrAgentContext
from astrbot.core.astr_agent_runtime.history import ConversationHistoryObserver
from astrbot.core.pipeline.context_utils import call_event_hook
from astrbot.core.star.star_handler import EventType

if TYPE_CHECKING:
    from astrbot.core.provider.entities import ProviderRequest


def _sdk_safe_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_sdk_safe_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _sdk_safe_payload(item) for key, item in value.items()}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
        except Exception:
            return str(value)
        return _sdk_safe_payload(dumped)
    return str(value)


class MainAgentHooks(BaseAgentRunHooks[AstrAgentContext]):
    def __init__(
        self,
        request: "ProviderRequest | None" = None,
        *,
        context_observer: ConversationHistoryObserver | None = None,
    ) -> None:
        """Bind hooks to the prepared native request when one is available.

        Args:
            request: Native request with conversation and tool settings.
            context_observer: Host observer for plugin context mutations.
        """
        self._request = request
        self._context_observer = context_observer

    async def on_agent_begin(
        self, run_context: ContextWrapper[AstrAgentContext]
    ) -> None:
        if self._request is not None:
            from astrbot.core.astr_agent_runtime.main_agent import subagent

            conversation = self._request.conversation
            await subagent.begin_main_agent(
                run_context,
                conversation_id=conversation.cid if conversation is not None else None,
                tools=self._request.func_tool,
            )
        await call_event_hook(
            run_context.context.event,
            EventType.OnAgentBeginEvent,
            run_context,
            context_observer=self._context_observer,
        )

    async def on_llm_response(self, run_context, llm_response) -> None:
        if llm_response.reasoning_content:
            # we will use this in result_decorate stage to inject reasoning content to chain
            run_context.context.event.set_extra(
                "_llm_reasoning_content", llm_response.reasoning_content
            )

        await call_event_hook(
            run_context.context.event,
            EventType.OnLLMResponseEvent,
            llm_response,
            context_observer=self._context_observer,
        )

        sdk_plugin_bridge = getattr(
            getattr(run_context.context, "context", None),
            "sdk_plugin_bridge",
            None,
        )
        if sdk_plugin_bridge is not None:
            try:
                await sdk_plugin_bridge.dispatch_message_event(
                    "llm_response",
                    run_context.context.event,
                    {
                        "completion_text": (
                            llm_response.completion_text if llm_response else ""
                        ),
                        "tool_call_names": (
                            list(llm_response.tools_call_name)
                            if llm_response and llm_response.tools_call_name
                            else []
                        ),
                    },
                    llm_response=llm_response,
                )
            except Exception as exc:
                logger.warning("SDK llm_response dispatch failed: %s", exc)

    async def on_agent_done(self, run_context, llm_response) -> None:
        await call_event_hook(
            run_context.context.event,
            EventType.OnAgentDoneEvent,
            run_context,
            llm_response,
            context_observer=self._context_observer,
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
            context_observer=self._context_observer,
        )

        sdk_plugin_bridge = getattr(
            getattr(run_context.context, "context", None),
            "sdk_plugin_bridge",
            None,
        )
        if sdk_plugin_bridge is not None:
            try:
                await sdk_plugin_bridge.dispatch_message_event(
                    "using_llm_tool",
                    run_context.context.event,
                    {
                        "tool_name": tool.name,
                        "tool_args": _sdk_safe_payload(tool_args),
                    },
                )
            except Exception as exc:
                logger.warning("SDK using_llm_tool dispatch failed: %s", exc)

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
            context_observer=self._context_observer,
        )

        sdk_plugin_bridge = getattr(
            getattr(run_context.context, "context", None),
            "sdk_plugin_bridge",
            None,
        )
        if sdk_plugin_bridge is not None:
            try:
                await sdk_plugin_bridge.dispatch_message_event(
                    "llm_tool_respond",
                    run_context.context.event,
                    {
                        "tool_name": tool.name,
                        "tool_args": _sdk_safe_payload(tool_args),
                        "tool_result": _sdk_safe_payload(tool_result),
                    },
                )
            except Exception as exc:
                logger.warning("SDK llm_tool_respond dispatch failed: %s", exc)


class EmptyAgentHooks(BaseAgentRunHooks[AstrAgentContext]):
    pass
