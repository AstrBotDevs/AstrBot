from __future__ import annotations

from astrbot.core import logger
from astrbot.core.star.node_star import NodeResult, NodeStar


class AgentNode(NodeStar):
    """Agent execution node (local + third-party)."""

    async def process(self, event) -> NodeResult:
        if event.get_extra("skip_agent", False):
            return NodeResult.CONTINUE

        if not self.context.get_config()["provider_settings"].get("enable", True):
            logger.debug("This pipeline does not enable AI capability, skip.")
            return NodeResult.CONTINUE

        chain_config = event.chain_config
        if chain_config and not chain_config.llm_enabled:
            logger.debug(
                f"The session {event.unified_msg_origin} has disabled AI capability."
            )
            return NodeResult.CONTINUE

        has_provider_request = event.get_extra("has_provider_request", False)
        if not has_provider_request:
            # 如果已有结果（命令已设置），跳过 LLM 调用
            if event.get_result():
                return NodeResult.CONTINUE

            if (
                not event._has_send_oper
                and event.is_at_or_wake_command
                and not event.call_llm
            ):
                pass  # 继续 LLM 调用
            else:
                return NodeResult.CONTINUE

        # 从 event 获取 AgentExecutor
        agent_executor = event.agent_executor
        if not agent_executor:
            logger.warning("AgentExecutor missing in event services.")
            return NodeResult.CONTINUE

        outcome = await agent_executor.run(event)
        if outcome.result:
            event.set_result(outcome.result)

        if outcome.stopped or event.is_stopped():
            return NodeResult.STOP

        return NodeResult.CONTINUE
