from __future__ import annotations

from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import InvalidRequest, NotFound
from astrbot_sdk.llm import AgentResponse, ProviderKind

from .llm import _resolve_provider

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


def _build_event(umo: Any, sdk_event: Any, context: Context) -> Any:
    """Build the agent event for a plugin-initiated run.

    Args:
        umo: Target SDK session.
        sdk_event: Optional triggering SDK event.
        context: Host context used for message delivery.

    Returns:
        A Host event scoped to the requested session.
    """
    from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
    from astrbot.core.platform.astrbot_message import MessageMember
    from astrbot.core.platform.message_session import MessageSession
    from astrbot.core.platform.platform_metadata import PlatformMetadata

    from ..convert import to_umo_string

    session = MessageSession.from_str(to_umo_string(umo))
    event = AgentWakeupEvent(
        context=context,
        session=session,
        platform_meta=PlatformMetadata(
            name=sdk_event.platform_type if sdk_event else session.platform_id,
            description="SDK plugin agent run",
            id=session.platform_id,
        ),
        prompt=sdk_event.text if sdk_event else "",
        source="plugin",
    )
    if sdk_event is not None:
        event.message_obj.sender = MessageMember(
            user_id=sdk_event.sender.id, nickname=sdk_event.sender.name
        )
    return event


class AgentRunService:
    """Serve the llm.agent capability by running the built-in tool-loop agent.

    The agent's toolset is scoped to the calling plugin's own registered
    tools; tool calls route back into the plugin through the usual stubs.
    """

    capability_id = "llm.agent"

    def __init__(
        self,
        context: Context,
        tool_names: list[str],
        store: Any = None,
    ) -> None:
        """Initialize the service.

        Args:
            context: AstrBot star context.
            tool_names: Tool names registered by the calling plugin, used as
                the agent's toolset scope.
            store: Optional asset store for content part resolution.
        """
        self._context = context
        self._tool_names = tool_names
        self._store = store

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve the run operation."""
        if operation != "run":
            raise NotFound(f"unknown agent operation: {operation}")
        umo = payload.get("umo")
        if umo is None:
            raise InvalidRequest("agent run requires a umo")

        # Imported lazily: these modules sit upstream of the bridge in the
        # import graph, and eager import creates a cycle at startup.
        from astrbot.core.agent.hooks import BaseAgentRunHooks
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            ToolLoopAgentRunner,
        )
        from astrbot.core.agent.tool import ToolSet
        from astrbot.core.astr_agent_context import (
            AgentContextWrapper,
            AstrAgentContext,
        )
        from astrbot.core.astr_agent_runtime.tool_executor import FunctionToolExecutor
        from astrbot.core.provider.entities import ProviderRequest
        from astrbot.core.provider.register import llm_tools

        provider = await _resolve_provider(
            self._context.provider_manager,
            payload,
            default_kind=ProviderKind.CHAT,
        )
        if provider is None:
            raise NotFound("no chat provider available")

        # A Runner can select only tools registered by its own bridge.
        tool_names = payload.get("tools")
        toolset: ToolSet | None = None
        if tool_names:
            toolset = ToolSet()
            for name in tool_names:
                if name in self._tool_names:
                    tool = llm_tools.get_func(name)
                    if tool is not None:
                        toolset.add_tool(tool)

        from ..convert import to_core_context_message

        request = ProviderRequest(
            prompt=payload.get("prompt"),
            contexts=[
                to_core_context_message(
                    message,
                    resolve_asset=self._store.resolve if self._store else None,
                )
                for message in payload.get("messages") or []
            ],
            system_prompt=payload.get("system_prompt") or "",
            func_tool=toolset,
        )

        agent_context = AstrAgentContext(
            context=self._context,
            event=_build_event(umo, payload.get("event"), self._context),
        )
        run_context = AgentContextWrapper(context=agent_context)
        runner = ToolLoopAgentRunner()
        await runner.reset(
            provider=provider,
            request=request,
            run_context=run_context,
            tool_executor=FunctionToolExecutor(),
            agent_hooks=BaseAgentRunHooks(),
            streaming=False,
        )
        max_steps = int(payload.get("max_steps") or 30)
        async for _ in runner.step_until_done(max_steps):
            pass
        response = runner.get_final_llm_resp()
        if response is None:
            raise InvalidRequest("agent did not produce a final response")
        return {
            "response": AgentResponse(
                text=response.completion_text,
                reasoning_content=response.reasoning_content or None,
            ),
        }
