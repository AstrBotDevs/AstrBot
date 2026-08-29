from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from astrbot import logger
from astrbot.core.db.po import CommandConfig
from astrbot.core.db.protocols import CommandStore
from astrbot.core.star.command_ids import (
    BUILTIN_COMMANDS_MODULE,
    compute_command_id,
    take_alter_cmd_entry,
)
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import ActionPermissionFilter
from astrbot.core.star.star_handler import HandlerRegistry, StarHandlerMetadata
from astrbot.core.utils.shared_preferences import SharedPreferences


@dataclass
class CommandDescriptor:
    handler: StarHandlerMetadata = field(repr=False)
    filter_ref: CommandFilter | CommandGroupFilter | None = field(
        default=None,
        repr=False,
    )
    command_id: str = ""
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
    signature: str = ""
    display_signature: str = ""
    aliases: list[str] = field(default_factory=list)
    action: str | None = None
    enabled: bool = True
    plugin_activated: bool = True
    is_group: bool = False
    is_sub_command: bool = False
    reserved: bool = False
    config: CommandConfig | None = None
    has_conflict: bool = False
    sub_commands: list[CommandDescriptor] = field(default_factory=list)


async def sync_command_configs(
    db: CommandStore,
    handler_registry: HandlerRegistry,
) -> None:
    """同步指令配置，清理过期配置。"""
    descriptors = _collect_descriptors(handler_registry, include_sub_commands=True)
    config_records = await db.get_command_configs()
    live_by_full_name = {desc.handler_full_name: desc for desc in descriptors}
    live_by_command_id = {desc.command_id: desc for desc in descriptors}
    live_by_plugin_original = {
        (desc.plugin_name, desc.original_command): desc for desc in descriptors
    }
    claimed_names: set[str] = set()
    migrated_records: list[CommandConfig] = []
    for config in config_records:
        descriptor = _claim_descriptor(
            config,
            live_by_full_name,
            live_by_command_id,
            live_by_plugin_original,
        )
        if descriptor is None:
            continue
        claimed_names.add(config.handler_full_name)
        claimed_names.add(descriptor.handler_full_name)
        config = await _relink_and_correct_config(db, config, descriptor)
        migrated_records.append(config)
    config_records = migrated_records
    _bind_configs_to_descriptors(
        handler_registry,
        descriptors,
        config_records,
    )
    await _persist_pending_conflicts(db, descriptors)
    live_handlers = {desc.handler_full_name for desc in descriptors}
    stale_configs = [
        config.handler_full_name
        for config in await db.get_command_configs()
        if config.handler_full_name not in live_handlers
        and config.handler_full_name not in claimed_names
    ]
    if stale_configs:
        await db.delete_command_configs(stale_configs)


async def persist_scoped_command_conflicts(
    db: CommandStore,
    handler_registry: HandlerRegistry,
    config_id: str,
    plugin_names: set[str] | None,
) -> None:
    """Persist pending public-path conflicts for one routing profile."""
    descriptors = _collect_descriptors(handler_registry, include_sub_commands=True)
    descriptors = _filter_descriptor_scope(descriptors, plugin_names)
    config_records = await db.get_command_configs()
    _bind_configs_to_descriptors(handler_registry, descriptors, config_records)
    await _persist_pending_conflicts(db, descriptors, config_id=config_id)


async def toggle_command(
    db: CommandStore,
    handler_registry: HandlerRegistry,
    command_id: str,
    enabled: bool,
) -> CommandDescriptor:
    descriptor = _build_descriptor_by_command_id(handler_registry, command_id)
    if not descriptor:
        raise ValueError("指定的处理函数不存在或不是指令。")

    existing_cfg = await _load_command_config(db, descriptor)
    config = await db.upsert_command_config(
        handler_full_name=descriptor.handler_full_name,
        command_id=descriptor.command_id,
        previous_handler_full_name=(
            existing_cfg.handler_full_name if existing_cfg else None
        ),
        plugin_name=descriptor.plugin_name or "",
        module_path=descriptor.module_path,
        original_command=descriptor.original_command or descriptor.handler_name,
        resolved_command=(
            existing_cfg.resolved_command
            if existing_cfg and existing_cfg.resolution_strategy == "manual_rename"
            else descriptor.current_fragment
        ),
        enabled=enabled,
        conflict_key=existing_cfg.conflict_key
        if existing_cfg and existing_cfg.conflict_key
        else descriptor.original_command,
        resolution_strategy=existing_cfg.resolution_strategy if existing_cfg else None,
        note=existing_cfg.note if existing_cfg else None,
        extra_data=existing_cfg.extra_data if existing_cfg else None,
        auto_managed=False,
    )
    _bind_descriptor_with_config(descriptor, config)
    await sync_command_configs(db, handler_registry)
    return descriptor


async def rename_command(
    db: CommandStore,
    handler_registry: HandlerRegistry,
    command_id: str,
    new_fragment: str,
    aliases: list[str] | None = None,
    *,
    config_id: str = "",
    config: dict | None = None,
) -> CommandDescriptor:
    descriptor = _build_descriptor_by_command_id(handler_registry, command_id)
    if not descriptor:
        raise ValueError("指定的处理函数不存在或不是指令。")

    new_fragment = new_fragment.strip()
    if not new_fragment:
        raise ValueError("指令名不能为空。")

    # 校验主指令名
    candidate_full = _compose_command(descriptor.parent_signature, new_fragment)
    plugin_names = _plugin_scope(config)
    if _is_command_in_use(
        handler_registry,
        descriptor.handler_full_name,
        candidate_full,
        plugin_names=plugin_names,
    ):
        raise ValueError(f"指令名 '{candidate_full}' 已被其他指令占用。")

    # 校验别名
    if aliases:
        for alias in aliases:
            alias = alias.strip()
            if not alias:
                continue
            alias_full = _compose_command(descriptor.parent_signature, alias)
            if _is_command_in_use(
                handler_registry,
                descriptor.handler_full_name,
                alias_full,
                plugin_names=plugin_names,
            ):
                raise ValueError(f"别名 '{alias_full}' 已被其他指令占用。")

    alias_paths = [
        _compose_command(descriptor.parent_signature, alias.strip())
        for alias in aliases or []
        if alias.strip()
    ]
    _validate_llm_prefix_occupancy(
        candidate_full,
        alias_paths,
        config=config,
    )

    existing_cfg = await _load_command_config(db, descriptor)
    merged_extra = dict(existing_cfg.extra_data or {}) if existing_cfg else {}
    merged_extra["resolved_aliases"] = aliases or []

    command_config = await db.upsert_command_config(
        handler_full_name=descriptor.handler_full_name,
        command_id=descriptor.command_id,
        previous_handler_full_name=(
            existing_cfg.handler_full_name if existing_cfg else None
        ),
        plugin_name=descriptor.plugin_name or "",
        module_path=descriptor.module_path,
        original_command=descriptor.original_command or descriptor.handler_name,
        resolved_command=new_fragment,
        enabled=True if descriptor.enabled else False,
        conflict_key=descriptor.original_command,
        resolution_strategy="manual_rename",
        note=None,
        extra_data=merged_extra,
        auto_managed=False,
    )
    _bind_descriptor_with_config(descriptor, command_config)
    writer = getattr(db, "upsert_command_conflict", None)
    if writer is not None:
        await writer(
            conflict_key=descriptor.original_command or candidate_full,
            handler_full_name=descriptor.handler_full_name,
            plugin_name=descriptor.plugin_name or "",
            command_id=descriptor.command_id,
            config_id=config_id,
            status="renamed",
            resolution="manual_rename",
            resolved_command=new_fragment,
            auto_generated=False,
        )

    await sync_command_configs(db, handler_registry)
    return descriptor


async def update_command_permission(
    preferences: SharedPreferences,
    handler_registry: HandlerRegistry,
    command_id: str,
    action: str,
) -> CommandDescriptor:
    descriptor = _build_descriptor_by_command_id(handler_registry, command_id)
    if not descriptor:
        raise ValueError("指定的处理函数不存在或不是指令。")

    if not action or "." not in action:
        raise ValueError("Permission must be a stable authorization action.")

    handler = descriptor.handler
    found_plugin = handler_registry.plugins.get_by_module(handler.handler_module_path)
    if not found_plugin:
        raise ValueError("未找到指令所属插件")

    # 1. Update Persistent Config (alter_cmd)
    alter_cmd_cfg = await preferences.global_get("alter_cmd", {})
    plugin_ = dict(alter_cmd_cfg.get(found_plugin.name, {}))
    cfg = dict(take_alter_cmd_entry(plugin_, descriptor.command_id) or {})
    cfg["permission_action"] = action
    plugin_[descriptor.command_id] = cfg
    alter_cmd_cfg[found_plugin.name] = plugin_

    await preferences.global_put("alter_cmd", alter_cmd_cfg)

    # 2. Update Runtime Filter
    found_permission_filter = False
    for filter_ in handler.event_filters:
        if isinstance(filter_, ActionPermissionFilter):
            filter_.action = action
            found_permission_filter = True
            break

    if not found_permission_filter:
        handler.event_filters.insert(0, ActionPermissionFilter(action))

    # Re-build descriptor to reflect changes
    return _build_descriptor(handler_registry, handler) or descriptor


async def list_commands(
    db: CommandStore,
    handler_registry: HandlerRegistry,
    plugin_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    descriptors = _collect_descriptors(handler_registry, include_sub_commands=True)
    descriptors = _filter_descriptor_scope(descriptors, plugin_names)
    config_records = await db.get_command_configs()
    _bind_configs_to_descriptors(handler_registry, descriptors, config_records)

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


async def list_command_conflicts(
    db: CommandStore,
    handler_registry: HandlerRegistry,
    config_id: str = "",
    plugin_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    """列出所有冲突的指令组。"""
    descriptors = _collect_descriptors(handler_registry, include_sub_commands=False)
    descriptors = _filter_descriptor_scope(descriptors, plugin_names)
    config_records = await db.get_command_configs()
    _bind_configs_to_descriptors(handler_registry, descriptors, config_records)

    conflict_groups = _group_conflicts(descriptors)
    stored = await db.list_command_conflicts(config_id=config_id)
    stored_status = {
        (row.conflict_key, row.command_id): row.status
        for row in stored
        if row.command_id
    }
    details = [
        {
            "config_id": config_id,
            "conflict_key": key,
            "public_path": key,
            "handlers": [
                {
                    "command_id": item.command_id,
                    "handler_full_name": item.handler_full_name,
                    "plugin": item.plugin_name,
                    "current_name": item.effective_command,
                    "status": stored_status.get((key, item.command_id), "pending"),
                }
                for item in group
            ],
        }
        for key, group in conflict_groups.items()
    ]
    return details


async def takeover_command(
    db: CommandStore,
    handler_registry: HandlerRegistry,
    command_id: str,
    *,
    config_id: str = "",
) -> CommandDescriptor:
    """Keep one command_id on its public path and suppress the others.

    The losing handlers stay enabled; only the shared public path is removed
    from the configuration profile's catalog.
    """
    descriptor = _build_descriptor_by_command_id(handler_registry, command_id)
    if not descriptor:
        raise ValueError("指定的处理函数不存在或不是指令。")
    public_path = (descriptor.effective_command or "").strip()
    if not public_path:
        raise ValueError("指令没有可接管的对外路径。")

    descriptors = _collect_descriptors(handler_registry, include_sub_commands=True)
    config_records = await db.get_command_configs()
    _bind_configs_to_descriptors(handler_registry, descriptors, config_records)
    claimants = [
        item
        for item in descriptors
        if item.enabled
        and item.plugin_activated
        and (item.effective_command or "").strip() == public_path
    ]
    if descriptor.command_id not in {item.command_id for item in claimants}:
        claimants.append(descriptor)
    if len(claimants) < 2 and all(
        item.command_id == descriptor.command_id for item in claimants
    ):
        raise ValueError("该对外路径没有需要接管的冲突。")

    for item in claimants:
        status = "takeover" if item.command_id == descriptor.command_id else "pending"
        await db.upsert_command_conflict(
            conflict_key=public_path,
            handler_full_name=item.handler_full_name,
            plugin_name=item.plugin_name or "",
            config_id=config_id,
            command_id=item.command_id,
            status=status,
            resolution="takeover" if status == "takeover" else None,
            auto_generated=False,
        )
    return descriptor


async def load_path_winners(
    db: CommandStore,
    config_id: str = "",
) -> dict[tuple[str, ...], str]:
    """Return takeover winners for one configuration profile."""
    records = await db.list_command_conflicts(status="takeover", config_id=config_id)
    winners: dict[tuple[str, ...], str] = {}
    for record in records:
        path = tuple((record.conflict_key or "").split())
        if path and record.handler_full_name:
            winners[path] = record.handler_full_name
    return winners


async def apply_path_winners(
    db: CommandStore,
    plugin_catalog: Any,
    config_ids: Iterable[str] | None = None,
) -> None:
    """Load persisted takeover winners onto the plugin catalog."""
    lister = getattr(db, "list_command_conflicts", None)
    if lister is None:
        return
    known = set(config_ids or ())
    stored = await lister(status="takeover")
    by_config: dict[str, dict[tuple[str, ...], str]] = defaultdict(dict)
    for record in stored:
        path = tuple((record.conflict_key or "").split())
        if path and record.handler_full_name:
            by_config[record.config_id][path] = record.handler_full_name
            known.add(record.config_id)
    catalogs = getattr(plugin_catalog, "_command_catalogs", {})
    known.update(catalogs)
    if not known:
        known.add("")
    setter = getattr(plugin_catalog, "set_path_winners", None)
    if setter is None:
        return
    for config_id in known:
        setter(config_id, by_config.get(config_id, {}))


# Internal helpers ----------------------------------------------------------


def _collect_descriptors(
    handler_registry: HandlerRegistry,
    include_sub_commands: bool,
) -> list[CommandDescriptor]:
    """收集指令，按需包含子指令。"""
    descriptors: list[CommandDescriptor] = []
    for handler in handler_registry:
        try:
            desc = _build_descriptor(handler_registry, handler)
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


def _filter_descriptor_scope(
    descriptors: list[CommandDescriptor],
    plugin_names: set[str] | None,
) -> list[CommandDescriptor]:
    """Limit descriptors to the plugins enabled by one routing profile."""
    if plugin_names is None:
        return descriptors
    return [
        descriptor
        for descriptor in descriptors
        if descriptor.plugin_name in plugin_names or descriptor.reserved
    ]


def _build_descriptor(
    handler_registry: HandlerRegistry,
    handler: StarHandlerMetadata,
) -> CommandDescriptor | None:
    filter_ref = _locate_primary_filter(handler)
    if filter_ref is None:
        return None

    plugin_meta = handler_registry.plugins.get_by_module(handler.handler_module_path)
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
        parent_names = (
            filter_ref.parent_group.get_complete_command_names()
            if filter_ref.parent_group is not None
            else filter_ref.parent_command_names
        )
        parent_signature = (parent_names or [""])[0].strip()
        original_parent_signature = (filter_ref.parent_command_names or [""])[0].strip()
        # 如果是子指令，尝试找到父指令组的 handler_full_name
        if is_sub_command and parent_signature:
            parent_group_handler = _find_parent_group_handler(
                handler_registry,
                handler.handler_module_path,
                parent_signature,
            )
    else:
        raw_fragment = getattr(
            filter_ref, "_original_group_name", filter_ref.group_name
        )
        current_fragment = filter_ref.group_name
        parent_signature = _resolve_group_parent_signature(filter_ref)
        original_parent_signature = _resolve_group_parent_signature(
            filter_ref,
            original=True,
        )

    original_command = _compose_command(original_parent_signature, raw_fragment)
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
        command_id=compute_command_id(plugin_name, original_command),
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
        signature=_build_command_signature(filter_ref, effective_command),
        display_signature=_build_command_signature(
            filter_ref,
            effective_command,
            include_aliases=True,
        ),
        aliases=sorted(getattr(filter_ref, "alias", set())),
        action=_determine_action(handler),
        enabled=handler.enabled,
        plugin_activated=plugin_meta.activated if plugin_meta else True,
        is_group=isinstance(filter_ref, CommandGroupFilter),
        is_sub_command=is_sub_command,
        reserved=plugin_meta.reserved if plugin_meta else False,
    )
    return descriptor


def _build_descriptor_by_command_id(
    handler_registry: HandlerRegistry,
    command_id: str,
) -> CommandDescriptor | None:
    for handler in handler_registry:
        descriptor = _build_descriptor(handler_registry, handler)
        if descriptor is not None and descriptor.command_id == command_id:
            return descriptor
    return None


def command_id_for_handler(plugin_name: str, handler: StarHandlerMetadata) -> str:
    """Return the stable command ID for one materialized handler."""
    original_command = _original_command_for_handler(handler)
    if not original_command:
        original_command = handler.handler_name
    return compute_command_id(plugin_name, original_command)


def _original_command_for_handler(handler: StarHandlerMetadata) -> str:
    filter_ref = _locate_primary_filter(handler)
    if filter_ref is None:
        return handler.handler_name
    if isinstance(filter_ref, CommandFilter):
        raw_fragment = getattr(
            filter_ref, "_original_command_name", filter_ref.command_name
        )
        original_parent_signature = (filter_ref.parent_command_names or [""])[0].strip()
    else:
        raw_fragment = getattr(
            filter_ref, "_original_group_name", filter_ref.group_name
        )
        original_parent_signature = _resolve_group_parent_signature(
            filter_ref,
            original=True,
        )
    return _compose_command(original_parent_signature, raw_fragment)


def _claim_descriptor(
    config: CommandConfig,
    live_by_full_name: dict[str, CommandDescriptor],
    live_by_command_id: dict[str, CommandDescriptor],
    live_by_plugin_original: dict[tuple[str, str | None], CommandDescriptor],
) -> CommandDescriptor | None:
    if config.handler_full_name in live_by_full_name:
        return live_by_full_name[config.handler_full_name]
    if config.command_id and config.command_id in live_by_command_id:
        return live_by_command_id[config.command_id]
    key = (config.plugin_name, config.original_command)
    return live_by_plugin_original.get(key)


async def _load_command_config(
    db: CommandStore,
    descriptor: CommandDescriptor,
) -> CommandConfig | None:
    existing = await db.get_command_config(descriptor.handler_full_name)
    if existing is not None:
        return existing
    return await db.get_command_config_by_command_id(descriptor.command_id)


async def _relink_and_correct_config(
    db: CommandStore,
    config: CommandConfig,
    descriptor: CommandDescriptor,
) -> CommandConfig:
    needs_relink = config.handler_full_name != descriptor.handler_full_name
    needs_command_id = config.command_id != descriptor.command_id
    if not (needs_relink or needs_command_id):
        return config

    if needs_relink:
        existing_new = await db.get_command_config(descriptor.handler_full_name)
        if (
            existing_new is not None
            and existing_new.handler_full_name != config.handler_full_name
        ):
            await db.delete_command_config(config.handler_full_name)
            config = existing_new
            needs_relink = False
            needs_command_id = config.command_id != descriptor.command_id
            if not (needs_relink or needs_command_id):
                return config

    return await db.upsert_command_config(
        handler_full_name=descriptor.handler_full_name,
        command_id=descriptor.command_id,
        previous_handler_full_name=(config.handler_full_name if needs_relink else None),
        plugin_name=descriptor.plugin_name or config.plugin_name,
        module_path=descriptor.module_path,
        original_command=config.original_command,
        resolved_command=config.resolved_command,
        enabled=config.enabled,
        conflict_key=config.conflict_key,
        resolution_strategy=config.resolution_strategy,
        note=config.note,
        extra_data=config.extra_data,
        auto_managed=config.auto_managed,
    )


def _locate_primary_filter(
    handler: StarHandlerMetadata,
) -> CommandFilter | CommandGroupFilter | None:
    for filter_ref in handler.event_filters:
        if isinstance(filter_ref, CommandFilter | CommandGroupFilter):
            return filter_ref
    return None


def _determine_action(handler: StarHandlerMetadata) -> str | None:
    for filter_ref in handler.event_filters:
        if isinstance(filter_ref, ActionPermissionFilter):
            return filter_ref.action
    return None


def _resolve_group_parent_signature(
    group_filter: CommandGroupFilter,
    *,
    original: bool = False,
) -> str:
    signatures: list[str] = []
    parent = group_filter.parent_group
    while parent:
        signatures.append(
            getattr(parent, "_original_group_name", parent.group_name)
            if original
            else parent.group_name
        )
        parent = parent.parent_group
    return " ".join(reversed(signatures)).strip()


def _find_parent_group_handler(
    handler_registry: HandlerRegistry,
    module_path: str,
    parent_signature: str,
) -> str:
    """根据模块路径和父级签名，找到对应的指令组 handler_full_name。"""
    parent_sig_normalized = parent_signature.strip()
    for handler in handler_registry:
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


def _build_command_signature(
    filter_ref: CommandFilter | CommandGroupFilter | None,
    command_name: str | None,
    include_aliases: bool = False,
) -> str:
    if filter_ref is None:
        return command_name or ""

    return filter_ref.format_invocation(
        command_name=command_name,
        include_aliases=include_aliases,
    )


def _bind_descriptor_with_config(
    descriptor: CommandDescriptor,
    config: CommandConfig,
) -> None:
    _apply_config_to_runtime(descriptor, config)
    _apply_config_to_descriptor(descriptor, config)


def _use_declared_builtin_names(
    descriptor: CommandDescriptor,
    config: CommandConfig,
) -> bool:
    return (
        descriptor.module_path == BUILTIN_COMMANDS_MODULE
        and config.resolution_strategy != "manual_rename"
    )


def _apply_config_to_descriptor(
    descriptor: CommandDescriptor,
    config: CommandConfig,
) -> None:
    descriptor.config = config
    descriptor.enabled = config.enabled

    if not _use_declared_builtin_names(descriptor, config):
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
    descriptor.signature = _build_command_signature(
        descriptor.filter_ref,
        descriptor.effective_command,
    )
    descriptor.display_signature = _build_command_signature(
        descriptor.filter_ref,
        descriptor.effective_command,
        include_aliases=True,
    )


def _apply_config_to_runtime(
    descriptor: CommandDescriptor,
    config: CommandConfig,
) -> None:
    descriptor.handler.enabled = config.enabled
    if descriptor.filter_ref:
        if not _use_declared_builtin_names(descriptor, config):
            new_fragment = config.resolved_command or descriptor.current_fragment
            if new_fragment:
                _set_filter_fragment(descriptor.filter_ref, new_fragment)
            extra = config.extra_data or {}
            resolved_aliases = extra.get("resolved_aliases")
            if isinstance(resolved_aliases, list):
                _set_filter_aliases(
                    descriptor.filter_ref,
                    [str(x) for x in resolved_aliases if str(x).strip()],
                )


def _config_for_descriptor(
    descriptor: CommandDescriptor,
    config_map: dict[str, CommandConfig],
    config_by_id: dict[str, CommandConfig],
) -> CommandConfig | None:
    return config_map.get(descriptor.handler_full_name) or config_by_id.get(
        descriptor.command_id,
    )


def _bind_configs_to_descriptors(
    handler_registry: HandlerRegistry,
    descriptors: list[CommandDescriptor],
    config_records: list[CommandConfig],
) -> dict[str, CommandConfig]:
    config_map = {cfg.handler_full_name: cfg for cfg in config_records}
    config_by_id = {cfg.command_id: cfg for cfg in config_records if cfg.command_id}
    for desc in descriptors:
        if cfg := _config_for_descriptor(desc, config_map, config_by_id):
            _apply_config_to_runtime(desc, cfg)

    for index, desc in enumerate(descriptors):
        rebuilt = _build_descriptor(handler_registry, desc.handler)
        if rebuilt is None:
            continue
        if cfg := _config_for_descriptor(rebuilt, config_map, config_by_id):
            _apply_config_to_descriptor(rebuilt, cfg)
        descriptors[index] = rebuilt
    return config_map


async def _persist_pending_conflicts(
    db: CommandStore,
    descriptors: list[CommandDescriptor],
    *,
    config_id: str = "",
) -> None:
    """Write pending occupancy rows for enabled public-path collisions."""
    lister = getattr(db, "list_command_conflicts", None)
    writer = getattr(db, "upsert_command_conflict", None)
    if lister is None or writer is None:
        return
    existing = await lister(config_id=config_id)
    protected = {
        (row.conflict_key, row.command_id)
        for row in existing
        if row.status in {"takeover", "renamed"}
    }
    for public_path, group in _group_conflicts(descriptors).items():
        for item in group:
            if (public_path, item.command_id) in protected:
                continue
            await writer(
                conflict_key=public_path,
                handler_full_name=item.handler_full_name,
                plugin_name=item.plugin_name or "",
                config_id=config_id,
                command_id=item.command_id,
                status="pending",
                auto_generated=True,
            )


def _group_conflicts(
    descriptors: list[CommandDescriptor],
) -> dict[str, list[CommandDescriptor]]:
    conflicts: dict[str, list[CommandDescriptor]] = defaultdict(list)
    for desc in descriptors:
        if not desc.enabled or not desc.plugin_activated:
            continue
        for public_path in _descriptor_public_paths(desc):
            if desc not in conflicts[public_path]:
                conflicts[public_path].append(desc)
    return {k: v for k, v in conflicts.items() if len(v) > 1}


def _descriptor_public_paths(desc: CommandDescriptor) -> tuple[str, ...]:
    """Return the effective command path and all effective alias paths."""
    paths: list[str] = []
    if desc.effective_command:
        paths.append(desc.effective_command)
    paths.extend(
        _compose_command(desc.parent_signature, alias)
        for alias in desc.aliases
        if alias.strip()
    )
    return tuple(dict.fromkeys(paths))


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
    handler_registry: HandlerRegistry,
    target_handler_full_name: str,
    candidate_full_command: str,
    *,
    plugin_names: set[str] | None = None,
) -> bool:
    candidate = candidate_full_command.strip()
    for handler in handler_registry:
        if handler.handler_full_name == target_handler_full_name:
            continue
        if not getattr(handler, "enabled", True):
            continue
        plugin = handler_registry.plugins.get_by_module(handler.handler_module_path)
        if plugin is not None and not plugin.activated:
            continue
        if plugin_names is not None and (
            plugin is None or plugin.name not in plugin_names
        ):
            continue
        filter_ref = _locate_primary_filter(handler)
        if not filter_ref:
            continue
        names = {name.strip() for name in filter_ref.get_complete_command_names()}
        if candidate in names:
            return True
    return False


def _plugin_scope(config: dict | None) -> set[str] | None:
    """Return the enabled plugin scope represented by a routing profile."""
    if not config:
        return None
    raw = config.get("plugin_set", ["*"])
    if raw == ["*"] or raw is None:
        return None
    return {str(name) for name in raw if str(name).strip()}


def _validate_llm_prefix_occupancy(
    candidate_full: str,
    aliases: list[str],
    *,
    config: dict | None,
) -> None:
    """Reject a rename that moves a command onto an LLM trigger root."""
    if not config:
        return
    from astrbot.core.pipeline.turn_router import (
        command_prefixes_from_config,
        public_root_token,
    )

    llm_access = config.get("llm_access") or {}
    llm_prefixes = tuple(
        str(value) for value in llm_access.get("prefixes", []) if str(value).strip()
    )
    command_prefixes = command_prefixes_from_config(config)
    for value in (candidate_full, *aliases):
        root = public_root_token(value, command_prefixes)
        if not root:
            continue
        for prefix in llm_prefixes:
            if public_root_token(prefix, command_prefixes) == root:
                raise ValueError(
                    f"指令路径 '{value}' 与 LLM 触发前缀 '{prefix}' 冲突。"
                )


def _descriptor_to_dict(desc: CommandDescriptor) -> dict[str, Any]:
    result = {
        "command_id": desc.command_id,
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
        "signature": desc.signature,
        "display_signature": desc.display_signature,
        "aliases": desc.aliases,
        "action": desc.action,
        "enabled": desc.enabled,
        "plugin_activated": desc.plugin_activated,
        "is_group": desc.is_group,
        "has_conflict": desc.has_conflict,
        "reserved": desc.reserved,
    }
    # 如果是指令组，包含子指令列表
    if desc.is_group and desc.sub_commands:
        result["sub_commands"] = [_descriptor_to_dict(sub) for sub in desc.sub_commands]
    else:
        result["sub_commands"] = []
    return result
