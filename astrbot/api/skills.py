"""
Skills Public API for AstrBot.

Two skill types:
1. Prompt-based: SKILL.md files injected into system prompt
2. Tool-based: Skills with input_schema converted to FunctionTool

Example:
    from astrbot.api.skills import get_skill_manager, skill_to_tool

    # List skills
    mgr = get_skill_manager()
    skills = mgr.list_skills()

    # Convert tool-based skill to FunctionTool
    tool_skills = [s for s in skills if s.input_schema]
    if tool_skills:
        func_tool = skill_to_tool(tool_skills[0])
"""

from __future__ import annotations

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.skills.skill_manager import SkillInfo, SkillManager

__all__ = ["SkillInfo", "SkillManager", "get_skill_manager", "skill_to_tool"]


def get_skill_manager() -> SkillManager:
    """Get the global SkillManager instance."""
    return SkillManager()


def skill_to_tool(skill: SkillInfo) -> FunctionTool | None:
    """Convert a tool-based skill (with input_schema) to a FunctionTool.

    Args:
        skill: A SkillInfo instance with an input_schema

    Returns:
        A FunctionTool, or None if the skill has no input_schema
    """
    if not skill.input_schema:
        return None

    return FunctionTool(
        name=f"skill_{skill.name}",
        description=skill.description or f"Skill: {skill.name}",
        parameters=skill.input_schema,
        handler=None,
        source="skill",
    )
