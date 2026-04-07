"""Internal skills module - re-exports from core.skills.skill_manager."""

from astrbot.core.skills.skill_manager import (
    SkillInfo,
    SkillManager,
    build_skills_prompt,
)

__all__ = [
    "SkillInfo",
    "SkillManager",
    "build_skills_prompt",
]
