"""One-time authorization upgrade preflight. Absence of users is not evidence."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import select

from astrbot.core.auth.models import (
    AuthorizationValueError,
    Role,
    parse_canonical_session_resource,
    utc_now,
)
from astrbot.core.auth.registry import (
    ACTION_ROLE_GRANTS,
    DEFAULT_API_KEY_SCOPES,
    ENABLED_RELATIONS,
    ROLE_TO_RELATION,
)
from astrbot.core.db.po import (
    ApiKey,
    AuthCapability,
    AuthPolicyOverride,
    AuthRoleBinding,
)
from astrbot.core.db.protocols import DatabaseSessionStore


@dataclass(slots=True)
class PreflightReport:
    blocking: list[str] = field(default_factory=list)
    rebuild_api_keys: list[str] = field(default_factory=list)
    expandable_null_keys: list[str] = field(default_factory=list)
    binding_count: int = 0
    override_count: int = 0
    api_key_count: int = 0

    @property
    def ok(self) -> bool:
        return not self.blocking


async def inspect_authorization_upgrade(db: DatabaseSessionStore) -> PreflightReport:
    report = PreflightReport()
    async with db.get_db() as session:
        bindings = list((await session.execute(select(AuthRoleBinding))).scalars())
        overrides = list((await session.execute(select(AuthPolicyOverride))).scalars())
        keys = list((await session.execute(select(ApiKey))).scalars())
        capabilities = list((await session.execute(select(AuthCapability))).scalars())
    report.binding_count = len(bindings)
    report.override_count = len(overrides)
    report.api_key_count = len(keys)
    now = utc_now()
    live_capability_subjects = {
        capability.subject_id
        for capability in capabilities
        if capability.revoked_at is None
        and (capability.expires_at is None or capability.expires_at > now)
    }
    for binding in bindings:
        if binding.revoked_at is not None:
            continue
        try:
            role = Role(binding.role)
        except ValueError:
            report.blocking.append(f"unmapped_binding_role:{binding.binding_id}")
            continue
        if ROLE_TO_RELATION[role] not in ENABLED_RELATIONS:
            report.blocking.append(f"reserved_relation:{binding.binding_id}")
        if binding.scope_type == "session":
            try:
                parsed_config_id, _umo = parse_canonical_session_resource(
                    str(binding.scope_id)
                )
            except AuthorizationValueError, TypeError, ValueError:
                report.blocking.append(f"non_canonical_session:{binding.binding_id}")
            else:
                if binding.config_id and binding.config_id != parsed_config_id:
                    report.blocking.append(
                        f"session_config_mismatch:{binding.binding_id}"
                    )
        if binding.role in {Role.ROOT.value, Role.OPERATOR.value}:
            if binding.scope_type != "global" or not binding.subject_id.startswith(
                "dashboard-account:"
            ):
                report.blocking.append(f"control_plane_scope:{binding.binding_id}")
        if (
            binding.role == Role.INSTANCE_OPERATOR.value
            and binding.scope_type != "instance"
        ):
            report.blocking.append(f"instance_operator_scope:{binding.binding_id}")
    for override in overrides:
        if override.action not in ACTION_ROLE_GRANTS:
            report.blocking.append(f"override_unknown_action:{override.override_id}")
        allowed = {str(item) for item in (override.allowed_roles or [])}
        if allowed.difference(
            {role.value for role in ACTION_ROLE_GRANTS.get(override.action, ())}
        ):
            report.blocking.append(f"override_unmapped_roles:{override.override_id}")
    for key in keys:
        if key.revoked_at is not None:
            continue
        scopes = key.scopes
        if scopes is None:
            report.expandable_null_keys.append(key.key_id)
            report.rebuild_api_keys.append(key.key_id)
            report.blocking.append(f"api_key_null_scope:{key.key_id}")
            continue
        if not isinstance(scopes, list):
            report.blocking.append(f"api_key_invalid_scopes:{key.key_id}")
            continue
        if "*" in scopes:
            report.rebuild_api_keys.append(key.key_id)
            report.blocking.append(f"api_key_wildcard:{key.key_id}")
            continue
        if f"api-key:{key.key_id}" not in live_capability_subjects:
            report.rebuild_api_keys.append(key.key_id)
            report.blocking.append(f"api_key_missing_capabilities:{key.key_id}")
    return report


def default_null_scope_actions() -> frozenset[str]:
    from astrbot.core.auth.registry import API_SCOPE_ACTIONS

    actions: set[str] = set()
    for scope in DEFAULT_API_KEY_SCOPES:
        actions.update(API_SCOPE_ACTIONS.get(scope, ()))
    return frozenset(actions)
