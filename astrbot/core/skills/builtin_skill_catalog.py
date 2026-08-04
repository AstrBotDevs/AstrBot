"""Runtime-owned inventory of Skills bundled with loaded builtin Stars."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core.star.star import PluginRegistry


@dataclass(frozen=True, slots=True)
class BuiltinSkillSource:
    """One trusted builtin Star directory that may provide Skills."""

    root_dir_name: str
    source_label: str
    root_path: Path


class BuiltinSkillCatalog:
    """Resolve builtin Skill sources from one initialized plugin registry.

    The catalog holds no process-global plugin state. The lifecycle binds it to
    its runtime registry only after builtin Stars have been loaded.
    """

    def __init__(self) -> None:
        self._plugins: PluginRegistry | None = None
        self._builtin_root: Path | None = None

    def bind(self, plugins: PluginRegistry, builtin_root: str | Path) -> None:
        """Bind this catalog to the initialized runtime plugin registry."""
        self._plugins = plugins
        self._builtin_root = Path(builtin_root).resolve(strict=False)

    def sources(self) -> tuple[BuiltinSkillSource, ...]:
        """Return trusted Skill roots from currently loaded builtin Stars."""
        if self._plugins is None or self._builtin_root is None:
            return ()

        sources: list[BuiltinSkillSource] = []
        for metadata in self._plugins.all():
            root_dir_name = metadata.root_dir_name
            if not metadata.reserved or not isinstance(root_dir_name, str):
                continue
            if not root_dir_name or Path(root_dir_name).name != root_dir_name:
                continue
            source_root = self._resolve_source_root(root_dir_name)
            if source_root is None:
                continue
            source_label = metadata.display_name or metadata.name or root_dir_name
            sources.append(
                BuiltinSkillSource(
                    root_dir_name=root_dir_name,
                    source_label=str(source_label),
                    root_path=source_root,
                )
            )
        return tuple(sorted(sources, key=lambda source: source.root_dir_name))

    def _resolve_source_root(self, root_dir_name: str) -> Path | None:
        assert self._builtin_root is not None
        try:
            builtin_root = self._builtin_root.resolve(strict=True)
            source_root = (builtin_root / root_dir_name).resolve(strict=True)
        except OSError:
            return None
        if not source_root.is_dir() or not source_root.is_relative_to(builtin_root):
            return None
        return source_root
