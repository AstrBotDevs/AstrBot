import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from astrbot.core.skills._skill_inventory import (
    SANDBOX_SKILLS_ROOT,
    SANDBOX_WORKSPACE_ROOT,
    WORKSPACE_SKILLS_ROOT,
    SkillInfo,
    _parse_frontmatter_description,
    build_skills_prompt,
)
from astrbot.core.skills._skill_manager_archive import SkillManagerArchiveMixin
from astrbot.core.skills._skill_manager_inventory import SkillManagerInventoryMixin
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_plugin_path,
    get_astrbot_skills_path,
)
from astrbot.core.utils.astrbot_path import (
    get_astrbot_temp_path as _get_astrbot_temp_path,
)

SKILLS_CONFIG_FILENAME = "skills.json"
SANDBOX_SKILLS_CACHE_FILENAME = "sandbox_skills_cache.json"
DEFAULT_SKILLS_CONFIG: dict[str, dict] = {"skills": {}}
_SANDBOX_SKILLS_CACHE_VERSION = 1
get_astrbot_temp_path = _get_astrbot_temp_path

if TYPE_CHECKING:
    from astrbot.core.skills.builtin_skill_catalog import BuiltinSkillCatalog

__all__ = [
    "SANDBOX_SKILLS_ROOT",
    "SANDBOX_WORKSPACE_ROOT",
    "WORKSPACE_SKILLS_ROOT",
    "SkillInfo",
    "SkillManager",
    "build_skills_prompt",
    "_parse_frontmatter_description",
    "get_astrbot_temp_path",
]


class SkillManager(SkillManagerInventoryMixin, SkillManagerArchiveMixin):
    _SANDBOX_SKILLS_CACHE_VERSION = _SANDBOX_SKILLS_CACHE_VERSION

    def __init__(
        self,
        skills_root: str | None = None,
        plugins_root: str | None = None,
        builtin_skill_catalog: BuiltinSkillCatalog | None = None,
    ) -> None:
        self.skills_root = skills_root or get_astrbot_skills_path()
        self.plugins_root = plugins_root or get_astrbot_plugin_path()
        self.builtin_skill_catalog = builtin_skill_catalog
        data_path = Path(get_astrbot_data_path())
        self.config_path = str(data_path / SKILLS_CONFIG_FILENAME)
        self.sandbox_skills_cache_path = str(data_path / SANDBOX_SKILLS_CACHE_FILENAME)
        os.makedirs(self.skills_root, exist_ok=True)

    def _load_config(self) -> dict:
        if not os.path.exists(self.config_path):
            self._save_config(DEFAULT_SKILLS_CONFIG.copy())
            return DEFAULT_SKILLS_CONFIG.copy()
        with open(self.config_path, encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict) or "skills" not in data:
            return DEFAULT_SKILLS_CONFIG.copy()
        return data

    def _save_config(self, config: dict) -> None:
        with open(self.config_path, "w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=4)

    def _load_sandbox_skills_cache(self) -> dict:
        if not os.path.exists(self.sandbox_skills_cache_path):
            return {"version": _SANDBOX_SKILLS_CACHE_VERSION, "skills": []}
        try:
            with open(self.sandbox_skills_cache_path, encoding="utf-8") as file:
                data = json.load(file)
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
        cache["updated_at"] = datetime.now(UTC).isoformat()
        with open(self.sandbox_skills_cache_path, "w", encoding="utf-8") as file:
            json.dump(cache, file, ensure_ascii=False, indent=2)
