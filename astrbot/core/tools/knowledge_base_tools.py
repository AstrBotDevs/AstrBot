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
    """Check whether all loaded knowledge bases are empty.

    Args:
        kb_list: Resolved knowledge base instances. Unresolved entries are None.

    Returns:
        True when no non-empty knowledge base is available, otherwise False.
    """
    return not any(
        kb and (kb.kb.doc_count != 0 or kb.kb.chunk_count != 0) for kb in kb_list
    )


async def retrieve_knowledge_base(
    query: str,
    umo: str,
    context: Context,
) -> str | None:
    """Retrieve knowledge base context for the given query.

    Args:
        query: User query text used for retrieval.
        umo: Unified message origin of the current session.
        context: Runtime context that provides config and knowledge base manager.

    Returns:
        Retrieved context text, or None when no usable knowledge base matches.
    """
    kb_mgr = context.kb_manager
    config = context.get_config(umo=umo)

    session_config = await sp.session_get(umo, "kb_config", default={})
    if session_config and "kb_ids" in session_config:
        kb_ids = session_config.get("kb_ids", [])
        if not kb_ids:
            logger.info(
                "[Knowledge Base] Session %s is configured to skip knowledge bases.",
                umo,
            )
            return None

        top_k = session_config.get("top_k", 5)
        kb_names = []
        invalid_kb_ids = []
        for kb_id in kb_ids:
            kb_helper = await kb_mgr.get_kb(kb_id)
            if kb_helper:
                kb_names.append(kb_helper.kb.kb_name)
            else:
                logger.warning(
                    "[Knowledge Base] Knowledge base %s does not exist or is not loaded.",
                    kb_id,
                )
                invalid_kb_ids.append(kb_id)

        if invalid_kb_ids:
            logger.warning(
                "[Knowledge Base] Session %s references invalid knowledge base IDs: %s",
                umo,
                invalid_kb_ids,
            )
        if not kb_names:
            return None
        logger.debug(
            "[Knowledge Base] Session %s uses session-scoped config with %s "
            "knowledge bases.",
            umo,
            len(kb_names),
        )
    else:
        kb_names = config.get("kb_names", [])
        top_k = config.get("kb_final_top_k", 5)
        logger.debug(
            "[Knowledge Base] Session %s uses global config with %s knowledge bases.",
            umo,
            len(kb_names),
        )

    top_k_fusion = config.get("kb_fusion_top_k", 20)
    if not kb_names:
        return None

    resolved_kb_names = []
    all_kbs = []
    invalid_kb_names = []
    for kb_name in kb_names:
        kb_helper = await kb_mgr.get_kb_by_name(kb_name)
        if kb_helper:
            resolved_kb_names.append(kb_helper.kb.kb_name)
            all_kbs.append(kb_helper)
            continue
        invalid_kb_names.append(kb_name)

    if invalid_kb_names:
        logger.warning(
            "[Knowledge Base] Session %s references missing or unloaded "
            "knowledge bases: %s",
            umo,
            invalid_kb_names,
        )
    if not resolved_kb_names:
        return None
    if check_all_kb(all_kbs):
        logger.debug(
            "[Knowledge Base] All resolved knowledge bases are empty; skipping retrieval.",
        )
        return None

    logger.debug(
        "[Knowledge Base] Starting retrieval across %s knowledge bases with top_k=%s.",
        len(resolved_kb_names),
        top_k,
    )
    kb_context = await kb_mgr.retrieve(
        query=query,
        kb_names=resolved_kb_names,
        top_k_fusion=top_k_fusion,
        top_m_final=top_k,
    )
    if not kb_context:
        return None

    formatted = kb_context.get("context_text", "")
    if formatted:
        results = kb_context.get("results", [])
        logger.debug(
            "[Knowledge Base] Injected %s relevant chunks into session %s.",
            len(results),
            umo,
        )
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
