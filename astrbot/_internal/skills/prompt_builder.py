"""Skills prompt builder - builds the system prompt section for skills."""

from __future__ import annotations

import json
import os
import re
import shlex

from .manager import SkillInfo

# Regex for sanitizing paths used in prompt examples — only allow
# safe path characters to prevent prompt injection via crafted skill paths.
_SAFE_PATH_RE = re.compile(r"[^\w./ ,()'\-]", re.UNICODE)
_WINDOWS_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:(?:/|\\)")
_WINDOWS_UNC_PATH_RE = re.compile(r"^(//|\\\\)[^/\\]+[/\\][^/\\]+")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")

SANDBOX_WORKSPACE_ROOT = "/workspace"
SANDBOX_SKILLS_ROOT = "skills"


def _is_windows_prompt_path(path: str) -> bool:
    if os.name != "nt":
        return False
    return bool(_WINDOWS_DRIVE_PATH_RE.match(path) or _WINDOWS_UNC_PATH_RE.match(path))


def _sanitize_prompt_path_for_prompt(path: str) -> str:
    if not path:
        return ""

    if _WINDOWS_DRIVE_PATH_RE.match(path) or _WINDOWS_UNC_PATH_RE.match(path):
        path = path.replace("\\", "/")

    drive_prefix = ""
    if _WINDOWS_DRIVE_PATH_RE.match(path):
        drive_prefix = path[:2]
        path = path[2:]

    path = path.replace("`", "")
    path = _CONTROL_CHARS_RE.sub("", path)
    sanitized = _SAFE_PATH_RE.sub("", path)
    return f"{drive_prefix}{sanitized}"


def _sanitize_prompt_description(description: str) -> str:
    description = description.replace("`", "")
    description = _CONTROL_CHARS_RE.sub(" ", description)
    description = " ".join(description.split())
    return description


_SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _sanitize_skill_display_name(name: str) -> str:
    if _SKILL_NAME_RE.fullmatch(name):
        return name
    return "<invalid_skill_name>"


def _default_sandbox_skill_path(name: str) -> str:
    return f"{SANDBOX_WORKSPACE_ROOT}/{SANDBOX_SKILLS_ROOT}/{name}/SKILL.md"


def _build_skill_read_command_example(path: str) -> str:
    if path == "<skills_root>/<skill_name>/SKILL.md":
        return f"cat {path}"
    if _is_windows_prompt_path(path):
        command = "type"
        path_arg = f'"{os.path.normpath(path)}"'
    else:
        command = "cat"
        path_arg = shlex.quote(path)
    return f"{command} {path_arg}"


def build_skills_prompt(skills: list[SkillInfo]) -> str:
    """Build the skills section of the system prompt.

    Generates a markdown-formatted skill inventory for the LLM.  Only
    ``name`` and ``description`` are shown upfront; the LLM must read
    the full ``SKILL.md`` before execution (progressive disclosure).
    """
    skills_lines: list[str] = []
    example_path = ""
    for skill in skills:
        display_name = _sanitize_skill_display_name(skill.name)

        description = skill.description or "No description"
        if skill.source_type == "sandbox_only":
            description = _sanitize_prompt_description(description)
            if not description:
                description = "Read SKILL.md for details."

        if skill.source_type == "sandbox_only":
            # Prefer the actual path from sandbox cache if available
            rendered_path = _sanitize_prompt_path_for_prompt(skill.path)
            if not rendered_path:
                rendered_path = _default_sandbox_skill_path(skill.name)
        else:
            rendered_path = _sanitize_prompt_path_for_prompt(skill.path)
            if not rendered_path:
                rendered_path = "<skills_root>/<skill_name>/SKILL.md"

        entry = f"- **{display_name}**: {description}\n  File: `{rendered_path}`"
        if skill.input_schema:
            entry += f"\n  Input Schema: {json.dumps(skill.input_schema, ensure_ascii=False)}"
        if skill.output_schema:
            entry += f"\n  Output Schema: {json.dumps(skill.output_schema, ensure_ascii=False)}"
        skills_lines.append(entry)
        if not example_path:
            example_path = rendered_path
    skills_block = "\n".join(skills_lines)
    # Sanitize example_path — it may originate from sandbox cache (untrusted)
    if example_path == "<skills_root>/<skill_name>/SKILL.md":
        example_path = "<skills_root>/<skill_name>/SKILL.md"
    else:
        example_path = _sanitize_prompt_path_for_prompt(example_path)
        example_path = example_path or "<skills_root>/<skill_name>/SKILL.md"
    example_command = _build_skill_read_command_example(example_path)

    return (
        "## Skills\n\n"
        "You have specialized skills — reusable instruction bundles stored "
        "in `SKILL.md` files. Each skill has a **name** and a **description** "
        "that tells you what it does and when to use it.\n\n"
        "### Available skills\n\n"
        f"{skills_block}\n\n"
        "### Skill rules\n\n"
        "1. **Discovery** — The list above is the complete skill inventory "
        "for this session. Full instructions are in the referenced "
        "`SKILL.md` file.\n"
        "2. **When to trigger** — Use a skill if the user names it "
        "explicitly, or if the task clearly matches the skill's description. "
        "*Never silently skip a matching skill* — either use it or briefly "
        "explain why you chose not to.\n"
        "3. **Mandatory grounding** — Before executing any skill you MUST "
        "first read its `SKILL.md` by running a shell command compatible "
        "with the current runtime shell and using the **absolute path** "
        f"shown above (e.g. `{example_command}`). "
        "Never rely on memory or assumptions about a skill's content.\n"
        "4. **Progressive disclosure** — Load only what is directly "
        "referenced from `SKILL.md`:\n"
        "   - If `scripts/` exist, prefer running or patching them over "
        "rewriting code from scratch.\n"
        "   - If `assets/` or templates exist, reuse them.\n"
        "   - Do NOT bulk-load every file in the skill directory.\n"
        "5. **Coordination** — When multiple skills apply, pick the minimal "
        "set needed. Announce which skill(s) you are using and why "
        "(one short line). Prefer `astrbot_*` tools when running skill "
        "scripts.\n"
        "6. **Context hygiene** — Avoid deep reference chasing; open only "
        "files that are directly linked from `SKILL.md`.\n"
        "7. **Failure handling** — If a skill cannot be applied, state the "
        "issue clearly and continue with the best alternative.\n"
    )
