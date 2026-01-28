from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from astrbot.core import db_helper, logger
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
    command_type: str = "command"  # "command" | "group" | "sub_command"
    raw_command_name: str | None = None
    current_fragment: str | None = None
    parent_signature: str = ""
    parent_group_handler: str = ""
    original_command: str | None = None
    effective_command: str | None = None
    aliases: list[str] = field(default_factory=list)
    permission: str = "everyone"
    enabled: bool = True
    is_group: bool = False
    is_sub_command: bool = False
    reserved: bool = False
    priority: int = 0
    config: CommandConfig | None = None
    has_conflict: bool = False
    sub_commands: list[CommandDescriptor] = field(default_factory=list)


async def sync_command_configs() -> None:
    """同步指令配置，清理过期配置。"""
    descriptors = _collect_descriptors(include_sub_commands=False)
    config_records = await db_helper.get_command_configs()
    config_map = _bind_configs_to_descriptors(descriptors, config_records)
    live_handlers = {desc.handler_full_name for desc in descriptors}

    stale_configs = [key for key in config_map if key not in live_handlers]
    if stale_configs:
        await db_helper.delete_command_configs(stale_configs)


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
        keep_original_alias=False,
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
    aliases: list[str] | None = None,
) -> CommandDescriptor:
    descriptor = _build_descriptor_by_full_name(handler_full_name)
    if not descriptor:
        raise ValueError("指定的处理函数不存在或不是指令。")

    new_fragment = new_fragment.strip()
    if not new_fragment:
        raise ValueError("指令名不能为空。")

    # 校验主指令名
    candidate_full = _compose_command(descriptor.parent_signature, new_fragment)
    if _is_command_in_use(handler_full_name, candidate_full):
        raise ValueError(f"指令名 '{candidate_full}' 已被其他指令占用。")

    # 校验别名
    if aliases:
        for alias in aliases:
            alias = alias.strip()
            if not alias:
                continue
            alias_full = _compose_command(descriptor.parent_signature, alias)
            if _is_command_in_use(handler_full_name, alias_full):
                raise ValueError(f"别名 '{alias_full}' 已被其他指令占用。")

    existing_cfg = await db_helper.get_command_config(handler_full_name)
    merged_extra = dict(existing_cfg.extra_data or {}) if existing_cfg else {}
    merged_extra["resolved_aliases"] = aliases or []

    config = await db_helper.upsert_command_config(
        handler_full_name=handler_full_name,
        plugin_name=descriptor.plugin_name or "",
        module_path=descriptor.module_path,
        original_command=descriptor.original_command or descriptor.handler_name,
        resolved_command=new_fragment,
        enabled=True if descriptor.enabled else False,
        keep_original_alias=False,
        conflict_key=descriptor.original_command,
        resolution_strategy="manual_rename",
        note=None,
        extra_data=merged_extra,
        auto_managed=False,
    )
    _bind_descriptor_with_config(descriptor, config)

    await sync_command_configs()
    return descriptor


async def list_commands() -> list[dict[str, Any]]:
    descriptors = _collect_descriptors(include_sub_commands=True)
    config_records = await db_helper.get_command_configs()
    _bind_configs_to_descriptors(descriptors, config_records)

    conflict_groups = _group_conflicts(descriptors)
    conflict_handler_names: set[str] = {
        d.handler_full_name for group in conflict_groups.values() for d in group
    }

    # 分类，设置冲突标志，将子指令挂载到父指令组
    group_map: dict[str, CommandDescriptor] = {}
    sub_commands: list[CommandDescriptor] = []
    root_commands: list[CommandDescriptor] = []

    for desc in descriptors:
        desc.has_conflict = desc.handler_full_name in conflict_handler_names
        if desc.is_group:
            group_map[desc.handler_full_name] = desc
        elif desc.is_sub_command:
            sub_commands.append(desc)
        else:
            root_commands.append(desc)

    for sub in sub_commands:
        if sub.parent_group_handler and sub.parent_group_handler in group_map:
            group_map[sub.parent_group_handler].sub_commands.append(sub)
        else:
            root_commands.append(sub)

    # 指令组 + 普通指令，按 effective_command 字母排序
    all_commands = list(group_map.values()) + root_commands
    all_commands.sort(key=lambda d: (d.effective_command or "").lower())

    result = [_descriptor_to_dict(desc) for desc in all_commands]
    return result


async def list_command_conflicts() -> list[dict[str, Any]]:
    """列出所有冲突的指令组。"""
    descriptors = _collect_descriptors(include_sub_commands=False)
    config_records = await db_helper.get_command_configs()
    _bind_configs_to_descriptors(descriptors, config_records)

    conflict_groups = _group_conflicts(descriptors)
    details = [
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
        }
        for key, group in conflict_groups.items()
    ]
    return details


# Internal helpers ----------------------------------------------------------


def _collect_descriptors(include_sub_commands: bool) -> list[CommandDescriptor]:
    """收集指令，按需包含子指令。"""
    descriptors: list[CommandDescriptor] = []
    for handler in star_handlers_registry:
        try:
            desc = _build_descriptor(handler)
            if not desc:
                continue
            if not include_sub_commands and desc.is_sub_command:
                continue
            descriptors.append(desc)
        except Exception as e:
            logger.warning(
                f"解析指令处理函数 {handler.handler_full_name} 失败，跳过该指令。原因: {e!s}"
            )
            continue
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

    is_sub_command = bool(handler.extras_configs.get("sub_command"))
    parent_group_handler = ""

    if isinstance(filter_ref, CommandFilter):
        raw_fragment = getattr(
            filter_ref, "_original_command_name", filter_ref.command_name
        )
        current_fragment = filter_ref.command_name
        parent_signature = (filter_ref.parent_command_names or [""])[0].strip()
        # 如果是子指令，尝试找到父指令组的 handler_full_name
        if is_sub_command and parent_signature:
            parent_group_handler = _find_parent_group_handler(
                handler.handler_module_path, parent_signature
            )
    else:
        raw_fragment = getattr(
            filter_ref, "_original_group_name", filter_ref.group_name
        )
        current_fragment = filter_ref.group_name
        parent_signature = _resolve_group_parent_signature(filter_ref)

    original_command = _compose_command(parent_signature, raw_fragment)
    effective_command = _compose_command(parent_signature, current_fragment)

    # 确定 command_type
    if isinstance(filter_ref, CommandGroupFilter):
        command_type = "group"
    elif is_sub_command:
        command_type = "sub_command"
    else:
        command_type = "command"

    descriptor = CommandDescriptor(
        handler=handler,
        filter_ref=filter_ref,
        handler_full_name=handler.handler_full_name,
        handler_name=handler.handler_name,
        plugin_name=plugin_name,
        plugin_display_name=plugin_display,
        module_path=handler.handler_module_path,
        description=handler.desc or "",
        command_type=command_type,
        raw_command_name=raw_fragment,
        current_fragment=current_fragment,
        parent_signature=parent_signature,
        parent_group_handler=parent_group_handler,
        original_command=original_command,
        effective_command=effective_command,
        aliases=sorted(getattr(filter_ref, "alias", set())),
        permission=_determine_permission(handler),
        enabled=handler.enabled,
        is_group=isinstance(filter_ref, CommandGroupFilter),
        is_sub_command=is_sub_command,
        reserved=plugin_meta.reserved if plugin_meta else False,
        priority=star_handlers_registry._get_effective_priority(handler),
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
        if isinstance(filter_ref, CommandFilter | CommandGroupFilter):
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


def _find_parent_group_handler(module_path: str, parent_signature: str) -> str:
    """根据模块路径和父级签名，找到对应的指令组 handler_full_name。"""
    parent_sig_normalized = parent_signature.strip()
    for handler in star_handlers_registry:
        if handler.handler_module_path != module_path:
            continue
        filter_ref = _locate_primary_filter(handler)
        if not isinstance(filter_ref, CommandGroupFilter):
            continue
        # 检查该指令组的完整指令名是否匹配 parent_signature
        group_names = filter_ref.get_complete_command_names()
        if parent_sig_normalized in group_names:
            return handler.handler_full_name
    return ""


def _compose_command(parent_signature: str, fragment: str | None) -> str:
    fragment = (fragment or "").strip()
    parent_signature = parent_signature.strip()
    if not parent_signature:
        return fragment
    if not fragment:
        return parent_signature
    return f"{parent_signature} {fragment}"


def _bind_descriptor_with_config(
    descriptor: CommandDescriptor,
    config: CommandConfig,
) -> None:
    _apply_config_to_descriptor(descriptor, config)
    _apply_config_to_runtime(descriptor, config)


def _apply_config_to_descriptor(
    descriptor: CommandDescriptor,
    config: CommandConfig,
) -> None:
    descriptor.config = config
    descriptor.enabled = config.enabled

    if config.original_command:
        descriptor.original_command = config.original_command

    new_fragment = config.resolved_command or descriptor.current_fragment
    descriptor.current_fragment = new_fragment
    descriptor.effective_command = _compose_command(
        descriptor.parent_signature,
        new_fragment,
    )

    extra = config.extra_data or {}
    resolved_aliases = extra.get("resolved_aliases")
    if isinstance(resolved_aliases, list):
        descriptor.aliases = [str(x) for x in resolved_aliases if str(x).strip()]


def _apply_config_to_runtime(
    descriptor: CommandDescriptor,
    config: CommandConfig,
) -> None:
    descriptor.handler.enabled = config.enabled
    if descriptor.filter_ref:
        if descriptor.current_fragment:
            _set_filter_fragment(descriptor.filter_ref, descriptor.current_fragment)
        extra = config.extra_data or {}
        resolved_aliases = extra.get("resolved_aliases")
        if isinstance(resolved_aliases, list):
            _set_filter_aliases(
                descriptor.filter_ref,
                [str(x) for x in resolved_aliases if str(x).strip()],
            )


def _bind_configs_to_descriptors(
    descriptors: list[CommandDescriptor],
    config_records: list[CommandConfig],
) -> dict[str, CommandConfig]:
    config_map = {cfg.handler_full_name: cfg for cfg in config_records}
    for desc in descriptors:
        if cfg := config_map.get(desc.handler_full_name):
            _bind_descriptor_with_config(desc, cfg)
    return config_map


def _group_conflicts(
    descriptors: list[CommandDescriptor],
) -> dict[str, list[CommandDescriptor]]:
    conflicts: dict[str, list[CommandDescriptor]] = defaultdict(list)
    for desc in descriptors:
        if desc.effective_command and desc.enabled:
            conflicts[desc.effective_command].append(desc)
    return {k: v for k, v in conflicts.items() if len(v) > 1}


def _set_filter_fragment(
    filter_ref: CommandFilter | CommandGroupFilter,
    fragment: str,
) -> None:
    attr = (
        "group_name" if isinstance(filter_ref, CommandGroupFilter) else "command_name"
    )
    current_value = getattr(filter_ref, attr)
    if fragment == current_value:
        return
    setattr(filter_ref, attr, fragment)
    if hasattr(filter_ref, "_cmpl_cmd_names"):
        filter_ref._cmpl_cmd_names = None


def _set_filter_aliases(
    filter_ref: CommandFilter | CommandGroupFilter,
    aliases: list[str],
) -> None:
    current_aliases = getattr(filter_ref, "alias", set())
    if set(aliases) == current_aliases:
        return
    setattr(filter_ref, "alias", set(aliases))
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
    result = {
        "handler_full_name": desc.handler_full_name,
        "handler_name": desc.handler_name,
        "plugin": desc.plugin_name,
        "plugin_display_name": desc.plugin_display_name,
        "module_path": desc.module_path,
        "description": desc.description,
        "type": desc.command_type,
        "parent_signature": desc.parent_signature,
        "parent_group_handler": desc.parent_group_handler,
        "original_command": desc.original_command,
        "current_fragment": desc.current_fragment,
        "effective_command": desc.effective_command,
        "aliases": desc.aliases,
        "permission": desc.permission,
        "enabled": desc.enabled,
        "is_group": desc.is_group,
        "has_conflict": desc.has_conflict,
        "reserved": desc.reserved,
        "priority": desc.priority,
    }
    # 如果是指令组，包含子指令列表
    if desc.is_group and desc.sub_commands:
        result["sub_commands"] = [_descriptor_to_dict(sub) for sub in desc.sub_commands]
    else:
        result["sub_commands"] = []
    return result
