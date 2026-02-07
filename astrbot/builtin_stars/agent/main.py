from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.core import logger
from astrbot.core.pipeline.engine.node_context import NodePacket
from astrbot.core.star.node_star import NodeResult, NodeStar

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


class AgentNode(NodeStar):
    """Agent execution node (local + third-party)."""

    async def process(self, event: AstrMessageEvent) -> NodeResult:
        ctx = event.node_context

        # 合并上游输出作为 agent 输入
        if ctx:
            merged_input = await event.get_node_input(strategy="text_concat")
            if isinstance(merged_input, str):
                if merged_input.strip():
                    ctx.input = NodePacket.create(merged_input)
            elif merged_input is not None:
                ctx.input = NodePacket.create(merged_input)

        if event.get_extra("_provider_request_consumed", False):
            return NodeResult.SKIP

        has_provider_request = event.get_extra("has_provider_request", False)
        if not has_provider_request:
            has_upstream_input = bool(ctx and ctx.input is not None)
            should_wake = (
                not event._has_send_oper
                and event.is_at_or_wake_command
                and not event.call_llm
            )
            if not (has_upstream_input or should_wake):
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
