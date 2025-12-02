from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from astrbot.core import db_helper
from astrbot.core.db.po import CommandConfig
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import PermissionType, PermissionTypeFilter
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import StarHandlerMetadata, star_handlers_registry


@dataclass
class CommandDescriptor:
    handler: StarHandlerMetadata = field(repr=False)
    filter_ref: CommandFilter | CommandGroupFilter | None = field(
        default=None,
        repr=False,
    )
    handler_full_name: str = ""
    handler_name: str = ""
    plugin_name: str = ""
    plugin_display_name: str | None = None
    module_path: str = ""
    description: str = ""
    command_type: str = "command"
    raw_command_name: str | None = None
    current_fragment: str | None = None
    parent_signature: str = ""
    original_command: str | None = None
    effective_command: str | None = None
    aliases: list[str] = field(default_factory=list)
    permission: str = "everyone"
    enabled: bool = True
    is_group: bool = False
    is_sub_command: bool = False
    config: CommandConfig | None = None
    keep_original_alias: bool = False
    has_conflict: bool = False


async def sync_command_configs() -> None:
    """同步指令配置，清理过期配置。"""
    descriptors = _collect_raw_descriptors()
    config_records = await db_helper.get_command_configs()
    config_map = {cfg.handler_full_name: cfg for cfg in config_records}
    live_handlers = {desc.handler_full_name for desc in descriptors}

    stale_configs = [key for key in config_map if key not in live_handlers]
    if stale_configs:
        await db_helper.delete_command_configs(stale_configs)
        for key in stale_configs:
            config_map.pop(key, None)

    for desc in descriptors:
        if cfg := config_map.get(desc.handler_full_name):
            _bind_descriptor_with_config(desc, cfg)


async def toggle_command(handler_full_name: str, enabled: bool) -> CommandDescriptor:
    descriptor = _build_descriptor_by_full_name(handler_full_name)
    if not descriptor:
        raise ValueError("指定的处理函数不存在或不是指令。")

    existing_cfg = await db_helper.get_command_config(handler_full_name)
    config = await db_helper.upsert_command_config(
        handler_full_name=handler_full_name,
        plugin_name=descriptor.plugin_name or "",
        module_path=descriptor.module_path,
        original_command=descriptor.original_command or descriptor.handler_name,
        resolved_command=(
            existing_cfg.resolved_command
            if existing_cfg
            else descriptor.current_fragment
        ),
        enabled=enabled,
        keep_original_alias=existing_cfg.keep_original_alias if existing_cfg else False,
        conflict_key=existing_cfg.conflict_key
        if existing_cfg and existing_cfg.conflict_key
        else descriptor.original_command,
        resolution_strategy=existing_cfg.resolution_strategy if existing_cfg else None,
        note=existing_cfg.note if existing_cfg else None,
        extra_data=existing_cfg.extra_data if existing_cfg else None,
        auto_managed=False,
    )
    _bind_descriptor_with_config(descriptor, config)
    await sync_command_configs()
    return descriptor


async def rename_command(
    handler_full_name: str,
    new_fragment: str,
    keep_original_alias: bool = False,
) -> CommandDescriptor:
    descriptor = _build_descriptor_by_full_name(handler_full_name)
    if not descriptor:
        raise ValueError("指定的处理函数不存在或不是指令。")

    new_fragment = new_fragment.strip()
    if not new_fragment:
        raise ValueError("指令名不能为空。")

    candidate_full = _compose_command(descriptor.parent_signature, new_fragment)
    if _is_command_in_use(handler_full_name, candidate_full):
        raise ValueError("新的指令名已被其他指令占用，请换一个名称。")

    config = await db_helper.upsert_command_config(
        handler_full_name=handler_full_name,
        plugin_name=descriptor.plugin_name or "",
        module_path=descriptor.module_path,
        original_command=descriptor.original_command or descriptor.handler_name,
        resolved_command=new_fragment,
        enabled=True if descriptor.enabled else False,
        keep_original_alias=keep_original_alias,
        conflict_key=descriptor.original_command,
        resolution_strategy="manual_rename",
        note=None,
        extra_data=None,
        auto_managed=False,
    )
    _bind_descriptor_with_config(descriptor, config)

    await sync_command_configs()
    return descriptor


async def list_commands() -> list[dict[str, Any]]:
    descriptors = _collect_raw_descriptors()
    config_records = await db_helper.get_command_configs()
    config_map = {cfg.handler_full_name: cfg for cfg in config_records}

    # 检测冲突：按 original_command 分组
    conflict_groups: dict[str, list[CommandDescriptor]] = defaultdict(list)
    for desc in descriptors:
        if desc.original_command:
            conflict_groups[desc.original_command].append(desc)

    # 标记冲突的指令
    conflict_handler_names: set[str] = set()
    for key, group in conflict_groups.items():
        if len(group) > 1:
            for desc in group:
                conflict_handler_names.add(desc.handler_full_name)

    result = []
    for desc in descriptors:
        if cfg := config_map.get(desc.handler_full_name):
            _bind_descriptor_with_config(desc, cfg)
        desc.has_conflict = desc.handler_full_name in conflict_handler_names
        result.append(_descriptor_to_dict(desc))
    return result


async def list_command_conflicts() -> list[dict[str, Any]]:
    """列出所有冲突的指令组。"""
    descriptors = _collect_raw_descriptors()
    config_records = await db_helper.get_command_configs()
    config_map = {cfg.handler_full_name: cfg for cfg in config_records}
    for desc in descriptors:
        if cfg := config_map.get(desc.handler_full_name):
            _bind_descriptor_with_config(desc, cfg)

    conflicts = defaultdict(list)
    for desc in descriptors:
        if not desc.original_command:
            continue
        conflicts[desc.original_command].append(desc)

    details = []
    for key, group in conflicts.items():
        if len(group) <= 1:
            continue
        details.append(
            {
                "conflict_key": key,
                "handlers": [
                    {
                        "handler_full_name": item.handler_full_name,
                        "plugin": item.plugin_name,
                        "current_name": item.effective_command,
                    }
                    for item in group
                ],
            },
        )
    return details


# Internal helpers ----------------------------------------------------------


def _collect_raw_descriptors() -> list[CommandDescriptor]:
    descriptors: list[CommandDescriptor] = []
    for handler in star_handlers_registry:
        desc = _build_descriptor(handler)
        if not desc or desc.is_sub_command:
            continue
        descriptors.append(desc)
    return descriptors


def _build_descriptor(handler: StarHandlerMetadata) -> CommandDescriptor | None:
    filter_ref = _locate_primary_filter(handler)
    if filter_ref is None:
        return None

    plugin_meta = star_map.get(handler.handler_module_path)
    plugin_name = (
        plugin_meta.name if plugin_meta else None
    ) or handler.handler_module_path
    plugin_display = plugin_meta.display_name if plugin_meta else None

    if isinstance(filter_ref, CommandFilter):
        raw_fragment = getattr(
            filter_ref, "_original_command_name", filter_ref.command_name
        )
        current_fragment = filter_ref.command_name
        parent_signature = (filter_ref.parent_command_names or [""])[0].strip()
    else:
        raw_fragment = getattr(
            filter_ref, "_original_group_name", filter_ref.group_name
        )
        current_fragment = filter_ref.group_name
        parent_signature = _resolve_group_parent_signature(filter_ref)

    original_command = _compose_command(parent_signature, raw_fragment)
    effective_command = _compose_command(parent_signature, current_fragment)

    descriptor = CommandDescriptor(
        handler=handler,
        filter_ref=filter_ref,
        handler_full_name=handler.handler_full_name,
        handler_name=handler.handler_name,
        plugin_name=plugin_name,
        plugin_display_name=plugin_display,
        module_path=handler.handler_module_path,
        description=handler.desc or "",
        command_type="group"
        if isinstance(filter_ref, CommandGroupFilter)
        else "command",
        raw_command_name=raw_fragment,
        current_fragment=current_fragment,
        parent_signature=parent_signature,
        original_command=original_command,
        effective_command=effective_command,
        aliases=sorted(getattr(filter_ref, "alias", set())),
        permission=_determine_permission(handler),
        enabled=handler.enabled,
        is_group=isinstance(filter_ref, CommandGroupFilter),
        is_sub_command=bool(handler.extras_configs.get("sub_command")),
    )
    return descriptor


def _build_descriptor_by_full_name(full_name: str) -> CommandDescriptor | None:
    handler = star_handlers_registry.get_handler_by_full_name(full_name)
    if not handler:
        return None
    return _build_descriptor(handler)


def _locate_primary_filter(
    handler: StarHandlerMetadata,
) -> CommandFilter | CommandGroupFilter | None:
    for filter_ref in handler.event_filters:
        if isinstance(filter_ref, (CommandFilter, CommandGroupFilter)):
            return filter_ref
    return None


def _determine_permission(handler: StarHandlerMetadata) -> str:
    for filter_ref in handler.event_filters:
        if isinstance(filter_ref, PermissionTypeFilter):
            return (
                "admin"
                if filter_ref.permission_type == PermissionType.ADMIN
                else "member"
            )
    return "everyone"


def _resolve_group_parent_signature(group_filter: CommandGroupFilter) -> str:
    signatures: list[str] = []
    parent = group_filter.parent_group
    while parent:
        signatures.append(getattr(parent, "_original_group_name", parent.group_name))
        parent = parent.parent_group
    return " ".join(reversed(signatures)).strip()


def _compose_command(parent_signature: str, fragment: str | None) -> str:
    fragment = (fragment or "").strip()
    parent_signature = parent_signature.strip()
    if not parent_signature:
        return fragment
    if not fragment:
        return parent_signature
    return f"{parent_signature} {fragment}"


def _bind_descriptor_with_config(descriptor: CommandDescriptor, config: CommandConfig):
    descriptor.config = config
    descriptor.keep_original_alias = config.keep_original_alias
    descriptor.enabled = config.enabled
    descriptor.handler.enabled = config.enabled

    if config.original_command:
        descriptor.original_command = config.original_command

    new_fragment = config.resolved_command or descriptor.current_fragment
    descriptor.current_fragment = new_fragment
    descriptor.effective_command = _compose_command(
        descriptor.parent_signature,
        new_fragment,
    )

    if descriptor.filter_ref and new_fragment:
        _set_filter_fragment(
            descriptor.filter_ref,
            new_fragment,
            keep_original=config.keep_original_alias,
            original_fragment=descriptor.raw_command_name,
        )


def _set_filter_fragment(
    filter_ref: CommandFilter | CommandGroupFilter,
    fragment: str,
    *,
    keep_original: bool,
    original_fragment: str | None,
) -> None:
    attr = (
        "group_name" if isinstance(filter_ref, CommandGroupFilter) else "command_name"
    )
    current_value = getattr(filter_ref, attr)
    if fragment == current_value:
        return
    if keep_original and original_fragment:
        alias_set = getattr(filter_ref, "alias", set())
        alias_set.add(original_fragment)
    setattr(filter_ref, attr, fragment)
    if hasattr(filter_ref, "_cmpl_cmd_names"):
        filter_ref._cmpl_cmd_names = None


def _is_command_in_use(
    target_handler_full_name: str,
    candidate_full_command: str,
) -> bool:
    candidate = candidate_full_command.strip()
    for handler in star_handlers_registry:
        if handler.handler_full_name == target_handler_full_name:
            continue
        filter_ref = _locate_primary_filter(handler)
        if not filter_ref:
            continue
        names = {name.strip() for name in filter_ref.get_complete_command_names()}
        if candidate in names:
            return True
    return False


def _descriptor_to_dict(desc: CommandDescriptor) -> dict[str, Any]:
    return {
        "handler_full_name": desc.handler_full_name,
        "handler_name": desc.handler_name,
        "plugin": desc.plugin_name,
        "plugin_display_name": desc.plugin_display_name,
        "module_path": desc.module_path,
        "description": desc.description,
        "type": desc.command_type,
        "parent_signature": desc.parent_signature,
        "original_command": desc.original_command,
        "current_fragment": desc.current_fragment,
        "effective_command": desc.effective_command,
        "aliases": desc.aliases,
        "permission": desc.permission,
        "enabled": desc.enabled,
        "is_group": desc.is_group,
        "has_conflict": desc.has_conflict,
        "keep_original_alias": desc.keep_original_alias,
    }
