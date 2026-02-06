from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING

from astrbot.core import logger
from astrbot.core.config import AstrBotNodeConfig
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.star import Star
from astrbot.core.star.node_star import NodeResult, NodeStar
from astrbot.core.star.star import StarMetadata, star_registry

from .node_context import NodeContext, NodeExecutionStatus
from .wait_registry import WaitState, build_wait_key, wait_registry

if TYPE_CHECKING:
    from astrbot.core.pipeline.agent import AgentExecutor
    from astrbot.core.pipeline.engine.chain_config import ChainConfig
    from astrbot.core.pipeline.engine.send_service import SendService
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.star.context import Context


@dataclass
class ChainExecutionResult:
    """Chain 执行结果"""

    success: bool = True
    should_send: bool = True
    error: Exception | None = None
    nodes_executed: int = 0


class ChainExecutor:
    """Chain 执行器

    执行 NodeStar 节点链。
    节点直接从 star_registry 动态获取，自动响应插件的禁用/卸载/重载。
    """

    def __init__(self, context: Context) -> None:
        self.context = context

    @staticmethod
    async def execute(
        event: AstrMessageEvent,
        chain_config: ChainConfig,
        send_service: SendService,
        agent_executor: AgentExecutor,
        start_node_name: str | None = None,
        start_node_uuid: str | None = None,
    ) -> ChainExecutionResult:
        """执行 Chain

        Args:
            event: 消息事件
            chain_config: Chain 配置
            send_service: 发送服务
            agent_executor: Agent 执行器
            start_node_name: 从指定节点开始执行（用于 WAIT 恢复）
            start_node_uuid: 指定节点UUID
        Returns:
            ChainExecutionResult
        """
        result = ChainExecutionResult()

        # 将服务挂到 event，供节点使用
        event.send_service = send_service
        event.agent_executor = agent_executor

        # 执行节点链
        nodes = chain_config.nodes
        start_chain_index = 0

        if start_node_uuid:
            try:
                start_chain_index = next(
                    idx
                    for idx, node in enumerate(nodes)
                    if node.uuid == start_node_uuid
                )
                nodes = nodes[start_chain_index:]
            except StopIteration:
                logger.warning(
                    f"Start node '{start_node_uuid}' not found in chain, "
                    "fallback to full chain.",
                )
        elif start_node_name:
            try:
                start_chain_index = next(
                    idx
                    for idx, node in enumerate(nodes)
                    if node.name == start_node_name
                )
                nodes = nodes[start_chain_index:]
            except StopIteration:
                logger.warning(
                    f"Start node '{start_node_name}' not found in chain, "
                    "fallback to full chain.",
                )

        context_stack = event.context_stack

        for offset, node_entry in enumerate(nodes):
            chain_index = start_chain_index + offset
            node_name = node_entry.name

            # Create node context
            node_ctx = NodeContext(
                node_name=node_name,
                node_uuid=node_entry.uuid,
                chain_index=chain_index,
            )

            # Push first, then set input from last EXECUTED node's output
            # This ordering doesn't matter because we use last_executed_output()
            # which searches all EXECUTED nodes (current is still PENDING)
            context_stack.push(node_ctx)
            upstream_output = context_stack.last_executed_output()
            if upstream_output is not None:
                node_ctx.input = upstream_output

            # 动态从 star_registry 获取节点
            node: NodeStar | None = None
            metadata: StarMetadata | None = None
            for m in star_registry:
                if not m.star_cls or not isinstance(m.star_cls, NodeStar):
                    continue
                if m.name == node_name:
                    metadata = m
                    if m.activated:
                        node = m.star_cls
                    break

            if not node:
                logger.error(f"Node unavailable: {node_name}")
                node_ctx.status = NodeExecutionStatus.FAILED
                result.success = False
                result.error = RuntimeError(f"Node '{node_name}' is not available")
                return result

            # 懒初始化（按 chain_id）
            chain_id = chain_config.chain_id
            if chain_id not in node.initialized_chain_ids:
                try:
                    await node.node_initialize()
                    node.initialized_chain_ids.add(chain_id)
                except Exception as e:
                    logger.error(f"Node {node_name} initialize error: {e}")
                    logger.error(traceback.format_exc())
                    node_ctx.status = NodeExecutionStatus.FAILED
                    result.success = False
                    result.error = e
                    return result

            # 加载节点配置
            schema = metadata.node_schema if metadata else None
            node_config = AstrBotNodeConfig.get_cached(
                node_name=node_name,
                chain_id=chain_config.chain_id,
                node_uuid=node_entry.uuid,
                schema=schema,
            )
            event.node_config = node_config

            # 执行节点
            try:
                node_result = await node.process(event)

                # Unified status mapping
                match node_result:
                    case NodeResult.WAIT:
                        node_ctx.status = NodeExecutionStatus.WAITING
                    case NodeResult.SKIP:
                        node_ctx.status = NodeExecutionStatus.SKIPPED
                    case _:  # CONTINUE / STOP
                        node_ctx.status = NodeExecutionStatus.EXECUTED

                result.nodes_executed += 1
                if node_ctx.status == NodeExecutionStatus.EXECUTED:
                    ChainExecutor._sync_node_output(event, node_ctx)

            except Exception as e:
                node_ctx.status = NodeExecutionStatus.FAILED
                logger.error(f"Node {node_name} error: {e}")
                logger.error(traceback.format_exc())
                result.success = False
                result.error = e
                return result

            # 处理结果
            if event.is_stopped():
                event.set_extra("_node_stop_event", True)
                break
            if node_result == NodeResult.WAIT:
                wait_key = build_wait_key(event)
                await wait_registry.set(
                    wait_key,
                    WaitState(
                        chain_config=chain_config,
                        node_name=node_name,
                        node_uuid=node_entry.uuid,
                        config_id=chain_config.config_id,
                    ),
                )
                result.should_send = False
                break
            elif node_result == NodeResult.STOP:
                break
            # CONTINUE / SKIP: 继续下一个节点

        # 发送与否由 result 是否存在决定（WAIT 除外）
        # Fallback to last_output if event.result not set
        if result.should_send:
            if not event.get_result():
                last_output = context_stack.last_executed_output()
                if last_output is not None:
                    event.set_result(last_output)
            result.should_send = event.get_result() is not None

        return result

    @staticmethod
    def _sync_node_output(event: AstrMessageEvent, node_ctx: NodeContext) -> None:
        """Align event result and node output for executed nodes."""
        evt_result = event.get_result()
        if node_ctx.output is None and evt_result is not None:
            node_ctx.output = evt_result
            return
        if node_ctx.output is not None and evt_result is None:
            if isinstance(node_ctx.output, MessageEventResult):
                event.set_result(node_ctx.output)

    @property
    def nodes(self) -> dict[str | None, Star | None]:
        """获取所有活跃节点"""
        return {
            m.name: m.star_cls
            for m in star_registry
            if m.activated and m.name and isinstance(m.star_cls, NodeStar)
        }
