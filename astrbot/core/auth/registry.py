"""Frozen action, relation, and risk registry for authorization v1/v2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from astrbot.core.auth.models import ACTIONS, HIGH_RISK_ACTIONS, Resource, Role


class Relation(StrEnum):
    ROOT = "root"
    OPERATOR = "operator"
    INSTANCE_OPERATOR = "instance_operator"
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    GUEST = "guest"
    VIEWER = "viewer"
    EDITOR = "editor"
    EXECUTOR = "executor"
    CALLER = "caller"


ENABLED_RELATIONS = frozenset(
    {
        Relation.ROOT,
        Relation.OPERATOR,
        Relation.INSTANCE_OPERATOR,
        Relation.OWNER,
        Relation.ADMIN,
        Relation.MEMBER,
        Relation.GUEST,
    }
)

RESERVED_RELATIONS = frozenset(
    {Relation.VIEWER, Relation.EDITOR, Relation.EXECUTOR, Relation.CALLER}
)

ROLE_TO_RELATION: dict[Role, Relation] = {
    Role.ROOT: Relation.ROOT,
    Role.OPERATOR: Relation.OPERATOR,
    Role.INSTANCE_OPERATOR: Relation.INSTANCE_OPERATOR,
    Role.SESSION_OWNER: Relation.OWNER,
    Role.SESSION_ADMIN: Relation.ADMIN,
    Role.MEMBER: Relation.MEMBER,
    Role.GUEST: Relation.GUEST,
}

RELATION_TO_ROLE: dict[Relation, Role] = {
    relation: role for role, relation in ROLE_TO_RELATION.items()
}

_SESSION_AND_ABOVE = frozenset(
    {
        Role.MEMBER,
        Role.SESSION_ADMIN,
        Role.SESSION_OWNER,
        Role.INSTANCE_OPERATOR,
        Role.OPERATOR,
        Role.ROOT,
    }
)
_SESSION_ADMIN_AND_ABOVE = frozenset(
    {
        Role.SESSION_ADMIN,
        Role.SESSION_OWNER,
        Role.INSTANCE_OPERATOR,
        Role.OPERATOR,
        Role.ROOT,
    }
)
_SESSION_OWNER_AND_ABOVE = frozenset(
    {Role.SESSION_OWNER, Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}
)
_INSTANCE_AND_ABOVE = frozenset({Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT})
_ROOT_ONLY = frozenset({Role.ROOT})

ACTION_ROLE_GRANTS: dict[str, frozenset[Role]] = {
    "session.read": _SESSION_AND_ABOVE,
    "session.manage": _SESSION_ADMIN_AND_ABOVE,
    "session.assign": _SESSION_OWNER_AND_ABOVE,
    "provider.read": _SESSION_AND_ABOVE,
    "provider.use": _SESSION_AND_ABOVE,
    "platform.read": _SESSION_AND_ABOVE,
    "provider.manage": _INSTANCE_AND_ABOVE,
    "provider.credentials.write": _INSTANCE_AND_ABOVE,
    "platform.manage": _INSTANCE_AND_ABOVE,
    "agent.manage": _SESSION_OWNER_AND_ABOVE,
    "extension.read": _SESSION_AND_ABOVE,
    "extension.manage": _INSTANCE_AND_ABOVE,
    "extension.plugin_install": _INSTANCE_AND_ABOVE,
    "data.manage": _SESSION_AND_ABOVE,
    "data.export_all": _INSTANCE_AND_ABOVE,
    "system.manage": _ROOT_ONLY,
    "system.update": _ROOT_ONLY,
    "system.restart": _ROOT_ONLY,
    "system.pip_install": _ROOT_ONLY,
    "identity.read": _INSTANCE_AND_ABOVE,
    "identity.manage": _SESSION_OWNER_AND_ABOVE,
    "identity.operator.write": _ROOT_ONLY,
    "identity.root.write": _ROOT_ONLY,
    "tool.local_exec": _INSTANCE_AND_ABOVE,
    "tool.python_exec": _INSTANCE_AND_ABOVE,
    "tool.file_read": _SESSION_AND_ABOVE,
    "tool.file_write": _INSTANCE_AND_ABOVE,
    "tool.browser_control": _INSTANCE_AND_ABOVE,
    "tool.mcp_read": _SESSION_AND_ABOVE,
    "tool.mcp_write": _INSTANCE_AND_ABOVE,
    "tool.computer_use": _INSTANCE_AND_ABOVE,
    "dashboard.account.manage": _ROOT_ONLY,
    "filesystem.read": frozenset({Role.OPERATOR, Role.ROOT}),
    "filesystem.write": frozenset({Role.OPERATOR, Role.ROOT}),
    "filesystem.manage": _ROOT_ONLY,
}

# Frozen historical NULL-scope expansion. Not a runtime wildcard.
DEFAULT_API_KEY_SCOPES = (
    "bot",
    "provider",
    "persona",
    "im",
    "config",
    "chat",
    "kb",
    "memory",
    "data",
    "file",
    "plugin",
    "mcp",
    "skill",
)

API_KEY_HTTP_METHODS = ("get", "head", "post", "put", "patch", "delete")
_SAFE_HTTP_METHODS = frozenset({"get", "head"})

API_SCOPE_ACTIONS: dict[str, frozenset[str]] = {
    "provider": frozenset({"provider.read", "provider.use"}),
    "config": frozenset(
        {"platform.read", "platform.manage", "provider.read", "provider.manage"}
    ),
    "chat": frozenset({"session.read", "session.manage", "provider.use"}),
    "persona": frozenset({"agent.manage"}),
    "plugin": frozenset({"extension.read", "extension.manage"}),
    "mcp": frozenset({"tool.mcp_read", "tool.mcp_write"}),
    "skill": frozenset({"extension.manage"}),
    "kb": frozenset({"data.manage"}),
    "memory": frozenset({"data.manage"}),
    "data": frozenset({"data.manage"}),
    "file": frozenset({"data.manage", "tool.file_read", "tool.file_write"}),
    "im": frozenset({"session.manage"}),
    "bot": frozenset({"platform.read"}),
}


@dataclass(frozen=True, slots=True)
class ActionPolicy:
    action: str
    resource_types: frozenset[str]
    relations: frozenset[Relation]
    parent_resource_types: frozenset[str]
    parent_depth: int
    required_context: frozenset[str]
    risk: str
    requires_step_up: bool
    plugin_namespace: bool = False


def _resource_types_for(action: str) -> frozenset[str]:
    if action.startswith("session."):
        return frozenset(
            {"session", "dashboard-api", "webchat", "webchat-user", "conversation"}
        )
    if action.startswith("provider."):
        return frozenset(
            {
                "provider",
                "provider-model",
                "provider-source",
                "instance",
                "dashboard-api",
            }
        )
    if action.startswith("platform."):
        return frozenset(
            {
                "platform",
                "bot",
                "instance",
                "dashboard-api",
                "config-profile",
                "config-route",
            }
        )
    if action.startswith("agent."):
        return frozenset({"persona", "session", "tool", "dashboard-api"})
    if action.startswith("extension."):
        return frozenset({"plugin", "skill", "dashboard-api"})
    if action.startswith("data."):
        return frozenset(
            {
                "data",
                "conversation",
                "memory",
                "file",
                "knowledge-base",
                "dashboard-api",
            }
        )
    if action.startswith("system."):
        return frozenset({"system", "dashboard-api"})
    if action.startswith("filesystem."):
        return frozenset({"filesystem", "dashboard-api"})
    if action.startswith("identity.") or action == "dashboard.account.manage":
        return frozenset(
            {
                "session",
                "instance",
                "identity",
                "identity-batch",
                "api-key",
                "dashboard-api",
                "dashboard-account",
            }
        )
    if action in {"tool.mcp_read", "tool.mcp_write"}:
        # Dashboard MCP management routes authorize their collection-level
        # request before resolving an individual server resource.
        return frozenset({"tool", "file", "mcp", "session", "dashboard-api"})
    if action.startswith("tool."):
        return frozenset({"tool", "file", "mcp", "session"})
    return frozenset({"instance", "session", "dashboard-api"})


def _parent_types(action: str) -> tuple[frozenset[str], int]:
    if action.startswith(("tool.", "agent.")):
        return frozenset({"session", "instance"}), 1
    if action.startswith(
        (
            "session.",
            "provider.",
            "platform.",
            "extension.",
            "data.",
            "identity.",
        )
    ):
        return frozenset({"instance"}), 1
    return frozenset(), 0


def _required_context(action: str, high_risk: bool) -> frozenset[str]:
    required = {"source"}
    if action.startswith(("session.", "identity.", "agent.", "tool.")):
        required.update({"config", "origin_session"})
    if high_risk:
        required.add("auth_strength")
    return frozenset(required)


def build_action_policies() -> dict[str, ActionPolicy]:
    missing = ACTIONS.difference(ACTION_ROLE_GRANTS)
    extra = set(ACTION_ROLE_GRANTS).difference(ACTIONS)
    if missing or extra:
        raise RuntimeError(f"Action registry drift: missing={missing} extra={extra}")
    policies: dict[str, ActionPolicy] = {}
    for action, roles in ACTION_ROLE_GRANTS.items():
        high_risk = action in HIGH_RISK_ACTIONS
        parent_types, parent_depth = _parent_types(action)
        policies[action] = ActionPolicy(
            action=action,
            resource_types=_resource_types_for(action),
            relations=frozenset(ROLE_TO_RELATION[role] for role in roles),
            parent_resource_types=parent_types,
            parent_depth=parent_depth,
            required_context=_required_context(action, high_risk),
            risk="high" if high_risk else "normal",
            requires_step_up=high_risk,
        )
    return policies


ACTION_POLICIES = build_action_policies()

PLUGIN_ACTION_POLICY = ActionPolicy(
    action="plugin:<plugin-id>:<action>",
    resource_types=frozenset({"session", "plugin"}),
    relations=frozenset(
        ROLE_TO_RELATION[role] for role in ACTION_ROLE_GRANTS["session.manage"]
    ),
    parent_resource_types=frozenset(),
    parent_depth=0,
    required_context=frozenset({"source", "config", "origin_session"}),
    risk="normal",
    requires_step_up=False,
    plugin_namespace=True,
)


def api_key_scope_action(method: str, scope: str) -> str | None:
    safe = method.lower() in _SAFE_HTTP_METHODS
    if scope == "provider":
        return "provider.read" if safe else None
    if scope == "bot":
        return "platform.read" if safe else "platform.manage"
    if scope == "config":
        return "platform.read" if safe else "platform.manage"
    if scope in {"plugin", "skill", "tool"}:
        return "extension.read" if safe else "extension.manage"
    if scope == "mcp":
        return "tool.mcp_read" if safe else "tool.mcp_write"
    if scope == "data":
        return "data.manage"
    if scope == "chat":
        return "session.read" if safe else "session.manage"
    if scope == "im":
        return "session.read" if safe else "session.manage"
    return {
        "persona": "agent.manage",
        "kb": "data.manage",
        "memory": "data.manage",
        "file": "data.manage",
    }.get(scope)


def dashboard_api_capability_specs(
    scopes: list[str],
) -> tuple[tuple[str, str, str], ...]:
    specs: list[tuple[str, str, str]] = []
    selected = set(scopes)
    for scope in scopes:
        if scope not in API_SCOPE_ACTIONS:
            continue
        for method in API_KEY_HTTP_METHODS:
            action = api_key_scope_action(method, scope)
            if action is None or action in HIGH_RISK_ACTIONS:
                continue
            resource = Resource.named("dashboard-api", f"{method}-{scope}")
            specs.append((action, resource.type, resource.id))
    if "config" in selected:
        instance = Resource.instance("default")
        specs.append(("platform.read", instance.type, instance.id))
        specs.append(("platform.manage", instance.type, instance.id))
        collection = Resource.named("config-profile", "collection", config_id="default")
        specs.append(("platform.manage", collection.type, collection.id))
    if "bot" in selected:
        collection = Resource.named("bot", "collection")
        specs.append(("platform.read", collection.type, collection.id))
        specs.append(("platform.manage", collection.type, collection.id))
    if "provider" in selected:
        schema = Resource.named("provider", "schema", config_id="default")
        specs.append(("provider.read", schema.type, schema.id))
        sources = Resource.named("provider-source", "collection", config_id="default")
        specs.append(("provider.read", sources.type, sources.id))
    if "file" in selected:
        collection = Resource.named("file", "collection")
        specs.append(("data.manage", collection.type, collection.id))
    if "chat" in selected:
        socket = Resource.named("webchat", "socket")
        specs.append(("session.read", socket.type, socket.id))
    if "skill" in selected:
        collection = Resource.named("skill", "collection")
        specs.append(("extension.read", collection.type, collection.id))
        specs.append(("extension.manage", collection.type, collection.id))
        for neo_collection in ("neo-candidates", "neo-releases"):
            named = Resource.named("skill", neo_collection)
            specs.append(("extension.read", named.type, named.id))
    return tuple(dict.fromkeys(specs))


def policy_for(action: str) -> ActionPolicy | None:
    if action in ACTION_POLICIES:
        return ACTION_POLICIES[action]
    if action.startswith("plugin:"):
        parts = action.split(":")
        if len(parts) == 3 and all(parts):
            return PLUGIN_ACTION_POLICY
    return None
