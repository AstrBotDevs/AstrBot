from __future__ import annotations

from astrbot.core import logger
from astrbot.core.message.message_event_result import ResultContentType
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

        # 执行 Agent 并收集结果
        latest_result = None
        async for _ in agent_executor.process(event):
            result = event.get_result()
            if not result:
                continue

            if result.result_content_type == ResultContentType.STREAMING_RESULT:
                # 流式结果，不清空，让后续节点处理
                continue

            latest_result = result

        # 最终结果：优先使用 event 中的结果，否则使用收集到的结果
        final_result = event.get_result() or latest_result
        if final_result:
            event.set_result(final_result)

        if event.is_stopped():
            return NodeResult.STOP

        return NodeResult.CONTINUE
