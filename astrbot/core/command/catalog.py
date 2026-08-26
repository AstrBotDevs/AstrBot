from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .models import (
    CommandResolution,
    CommandResolutionKind,
    SourceSpan,
)
from .schema import CommandSchema


@dataclass(frozen=True, slots=True)
class CommandCatalogEntry:
    handler_id: str
    handler: Any
    schema: CommandSchema
    path: tuple[str, ...]
    filter_ref: Any = None


@dataclass(frozen=True, slots=True)
class CommandCatalogRegistration:
    handler_id: str
    handler: Any
    schema: CommandSchema
    paths: tuple[tuple[str, ...], ...]
    filter_ref: Any = None


@dataclass(frozen=True, slots=True)
class CommandGroupRegistration:
    paths: tuple[tuple[str, ...], ...]
    handler_id: str = ""
    handler: Any = None


class CommandCatalog:
    """An immutable command lookup snapshot."""

    __slots__ = ("_commands", "_groups", "_group_owners", "_max_depth")

    def __init__(
        self,
        commands: Iterable[CommandCatalogRegistration] = (),
        groups: Iterable[CommandGroupRegistration] = (),
    ) -> None:
        command_map: dict[tuple[str, ...], list[CommandCatalogEntry]] = {}
        group_paths: set[tuple[str, ...]] = set()
        group_owners: dict[tuple[str, ...], str] = {}
        max_depth = 1
        for registration in commands:
            seen_paths: set[tuple[str, ...]] = set()
            for path in registration.paths:
                if not path or path in seen_paths:
                    continue
                seen_paths.add(path)
                max_depth = max(max_depth, len(path))
                command_map.setdefault(path, []).append(
                    CommandCatalogEntry(
                        registration.handler_id,
                        registration.handler,
                        registration.schema,
                        path,
                        registration.filter_ref,
                    )
                )
        for registration in groups:
            for path in dict.fromkeys(registration.paths):
                if path:
                    group_paths.add(path)
                    group_owners.setdefault(path, registration.handler_id)
                    max_depth = max(max_depth, len(path))
        self._commands: Mapping[tuple[str, ...], tuple[CommandCatalogEntry, ...]] = (
            MappingProxyType(
                {path: tuple(entries) for path, entries in command_map.items()}
            )
        )
        self._groups = frozenset(group_paths)
        self._group_owners = MappingProxyType(group_owners)
        self._max_depth = max_depth

    @property
    def commands(self) -> Mapping[tuple[str, ...], tuple[CommandCatalogEntry, ...]]:
        return self._commands

    @property
    def groups(self) -> frozenset[tuple[str, ...]]:
        return self._groups

    @property
    def group_owners(self) -> Mapping[tuple[str, ...], str]:
        """Return the owner handler id for each dispatchable command group."""
        return self._group_owners

    def resolve(self, source: str) -> CommandResolution:
        tokens = self._scan_header_tokens(source, self._max_depth + 1)
        if not tokens:
            return CommandResolution(CommandResolutionKind.UNKNOWN_ROOT, source)
        values = tuple(token[0] for token in tokens)

        matched_path: tuple[str, ...] | None = None
        matched_entries: tuple[CommandCatalogEntry, ...] = ()
        for depth in range(min(len(values), self._max_depth), 0, -1):
            path = values[:depth]
            if path in self._commands:
                matched_path = path
                matched_entries = self._commands[path]
                break
        if matched_path is not None:
            command_end = tokens[len(matched_path) - 1][2]
            argument_start = command_end
            while argument_start < len(source) and source[argument_start] in " \t":
                argument_start += 1
            return CommandResolution(
                CommandResolutionKind.MATCHED,
                source,
                SourceSpan(tokens[0][1], command_end),
                SourceSpan(argument_start, len(source)),
                matched_path,
                matched_entries,
            )

        group_path: tuple[str, ...] | None = None
        for depth in range(min(len(values), self._max_depth), 0, -1):
            path = values[:depth]
            if path in self._groups:
                group_path = path
                break
        if group_path is None:
            return CommandResolution(CommandResolutionKind.UNKNOWN_ROOT, source)

        children = sorted(
            {
                " ".join(path[len(group_path) :])
                for path in self._commands
                if len(path) > len(group_path) and path[: len(group_path)] == group_path
            }
        )
        if len(values) == len(group_path):
            span = SourceSpan(tokens[0][1], tokens[-1][2])
            return CommandResolution(
                CommandResolutionKind.INCOMPLETE_GROUP,
                source,
                span,
                command_path=group_path,
                group_path=group_path,
                available_subcommands=tuple(children),
            )
        unknown = tokens[len(group_path)]
        return CommandResolution(
            CommandResolutionKind.UNKNOWN_SUBCOMMAND,
            source,
            SourceSpan(unknown[1], unknown[2]),
            command_path=values[: len(group_path) + 1],
            group_path=group_path,
            available_subcommands=tuple(children),
        )

    @staticmethod
    def _scan_header_tokens(source: str, limit: int) -> list[tuple[str, int, int]]:
        tokens: list[tuple[str, int, int]] = []
        index = 0
        while index < len(source) and len(tokens) < limit:
            while index < len(source) and source[index] in " \t":
                index += 1
            if index >= len(source):
                break
            start = index
            while index < len(source) and source[index] not in " \t\r\n":
                index += 1
            tokens.append((source[start:index], start, index))
            if index < len(source) and source[index] in "\r\n":
                break
        return tokens


class CommandCatalogStore:
    """Own the current immutable snapshot and replace it atomically."""

    __slots__ = ("_snapshot",)

    def __init__(self, snapshot: CommandCatalog | None = None) -> None:
        self._snapshot = snapshot or CommandCatalog()

    @property
    def snapshot(self) -> CommandCatalog:
        return self._snapshot

    def replace(self, snapshot: CommandCatalog) -> None:
        self._snapshot = snapshot


def build_command_catalog(
    handlers: Iterable[Any],
    *,
    path_winners: Mapping[tuple[str, ...], str] | None = None,
) -> CommandCatalog:
    """Build an immutable catalog snapshot from registered command handlers.

    Args:
        handlers: Enabled command handlers for one configuration profile.
        path_winners: Optional takeover map of public path to remaining
            handler id. Conflicting paths without a unique owner are omitted.
    """
    from astrbot.core.star.filter.command import CommandFilter
    from astrbot.core.star.filter.command_group import CommandGroupFilter

    handler_list = tuple(handlers)
    registrations: list[CommandCatalogRegistration] = []
    groups: list[CommandGroupRegistration] = []
    command_paths: dict[int, tuple[tuple[str, ...], ...]] = {}
    group_paths: dict[int, tuple[tuple[str, ...], ...]] = {}
    active_group_ids = {
        id(filter_ref)
        for handler in handler_list
        for filter_ref in handler.event_filters
        if isinstance(filter_ref, CommandGroupFilter)
    }
    root_groups = [
        filter_ref
        for handler in handler_list
        for filter_ref in handler.event_filters
        if isinstance(filter_ref, CommandGroupFilter)
        and filter_ref.parent_group is None
    ]
    stack: list[tuple[CommandGroupFilter, tuple[tuple[str, ...], ...]]] = [
        (
            group,
            tuple((name,) for name in [group.group_name, *sorted(group.alias)]),
        )
        for group in root_groups
    ]
    while stack:
        group, paths = stack.pop()
        group_paths[id(group)] = paths
        for child in group.sub_command_filters:
            names = (
                [child.command_name, *sorted(child.alias)]
                if isinstance(child, CommandFilter)
                else [child.group_name, *sorted(child.alias)]
            )
            child_paths = tuple(
                (*parent_path, name) for parent_path in paths for name in names
            )
            if isinstance(child, CommandFilter):
                command_paths[id(child)] = child_paths
            elif id(child) in active_group_ids:
                stack.append((child, child_paths))

    for handler in handler_list:
        for filter_ref in handler.event_filters:
            if isinstance(filter_ref, CommandFilter):
                if (
                    filter_ref.parent_group is not None
                    and id(filter_ref) not in command_paths
                ):
                    continue
                paths = command_paths.get(
                    id(filter_ref),
                    tuple(
                        tuple(name.split(" "))
                        for name in filter_ref.get_complete_command_names()
                    ),
                )
                registrations.append(
                    CommandCatalogRegistration(
                        handler.handler_full_name,
                        handler,
                        filter_ref.schema,
                        paths,
                        filter_ref,
                    )
                )
            elif isinstance(filter_ref, CommandGroupFilter):
                paths = group_paths.get(
                    id(filter_ref),
                    tuple(
                        tuple(name.split(" "))
                        for name in filter_ref.get_complete_command_names()
                    ),
                )
                groups.append(
                    CommandGroupRegistration(
                        paths,
                        handler.handler_full_name,
                        handler,
                    )
                )
    from .occupancy import apply_exclusive_occupancy

    registrations, groups, _conflicts = apply_exclusive_occupancy(
        registrations,
        groups,
        path_winners=path_winners,
    )
    return CommandCatalog(registrations, groups)
