"""AstrBot internal skills module.

This module provides the skill management system for AstrBot, including:
- SkillManager: Manages skill lifecycle (install, activate, delete, etc.)
- SkillInfo: Dataclass representing skill metadata
- build_skills_prompt: Builds the system prompt section for skills
- SkillToToolConverter: Converts skills with input_schema to FunctionTool
"""

from .manager import (
    DEFAULT_SKILLS_CONFIG,
    SANDBOX_SKILLS_CACHE_FILENAME,
    SANDBOX_SKILLS_ROOT,
    SANDBOX_WORKSPACE_ROOT,
    SKILLS_CONFIG_FILENAME,
    SkillInfo,
    SkillManager,
    build_skills_prompt,
)
from .parser import parse_frontmatter, parse_skill_markdown
from .to_tool import SkillToToolConverter

__all__ = [
    # Constants
    "DEFAULT_SKILLS_CONFIG",
    "SANDBOX_SKILLS_CACHE_FILENAME",
    "SANDBOX_SKILLS_ROOT",
    "SANDBOX_WORKSPACE_ROOT",
    "SKILLS_CONFIG_FILENAME",
    "SkillInfo",
    "SkillManager",
    "SkillToToolConverter",
    "build_skills_prompt",
    # Parser
    "parse_frontmatter",
    "parse_skill_markdown",
]
