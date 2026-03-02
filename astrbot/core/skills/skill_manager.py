from __future__ import annotations
from astrbot.core.lang import t

import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_skills_path,
    get_astrbot_temp_path,
)

SKILLS_CONFIG_FILENAME = "skills.json"
SANDBOX_SKILLS_CACHE_FILENAME = "sandbox_skills_cache.json"
DEFAULT_SKILLS_CONFIG: dict[str, dict] = {"skills": {}}
SANDBOX_SKILLS_ROOT = "skills"
SANDBOX_WORKSPACE_ROOT = "/workspace"
_SANDBOX_SKILLS_CACHE_VERSION = 1

_SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass
class SkillInfo:
    name: str
    description: str
    path: str
    active: bool
    source_type: str = "local_only"
    source_label: str = "local"
    local_exists: bool = True
    sandbox_exists: bool = False


def _parse_frontmatter_description(text: str) -> str:
    """Extract the ``description`` value from YAML frontmatter.

    Expects the standard SKILL.md format used by OpenAI Codex CLI and
    Anthropic Claude Skills::

        ---
        name: my-skill
        description: What this skill does and when to use it.
        ---
    """
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


# Regex for sanitizing paths used in prompt examples — only allow
# safe path characters to prevent prompt injection via crafted skill paths.
_SAFE_PATH_RE = re.compile(r"[^A-Za-z0-9_./ -]")


def build_skills_prompt(skills: list[SkillInfo]) -> str:
    """Build the skills section of the system prompt.

    Generates a markdown-formatted skill inventory for the LLM.  Only
    ``name`` and ``description`` are shown upfront; the LLM must read
    the full ``SKILL.md`` before execution (progressive disclosure).
    """
    skills_lines: list[str] = []
    example_path = ""
    for skill in skills:
        description = skill.description or "No description"
        skills_lines.append(
            f"- **{skill.name}**: {description}\n  File: `{skill.path}`"
        )
        if not example_path:
            example_path = skill.path
    skills_block = "\n".join(skills_lines)
    # Sanitize example_path — it may originate from sandbox cache (untrusted)
    example_path = _SAFE_PATH_RE.sub("", example_path) if example_path else ""
    example_path = example_path or "<skills_root>/<skill_name>/SKILL.md"

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
        "first read its `SKILL.md` by running a shell command with the "
        f"**absolute path** shown above (e.g. `cat {example_path}`). "
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


class SkillManager:
    def __init__(self, skills_root: str | None = None) -> None:
        self.skills_root = skills_root or get_astrbot_skills_path()
        data_path = Path(get_astrbot_data_path())
        self.config_path = str(data_path / SKILLS_CONFIG_FILENAME)
        self.sandbox_skills_cache_path = str(data_path / SANDBOX_SKILLS_CACHE_FILENAME)
        os.makedirs(self.skills_root, exist_ok=True)

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

    def _load_sandbox_skills_cache(self) -> dict:
        if not os.path.exists(self.sandbox_skills_cache_path):
            return {"version": _SANDBOX_SKILLS_CACHE_VERSION, "skills": []}
        try:
            with open(self.sandbox_skills_cache_path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {"version": _SANDBOX_SKILLS_CACHE_VERSION, "skills": []}
            skills = data.get("skills", [])
            if not isinstance(skills, list):
                skills = []
            return {
                "version": int(data.get("version", _SANDBOX_SKILLS_CACHE_VERSION)),
                "skills": skills,
                "updated_at": data.get("updated_at"),
            }
        except Exception:
            return {"version": _SANDBOX_SKILLS_CACHE_VERSION, "skills": []}

    def _save_sandbox_skills_cache(self, cache: dict) -> None:
        cache["version"] = _SANDBOX_SKILLS_CACHE_VERSION
        cache["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(self.sandbox_skills_cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

    def set_sandbox_skills_cache(self, skills: list[dict]) -> None:
        """Persist sandbox skill metadata discovered from runtime side."""
        deduped: dict[str, dict[str, str]] = {}
        for item in skills:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name or not _SKILL_NAME_RE.match(name):
                continue
            description = str(item.get("description", "") or "")
            path = str(item.get("path", "") or "")
            if not path:
                path = f"{SANDBOX_WORKSPACE_ROOT}/{SANDBOX_SKILLS_ROOT}/{name}/SKILL.md"
            deduped[name] = {
                "name": name,
                "description": description,
                "path": path.replace("\\", "/"),
            }
        cache = {
            "version": _SANDBOX_SKILLS_CACHE_VERSION,
            "skills": [deduped[name] for name in sorted(deduped)],
        }
        self._save_sandbox_skills_cache(cache)

    def get_sandbox_skills_cache_status(self) -> dict[str, object]:
        cache = self._load_sandbox_skills_cache()
        skills = cache.get("skills", [])
        count = len(skills) if isinstance(skills, list) else 0
        return {
            "exists": os.path.exists(self.sandbox_skills_cache_path),
            "ready": count > 0,
            "count": count,
            "updated_at": cache.get("updated_at"),
        }

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
        skills_by_name: dict[str, SkillInfo] = {}

        sandbox_cached_paths: dict[str, str] = {}
        sandbox_cached_descriptions: dict[str, str] = {}
        cache_for_paths = self._load_sandbox_skills_cache()
        for item in cache_for_paths.get("skills", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "") or "").strip()
            path = str(item.get("path", "") or "").strip().replace("\\", "/")
            if not name or not _SKILL_NAME_RE.match(name):
                continue
            sandbox_cached_descriptions[name] = str(item.get("description", "") or "")
            if path:
                sandbox_cached_paths[name] = path

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
            sandbox_exists = (
                runtime == "sandbox" and skill_name in sandbox_cached_descriptions
            )
            source_type = "both" if sandbox_exists else "local_only"
            source_label = "synced" if sandbox_exists else "local"
            if runtime == "sandbox" and show_sandbox_path:
                path_str = sandbox_cached_paths.get(skill_name) or (
                    f"{SANDBOX_WORKSPACE_ROOT}/{SANDBOX_SKILLS_ROOT}/{skill_name}/SKILL.md"
                )
            else:
                path_str = str(skill_md)
            path_str = path_str.replace("\\", "/")
            skills_by_name[skill_name] = SkillInfo(
                name=skill_name,
                description=description,
                path=path_str,
                active=active,
                source_type=source_type,
                source_label=source_label,
                local_exists=True,
                sandbox_exists=sandbox_exists,
            )

        if runtime == "sandbox":
            cache = self._load_sandbox_skills_cache()
            for item in cache.get("skills", []):
                if not isinstance(item, dict):
                    continue
                skill_name = str(item.get("name", "")).strip()
                if (
                    not skill_name
                    or skill_name in skills_by_name
                    or not _SKILL_NAME_RE.match(skill_name)
                ):
                    continue
                active = skill_configs.get(skill_name, {}).get("active", True)
                if skill_name not in skill_configs:
                    skill_configs[skill_name] = {"active": active}
                    modified = True
                if active_only and not active:
                    continue
                description = sandbox_cached_descriptions.get(skill_name, "")
                if show_sandbox_path:
                    path_str = f"{SANDBOX_WORKSPACE_ROOT}/{SANDBOX_SKILLS_ROOT}/{skill_name}/SKILL.md"
                else:
                    path_str = sandbox_cached_paths.get(skill_name, "")
                    if not path_str:
                        path_str = f"{SANDBOX_WORKSPACE_ROOT}/{SANDBOX_SKILLS_ROOT}/{skill_name}/SKILL.md"
                skills_by_name[skill_name] = SkillInfo(
                    name=skill_name,
                    description=description,
                    path=path_str.replace("\\", "/"),
                    active=active,
                    source_type="sandbox_only",
                    source_label="sandbox_preset",
                    local_exists=False,
                    sandbox_exists=True,
                )

        if modified:
            config["skills"] = skill_configs
            self._save_config(config)

        return [skills_by_name[name] for name in sorted(skills_by_name)]

    def is_sandbox_only_skill(self, name: str) -> bool:
        skill_dir = Path(self.skills_root) / name
        skill_md_exists = (skill_dir / "SKILL.md").exists()
        if skill_md_exists:
            return False
        cache = self._load_sandbox_skills_cache()
        skills = cache.get("skills", [])
        if not isinstance(skills, list):
            return False
        for item in skills:
            if not isinstance(item, dict):
                continue
            if str(item.get("name", "")).strip() == name:
                return True
        return False

    def set_skill_active(self, name: str, active: bool) -> None:
        if self.is_sandbox_only_skill(name):
            raise PermissionError(
                "Sandbox preset skill cannot be enabled/disabled from local skill management."
            )
        config = self._load_config()
        config.setdefault("skills", {})
        config["skills"][name] = {"active": bool(active)}
        self._save_config(config)

    def _remove_skill_from_sandbox_cache(self, name: str) -> None:
        cache = self._load_sandbox_skills_cache()
        skills = cache.get("skills", [])
        if not isinstance(skills, list):
            return

        filtered = [
            item
            for item in skills
            if not (
                isinstance(item, dict) and str(item.get("name", "")).strip() == name
            )
        ]

        if len(filtered) != len(skills):
            cache["skills"] = filtered
            self._save_sandbox_skills_cache(cache)

    def delete_skill(self, name: str) -> None:
        if self.is_sandbox_only_skill(name):
            raise PermissionError(
                "Sandbox preset skill cannot be deleted from local skill management."
            )

        skill_dir = Path(self.skills_root) / name
        if skill_dir.exists():
            shutil.rmtree(skill_dir)

        # Ensure UI consistency even when there is no active sandbox session
        # to refresh cache from runtime side.
        self._remove_skill_from_sandbox_cache(name)

        config = self._load_config()
        if name in config.get("skills", {}):
            config["skills"].pop(name, None)
            self._save_config(config)

    def install_skill_from_zip(self, zip_path: str, *, overwrite: bool = True) -> str:
        zip_path_obj = Path(zip_path)
        if not zip_path_obj.exists():
            raise FileNotFoundError(t("msg-ed9670ad", zip_path=zip_path))
        if not zipfile.is_zipfile(zip_path):
            raise ValueError(t("msg-73f9cf65"))

        with zipfile.ZipFile(zip_path) as zf:
            names = [name.replace("\\", "/") for name in zf.namelist()]
            file_names = [name for name in names if name and not name.endswith("/")]
            if not file_names:
                raise ValueError(t("msg-69eb5f95"))

            top_dirs = {
                PurePosixPath(name).parts[0] for name in file_names if name.strip()
            }

            if len(top_dirs) != 1:
                raise ValueError(t("msg-20b8533f"))
            skill_name = next(iter(top_dirs))
            if skill_name in {".", "..", ""} or not _SKILL_NAME_RE.match(skill_name):
                raise ValueError(t("msg-1db1caf7"))

            for name in names:
                if not name:
                    continue
                if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
                    raise ValueError(t("msg-d7814054"))
                parts = PurePosixPath(name).parts
                if ".." in parts:
                    raise ValueError(t("msg-179bd10e"))
                if parts and parts[0] != skill_name:
                    raise ValueError(
                        t("msg-90f2904e")
                    )

            if (
                f"{skill_name}/SKILL.md" not in file_names
                and f"{skill_name}/skill.md" not in file_names
            ):
                raise ValueError(t("msg-95775a4d"))

            with tempfile.TemporaryDirectory(dir=get_astrbot_temp_path()) as tmp_dir:
                zf.extractall(tmp_dir)
                src_dir = Path(tmp_dir) / skill_name
                if not src_dir.exists():
                    raise ValueError(t("msg-a4117c0b"))
                dest_dir = Path(self.skills_root) / skill_name
                if dest_dir.exists():
                    if not overwrite:
                        raise FileExistsError(t("msg-94041ef2"))
                    shutil.rmtree(dest_dir)
                shutil.move(str(src_dir), str(dest_dir))

        self.set_skill_active(skill_name, True)
        return skill_name
