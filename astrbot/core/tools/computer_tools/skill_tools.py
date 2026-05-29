"""Skill self-authoring tools for local runtime.

These tools allow the LLM to create, package, and install skills
in local mode. The existing neo_skills.py tools only work in
shipyard_neo sandbox mode; these tools bridge the gap for local runtime.

Prerequisites for use:
1. The LLM writes SKILL.md (and optional supporting files) to
   ``data/skills/<skill_name>/`` using ``astrbot_file_write_tool``.
2. The LLM then calls ``create_skill_zip`` to package the directory.
3. The LLM calls ``install_skill_from_zip`` to register the skill.

Alternatively, since ``SkillManager.list_skills()`` auto-discovers any
directory containing SKILL.md under ``data/skills/`` on every request,
steps 2-3 are optional for immediate local use —but are useful for
distribution, backup, or reinstall workflows.
"""

import logging
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext

from ..registry import builtin_tool
from .util import check_admin_permission, is_local_runtime

logger = logging.getLogger(__name__)

_COMPUTER_RUNTIME_TOOL_CONFIG = {
    "provider_settings.computer_use_runtime": ("local", "sandbox"),
}

_SKILL_NAME_RE = re.compile(r"^[\w.\-]+$")


def _resolve_temp_path(local_env: bool, filename: str) -> Path:
    """Return temp directory path, consistent across local/sandbox runtimes.

    Raises ValueError if *filename* would escape the temp directory
    (e.g. contains ``..`` components or is absolute).
    """
    # Reject directory-traversal attempts
    clean = Path(filename)
    if clean.is_absolute() or ".." in clean.parts:
        raise ValueError(f"Invalid filename: {filename!r}")

    from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

    if local_env:
        return Path(get_astrbot_temp_path()) / filename
    # Sandbox runtime: use the same AstrBot temp path when available,
    # falling back to /tmp only on POSIX systems.
    try:
        return Path(get_astrbot_temp_path()) / filename
    except Exception:
        import tempfile

        return Path(tempfile.gettempdir()) / filename


def _is_within(path: Path, root: Path) -> bool:
    """Return True if *path* is inside *root* (after resolving both)."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


@builtin_tool(config=_COMPUTER_RUNTIME_TOOL_CONFIG)
@dataclass
class CreateSkillZipTool(FunctionTool):
    """Package a skill directory into a ZIP archive.

    The skill directory must already exist under ``data/skills/<skill_name>/``
    and contain at least a ``SKILL.md`` file.  The resulting ZIP is written
    to the temp directory and the path is returned so that
    ``install_skill_from_zip`` can consume it.
    """

    name: str = "astrbot_create_skill_zip"
    description: str = (
        "Package an existing skill directory into a ZIP archive for installation "
        "or distribution. The skill must already have a SKILL.md file in its directory."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Name of the skill directory under data/skills/ to package.",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Overwrite existing zip file if it exists. Defaults to false.",
                    "default": False,
                },
            },
            "required": ["skill_name"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        skill_name: str,
        overwrite: bool = False,
    ) -> ToolExecResult:
        if err := check_admin_permission(context, "Skill zip creation"):
            return err

        if not skill_name or not _SKILL_NAME_RE.fullmatch(skill_name):
            return "Error: Invalid skill name. Use only alphanumeric characters, dots, hyphens, and underscores."

        local_env = is_local_runtime(context)

        try:
            from astrbot.core.skills.skill_manager import (
                find_skill_markdown,
            )
            from astrbot.core.utils.astrbot_path import (
                get_astrbot_skills_path,
            )

            skills_root = get_astrbot_skills_path()
            skill_dir = Path(skills_root) / skill_name

            if not skill_dir.exists() or not skill_dir.is_dir():
                return f"Error: Skill directory not found: {skill_dir}"

            skill_md = find_skill_markdown(skill_dir)
            if skill_md is None:
                return "Error: No SKILL.md found in the skill directory."

            try:
                zip_path = _resolve_temp_path(local_env, f"{skill_name}.zip")
            except ValueError as ve:
                return f"Error: {ve}"
            zip_path.parent.mkdir(parents=True, exist_ok=True)

            if zip_path.exists() and not overwrite:
                return (
                    "Error: Zip file already exists. Set overwrite=true to replace it."
                )

            # Pack the skill directory into a zip
            with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _dirs, files in os.walk(skill_dir):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = Path(skill_name) / file_path.relative_to(skill_dir)
                        zf.write(str(file_path), str(arcname))

            return f"Skill '{skill_name}' packaged successfully. Zip file: {zip_path}"

        except ValueError as e:
            logger.warning("Validation error in create_skill_zip: %s", e)
            return f"Error: {e}"
        except Exception:
            logger.exception("Error creating skill zip")
            return "Error: Failed to create skill zip. Check logs for details."


@builtin_tool(config=_COMPUTER_RUNTIME_TOOL_CONFIG)
@dataclass
class InstallSkillFromZipTool(FunctionTool):
    """Install or update a skill from a ZIP archive.

    Wraps ``SkillManager.install_skill_from_zip()`` so the LLM can
    install a skill it just packaged (or received from a user).
    The ZIP must contain a ``SKILL.md`` at root or inside a top-level
    directory.
    """

    name: str = "astrbot_install_skill_from_zip"
    description: str = (
        "Install or update a skill from a ZIP file. The ZIP should contain "
        "a SKILL.md file either at the root or inside a single top-level directory."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "zip_path": {
                    "type": "string",
                    "description": (
                        "Path to the ZIP file. If relative, resolves under "
                        "the temp directory."
                    ),
                },
                "skill_name": {
                    "type": "string",
                    "description": (
                        "Optional name override for the installed skill. "
                        "If omitted, the name is derived from the zip contents."
                    ),
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Replace existing skill if it exists. Defaults to true.",
                    "default": True,
                },
            },
            "required": ["zip_path"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        zip_path: str,
        skill_name: str | None = None,
        overwrite: bool = True,
    ) -> ToolExecResult:
        if err := check_admin_permission(context, "Skill installation"):
            return err

        local_env = is_local_runtime(context)

        if skill_name and not _SKILL_NAME_RE.fullmatch(skill_name):
            return "Error: Invalid skill name. Use only alphanumeric characters, dots, hyphens, and underscores."

        try:
            from astrbot.core.skills.skill_manager import SkillManager

            # Resolve relative paths under temp dir; reject absolute paths
            # that escape allowed directories.
            if Path(zip_path).is_absolute():
                resolved = Path(zip_path)
                from astrbot.core.utils.astrbot_path import (
                    get_astrbot_skills_path,
                    get_astrbot_temp_path,
                )

                allowed_roots = [
                    Path(get_astrbot_temp_path()),
                    Path(get_astrbot_skills_path()),
                ]
                if not local_env:
                    # Sandbox runtime uses /tmp as its temp dir
                    allowed_roots.append(Path("/tmp"))
                if not any(_is_within(resolved, root) for root in allowed_roots):
                    return "Error: Absolute zip_path must be inside the temp or skills directory."
            else:
                try:
                    resolved = _resolve_temp_path(local_env, zip_path)
                except ValueError as ve:
                    return f"Error: {ve}"

            if not resolved.exists():
                return "Error: ZIP file not found."

            skill_manager = SkillManager()
            installed = skill_manager.install_skill_from_zip(
                zip_path=str(resolved),
                overwrite=overwrite,
                skill_name_hint=skill_name,
            )

            return f"Successfully installed skill(s): {installed}"

        except ValueError as e:
            logger.warning("Validation error in install_skill_from_zip: %s", e)
            return f"Error: {e}"
        except Exception:
            logger.exception("Error installing skill from zip")
            return "Error: Failed to install skill from zip. Check logs for details."
