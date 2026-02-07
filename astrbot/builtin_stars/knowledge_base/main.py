"""知识库检索节点 - 在Agent调用之前检索相关知识并注入上下文"""

from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.core import logger
from astrbot.core.star.node_star import NodeResult, NodeStar

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


class KnowledgeBaseNode(NodeStar):
    """知识库检索节点

    用户可手动添加到 Chain 中，在 Agent 节点之前运行。
    负责：
    1. 根据用户消息检索知识库
    2. 将检索结果注入到 ProviderRequest 的 system_prompt 中
    3. 后续 Agent 节点可以使用增强后的上下文

    注意：此节点实现的是非Agentic模式的知识库检索。
    如需Agentic模式（LLM主动调用知识库工具），请在provider_settings中启用kb_agentic_mode。
    """

    async def process(self, event: AstrMessageEvent) -> NodeResult:
        # 检查是否有消息内容需要检索
        merged_query = await event.get_node_input(strategy="text_concat")
        if isinstance(merged_query, str) and merged_query.strip():
            query = merged_query
        elif merged_query is not None:
            query = str(merged_query)
        else:
            # 无上游输出时回退使用原始消息。
            query = event.message_str
        if not query or not query.strip():
            return NodeResult.SKIP

        chain_config_id = event.chain_config.config_id if event.chain_config else None

        try:
            kb_result = await self._retrieve_knowledge_base(
                query,
                event.node_config,
                event.chain_config.chain_id if event.chain_config else "unknown",
                chain_config_id,
            )
            if kb_result:
                event.set_node_output(kb_result)
                logger.debug("[知识库节点] 检索到知识库上下文")
        except Exception as e:
            logger.error(f"[知识库节点] 检索知识库时发生错误: {e}")

        return NodeResult.CONTINUE

    async def _retrieve_knowledge_base(
        self,
        query: str,
        node_config,
        chain_id: str,
        config_id: str | None,
    ) -> str | None:
        """检索知识库

        Args:
            query: 查询文本
            node_config: Node config for this node

        Returns:
            检索到的知识库内容，如果没有则返回 None
        """
        kb_mgr = self.context.kb_manager
        config = self.context.get_config_by_id(config_id)
        node_config = node_config or {}
        use_global_kb = node_config.get("use_global_kb", True)
        kb_names = node_config.get("kb_names", []) or []

        if kb_names:
            top_k = node_config.get("top_k", 5)
            logger.debug(
                f"[知识库节点] 使用节点配置，知识库数量: {len(kb_names)}",
            )

            valid_kb_names = []
            invalid_kb_names = []
            for kb_name in kb_names:
                kb_helper = await kb_mgr.get_kb_by_name(kb_name)
                if kb_helper:
                    valid_kb_names.append(kb_helper.kb.kb_name)
                else:
                    logger.warning(f"[知识库节点] 知识库不存在或未加载: {kb_name}")
                    invalid_kb_names.append(kb_name)

            if invalid_kb_names:
                logger.warning(
                    f"[知识库节点] 配置的以下知识库名称无效: {invalid_kb_names}",
                )

            kb_names = valid_kb_names
        elif use_global_kb:
            kb_names = config.get("kb_names", [])
            top_k = config.get("kb_final_top_k", 5)
            logger.debug(
                f"[知识库节点] 使用全局配置，知识库数量: {len(kb_names)}",
            )
            if not kb_names:
                return None
            return await self._do_retrieve(
                kb_mgr,
                query,
                kb_names,
                top_k,
                None,
                config,
            )
        else:
            logger.info(f"[知识库节点] 节点已禁用知识库: {chain_id}")
            return None

        if not kb_names:
            return None

        fusion_top_k = node_config.get("fusion_top_k")
        if fusion_top_k is not None:
            try:
                fusion_top_k = int(fusion_top_k)
            except (TypeError, ValueError):
                fusion_top_k = None

        return await self._do_retrieve(
            kb_mgr,
            query,
            kb_names,
            top_k,
            fusion_top_k,
            config,
        )

    @staticmethod
    async def _do_retrieve(
        kb_mgr,
        query: str,
        kb_names: list[str],
        top_k: int,
        fusion_top_k: int | None,
        config: dict,
    ) -> str | None:
        """执行知识库检索"""
        if fusion_top_k is None:
            top_k_fusion = config.get("kb_fusion_top_k", 20)
        else:
            top_k_fusion = fusion_top_k

        logger.debug(
            f"[知识库节点] 开始检索知识库，数量: {len(kb_names)}, top_k={top_k}"
        )
        kb_context = await kb_mgr.retrieve(
            query=query,
            kb_names=kb_names,
            top_k_fusion=top_k_fusion,
            top_m_final=top_k,
        )

        if not kb_context:
            return None

        formatted = kb_context.get("context_text", "")
        if formatted:
            results = kb_context.get("results", [])
            logger.debug(f"[知识库节点] 检索到 {len(results)} 条相关知识块")
            return formatted

        return None
