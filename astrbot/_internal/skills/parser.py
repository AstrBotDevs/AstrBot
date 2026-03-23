"""SKILL.md parser for extracting frontmatter and content."""

from __future__ import annotations

from pathlib import Path

import yaml


def parse_frontmatter(text: str) -> dict:
    """Extract metadata from YAML frontmatter.

    Expects the standard SKILL.md format used by OpenAI Codex CLI and
    Anthropic Claude Skills::

        ---
        name: my-skill
        description: What this skill does and when to use it.
        input_schema: ...
        output_schema: ...
        ---
    """
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}

    frontmatter = "\n".join(lines[1:end_idx])
    try:
        payload = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError:
        return {}
    if not isinstance(payload, dict):
        return {}

    return payload


def parse_skill_markdown(path: Path) -> dict:
    """Parse a SKILL.md file and return frontmatter + content.

    Args:
        path: Path to the SKILL.md file

    Returns:
        dict with keys: frontmatter (dict), content (str)
    """
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {"frontmatter": {}, "content": ""}

    frontmatter = parse_frontmatter(text)

    # Extract content after frontmatter
    if text.startswith("---"):
        lines = text.splitlines()
        end_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break
        if end_idx is not None:
            content = "\n".join(lines[end_idx + 1 :]).strip()
        else:
            content = ""
    else:
        content = text

    return {
        "frontmatter": frontmatter,
        "content": content,
    }
