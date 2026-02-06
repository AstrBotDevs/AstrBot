from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.core import logger
from astrbot.core.star.node_star import NodeResult, NodeStar

if TYPE_CHECKING:
    from astrbot.core.pipeline.engine.node_context import NodeContext
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


class AgentNode(NodeStar):
    """Agent execution node (local + third-party)."""

    async def process(self, event: AstrMessageEvent) -> NodeResult:
        ctx = event.node_context

        if event.get_extra("skip_agent", False):
            return NodeResult.SKIP

        if not self.context.get_config()["provider_settings"].get("enable", True):
            logger.debug("This pipeline does not enable AI capability, skip.")
            return NodeResult.SKIP

        chain_config = event.chain_config
        if chain_config and not chain_config.llm_enabled:
            logger.debug(
                f"The session {event.unified_msg_origin} has disabled AI capability."
            )
            return NodeResult.SKIP

        # Merge upstream outputs for agent input
        if ctx:
            merged_input = await event.get_node_input(strategy="text_concat")
            if isinstance(merged_input, str):
                if merged_input.strip():
                    ctx.input = merged_input
            elif merged_input is not None:
                ctx.input = merged_input

        if not self._should_execute(event, ctx):
            return NodeResult.SKIP

        # 从 event 获取 AgentExecutor
        agent_executor = event.agent_executor
        if not agent_executor:
            logger.warning("AgentExecutor missing in event services.")
            return NodeResult.SKIP

        outcome = await agent_executor.run(event)

        if outcome.result:
            event.set_node_output(outcome.result)

        if outcome.stopped or event.is_stopped():
            return NodeResult.STOP

        return NodeResult.CONTINUE

    def _should_execute(self, event: AstrMessageEvent, ctx: NodeContext | None) -> bool:
        """Determine whether this agent node should execute."""
        has_provider_request = event.get_extra("has_provider_request", False)
        if has_provider_request:
            return True

        # Upstream node provided input -> chained execution
        if ctx and ctx.input is not None:
            return True

        # Original wake logic (unchanged)
        if (
            not event._has_send_oper
            and event.is_at_or_wake_command
            and not event.call_llm
        ):
            return True

        return False
