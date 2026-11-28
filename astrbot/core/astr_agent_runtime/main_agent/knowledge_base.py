"""Knowledge-base retrieval and agentic query capability."""

from astrbot.core import logger
from astrbot.core.agent.message import TextPart
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_runtime.tools.knowledge_base_tools import (
    KnowledgeBaseQueryTool,
    retrieve_knowledge_base,
)
from astrbot.core.auxiliary_model_errors import notify_auxiliary_model_failure
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context

from .config import MainAgentBuildConfig


async def apply_knowledge_base(
    event: AstrMessageEvent,
    req: ProviderRequest,
    plugin_context: Context,
    config: MainAgentBuildConfig,
) -> None:
    """Choose agentic querying or inject retrieved knowledge for this turn.

    Args:
        event: Event identifying the session's knowledge bases.
        req: Request receiving a query tool or temporary retrieved context.
        plugin_context: Knowledge-base services.
        config: Knowledge-base mode for this build.
    """
    if config.kb_agentic_mode:
        if req.func_tool is None:
            req.func_tool = ToolSet()
        req.func_tool.add_tool(KnowledgeBaseQueryTool())
    else:
        if req.prompt is None or not req.prompt.strip():
            return
        errors: list[str] = []
        try:
            kb_result = await retrieve_knowledge_base(
                query=req.prompt,
                umo=event.unified_msg_origin,
                context=plugin_context,
                errors=errors,
            )
            if kb_result:
                req.extra_user_content_parts.append(
                    TextPart(
                        text=f"[Related Knowledge Base Results]:\n{kb_result}",
                    ).mark_as_temp()
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("Error occurred while retrieving knowledge base: %s", exc)
            errors.append(str(exc))
        if errors:
            await notify_auxiliary_model_failure(
                event, "Knowledge base", "; ".join(errors)
            )
