from pathlib import Path

from astrbot.core.skills._skill_inventory import (
    _SKILL_NAME_RE,
    WORKSPACE_SKILL_FRONTMATTER_MAX_CHARS,
    WORKSPACE_SKILLS_ROOT,
    SkillInfo,
    _normalize_skill_markdown_path,
    _parse_frontmatter_description,
)
from astrbot.core.skills.builtin_skill_catalog import BuiltinSkillCatalog


class SkillManagerDiscoveryMixin:
    plugins_root: str
    builtin_skill_catalog: BuiltinSkillCatalog | None

    def _iter_builtin_skill_dirs(self) -> list[tuple[str, str, Path]]:
        """Return loaded builtin Skill directories as (skill, source, dir)."""
        catalog = self.builtin_skill_catalog
        if catalog is None:
            return []

        result: list[tuple[str, str, Path]] = []
        for source in catalog.sources():
            skills_dir = source.root_path / "skills"
            if not skills_dir.is_dir():
                continue
            root_entry = self._build_root_plugin_skill_entry(
                skills_dir,
                source.root_dir_name,
            )
            if root_entry is not None:
                skill_name, _unused, skill_dir = root_entry
                result.append((skill_name, source.source_label, skill_dir))
            for nested in self._iter_nested_plugin_skill_entries(
                skills_dir,
                source.root_dir_name,
            ):
                skill_name, _unused, skill_dir = nested
                result.append((skill_name, source.source_label, skill_dir))
        return result

    def _iter_plugin_skill_dirs(self) -> list[tuple[str, str, Path]]:
        """Return plugin-provided skill directories as (skill, plugin, dir)."""
        plugins_root = Path(self.plugins_root)
        if not plugins_root.is_dir():
            return []

        result: list[tuple[str, str, Path]] = []
        for plugin_dir in sorted(plugins_root.iterdir(), key=lambda item: item.name):
            plugin_entries = self._collect_plugin_skill_dirs(plugin_dir)
            if plugin_entries:
                result.extend(plugin_entries)
        return result

    def _collect_plugin_skill_dirs(
        self,
        plugin_dir: Path,
    ) -> list[tuple[str, str, Path]]:
        if not plugin_dir.is_dir():
            return []
        plugin_name = plugin_dir.name
        skills_dir = plugin_dir / "skills"
        if not skills_dir.is_dir():
            return []

        result: list[tuple[str, str, Path]] = []
        root_entry = self._build_root_plugin_skill_entry(skills_dir, plugin_name)
        if root_entry is not None:
            result.append(root_entry)
        result.extend(self._iter_nested_plugin_skill_entries(skills_dir, plugin_name))
        return result

    @staticmethod
    def _build_root_plugin_skill_entry(
        skills_dir: Path,
        plugin_name: str,
    ) -> tuple[str, str, Path] | None:
        if _normalize_skill_markdown_path(skills_dir) is None:
            return None
        if not _SKILL_NAME_RE.match(plugin_name):
            return None
        return plugin_name, plugin_name, skills_dir

    def _iter_nested_plugin_skill_entries(
        self,
        skills_dir: Path,
        plugin_name: str,
    ) -> list[tuple[str, str, Path]]:
        result: list[tuple[str, str, Path]] = []
        for skill_dir in sorted(skills_dir.iterdir(), key=lambda item: item.name):
            nested_entry = self._build_nested_plugin_skill_entry(skill_dir, plugin_name)
            if nested_entry is not None:
                result.append(nested_entry)
        return result

    @staticmethod
    def _build_nested_plugin_skill_entry(
        skill_dir: Path,
        plugin_name: str,
    ) -> tuple[str, str, Path] | None:
        if not skill_dir.is_dir():
            return None
        skill_name = skill_dir.name
        if not _SKILL_NAME_RE.match(skill_name):
            return None
        if _normalize_skill_markdown_path(skill_dir) is None:
            return None
        return skill_name, plugin_name, skill_dir

    def _get_plugin_skill_dir(self, name: str) -> Path | None:
        for skill_name, _plugin_name, skill_dir in self._iter_plugin_skill_dirs():
            if skill_name == name:
                return skill_dir
        return None

    def _get_builtin_skill_dir(self, name: str) -> Path | None:
        for skill_name, _source_label, skill_dir in self._iter_builtin_skill_dirs():
            if skill_name == name:
                return skill_dir
        return None

    @staticmethod
    def _resolve_workspace_skills_root(
        workspace_root: str | Path | None,
    ) -> Path | None:
        if not workspace_root:
            return None
        raw_workspace_root = Path(workspace_root)
        skills_root = raw_workspace_root / WORKSPACE_SKILLS_ROOT
        if not skills_root.is_dir():
            return None
        try:
            resolved_workspace_root = raw_workspace_root.resolve(strict=True)
            resolved_skills_root = skills_root.resolve(strict=True)
        except OSError:
            return None
        if not resolved_skills_root.is_relative_to(resolved_workspace_root):
            return None
        return resolved_skills_root

    @staticmethod
    def _read_workspace_skill_description(skill_md: Path) -> str:
        try:
            with skill_md.open(encoding="utf-8") as file:
                content = file.read(WORKSPACE_SKILL_FRONTMATTER_MAX_CHARS)
            return _parse_frontmatter_description(content)
        except OSError, UnicodeError:
            return ""

    @staticmethod
    def _build_workspace_skill_info(
        *,
        skill_name: str,
        skill_md: Path,
        description: str,
    ) -> SkillInfo:
        return SkillInfo(
            name=skill_name,
            description=description,
            path=skill_md.as_posix(),
            active=True,
            source_type="workspace",
            source_label="workspace",
            local_exists=True,
            readonly=True,
        )

    @staticmethod
    def _resolve_workspace_skill_md(
        skill_dir: Path,
        resolved_skills_root: Path,
    ) -> Path | None:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            return None
        try:
            resolved_skill_md = skill_md.resolve(strict=True)
        except OSError:
            return None
        if not resolved_skill_md.is_relative_to(resolved_skills_root):
            return None
        return resolved_skill_md

    def list_workspace_skills(
        self, workspace_root: str | Path | None
    ) -> list[SkillInfo]:
        """List request-scoped skills from a session workspace."""
        resolved_skills_root = self._resolve_workspace_skills_root(workspace_root)
        if resolved_skills_root is None:
            return []

        try:
            skill_dirs = sorted(
                resolved_skills_root.iterdir(), key=lambda item: item.name
            )
        except OSError:
            return []

        skills: list[SkillInfo] = []
        for skill_dir in skill_dirs:
            skill = self._build_workspace_listed_skill(
                skill_dir,
                resolved_skills_root=resolved_skills_root,
            )
            if skill is not None:
                skills.append(skill)

        return skills

    def _build_workspace_listed_skill(
        self,
        skill_dir: Path,
        *,
        resolved_skills_root: Path,
    ) -> SkillInfo | None:
        skill_name = self._get_valid_workspace_skill_name(skill_dir)
        if skill_name is None or not self._has_workspace_skill_file(skill_dir):
            return None
        resolved_skill_md = self._resolve_workspace_skill_md(
            skill_dir,
            resolved_skills_root,
        )
        if resolved_skill_md is None:
            return None
        return self._build_workspace_skill_info(
            skill_name=skill_name,
            skill_md=resolved_skill_md,
            description=self._read_workspace_skill_description(resolved_skill_md),
        )

    @staticmethod
    def _get_valid_workspace_skill_name(skill_dir: Path) -> str | None:
        if not skill_dir.is_dir():
            return None
        skill_name = skill_dir.name
        if not _SKILL_NAME_RE.match(skill_name):
            return None
        return skill_name

    @staticmethod
    def _has_workspace_skill_file(skill_dir: Path) -> bool:
        try:
            return "SKILL.md" in {entry.name for entry in skill_dir.iterdir()}
        except OSError:
            return False
