"""Resource identities, persona selections, and global settings."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, model_validator

from astrbot.core import sp


class SourceSelectionGroup(BaseModel):
    """Persisted selection of individual or all available members of a source."""

    kind: Literal["tool", "skill"]
    source: Literal["plugin", "mcp", "local", "sandbox", "astrbot"]
    source_id: str | None = None
    items: list[str] | None

    @model_validator(mode="after")
    def validate_source(self) -> SourceSelectionGroup:
        valid = {
            "tool": {"plugin", "mcp", "astrbot"},
            "skill": {"plugin", "local", "sandbox"},
        }
        if self.source not in valid[self.kind]:
            raise ValueError("Invalid source for this selection kind")
        if (self.source in {"plugin", "mcp"}) != bool(self.source_id):
            raise ValueError("Plugin and MCP selections require a source ID")
        if any(not name for name in self.items or []):
            raise ValueError("Selection member names cannot be empty")
        return self


PersonaSelection = list[str | dict] | None


@dataclass(frozen=True)
class ResourceRef:
    """One member's identity, independent of its display and model names."""

    kind: Literal["plugin", "tool", "skill"]
    source: str
    source_id: str | None
    name: str

    @property
    def key(self) -> str:
        member = quote(self.name, safe="")
        if self.kind == "plugin":
            return f"plugin/{member}"
        if self.source == "plugin":
            return (
                f"plugin/{quote(self.source_id or '', safe='')}/{self.kind}s/{member}"
            )
        if self.source == "mcp":
            return f"mcp_servers/{quote(self.source_id or '', safe='')}/tools/{member}"
        if self.source == "local":
            return f"skills/{member}"
        return f"{self.source}/{self.kind}s/{member}"

    def metadata(self) -> dict:
        return {
            "source": self.source,
            "source_id": self.source_id,
            "name": self.name,
            "key": self.key,
        }


def tool_ref(tool) -> ResourceRef:
    """Resolve a registered tool's identity, including permission wrappers."""
    from astrbot.core.agent.mcp_client import MCPTool
    from astrbot.core.star.star import star_map

    ref = getattr(tool, "resource_ref", None)
    if ref is not None:
        return ref
    if isinstance(tool, MCPTool):
        return ResourceRef("tool", "mcp", tool.mcp_server_name, tool.mcp_tool.name)
    plugin = star_map.get(getattr(tool, "handler_module_path", None))
    if plugin is not None:
        return ResourceRef("tool", "plugin", plugin.plugin_id, tool.name)
    return ResourceRef("tool", "astrbot", None, tool.name)


def selected_members(
    selection: PersonaSelection,
    kind: Literal["tool", "skill"],
    available: Iterable[ResourceRef],
) -> Iterable[str | ResourceRef]:
    """Expand selected sources after individual selections.

    Args:
        selection: The saved tool or skill selection.
        kind: The member type for this selection.
        available: Runtime-authorized resource references for expanding sources.

    Yields:
        Legacy names and resource references in selection order, followed by
        available members of all-selected sources.
    """
    selected_sources = set()
    for entry in selection or []:
        if isinstance(entry, str):
            yield entry
        elif isinstance(entry, dict):
            try:
                group = SourceSelectionGroup.model_validate(entry)
            except ValueError:
                continue
            if group.kind != kind:
                continue
            if group.items is None:
                selected_sources.add((group.source, group.source_id))
            else:
                for name in group.items:
                    yield ResourceRef(kind, group.source, group.source_id, name)
    if selected_sources:
        for ref in available:
            if ref.kind == kind and (ref.source, ref.source_id) in selected_sources:
                yield ref


def resolve_tools(selection: PersonaSelection, tools) -> list:
    """Resolve exact selections before deduplicating model names."""
    candidates = list(tools)
    by_ref = {}
    by_name = {}
    for tool in candidates:
        ref = tool_ref(tool)
        if tool.active or ref not in by_ref or not by_ref[ref].active:
            by_ref[ref] = tool
        if tool.active or tool.name not in by_name or not by_name[tool.name].active:
            by_name[tool.name] = tool
    if selection is None:
        return [tool for tool in by_name.values() if tool.active]
    selected = {}
    refs = list(selected_members(selection, "tool", by_ref))
    # Prioritize explicit choices over legacy same-name entries.
    for ref in [item for item in refs if not isinstance(item, str)] + [
        item for item in refs if isinstance(item, str)
    ]:
        tool = by_name.get(ref) if isinstance(ref, str) else by_ref.get(ref)
        if tool is not None and tool.active:
            selected.setdefault(tool.name, tool)
    return list(selected.values())


SETTINGS_SCOPE = "global_resource_settings"
LEGACY_SKILLS_KEY = "legacy_skill_switches"
_settings_lock = asyncio.Lock()


async def update_setting(ref: ResourceRef, **changes) -> None:
    """Update one resource without discarding other fields on the same row."""
    async with _settings_lock:
        current = await sp.get_async(SETTINGS_SCOPE, "global", ref.key, {})
        await sp.put_async(SETTINGS_SCOPE, "global", ref.key, {**current, **changes})


async def global_settings() -> dict[str, dict]:
    """Load the resource settings in one query for a catalog or reload."""
    rows = await sp.range_get_async(SETTINGS_SCOPE, "global")
    return {
        row.key: row.value["val"]
        for row in rows
        if isinstance(row.value.get("val"), dict)
    }


async def legacy_setting(key: str, default):
    """Read the migrated legacy rule or its original row during initialization."""
    value = await sp.get_async(SETTINGS_SCOPE, "legacy", key, None)
    return await sp.global_get(key, default) if value is None else value


async def write_legacy_setting(key: str, value) -> None:
    """Update a compatibility rule, retaining its original lookup semantics."""
    await sp.put_async(SETTINGS_SCOPE, "legacy", key, value)


async def migrate_legacy_settings(filename: Path) -> None:
    """Copy compatibility rules before retiring their former storage locations.

    Args:
        filename: Path of the old skill settings file.
    """
    for key in ("inactivated_plugins", "inactivated_llm_tools", "tool_permissions"):
        original = await sp.global_get(key, None)
        if original is None:
            continue
        if await sp.get_async(SETTINGS_SCOPE, "legacy", key, None) is None:
            await write_legacy_setting(key, original)
        await sp.remove_async("global", "global", key)

    imported = await sp.get_async(SETTINGS_SCOPE, "legacy", LEGACY_SKILLS_KEY, None)
    if not filename.is_file():
        if imported is None:
            await write_legacy_setting(LEGACY_SKILLS_KEY, {})
        return

    with filename.open(encoding="utf-8") as file:
        data = json.load(file)
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("skills"), dict)
        or any(not isinstance(entry, dict) for entry in data["skills"].values())
    ):
        raise ValueError("Invalid legacy skill settings")

    legacy = data["skills"]
    if imported is None:
        await write_legacy_setting(LEGACY_SKILLS_KEY, legacy)
    elif imported != legacy:
        # A retry can remove the imported file, but a later replacement may contain new data.
        return
    filename.unlink(missing_ok=True)
