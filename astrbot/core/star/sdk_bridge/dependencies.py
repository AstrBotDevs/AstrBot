"""Dependency graph resolution and topological scheduling for SDK plugins."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from astrbot_sdk.runtime.metadata import PluginMetadata
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version


@dataclass(frozen=True, slots=True)
class BlockedPlugin:
    """Describe why one plugin could not start due to dependency constraints."""

    plugin_id: str
    dir_name: str
    reason: str
    code: str = "DEPENDENCY_BLOCKED"


@dataclass(frozen=True, slots=True)
class DependencyPlan:
    """Resolved startup/shutdown order and isolated blocked plugins."""

    load_order: tuple[str, ...]
    unload_order: tuple[str, ...]
    blocked: dict[str, BlockedPlugin]
    dependents: dict[str, tuple[str, ...]]

    def dependents_of(self, dir_name: str) -> tuple[str, ...]:
        """Return unblocked plugins that depend on `dir_name` in reverse load order."""
        return self.dependents.get(dir_name, ())


def build_dependency_plan(
    candidates: Mapping[str, PluginMetadata],
) -> DependencyPlan:
    """Resolve SemVer requirements, detect cycles, and compute topological order.

    Independent plugins preserve the input iteration order so handler
    registration order matches directory scan order.

    Args:
        candidates: Ordered mapping from plugin directory name to `PluginMetadata`.

    Returns:
        `DependencyPlan` containing unblocked load/unload orders and blocked entries.
    """
    alias_to_dir: dict[str, str] = {}
    parsed_versions: dict[str, Version] = {}
    blocked: dict[str, BlockedPlugin] = {}

    for dir_name, meta in candidates.items():
        alias_to_dir[dir_name] = dir_name
        alias_to_dir.setdefault(meta.plugin_id, dir_name)
        alias_to_dir.setdefault(meta.name, dir_name)
        try:
            parsed_versions[dir_name] = Version(meta.version)
        except InvalidVersion:
            blocked[dir_name] = BlockedPlugin(
                plugin_id=meta.plugin_id,
                dir_name=dir_name,
                reason=f"invalid plugin version {meta.version!r}",
            )

    # Iteratively isolate plugins whose required dependencies are missing,
    # incompatible, or already blocked (transitive block propagation).
    changed = True
    while changed:
        changed = False
        for dir_name, meta in candidates.items():
            if dir_name in blocked:
                continue
            for dep_key, spec_str in meta.dependencies.items():
                target_dir = alias_to_dir.get(dep_key)
                if target_dir is None:
                    blocked[dir_name] = BlockedPlugin(
                        plugin_id=meta.plugin_id,
                        dir_name=dir_name,
                        reason=f"missing required dependency {dep_key!r}",
                    )
                    changed = True
                    break
                if target_dir == dir_name:
                    blocked[dir_name] = BlockedPlugin(
                        plugin_id=meta.plugin_id,
                        dir_name=dir_name,
                        reason="plugin cannot depend on itself",
                    )
                    changed = True
                    break
                if target_dir in blocked:
                    blocked[dir_name] = BlockedPlugin(
                        plugin_id=meta.plugin_id,
                        dir_name=dir_name,
                        reason=(
                            f"required dependency {dep_key!r} is blocked: "
                            f"{blocked[target_dir].reason}"
                        ),
                    )
                    changed = True
                    break
                spec = SpecifierSet(spec_str)
                if not spec.contains(parsed_versions[target_dir], prereleases=True):
                    blocked[dir_name] = BlockedPlugin(
                        plugin_id=meta.plugin_id,
                        dir_name=dir_name,
                        reason=(
                            f"dependency {dep_key!r} version "
                            f"{candidates[target_dir].version} does not satisfy {spec_str}"
                        ),
                    )
                    changed = True
                    break

    active_order = [dir_name for dir_name in candidates if dir_name not in blocked]
    order_index = {dir_name: idx for idx, dir_name in enumerate(active_order)}
    deps_of: dict[str, set[str]] = {dir_name: set() for dir_name in active_order}
    rev_edges: dict[str, list[str]] = {dir_name: [] for dir_name in active_order}

    for dir_name in active_order:
        meta = candidates[dir_name]
        for dep_key, _ in meta.dependencies.items():
            target_dir = alias_to_dir[dep_key]
            deps_of[dir_name].add(target_dir)
            rev_edges[target_dir].append(dir_name)
        for dep_key, spec_str in meta.optional_dependencies.items():
            target_dir = alias_to_dir.get(dep_key)
            if target_dir is None or target_dir in blocked or target_dir == dir_name:
                continue
            spec = SpecifierSet(spec_str)
            if spec.contains(parsed_versions[target_dir], prereleases=True):
                deps_of[dir_name].add(target_dir)
                rev_edges[target_dir].append(dir_name)

    in_degree = {dir_name: len(deps_of[dir_name]) for dir_name in active_order}
    ready = [dir_name for dir_name in active_order if in_degree[dir_name] == 0]
    load_order: list[str] = []

    while ready:
        # Pop in directory scan order to preserve deterministic loading.
        ready.sort(key=order_index.__getitem__)
        current = ready.pop(0)
        load_order.append(current)
        for dependent in rev_edges[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                ready.append(dependent)

    if len(load_order) != len(active_order):
        cycle_nodes = [d for d in active_order if d not in load_order]
        for dir_name in cycle_nodes:
            meta = candidates[dir_name]
            blocked[dir_name] = BlockedPlugin(
                plugin_id=meta.plugin_id,
                dir_name=dir_name,
                reason="dependency cycle detected",
            )
        # Re-run cleanly without cycle nodes if optional edges formed a cycle
        # mixed with healthy nodes that were only blocked downstream.
        clean_candidates = {k: v for k, v in candidates.items() if k not in blocked}
        if clean_candidates and len(clean_candidates) < len(candidates):
            sub_plan = build_dependency_plan(clean_candidates)
            combined_blocked = {**blocked, **sub_plan.blocked}
            return DependencyPlan(
                load_order=sub_plan.load_order,
                unload_order=sub_plan.unload_order,
                blocked=combined_blocked,
                dependents=sub_plan.dependents,
            )

    load_tuple = tuple(load_order)
    load_pos = {d: i for i, d in enumerate(load_tuple)}
    dependents_map: dict[str, tuple[str, ...]] = {}
    for root_dir in load_tuple:
        seen: set[str] = set()
        stack = list(rev_edges.get(root_dir, ()))
        while stack:
            nxt = stack.pop()
            if nxt in seen or nxt not in load_pos:
                continue
            seen.add(nxt)
            stack.extend(rev_edges.get(nxt, ()))
        dependents_map[root_dir] = tuple(
            sorted(seen, key=load_pos.__getitem__, reverse=True)
        )

    return DependencyPlan(
        load_order=load_tuple,
        unload_order=tuple(reversed(load_tuple)),
        blocked=blocked,
        dependents=dependents_map,
    )
