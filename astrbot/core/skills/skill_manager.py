from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_skills_path,
    get_astrbot_temp_path,
)

SKILLS_CONFIG_FILENAME = "skills.json"
DEFAULT_SKILLS_CONFIG: dict[str, dict] = {"skills": {}}
# SANDBOX_SKILLS_ROOT = "/home/shared/skills"
SANDBOX_SKILLS_ROOT = "skills"

_SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass
class SkillInfo:
    name: str
    description: str
    path: str
    active: bool


def _parse_frontmatter_description(text: str) -> str:
    if not text.startswith("---"):
        return ""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return ""
    for line in lines[1:end_idx]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip().lower() == "description":
            return value.strip().strip('"').strip("'")
    return ""


def build_skills_prompt(skills: list[SkillInfo]) -> str:
    skills_lines = []
    for skill in skills:
        description = skill.description or "No description"
        skills_lines.append(f"- {skill.name}: {description} (file: {skill.path})")
    skills_block = "\n".join(skills_lines)
    # Based on openai/codex
    return (
        "## Skills\n"
        "A skill is a set of local instructions stored in a `SKILL.md` file.\n"
        "### Available skills\n"
        f"{skills_block}\n"
        "### Skill Rules\n"
        "\n"
        "- Discovery: The list above shows all skills available in this session. Full instructions live in the referenced `SKILL.md`.\n"
        "- Trigger rules: Use a skill if the user names it or the task matches its description. Do not carry skills across turns unless re-mentioned\n"
        "- Unavailable: If a skill is missing or unreadable, say so and fallback.\n"
        "### How to use a skill (progressive disclosure):\n"
        "  1) After deciding to use a skill, open its `SKILL.md` and read only what is necessary to follow the workflow.\n"
        "  2) Load only directly referenced files, DO NOT bulk-load everything.\n"
        "  3) If `scripts/` exist, prefer running or patching them instead of retyping large blocks of code.\n"
        "  4) If `assets/` or templates exist, reuse them rather than recreating everything from scratch.\n"
        "- Coordination:\n"
        "  - If multiple skills apply, choose the minimal set that covers the request and state the order in which you will use them.\n"
        "  - Announce which skill(s) you are using and why (one short line). If you skip an obvious skill, explain why.\n"
        "  - Prefer to use `astrbot_*` tools to perform skills that need to run scripts.\n"
        "- Context hygiene:\n"
        "  - Keep context small: summarize long sections instead of pasting them, and load extra files only when necessary.\n"
        "  - Avoid deep reference chasing: unless blocked, open only files that are directly linked from `SKILL.md`.\n"
        "  - When variants exist (frameworks, providers, domains), select only the relevant reference file(s) and note that choice.\n"
        "- Failure handling: If a skill cannot be applied, state the issue and continue with the best alternative."
    )


class SkillManager:
    def __init__(self, skills_root: str | None = None) -> None:
        self.skills_root = skills_root or get_astrbot_skills_path()
        self.config_path = os.path.join(get_astrbot_data_path(), SKILLS_CONFIG_FILENAME)
        os.makedirs(self.skills_root, exist_ok=True)
        os.makedirs(get_astrbot_temp_path(), exist_ok=True)

    def _load_config(self) -> dict:
        if not os.path.exists(self.config_path):
            self._save_config(DEFAULT_SKILLS_CONFIG.copy())
            return DEFAULT_SKILLS_CONFIG.copy()
        with open(self.config_path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "skills" not in data:
            return DEFAULT_SKILLS_CONFIG.copy()
        return data

    def _save_config(self, config: dict) -> None:
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)

    def list_skills(
        self,
        *,
        active_only: bool = False,
        runtime: str = "local",
        show_sandbox_path: bool = True,
    ) -> list[SkillInfo]:
        """List all skills.

        show_sandbox_path: If True and runtime is "sandbox",
            return the path as it would appear in the sandbox environment,
            otherwise return the local filesystem path.
        """
        config = self._load_config()
        skill_configs = config.get("skills", {})
        modified = False
        skills: list[SkillInfo] = []

        for entry in sorted(Path(self.skills_root).iterdir()):
            if not entry.is_dir():
                continue
            skill_name = entry.name
            skill_md = entry / "SKILL.md"
            if not skill_md.exists():
                continue
            active = skill_configs.get(skill_name, {}).get("active", True)
            if skill_name not in skill_configs:
                skill_configs[skill_name] = {"active": active}
                modified = True
            if active_only and not active:
                continue
            description = ""
            try:
                content = skill_md.read_text(encoding="utf-8")
                description = _parse_frontmatter_description(content)
            except Exception:
                description = ""
            if runtime == "sandbox" and show_sandbox_path:
                path_str = f"{SANDBOX_SKILLS_ROOT}/{skill_name}/SKILL.md"
            else:
                path_str = str(skill_md)
            path_str = path_str.replace("\\", "/")
            skills.append(
                SkillInfo(
                    name=skill_name,
                    description=description,
                    path=path_str,
                    active=active,
                )
            )

        if modified:
            config["skills"] = skill_configs
            self._save_config(config)

        return skills

    def set_skill_active(self, name: str, active: bool) -> None:
        config = self._load_config()
        config.setdefault("skills", {})
        config["skills"][name] = {"active": bool(active)}
        self._save_config(config)

    def delete_skill(self, name: str) -> None:
        skill_dir = Path(self.skills_root) / name
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
        config = self._load_config()
        if name in config.get("skills", {}):
            config["skills"].pop(name, None)
            self._save_config(config)

    def install_skill_from_zip(self, zip_path: str, *, overwrite: bool = True) -> str:
        zip_path_obj = Path(zip_path)
        if not zip_path_obj.exists():
            raise FileNotFoundError(f"Zip file not found: {zip_path}")
        if not zipfile.is_zipfile(zip_path):
            raise ValueError("Uploaded file is not a valid zip archive.")

        with zipfile.ZipFile(zip_path) as zf:
            names = [name.replace("\\", "/") for name in zf.namelist()]
            file_names = [name for name in names if name and not name.endswith("/")]
            if not file_names:
                raise ValueError("Zip archive is empty.")

            top_dirs = {
                PurePosixPath(name).parts[0] for name in file_names if name.strip()
            }
            print(top_dirs)
            if len(top_dirs) != 1:
                raise ValueError("Zip archive must contain a single top-level folder.")
            skill_name = next(iter(top_dirs))
            if skill_name in {".", "..", ""} or not _SKILL_NAME_RE.match(skill_name):
                raise ValueError("Invalid skill folder name.")

            for name in names:
                if not name:
                    continue
                if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
                    raise ValueError("Zip archive contains absolute paths.")
                parts = PurePosixPath(name).parts
                if ".." in parts:
                    raise ValueError("Zip archive contains invalid relative paths.")
                if parts and parts[0] != skill_name:
                    raise ValueError(
                        "Zip archive contains unexpected top-level entries."
                    )

            if (
                f"{skill_name}/SKILL.md" not in file_names
                and f"{skill_name}/skill.md" not in file_names
            ):
                raise ValueError("SKILL.md not found in the skill folder.")

            with tempfile.TemporaryDirectory(dir=get_astrbot_temp_path()) as tmp_dir:
                zf.extractall(tmp_dir)
                src_dir = Path(tmp_dir) / skill_name
                if not src_dir.exists():
                    raise ValueError("Skill folder not found after extraction.")
                dest_dir = Path(self.skills_root) / skill_name
                if dest_dir.exists():
                    if not overwrite:
                        raise FileExistsError("Skill already exists.")
                    shutil.rmtree(dest_dir)
                shutil.move(str(src_dir), str(dest_dir))

        self.set_skill_active(skill_name, True)
        return skill_name
