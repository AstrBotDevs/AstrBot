import math

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.api import logger
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_runtime.context import AstrAgentContext
from astrbot.core.knowledge_base.kb_helper import KBHelper
from astrbot.core.star.context import Context


def check_all_kb(kb_list: list[KBHelper | None]) -> bool:
    """检查是否所有的知识库都为空

    Args:
        kb_list: 知识库实例列表，可能包含 None（未找到的知识库）

    Returns:
        bool: True 表示所有知识库都为空或未找到
    """
    # 检查是否有未找到的知识库（None）
    none_count = sum(1 for kb in kb_list if kb is None)
    if none_count > 0:
        logger.warning(
            f"[知识库] {none_count}/{len(kb_list)} 个知识库未找到或未加载，"
            "请检查配置中的知识库名称或 ID 是否正确"
        )

    # 检查是否所有非 None 的知识库都为空
    return not any(
        kb and (kb.kb.doc_count != 0 or kb.kb.chunk_count != 0) for kb in kb_list
    )


async def retrieve_knowledge_base(
    query: str,
    umo: str,
    context: Context,
    *,
    min_score: float | None = None,
) -> str | None:
    """Retrieve knowledge base context for the given query.

    Args:
        query: Clean retrieval query string.
        umo: Unified message origin identifying session KB configuration.
        context: Host context providing the KB manager and session config.
        min_score: Optional relevance score floor. Defaults to the session
            ``kb_min_score`` setting (0.0 disables filtering).

    Returns:
        Formatted knowledge-base context string, or None when no results match.
    """
    kb_mgr = context.kb_manager
    config = context.get_config(umo=umo)

    kb_names = config.get("kb_names", [])
    top_k = config.get("kb_final_top_k", 5)

    top_k_fusion = config.get("kb_fusion_top_k", 20)
    if not kb_names:
        return None

    threshold = 0.0
    raw_threshold = config.get("kb_min_score", 0.0) if min_score is None else min_score
    if not isinstance(raw_threshold, bool) and raw_threshold is not None:
        try:
            parsed = float(raw_threshold)
            if math.isfinite(parsed) and parsed > 0.0:
                threshold = parsed
        except (TypeError, ValueError, OverflowError):
            threshold = 0.0

    all_kbs = [await kb_mgr.get_kb_by_name(kb) for kb in kb_names]
    if check_all_kb(all_kbs):
        logger.debug("All configured knowledge bases are empty; skipping retrieval.")
        return None

    logger.debug(
        "[KB] Starting retrieval across %d knowledge bases (top_k=%s, min_score=%s)",
        len(kb_names),
        top_k,
        threshold,
    )
    kb_context = await kb_mgr.retrieve(
        query=query,
        kb_names=kb_names,
        top_k_fusion=top_k_fusion,
        top_m_final=top_k,
    )
    if not kb_context:
        return None

    results = kb_context.get("results", [])
    if threshold > 0.0 and isinstance(results, list):
        filtered: list[tuple[dict, float]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            # Prefer the absolute relevance_score (rerank relevance or raw dense
            # cosine similarity) over RankFusion's batch-normalized score so
            # lone or tied weak candidates do not bypass kb_min_score.
            raw_score = (
                item.get("relevance_score")
                if "relevance_score" in item
                else item.get("score")
            )
            if isinstance(raw_score, bool) or raw_score is None:
                continue
            try:
                score = float(raw_score)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(score) and score >= threshold:
                filtered.append((item, score))
        if not filtered:
            logger.debug(
                "[KB] Filtered out all %d results below min_score=%.4f for session %s",
                len(results),
                threshold,
                umo,
            )
            return None
        if len(filtered) < len(results):
            lines = ["以下是相关的知识库内容,请参考这些信息回答用户的问题:\n"]
            for idx, (item, score) in enumerate(filtered, 1):
                lines.append(f"【知识 {idx}】")
                lines.append(
                    f"来源: {item.get('kb_name', '')} / {item.get('doc_name', '')}"
                )
                lines.append(f"内容: {item.get('content', '')}")
                lines.append(f"相关度: {score:.2f}")
                lines.append("")
            logger.debug(
                "[KB] Injected %d/%d results passing min_score=%.4f for session %s",
                len(filtered),
                len(results),
                threshold,
                umo,
            )
            return "\n".join(lines)

    formatted = kb_context.get("context_text", "")
    if formatted:
        logger.debug(
            "[KB] Injected %d knowledge chunks for session %s", len(results), umo
        )
        return formatted
    return None


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
            min_score=0.0,
        )
        if not result:
            return "No relevant knowledge found."
        return result


__all__ = [
    "KnowledgeBaseQueryTool",
    "check_all_kb",
    "retrieve_knowledge_base",
]
