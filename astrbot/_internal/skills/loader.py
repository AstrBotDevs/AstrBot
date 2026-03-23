"""Skill loader - loads skills from filesystem."""

from __future__ import annotations

from pathlib import Path

from .manager import SkillInfo, _normalize_skill_markdown_path, _parse_frontmatter


def load_skill(skill_name: str, skills_root: Path) -> SkillInfo | None:
    """Load a single skill by name from the skills root directory.

    Args:
        skill_name: The name of the skill to load
        skills_root: Path to the skills root directory

    Returns:
        SkillInfo if the skill exists and has a valid SKILL.md, None otherwise
    """
    skill_dir = skills_root / skill_name
    if not skill_dir.is_dir():
        return None

    skill_md = _normalize_skill_markdown_path(skill_dir)
    if skill_md is None:
        return None

    try:
        content = skill_md.read_text(encoding="utf-8")
        meta = _parse_frontmatter(content)
    except Exception:
        return None

    description = meta.get("description", "")
    if not isinstance(description, str):
        description = ""
    description = description.strip()

    input_schema = meta.get("input_schema")
    output_schema = meta.get("output_schema")

    return SkillInfo(
        name=skill_name,
        description=description,
        path=str(skill_md).replace("\\", "/"),
        active=True,
        source_type="local_only",
        source_label="local",
        local_exists=True,
        sandbox_exists=False,
        input_schema=input_schema,
        output_schema=output_schema,
    )


def load_all_skills(skills_root: Path) -> list[SkillInfo]:
    """Load all skills from the skills root directory.

    Args:
        skills_root: Path to the skills root directory

    Returns:
        List of SkillInfo objects for all valid skills
    """
    skills: list[SkillInfo] = []

    if not skills_root.is_dir():
        return skills

    for entry in sorted(skills_root.iterdir()):
        if not entry.is_dir():
            continue

        skill_name = entry.name
        skill_info = load_skill(skill_name, skills_root)
        if skill_info is not None:
            skills.append(skill_info)

    return skills
