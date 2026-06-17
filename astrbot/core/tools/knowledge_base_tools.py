from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.api import logger, sp
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.knowledge_base.kb_helper import KBHelper
from astrbot.core.star.context import Context
from astrbot.core.tools.registry import builtin_tool

_KNOWLEDGE_BASE_TOOL_CONFIG = {
    "kb_agentic_mode": True,
}


def check_all_kb(kb_list: list[KBHelper | None]) -> bool:
    """检查是否所有的知识库都为空"""
    return not any(
        kb and (kb.kb.doc_count != 0 or kb.kb.chunk_count != 0) for kb in kb_list
    )


async def retrieve_knowledge_base(
    query: str,
    umo: str,
    context: Context,
) -> str | None:
    """Retrieve knowledge base context for the given query."""
    kb_mgr = context.kb_manager
    config = context.get_config(umo=umo)

    session_config = await sp.session_get(umo, "kb_config", default={})
    if session_config and "kb_ids" in session_config:
        kb_ids = session_config.get("kb_ids", [])
        if not kb_ids:
            logger.info(f"[知识库] 会话 {umo} 已被配置为不使用知识库")
            return None

        top_k = session_config.get("top_k", 5)
        kb_names = []
        invalid_kb_ids = []
        for kb_id in kb_ids:
            kb_helper = await kb_mgr.get_kb(kb_id)
            if kb_helper:
                kb_names.append(kb_helper.kb.kb_name)
            else:
                logger.warning(f"[知识库] 知识库不存在或未加载: {kb_id}")
                invalid_kb_ids.append(kb_id)

        if invalid_kb_ids:
            logger.warning(
                f"[知识库] 会话 {umo} 配置的以下知识库无效: {invalid_kb_ids}",
            )
        if not kb_names:
            return None
        logger.debug(f"[知识库] 使用会话级配置，知识库数量: {len(kb_names)}")
    else:
        kb_names = config.get("kb_names", [])
        top_k = config.get("kb_final_top_k", 5)
        logger.debug(f"[知识库] 使用全局配置，知识库数量: {len(kb_names)}")

    top_k_fusion = config.get("kb_fusion_top_k", 20)
    if not kb_names:
        return None

    all_kbs = [await kb_mgr.get_kb_by_name(kb) for kb in kb_names]
    if check_all_kb(all_kbs):
        logger.debug("所配置的所有知识库全为空，跳过检索过程")
        return None

    logger.debug(f"[知识库] 开始检索知识库，数量: {len(kb_names)}, top_k={top_k}")
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
        logger.debug(f"[知识库] 为会话 {umo} 注入了 {len(results)} 条相关知识块")
        return formatted
    return None


@builtin_tool(config=_KNOWLEDGE_BASE_TOOL_CONFIG)
@dataclass
class KnowledgeBaseQueryTool(FunctionTool[AstrAgentContext]):
    name: str = "astr_kb_search"
    description: str = (
        "Query the knowledge base for facts or relevant context. "
        "Use this tool when the user's question requires factual information, "
        "definitions, background knowledge, or previously indexed content. "
        "Only send short keywords or a concise question as the query."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A concise keyword query for the knowledge base.",
                },
            },
            "required": ["query"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        query = kwargs.get("query", "")
        if not query:
            return "error: Query parameter is empty."
        result = await retrieve_knowledge_base(
            query=query,
            umo=context.context.event.unified_msg_origin,
            context=context.context.context,
        )
        if not result:
            return "No relevant knowledge found."
        return result


__all__ = [
    "KnowledgeBaseQueryTool",
    "check_all_kb",
    "retrieve_knowledge_base",
]
