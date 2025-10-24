from ..context import PipelineContext
from astrbot.core.provider.entities import ProviderRequest
from astrbot.api import logger


async def inject_kb_context(
    umo: str,
    p_ctx: PipelineContext,
    req: ProviderRequest,
) -> None:
    """inject knowledge base context into the provider request

    Args:
        p_ctx: Pipeline context
        req: Provider request
    """
    kb_mgr = p_ctx.plugin_manager.context.kb_manager
    kb_names = p_ctx.astrbot_config.get("kb_names", [])
    top_k_fusion = p_ctx.astrbot_config.get("kb_fusion_top_k", 20)
    top_k = p_ctx.astrbot_config.get("kb_final_top_k", 5)

    if not kb_names:
        return

    kb_context = await kb_mgr.retrieve(
        query=req.prompt,
        kb_names=kb_names,
        top_k_fusion=top_k_fusion,
        top_m_final=top_k,
    )
    if not kb_context:
        return
    formatted = kb_context.get("context_text", "") if kb_context else ""
    if formatted:
        results = kb_context.get("results", [])
        logger.debug(f"知识库上下文注入: 为请求注入了 {len(results)} 条相关知识块")
        req.system_prompt = f"{formatted}\n\n{req.system_prompt or ''}"
