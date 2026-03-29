from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from astrbot_sdk.protocol.descriptors import CommandTrigger, HandlerDescriptor

from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    star_handlers_registry,
)


@dataclass(slots=True)
class CommandRegistration:
    runtime_kind: Literal["legacy", "sdk"]
    plugin_name: str
    plugin_display_name: str | None
    handler_full_name: str
    command_name: str


@dataclass(slots=True)
class CrossSystemCommandConflict:
    command_name: str
    legacy: CommandRegistration
    sdk: CommandRegistration

    def to_dashboard_payload(self) -> dict[str, Any]:
        return {
            "conflict_key": self.command_name,
            "handlers": [
                {
                    "handler_full_name": self.legacy.handler_full_name,
                    "plugin": self.legacy.plugin_name,
                    "plugin_display_name": self.legacy.plugin_display_name,
                    "current_name": self.legacy.command_name,
                    "runtime_kind": self.legacy.runtime_kind,
                },
                {
                    "handler_full_name": self.sdk.handler_full_name,
                    "plugin": self.sdk.plugin_name,
                    "plugin_display_name": self.sdk.plugin_display_name,
                    "current_name": self.sdk.command_name,
                    "runtime_kind": self.sdk.runtime_kind,
                },
            ],
        }


def normalize_command_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip())


def command_matches_text(command_name: str, text: str) -> bool:
    normalized_command = normalize_command_name(command_name)
    normalized_text = normalize_command_name(text)
    if not normalized_command or not normalized_text:
        return False
    return normalized_text == normalized_command or normalized_text.startswith(
        f"{normalized_command} "
    )


def commands_overlap(left: str, right: str) -> bool:
    normalized_left = normalize_command_name(left)
    normalized_right = normalize_command_name(right)
    if not normalized_left or not normalized_right:
        return False
    return (
        normalized_left == normalized_right
        or normalized_left.startswith(f"{normalized_right} ")
        or normalized_right.startswith(f"{normalized_left} ")
    )


def _command_prefixes(command_name: str) -> tuple[str, ...]:
    normalized = normalize_command_name(command_name)
    if not normalized:
        return ()
    prefixes: list[str] = []
    parts: list[str] = []
    for token in normalized.split(" "):
        parts.append(token)
        prefixes.append(" ".join(parts))
    return tuple(prefixes)


def collect_legacy_command_registrations(
    handlers: Iterable[StarHandlerMetadata] | None = None,
) -> list[CommandRegistration]:
    source_handlers = (
        handlers
        if handlers is not None
        else star_handlers_registry.get_handlers_by_event_type(
            EventType.AdapterMessageEvent,
            only_activated=True,
        )
    )
    registrations: list[CommandRegistration] = []
    for handler in source_handlers:
        filter_ref = _locate_legacy_command_filter(handler)
        if filter_ref is None:
            continue
        plugin_meta = star_map.get(handler.handler_module_path)
        plugin_name = (
            plugin_meta.name if plugin_meta is not None else handler.handler_module_path
        )
        plugin_display_name = (
            plugin_meta.display_name if plugin_meta is not None else None
        )
        seen_names: set[str] = set()
        for command_name in filter_ref.get_complete_command_names():
            normalized = normalize_command_name(command_name)
            if not normalized or normalized in seen_names:
                continue
            seen_names.add(normalized)
            registrations.append(
                CommandRegistration(
                    runtime_kind="legacy",
                    plugin_name=plugin_name,
                    plugin_display_name=plugin_display_name,
                    handler_full_name=handler.handler_full_name,
                    command_name=normalized,
                )
            )
    return registrations


def match_legacy_command_registrations(
    handlers: Iterable[StarHandlerMetadata],
    text: str,
) -> list[CommandRegistration]:
    return [
        registration
        for registration in collect_legacy_command_registrations(handlers)
        if command_matches_text(registration.command_name, text)
    ]


def collect_sdk_command_registrations(
    *,
    plugin_name: str,
    plugin_display_name: str | None,
    handler_full_name: str,
    descriptor: HandlerDescriptor,
) -> list[CommandRegistration]:
    trigger = descriptor.trigger
    if not isinstance(trigger, CommandTrigger):
        return []
    registrations: list[CommandRegistration] = []
    seen_names: set[str] = set()
    for command_name in [trigger.command, *trigger.aliases]:
        normalized = normalize_command_name(command_name)
        if not normalized or normalized in seen_names:
            continue
        seen_names.add(normalized)
        registrations.append(
            CommandRegistration(
                runtime_kind="sdk",
                plugin_name=plugin_name,
                plugin_display_name=plugin_display_name,
                handler_full_name=handler_full_name,
                command_name=normalized,
            )
        )
    return registrations


def match_sdk_command_registrations(
    registrations: Iterable[CommandRegistration],
    text: str,
) -> list[CommandRegistration]:
    return [
        registration
        for registration in registrations
        if command_matches_text(registration.command_name, text)
    ]


def build_cross_system_conflicts(
    legacy_registrations: Iterable[CommandRegistration],
    sdk_registrations: Iterable[CommandRegistration],
) -> list[CrossSystemCommandConflict]:
    conflicts: list[CrossSystemCommandConflict] = []
    seen_pairs: set[tuple[str, str, str]] = set()
    legacy_by_exact: dict[str, list[CommandRegistration]] = {}
    legacy_by_prefix: dict[str, list[CommandRegistration]] = {}
    for legacy_registration in legacy_registrations:
        normalized_command = normalize_command_name(legacy_registration.command_name)
        if not normalized_command:
            continue
        legacy_by_exact.setdefault(normalized_command, []).append(legacy_registration)
        for prefix in _command_prefixes(normalized_command):
            legacy_by_prefix.setdefault(prefix, []).append(legacy_registration)

    for sdk_registration in sdk_registrations:
        normalized_sdk_command = normalize_command_name(sdk_registration.command_name)
        if not normalized_sdk_command:
            continue
        candidate_legacy: list[CommandRegistration] = []
        seen_legacy_commands: set[tuple[str, str]] = set()
        for prefix in _command_prefixes(normalized_sdk_command):
            for legacy_registration in legacy_by_exact.get(prefix, []):
                legacy_key = (
                    legacy_registration.handler_full_name,
                    legacy_registration.command_name,
                )
                if legacy_key in seen_legacy_commands:
                    continue
                seen_legacy_commands.add(legacy_key)
                candidate_legacy.append(legacy_registration)
        for legacy_registration in legacy_by_prefix.get(normalized_sdk_command, []):
            legacy_key = (
                legacy_registration.handler_full_name,
                legacy_registration.command_name,
            )
            if legacy_key in seen_legacy_commands:
                continue
            seen_legacy_commands.add(legacy_key)
            candidate_legacy.append(legacy_registration)

        for legacy_registration in candidate_legacy:
            pair_key = (
                _build_conflict_key(
                    legacy_registration.command_name,
                    sdk_registration.command_name,
                ),
                legacy_registration.handler_full_name,
                sdk_registration.handler_full_name,
            )
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            conflicts.append(
                CrossSystemCommandConflict(
                    command_name=_build_conflict_key(
                        legacy_registration.command_name,
                        sdk_registration.command_name,
                    ),
                    legacy=legacy_registration,
                    sdk=sdk_registration,
                )
            )
    return conflicts


def _locate_legacy_command_filter(
    handler: StarHandlerMetadata,
) -> CommandFilter | CommandGroupFilter | None:
    for filter_ref in handler.event_filters:
        if isinstance(filter_ref, CommandFilter | CommandGroupFilter):
            return filter_ref
    return None


def _build_conflict_key(legacy_command: str, sdk_command: str) -> str:
    if legacy_command == sdk_command:
        return legacy_command
    return f"{legacy_command} <> {sdk_command}"
