from __future__ import annotations

from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import InvalidRequest, NotFound
from astrbot_sdk.llm import AgentResponse, ProviderKind

from .llm import _resolve_provider

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


def _build_event(umo: Any, sdk_event: Any, context: Context) -> Any:
    """Build the agent event for a plugin-initiated run.

    When the SDK MessageEvent is available its real fields are preserved
    (sender, text, timestamp); otherwise a minimal UMO-only event is built,
    mirroring the CronMessageEvent pattern.
    """
    from astrbot.core.cron.events import CronMessageEvent
    from astrbot.core.platform.message_session import (
        MessageSesion as MessageSession,
    )

    from ..convert import to_core_message_type

    session = MessageSession(
        platform_name=umo.platform_id,
        message_type=to_core_message_type(umo.message_type),
        session_id=umo.session_id,
    )
    if sdk_event is not None:
        return CronMessageEvent(
            context=context,
            session=session,
            message=sdk_event.text,
            sender_id=sdk_event.sender.id,
            sender_name=sdk_event.sender.name,
            message_type=session.message_type,
        )
    return CronMessageEvent(
        context=context,
        session=session,
        message="",
        message_type=session.message_type,
    )


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
        from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
        from astrbot.core.provider.entities import ProviderRequest
        from astrbot.core.provider.register import llm_tools

        provider = await _resolve_provider(
            self._context.provider_manager,
            payload,
            default_kind=ProviderKind.CHAT,
        )
        if provider is None:
            raise NotFound("no chat provider available")

        # Legacy tool_loop_agent semantics: no tools by default; a names
        # list offers exactly those tools.
        tool_names = payload.get("tools")
        toolset: ToolSet | None = None
        if tool_names:
            toolset = ToolSet()
            for name in tool_names:
                tool = llm_tools.get_func(str(name))
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
