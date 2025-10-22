from ..context import PipelineContext
from astrbot.core.provider.entities import ProviderRequest
from astrbot.api import logger


async def inject_kb_context(
    umo: str,
    p_ctx: PipelineContext,
    req: ProviderRequest,
    top_k: int = 5,
) -> None:
    """inject knowledge base context into the provider request

    Args:
        p_ctx: Pipeline context
        req: Provider request
    """
    kb_injector = p_ctx.plugin_manager.context.kb_manager.get_kb_injector()
    if not kb_injector:
        return
    kb_context = await kb_injector.retrieve_and_inject(
        unified_msg_origin=umo,
        query=req.prompt,
        top_k=top_k,
    )
    if not kb_context:
        return
    formatted = kb_context.get("context_text", "") if kb_context else ""
    if formatted:
        results = kb_context.get("results", [])
        logger.debug(f"知识库上下文注入: 为请求注入了 {len(results)} 条相关知识块")
        req.system_prompt = f"{formatted}\n\n{req.system_prompt or ''}"
