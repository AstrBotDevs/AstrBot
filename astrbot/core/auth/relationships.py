"""Finite relationship tuples and one-level parent resolution."""

from __future__ import annotations

from dataclasses import dataclass

from astrbot.core.auth.models import AuthContext, Resource, Role
from astrbot.core.auth.registry import (
    ENABLED_RELATIONS,
    RELATION_TO_ROLE,
    ROLE_TO_RELATION,
    Relation,
    policy_for,
)


@dataclass(frozen=True, slots=True)
class RelationshipTuple:
    subject_id: str
    relation: Relation
    resource_type: str
    resource_id: str
    source: str
    parent_used: bool = False


def role_to_relation(role: Role) -> Relation:
    return ROLE_TO_RELATION[role]


def tuples_from_roles(
    *,
    subject_id: str,
    roles: list[tuple[Role, str, Resource]],
) -> tuple[RelationshipTuple, ...]:
    found: list[RelationshipTuple] = []
    for role, source, resource in roles:
        relation = ROLE_TO_RELATION.get(role)
        if relation is None or relation not in ENABLED_RELATIONS:
            continue
        found.append(
            RelationshipTuple(
                subject_id=subject_id,
                relation=relation,
                resource_type=resource.type,
                resource_id=resource.id,
                source=source,
            )
        )
    return tuple(found)


def parent_resource(resource: Resource, context: AuthContext) -> Resource | None:
    return _origin_parent(resource, context)


def _origin_parent(resource: Resource, context: AuthContext) -> Resource | None:
    if resource.type == "session":
        return None
    origin_id = context.origin_session_resource_id
    if origin_id is None or resource.config_id is None:
        return None
    if resource.type in {"tool", "file", "mcp"}:
        from astrbot.core.auth.models import parse_canonical_session_resource

        config_id, umo = parse_canonical_session_resource(origin_id)
        if config_id != resource.config_id:
            return None
        return Resource.session(config_id, umo)
    return None


def _parent_candidates(
    resource: Resource, context: AuthContext, *, parent_types: frozenset[str]
) -> tuple[Resource, ...]:
    parents: list[Resource] = []
    if "session" in parent_types:
        origin = _origin_parent(resource, context)
        if origin is not None:
            parents.append(origin)
    if (
        "instance" in parent_types
        and resource.type != "instance"
        and resource.config_id is not None
    ):
        parents.append(Resource.instance(resource.config_id))
    return tuple(parents)


def evaluate_relations(
    *,
    action: str,
    resource: Resource,
    context: AuthContext,
    tuples: tuple[RelationshipTuple, ...],
) -> tuple[bool, tuple[RelationshipTuple, ...]]:
    policy = policy_for(action)
    if policy is None:
        return False, ()
    if policy.parent_depth not in {0, 1}:
        return False, ()
    parents = (
        _parent_candidates(resource, context, parent_types=policy.parent_resource_types)
        if policy.parent_depth == 1
        else ()
    )
    matched: list[RelationshipTuple] = []
    seen: set[tuple[str, str, str]] = set()
    for item in tuples:
        if item.relation not in ENABLED_RELATIONS:
            continue
        if item.relation not in policy.relations:
            continue
        direct = item.resource_id == resource.id and item.resource_type == resource.type
        inherited = any(
            item.resource_id == parent.id and item.resource_type == parent.type
            for parent in parents
        )
        if not direct and not inherited:
            continue
        key = (item.subject_id, item.relation.value, item.resource_id)
        if key in seen:
            continue
        seen.add(key)
        matched.append(
            RelationshipTuple(
                subject_id=item.subject_id,
                relation=item.relation,
                resource_type=item.resource_type,
                resource_id=item.resource_id,
                source=item.source,
                parent_used=inherited and not direct,
            )
        )
    return bool(matched), tuple(matched)


def display_role(matched: tuple[RelationshipTuple, ...]) -> Role | None:
    if not matched:
        return None
    roles = [RELATION_TO_ROLE[item.relation] for item in matched]
    from astrbot.core.auth.models import ROLE_ORDER

    return max(roles, key=lambda role: ROLE_ORDER[role])
