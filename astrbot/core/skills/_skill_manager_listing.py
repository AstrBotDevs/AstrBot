import os
from pathlib import Path

from astrbot.core.skills._skill_inventory import (
    _SKILL_NAME_RE,
    SkillInfo,
    _default_sandbox_skill_path,
    _normalize_cached_sandbox_skill_path,
    _normalize_skill_markdown_path,
    _read_skill_description,
)


class SkillManagerListingMixin:
    skills_root: str
    sandbox_skills_cache_path: str
    _SANDBOX_SKILLS_CACHE_VERSION: int

    def _load_config(self) -> dict: ...
    def _save_config(self, config: dict) -> None: ...
    def _load_sandbox_skills_cache(self) -> dict: ...
    def _save_sandbox_skills_cache(self, cache: dict) -> None: ...
    def _get_plugin_skill_dir(self, name: str) -> Path | None: ...
    def _iter_plugin_skill_dirs(self) -> list[tuple[str, str, Path]]: ...
    def _get_builtin_skill_dir(self, name: str) -> Path | None: ...
    def _iter_builtin_skill_dirs(self) -> list[tuple[str, str, Path]]: ...

    def set_sandbox_skills_cache(self, skills: list[dict]) -> None:
        """Persist sandbox skill metadata discovered from runtime side."""
        deduped: dict[str, dict[str, str]] = {}
        for item in skills:
            normalized_item = self._normalize_sandbox_cache_item(item)
            if normalized_item is None:
                continue
            deduped[normalized_item["name"]] = normalized_item
        cache = {
            "version": self._SANDBOX_SKILLS_CACHE_VERSION,
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

    def _get_cached_sandbox_skills(self) -> dict[str, dict[str, str]]:
        cached_skills: dict[str, dict[str, str]] = {}
        cache = self._load_sandbox_skills_cache()
        for item in cache.get("skills", []):
            normalized_item = self._normalize_sandbox_cache_item(item)
            if normalized_item is None:
                continue
            cached_skills[normalized_item["name"]] = {
                "description": normalized_item["description"],
                "path": normalized_item["path"],
            }
        return cached_skills

    @staticmethod
    def _normalize_sandbox_cache_item(item: object) -> dict[str, str] | None:
        name = SkillManagerListingMixin._extract_valid_cached_skill_name(item)
        if name is None or not isinstance(item, dict):
            return None
        return {
            "name": name,
            "description": str(item.get("description", "") or ""),
            "path": _normalize_cached_sandbox_skill_path(
                name,
                str(item.get("path", "") or ""),
            ),
        }

    @staticmethod
    def _extract_valid_cached_skill_name(item: object) -> str | None:
        if not isinstance(item, dict):
            return None
        name = str(item.get("name", "") or "").strip()
        if not name or not _SKILL_NAME_RE.match(name):
            return None
        return name

    def _ensure_skill_config(
        self, skill_configs: dict[str, dict], skill_name: str
    ) -> tuple[bool, bool]:
        active = skill_configs.get(skill_name, {}).get("active", True)
        if skill_name in skill_configs:
            return active, False
        skill_configs[skill_name] = {"active": active}
        return active, True

    def _build_listed_skill_info(
        self,
        *,
        skill_name: str,
        description: str,
        active: bool,
        runtime: str,
        show_sandbox_path: bool,
        source_type: str,
        source_label: str,
        local_exists: bool,
        sandbox_exists: bool,
        sandbox_skill: dict[str, str] | None = None,
        skill_md: Path | None = None,
        plugin_name: str = "",
        readonly: bool = False,
    ) -> SkillInfo:
        path_str = self._resolve_listed_skill_path(
            skill_name=skill_name,
            runtime=runtime,
            show_sandbox_path=show_sandbox_path,
            local_exists=local_exists,
            sandbox_skill=sandbox_skill,
            skill_md=skill_md,
        )
        return SkillInfo(
            name=skill_name,
            description=description,
            path=path_str.replace("\\", "/"),
            active=active,
            source_type=source_type,
            source_label=source_label,
            local_exists=local_exists,
            sandbox_exists=sandbox_exists,
            plugin_name=plugin_name,
            readonly=readonly,
        )

    @staticmethod
    def _resolve_listed_skill_path(
        *,
        skill_name: str,
        runtime: str,
        show_sandbox_path: bool,
        local_exists: bool,
        sandbox_skill: dict[str, str] | None,
        skill_md: Path | None,
    ) -> str:
        if runtime == "sandbox" and (show_sandbox_path or not local_exists):
            if sandbox_skill is not None:
                return sandbox_skill["path"]
            return _default_sandbox_skill_path(skill_name)
        if skill_md is not None:
            return str(skill_md)
        return _default_sandbox_skill_path(skill_name)

    def _add_markdown_backed_skill(
        self,
        *,
        skills_by_name: dict[str, SkillInfo],
        cached_sandbox_skills: dict[str, dict[str, str]],
        skill_configs: dict[str, dict],
        skill_name: str,
        skill_md: Path,
        active_only: bool,
        runtime: str,
        show_sandbox_path: bool,
        source_type: str,
        source_label: str,
        plugin_name: str = "",
        readonly: bool = False,
    ) -> bool:
        active, added = self._ensure_skill_config(skill_configs, skill_name)
        if active_only and not active:
            return added

        sandbox_skill = cached_sandbox_skills.get(skill_name)
        sandbox_exists = runtime == "sandbox" and sandbox_skill is not None
        source_type, source_label = self._resolve_markdown_skill_source(
            source_type=source_type,
            source_label=source_label,
            sandbox_exists=sandbox_exists,
        )

        skills_by_name[skill_name] = self._build_listed_skill_info(
            skill_name=skill_name,
            description=_read_skill_description(skill_md),
            active=active,
            runtime=runtime,
            show_sandbox_path=show_sandbox_path,
            source_type=source_type,
            source_label=source_label,
            local_exists=True,
            sandbox_exists=sandbox_exists,
            sandbox_skill=sandbox_skill,
            skill_md=skill_md,
            plugin_name=plugin_name,
            readonly=readonly,
        )
        return added

    @staticmethod
    def _resolve_markdown_skill_source(
        *,
        source_type: str,
        source_label: str,
        sandbox_exists: bool,
    ) -> tuple[str, str]:
        if source_type == "local_only" and sandbox_exists:
            return "both", "synced"
        return source_type, source_label

    def _add_sandbox_only_listed_skill(
        self,
        *,
        skills_by_name: dict[str, SkillInfo],
        skill_configs: dict[str, dict],
        skill_name: str,
        sandbox_skill: dict[str, str],
        active_only: bool,
        runtime: str,
        show_sandbox_path: bool,
    ) -> bool:
        active, added = self._ensure_skill_config(skill_configs, skill_name)
        if active_only and not active:
            return added

        skills_by_name[skill_name] = self._build_listed_skill_info(
            skill_name=skill_name,
            description=sandbox_skill["description"],
            active=active,
            runtime=runtime,
            show_sandbox_path=show_sandbox_path,
            source_type="sandbox_only",
            source_label="sandbox_preset",
            local_exists=False,
            sandbox_exists=True,
            sandbox_skill=sandbox_skill,
        )
        return added

    def _add_local_listed_skills(
        self,
        *,
        skills_by_name: dict[str, SkillInfo],
        cached_sandbox_skills: dict[str, dict[str, str]],
        skill_configs: dict[str, dict],
        active_only: bool,
        runtime: str,
        show_sandbox_path: bool,
    ) -> bool:
        modified = False
        for entry in sorted(Path(self.skills_root).iterdir()):
            if not entry.is_dir():
                continue
            skill_name = entry.name
            skill_md = _normalize_skill_markdown_path(entry)
            if skill_md is None:
                continue
            modified = (
                self._add_markdown_backed_skill(
                    skills_by_name=skills_by_name,
                    cached_sandbox_skills=cached_sandbox_skills,
                    skill_configs=skill_configs,
                    skill_name=skill_name,
                    skill_md=skill_md,
                    active_only=active_only,
                    runtime=runtime,
                    show_sandbox_path=show_sandbox_path,
                    source_type="local_only",
                    source_label="local",
                )
                or modified
            )
        return modified

    def _add_plugin_listed_skills(
        self,
        *,
        skills_by_name: dict[str, SkillInfo],
        cached_sandbox_skills: dict[str, dict[str, str]],
        skill_configs: dict[str, dict],
        active_only: bool,
        runtime: str,
        show_sandbox_path: bool,
    ) -> bool:
        modified = False
        for skill_name, plugin_name, skill_dir in self._iter_plugin_skill_dirs():
            if skill_name in skills_by_name:
                continue
            skill_md = _normalize_skill_markdown_path(skill_dir)
            if skill_md is None:
                continue
            modified = (
                self._add_markdown_backed_skill(
                    skills_by_name=skills_by_name,
                    cached_sandbox_skills=cached_sandbox_skills,
                    skill_configs=skill_configs,
                    skill_name=skill_name,
                    skill_md=skill_md,
                    active_only=active_only,
                    runtime=runtime,
                    show_sandbox_path=show_sandbox_path,
                    source_type="plugin",
                    source_label=plugin_name,
                    plugin_name=plugin_name,
                    readonly=True,
                )
                or modified
            )
        return modified

    def _add_builtin_listed_skills(
        self,
        *,
        skills_by_name: dict[str, SkillInfo],
        cached_sandbox_skills: dict[str, dict[str, str]],
        skill_configs: dict[str, dict],
        active_only: bool,
        runtime: str,
        show_sandbox_path: bool,
    ) -> bool:
        modified = False
        for skill_name, source_label, skill_dir in self._iter_builtin_skill_dirs():
            if skill_name in skills_by_name:
                continue
            skill_md = _normalize_skill_markdown_path(skill_dir)
            if skill_md is None:
                continue
            modified = (
                self._add_markdown_backed_skill(
                    skills_by_name=skills_by_name,
                    cached_sandbox_skills=cached_sandbox_skills,
                    skill_configs=skill_configs,
                    skill_name=skill_name,
                    skill_md=skill_md,
                    active_only=active_only,
                    runtime=runtime,
                    show_sandbox_path=show_sandbox_path,
                    source_type="builtin_preset",
                    source_label=source_label,
                    readonly=True,
                )
                or modified
            )
        return modified

    def _add_sandbox_cached_listed_skills(
        self,
        *,
        skills_by_name: dict[str, SkillInfo],
        cached_sandbox_skills: dict[str, dict[str, str]],
        skill_configs: dict[str, dict],
        active_only: bool,
        runtime: str,
        show_sandbox_path: bool,
    ) -> bool:
        if runtime != "sandbox":
            return False
        modified = False
        for skill_name, sandbox_skill in cached_sandbox_skills.items():
            if skill_name in skills_by_name:
                continue
            modified = (
                self._add_sandbox_only_listed_skill(
                    skills_by_name=skills_by_name,
                    skill_configs=skill_configs,
                    skill_name=skill_name,
                    sandbox_skill=sandbox_skill,
                    active_only=active_only,
                    runtime=runtime,
                    show_sandbox_path=show_sandbox_path,
                )
                or modified
            )
        return modified

    def list_skills(
        self,
        *,
        active_only: bool = False,
        runtime: str = "local",
        show_sandbox_path: bool = True,
    ) -> list[SkillInfo]:
        """List all skills."""
        config = self._load_config()
        skill_configs = config.get("skills", {})
        skills_by_name: dict[str, SkillInfo] = {}
        cached_sandbox_skills = self._get_cached_sandbox_skills()

        modified = self._populate_listed_skills(
            skills_by_name=skills_by_name,
            cached_sandbox_skills=cached_sandbox_skills,
            skill_configs=skill_configs,
            active_only=active_only,
            runtime=runtime,
            show_sandbox_path=show_sandbox_path,
        )
        self._save_skill_config_if_modified(
            config=config,
            skill_configs=skill_configs,
            modified=modified,
        )
        return [skills_by_name[name] for name in sorted(skills_by_name)]

    def _populate_listed_skills(
        self,
        *,
        skills_by_name: dict[str, SkillInfo],
        cached_sandbox_skills: dict[str, dict[str, str]],
        skill_configs: dict[str, dict],
        active_only: bool,
        runtime: str,
        show_sandbox_path: bool,
    ) -> bool:
        modified = False
        for adder in (
            self._add_local_listed_skills,
            self._add_plugin_listed_skills,
            self._add_builtin_listed_skills,
            self._add_sandbox_cached_listed_skills,
        ):
            modified = (
                adder(
                    skills_by_name=skills_by_name,
                    cached_sandbox_skills=cached_sandbox_skills,
                    skill_configs=skill_configs,
                    active_only=active_only,
                    runtime=runtime,
                    show_sandbox_path=show_sandbox_path,
                )
                or modified
            )
        return modified

    def _save_skill_config_if_modified(
        self,
        *,
        config: dict,
        skill_configs: dict[str, dict],
        modified: bool,
    ) -> None:
        if not modified:
            return
        config["skills"] = skill_configs
        self._save_config(config)

    def is_sandbox_only_skill(self, name: str) -> bool:
        skill_dir = Path(self.skills_root) / name
        skill_md_exists = _normalize_skill_markdown_path(skill_dir) is not None
        if skill_md_exists or self._get_plugin_skill_dir(name) is not None:
            return False
        if self._get_builtin_skill_dir(name) is not None:
            return False
        return name in self._get_cached_sandbox_skills()

    def is_plugin_skill(self, name: str) -> bool:
        skill_dir = Path(self.skills_root) / name
        if _normalize_skill_markdown_path(skill_dir) is not None:
            return False
        return self._get_plugin_skill_dir(name) is not None

    def is_builtin_skill(self, name: str) -> bool:
        skill_dir = Path(self.skills_root) / name
        if _normalize_skill_markdown_path(skill_dir) is not None:
            return False
        if self._get_plugin_skill_dir(name) is not None:
            return False
        return self._get_builtin_skill_dir(name) is not None

    def set_skill_active(self, name: str, active: bool) -> None:
        if self.is_sandbox_only_skill(name):
            raise PermissionError(
                "Sandbox preset skill cannot be enabled/disabled from local skill management."
            )
        if self.is_plugin_skill(name):
            raise PermissionError(
                "Plugin-provided skill cannot be enabled/disabled from local skill management."
            )
        if self.is_builtin_skill(name):
            raise PermissionError(
                "Builtin preset skill cannot be enabled/disabled from local skill management."
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
            item for item in skills if not self._is_cached_skill_named(item, name)
        ]

        if len(filtered) != len(skills):
            cache["skills"] = filtered
            self._save_sandbox_skills_cache(cache)

    @staticmethod
    def _is_cached_skill_named(item: object, name: str) -> bool:
        return isinstance(item, dict) and str(item.get("name", "")).strip() == name
