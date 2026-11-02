"""Persona selection, dialogue, registered tools, skills, and safety instructions."""

from __future__ import annotations

import copy

from astrbot.core import logger
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_main_agent_resources import (
    CHATUI_INLINE_GENUI_SYSTEM_PROMPT,
    CHATUI_SPECIAL_DEFAULT_PERSONA_PROMPT,
    LLM_SAFETY_MODE_SYSTEM_PROMPT,
)
from astrbot.core.persona_error_reply import (
    extract_persona_custom_error_message_from_persona,
    set_persona_custom_error_message_on_event,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.skills.skill_manager import (
    SkillInfo,
    SkillManager,
    build_skills_prompt,
)
from astrbot.core.star.context import Context

from . import plugins
from .config import MainAgentBuildConfig
from .workspace import resolve_workspace_path


async def apply_persona(
    req: ProviderRequest,
    cfg: dict,
    plugin_context: Context,
    event: AstrMessageEvent,
) -> None:
    """Apply the selected persona, initial dialogue, skills, and registered tools.

    Args:
        req: Request receiving prompts and tools.
        cfg: Provider settings used for persona, tool, and skill selection.
        plugin_context: Services for resolving personas, skills and tools.
        event: Event identifying the current session.
    """
    event.set_extra("_trace_persona_id", None)
    if req.system_prompt is None:
        req.system_prompt = ""

    if event.get_extra("enable_inline_genui"):
        req.system_prompt += CHATUI_INLINE_GENUI_SYSTEM_PROMPT

    if not req.conversation:
        return

    (
        persona_id,
        persona,
        _,
        use_webchat_special_default,
    ) = await plugin_context.persona_manager.resolve_selected_persona(
        umo=event.unified_msg_origin,
        conversation_persona_id=req.conversation.persona_id,
        platform_name=event.get_platform_name(),
        provider_settings=cfg,
    )

    event.set_extra("_trace_persona_id", persona_id)

    set_persona_custom_error_message_on_event(
        event, extract_persona_custom_error_message_from_persona(persona)
    )

    if persona:
        # Inject persona system prompt
        if prompt := persona["prompt"]:
            req.system_prompt += (
                f"\n<persona_instructions>\n{prompt}\n</persona_instructions>\n"
            )
        if begin_dialogs := copy.deepcopy(persona.get("_begin_dialogs_processed")):
            req.contexts[:0] = begin_dialogs
    elif (
        use_webchat_special_default
        and event.get_extra("enable_default_system_prompt") is not False
    ):
        req.system_prompt += CHATUI_SPECIAL_DEFAULT_PERSONA_PROMPT

    # Inject skills prompt
    runtime = cfg.get("computer_use_runtime", "none")
    skills: list[SkillInfo] = []
    skill_manager = None
    try:
        skill_manager = SkillManager()
        skills = skill_manager.list_skills(active_only=True, runtime=runtime)
        skills = plugins.filter_skills(skills, cfg)
    except Exception:
        logger.exception("Failed to list skills while preparing LLM request.")
    workspace_skills: list[SkillInfo] = []
    if runtime == "local" and skill_manager:
        workspace_root = await resolve_workspace_path(
            event.unified_msg_origin,
            plugin_context,
        )
        workspace_skills.extend(skill_manager.list_workspace_skills(workspace_root))

    if skills or workspace_skills:
        if persona and persona.get("skills") is not None:
            if not persona["skills"]:
                skills = []
            else:
                allowed = set(persona["skills"])
                skills = [skill for skill in skills if skill.name in allowed]
        if workspace_skills and (not persona or persona.get("skills") != []):
            skills_by_name = {skill.name: skill for skill in skills}
            for skill in workspace_skills:
                skills_by_name[skill.name] = skill
            skills = [skills_by_name[name] for name in sorted(skills_by_name)]
        if skills:
            req.system_prompt += (
                f"\n<skills_instructions>\n{build_skills_prompt(skills)}\n"
            )
            if runtime == "none":
                req.system_prompt += (
                    "User has not enabled the Computer Use feature. "
                    "You cannot use shell or Python to perform skills. "
                    "If you need to use these capabilities, ask the user to enable Computer Use in the AstrBot WebUI -> Config."
                )
            req.system_prompt += "\n</skills_instructions>\n"

    tmgr = plugin_context.get_llm_tool_manager()

    # inject toolset in the persona
    if (persona and persona.get("tools") is None) or not persona:
        persona_toolset = tmgr.get_full_tool_set()
        for tool in list(persona_toolset):
            if not tool.active:
                persona_toolset.remove_tool(tool.name)
    else:
        persona_toolset = ToolSet()
        if persona["tools"]:
            for tool_name in persona["tools"]:
                tool = tmgr.get_func(tool_name)
                if tool and tool.active:
                    persona_toolset.add_tool(tool)
    if not req.func_tool:
        req.func_tool = persona_toolset
    else:
        req.func_tool.merge(persona_toolset)


def apply_safety_instructions(
    config: MainAgentBuildConfig, req: ProviderRequest
) -> None:
    """Prepend the configured safety instructions to the composed persona.

    Args:
        config: Safety mode settings for the build.
        req: Request receiving the system instructions.
    """
    if config.safety_mode_strategy == "system_prompt":
        req.system_prompt = f"{LLM_SAFETY_MODE_SYSTEM_PROMPT}\n\n{req.system_prompt}"
    else:
        logger.warning(
            "Unsupported llm_safety_mode strategy: %s.",
            config.safety_mode_strategy,
        )
