"""Path-level occupancy for exclusive public command names."""

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass

from .catalog import CommandCatalogRegistration, CommandGroupRegistration


@dataclass(frozen=True, slots=True)
class OccupancyConflict:
    """One public path claimed by more than one enabled owner."""

    path: tuple[str, ...]
    owner_ids: tuple[str, ...]


LLM_PREFIX_OCCUPIED = "llm_prefix_occupied"


def collect_command_roots(catalog) -> dict[str, str]:
    """Map command-root tokens to one occupying handler id.

    Args:
        catalog: Immutable command catalog snapshot.

    Returns:
        First-path-token to its occupying handler id. A synthetic group
        registration without an owner reports an empty id.
    """
    roots: dict[str, str] = {}
    for path, entries in catalog.commands.items():
        if path:
            roots.setdefault(path[0], entries[0].handler_id)
    for path in catalog.groups:
        if path:
            roots.setdefault(path[0], catalog.group_owners.get(path, ""))
    return roots


def llm_prefix_conflict(
    prefixes: list[str] | tuple[str, ...],
    command_prefixes: list[str] | tuple[str, ...],
    command_roots: dict[str, str],
    *,
    config_id: str,
) -> dict | None:
    """Return a conflict payload when an LLM prefix occupies a command root.

    Args:
        prefixes: Proposed ``llm_access.prefixes`` values.
        command_prefixes: Command framing prefixes.
        command_roots: Occupied first tokens from the scoped catalog.
        config_id: Configuration profile id included in the error payload.

    Returns:
        Dashboard ``data`` payload, or None when the prefixes are free.
    """
    from astrbot.core.pipeline.turn_router import public_root_token

    for prefix in prefixes:
        token = public_root_token(str(prefix), command_prefixes)
        if not token:
            continue
        owner = command_roots.get(token)
        if owner is None:
            continue
        return {
            "error_code": LLM_PREFIX_OCCUPIED,
            "config_id": config_id,
            "public_path": token,
            "command_id": owner,
            "owner": owner,
        }
    return None


def apply_exclusive_occupancy(
    commands: list[CommandCatalogRegistration],
    groups: list[CommandGroupRegistration],
    *,
    path_winners: Mapping[tuple[str, ...], str] | None = None,
) -> tuple[
    list[CommandCatalogRegistration],
    list[CommandGroupRegistration],
    tuple[OccupancyConflict, ...],
]:
    """Keep at most one owner per public path.

    Args:
        commands: Command registrations collected from enabled handlers.
        groups: Group registrations collected from enabled handlers.
        path_winners: Optional takeover map of public path to remaining
            handler id. Paths without a unique owner are excluded.

    Returns:
        Filtered command registrations, group registrations, and the
        unresolved conflict groups.
    """

    winners = dict(path_winners or {})
    owners: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for registration in commands:
        for path in registration.paths:
            if path:
                owners[path].add(registration.handler_id)
    for registration in groups:
        for path in registration.paths:
            if path:
                owners[path].add(registration.handler_id)

    unique_owners: dict[tuple[str, ...], set[str]] = {}
    conflicted: set[tuple[str, ...]] = set()
    takeover_roots: dict[tuple[str, ...], str] = {}
    for path, ids in owners.items():
        winner = winners.get(path)
        if winner is not None and winner in ids:
            unique_owners[path] = {winner}
            if len(ids) > 1:
                takeover_roots[path] = winner
            continue
        unique_owners[path] = set(ids)
        if len(ids) > 1:
            conflicted.add(path)

    suppressed: set[tuple[str, ...]] = set(conflicted)
    suppressed_handlers: set[str] = set()
    handler_modules = {
        registration.handler_id: getattr(
            registration.handler,
            "handler_module_path",
            None,
        )
        for registration in commands
    }
    winner_modules = {
        path: handler_modules.get(winner)
        or next(
            (
                getattr(registration.handler, "handler_module_path", None)
                for registration in groups
                if registration.handler_id == winner
            ),
            None,
        )
        for path, winner in takeover_roots.items()
    }
    for registration in (*commands, *groups):
        for root in conflicted:
            if any(_is_prefix(root, path) for path in registration.paths if path):
                suppressed.update(path for path in registration.paths if path)
        for root, winner in takeover_roots.items():
            if not any(_is_prefix(root, path) for path in registration.paths if path):
                continue
            winner_module = winner_modules[root]
            registration_module = getattr(
                registration.handler,
                "handler_module_path",
                None,
            )
            if (
                registration.handler_id != winner
                and registration_module != winner_module
            ):
                suppressed_handlers.add(registration.handler_id)

    filtered_commands = [
        CommandCatalogRegistration(
            registration.handler_id,
            registration.handler,
            registration.schema,
            kept,
            registration.filter_ref,
        )
        for registration in commands
        if (
            kept := _kept_paths(
                registration,
                unique_owners,
                suppressed,
                suppressed_handlers,
            )
        )
    ]
    filtered_groups = [
        CommandGroupRegistration(kept, registration.handler_id, registration.handler)
        for registration in groups
        if (
            kept := _kept_paths(
                registration,
                unique_owners,
                suppressed,
                suppressed_handlers,
            )
        )
    ]
    conflicts = tuple(
        OccupancyConflict(path, tuple(sorted(unique_owners[path])))
        for path in sorted(conflicted)
    )
    return filtered_commands, filtered_groups, conflicts


def _is_prefix(root: tuple[str, ...], path: tuple[str, ...]) -> bool:
    return len(path) >= len(root) and path[: len(root)] == root


def _kept_paths(
    registration: CommandCatalogRegistration | CommandGroupRegistration,
    unique_owners: Mapping[tuple[str, ...], set[str]],
    suppressed: set[tuple[str, ...]],
    suppressed_handlers: set[str],
) -> tuple[tuple[str, ...], ...]:
    handler_id = getattr(registration, "handler_id", "")
    if handler_id in suppressed_handlers:
        return ()
    kept: list[tuple[str, ...]] = []
    for path in registration.paths:
        if not path or path in suppressed:
            continue
        if unique_owners.get(path) == {handler_id}:
            kept.append(path)
    return tuple(kept)
