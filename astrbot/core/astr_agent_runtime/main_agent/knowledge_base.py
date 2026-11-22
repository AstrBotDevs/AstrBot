"""Knowledge-base retrieval and agentic query capability."""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from astrbot.core import logger
from astrbot.core.agent.message import TextPart
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_runtime.tools.knowledge_base_tools import (
    KnowledgeBaseQueryTool,
    retrieve_knowledge_base,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context

from .config import MainAgentBuildConfig

KB_RESULTS_HEADER = "[Related Knowledge Base Results]:"
_QUOTED_PREFIX = "<Quoted Message>\n"
_QUOTED_SUFFIX = "\n</Quoted Message>"
_QUOTED_SENDER_RE = re.compile(r"^\([^()\n]{1,80}\):\s*")
_PLACEHOLDER_RE = re.compile(
    r"(?:<attachment>|<提及自己>|\[提及机器人\]|\[Empty Text\]"
    r"|\[图片\]|\[语音\]|\[音频\]|\[视频\]|\[文件\]"
    r"|\[Image unavailable\]|\[Voice unavailable\])"
)
_MAX_QUOTED_EXCERPT_CHARS = 300


def extract_retrieval_query(
    prompt: str | None,
    extra_user_content_parts: Sequence[Any] = (),
    *,
    prompt_prefix: str | None = None,
) -> str:
    """Derive clean retrieval query text from user text and optional quoted content.

    Pure placeholder tokens (such as ``<attachment>`` or ``<提及自己>``) and
    optional configured ``prompt_prefix`` wrappers are stripped so empty
    attachment/mention turns or prompt templates do not pollute vector lookups.

    Args:
        prompt: Raw or current user prompt text.
        extra_user_content_parts: Additional user parts that may contain a
            ``<Quoted Message>`` block.
        prompt_prefix: Optional configured ``prompt_prefix`` string or
            ``{{prompt}}`` template to strip from ``prompt`` before cleaning.

    Returns:
        Normalized retrieval query string, or an empty string if no substantive
        text is present.
    """
    raw_prompt = prompt if isinstance(prompt, str) else ""
    if isinstance(prompt_prefix, str) and prompt_prefix and raw_prompt:
        if "{{prompt}}" in prompt_prefix:
            before, after = prompt_prefix.split("{{prompt}}", 1)
            if not before or raw_prompt.startswith(before):
                raw_prompt = raw_prompt.removeprefix(before)
                if after and raw_prompt.endswith(after):
                    raw_prompt = raw_prompt.removesuffix(after)
        elif raw_prompt.startswith(prompt_prefix):
            raw_prompt = raw_prompt.removeprefix(prompt_prefix)
    clean_prompt = " ".join(_PLACEHOLDER_RE.sub(" ", raw_prompt).split())

    quoted_excerpt = ""
    for part in extra_user_content_parts or ():
        if isinstance(part, Mapping):
            text = part.get("text") if part.get("type") == "text" else None
        else:
            text = (
                getattr(part, "text", None)
                if getattr(part, "type", None) == "text"
                else None
            )
        if not (isinstance(text, str) and text.startswith(_QUOTED_PREFIX)):
            continue
        body = text[len(_QUOTED_PREFIX) :]
        if body.endswith(_QUOTED_SUFFIX):
            body = body[: -len(_QUOTED_SUFFIX)]
        body = _QUOTED_SENDER_RE.sub("", body.strip(), count=1)
        body = " ".join(_PLACEHOLDER_RE.sub(" ", body).split())
        if body:
            quoted_excerpt = body[:_MAX_QUOTED_EXCERPT_CHARS]
            break

    if clean_prompt and quoted_excerpt:
        return f"{clean_prompt}\n{quoted_excerpt}"
    return clean_prompt or quoted_excerpt


async def apply_knowledge_base(
    event: AstrMessageEvent,
    req: ProviderRequest,
    plugin_context: Context,
    config: MainAgentBuildConfig,
    *,
    add_tool: bool = True,
    fallback_query: str | None = None,
) -> bool:
    """Apply configured knowledge-base retrieval and/or agentic query tool.

    Supports three effective modes resolved from ``config.effective_kb_mode``:
    - ``auto``: automatic retrieval injection before the turn.
    - ``agentic``: mount the ``astr_kb_search`` tool without automatic injection.
    - ``hybrid``: mount ``astr_kb_search`` and automatically inject hits passing
      ``config.kb_min_score``.

    Args:
        event: Event identifying the session's knowledge bases.
        req: Request receiving a query tool or temporary retrieved context.
        plugin_context: Knowledge-base services.
        config: Knowledge-base mode and score threshold for this build.
        add_tool: Whether to attach the agentic query tool when enabled by mode.
        fallback_query: Optional pre-extracted clean query used when
            ``req.retrieval_query`` is None, preventing ``prompt_prefix`` from
            leaking into pre-hook retrieval on empty/placeholder turns.

    Returns:
        True if automatic retrieval was executed for this request, False
        otherwise.
    """
    mode = config.effective_kb_mode
    if add_tool and mode in ("agentic", "hybrid"):
        if req.func_tool is None:
            req.func_tool = ToolSet()
        kb_tool = KnowledgeBaseQueryTool()
        if req.func_tool.get_tool(kb_tool.name) is None:
            req.func_tool.add_tool(kb_tool)

    if mode == "agentic":
        return False

    if getattr(req, "_kb_retrieved", False):
        return True

    if req.retrieval_query is not None:
        query = extract_retrieval_query(req.retrieval_query)
    elif fallback_query is not None:
        query = extract_retrieval_query(fallback_query)
    else:
        query = extract_retrieval_query(
            req.prompt,
            req.extra_user_content_parts,
            prompt_prefix=config.provider_settings.get("prompt_prefix"),
        )
    if not query:
        return False

    try:
        kb_result = await retrieve_knowledge_base(
            query=query,
            umo=event.unified_msg_origin,
            context=plugin_context,
            min_score=config.kb_min_score,
        )
        req._kb_retrieved = True
        if kb_result:
            req.extra_user_content_parts.append(
                TextPart(
                    text=f"{KB_RESULTS_HEADER}\n{kb_result}",
                ).mark_as_temp()
            )
        return True
    except Exception as exc:  # noqa: BLE001
        req._kb_retrieved = True
        logger.error("Error occurred while retrieving knowledge base: %s", exc)
        return True
