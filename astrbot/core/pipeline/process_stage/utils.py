from ..context import PipelineContext
from astrbot.core.provider.entities import ProviderRequest
from astrbot.api import logger, sp


async def inject_kb_context(
    umo: str,
    p_ctx: PipelineContext,
    req: ProviderRequest,
) -> None:
    """inject knowledge base context into the provider request

    Args:
        umo: Unique message object (session ID)
        p_ctx: Pipeline context
        req: Provider request
    """

    kb_mgr = p_ctx.plugin_manager.context.kb_manager

    # 1. 优先读取会话级配置
    session_config = await sp.session_get(umo, "kb_config", default={})

    if session_config and "kb_ids" in session_config:
        # 会话级配置
        kb_ids = session_config.get("kb_ids", [])

        # 如果配置为空列表，明确表示不使用知识库
        if not kb_ids:
            logger.info(f"[知识库] 会话 {umo} 已被配置为不使用知识库")
            return

        top_k = session_config.get("top_k", 5)

        # 将 kb_ids 转换为 kb_names
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
                f"[知识库] 会话 {umo} 配置的以下知识库无效: {invalid_kb_ids}"
            )

        if not kb_names:
            return

        logger.debug(f"[知识库] 使用会话级配置，知识库数量: {len(kb_names)}")
    else:
        kb_names = p_ctx.astrbot_config.get("kb_names", [])
        top_k = p_ctx.astrbot_config.get("kb_final_top_k", 5)
        logger.debug(f"[知识库] 使用全局配置，知识库数量: {len(kb_names)}")

    top_k_fusion = p_ctx.astrbot_config.get("kb_fusion_top_k", 20)

    if not kb_names:
        return

    logger.debug(f"[知识库] 开始检索知识库，数量: {len(kb_names)}, top_k={top_k}")
    kb_context = await kb_mgr.retrieve(
        query=req.prompt,
        kb_names=kb_names,
        top_k_fusion=top_k_fusion,
        top_m_final=top_k,
    )

    if not kb_context:
        return

    formatted = kb_context.get("context_text", "")
    if formatted:
        results = kb_context.get("results", [])
        logger.debug(f"[知识库] 为会话 {umo} 注入了 {len(results)} 条相关知识块")
        req.system_prompt = f"{formatted}\n\n{req.system_prompt or ''}"
