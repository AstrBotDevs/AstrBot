"""Runtime-owned authorization, audit, step-up, and elevation service."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from collections.abc import Iterable, Mapping
from datetime import timedelta
from typing import Any

from sqlalchemy import update
from sqlmodel import col, delete, select

from astrbot import logger
from astrbot.core.auth.models import (
    ACTIONS,
    GLOBAL_SCOPE_ID,
    HIGH_RISK_ACTIONS,
    ROLE_ORDER,
    AuthContext,
    AuthorizationValueError,
    Decision,
    Resource,
    Role,
    Subject,
    canonical_session_resource,
    parse_canonical_session_resource,
    utc_now,
)
from astrbot.core.db.po import (
    AuthAuditLog,
    AuthElevationRequest,
    AuthPlatformMembershipFact,
    AuthPolicyOverride,
    AuthRoleBinding,
    AuthStepUpCredential,
)
from astrbot.core.db.protocols import DatabaseSessionStore
from astrbot.core.utils.error_redaction import redact_sensitive_text

_AUDIT_QUEUE_SIZE = 2048
_STEP_UP_TTL_SECONDS = 300
_ELEVATION_TTL_SECONDS = 300
_SENSITIVE_KEYS = frozenset(
    {
        "jwt",
        "token",
        "api_key",
        "key",
        "nonce",
        "password",
        "credential",
        "secret",
        "message",
        "content",
    }
)

# A role is only meaningful after _binding_matches_resource has verified scope.
_ACTION_ROLES: dict[str, frozenset[Role]] = {
    "session.read": frozenset(
        {
            Role.MEMBER,
            Role.SESSION_ADMIN,
            Role.SESSION_OWNER,
            Role.INSTANCE_OPERATOR,
            Role.OPERATOR,
            Role.ROOT,
        }
    ),
    "session.manage": frozenset(
        {
            Role.SESSION_ADMIN,
            Role.SESSION_OWNER,
            Role.INSTANCE_OPERATOR,
            Role.OPERATOR,
            Role.ROOT,
        }
    ),
    "session.assign": frozenset(
        {Role.SESSION_OWNER, Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}
    ),
    "provider.read": frozenset(
        {
            Role.MEMBER,
            Role.SESSION_ADMIN,
            Role.SESSION_OWNER,
            Role.INSTANCE_OPERATOR,
            Role.OPERATOR,
            Role.ROOT,
        }
    ),
    "provider.use": frozenset(
        {
            Role.MEMBER,
            Role.SESSION_ADMIN,
            Role.SESSION_OWNER,
            Role.INSTANCE_OPERATOR,
            Role.OPERATOR,
            Role.ROOT,
        }
    ),
    "provider.manage": frozenset({Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}),
    "provider.credentials.write": frozenset(
        {Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}
    ),
    "platform.manage": frozenset({Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}),
    "agent.manage": frozenset(
        {Role.SESSION_OWNER, Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}
    ),
    "extension.read": frozenset(
        {
            Role.MEMBER,
            Role.SESSION_ADMIN,
            Role.SESSION_OWNER,
            Role.INSTANCE_OPERATOR,
            Role.OPERATOR,
            Role.ROOT,
        }
    ),
    "extension.manage": frozenset({Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}),
    "extension.plugin_install": frozenset(
        {Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}
    ),
    "data.manage": frozenset(
        {
            Role.MEMBER,
            Role.SESSION_ADMIN,
            Role.SESSION_OWNER,
            Role.INSTANCE_OPERATOR,
            Role.OPERATOR,
            Role.ROOT,
        }
    ),
    "data.export_all": frozenset({Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}),
    "system.manage": frozenset({Role.ROOT}),
    "system.update": frozenset({Role.ROOT}),
    "system.restart": frozenset({Role.ROOT}),
    "system.pip_install": frozenset({Role.ROOT}),
    "identity.read": frozenset({Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}),
    "identity.manage": frozenset({Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}),
    "identity.operator.write": frozenset({Role.ROOT}),
    "identity.root.write": frozenset({Role.ROOT}),
    "chat.impersonate_admin": frozenset(
        {Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}
    ),
    "elevation.request": frozenset(
        {
            Role.SESSION_ADMIN,
            Role.SESSION_OWNER,
            Role.INSTANCE_OPERATOR,
            Role.OPERATOR,
            Role.ROOT,
        }
    ),
    "elevation.approve": frozenset(
        {Role.SESSION_OWNER, Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}
    ),
    "elevation.execute": frozenset(
        {
            Role.SESSION_ADMIN,
            Role.SESSION_OWNER,
            Role.INSTANCE_OPERATOR,
            Role.OPERATOR,
            Role.ROOT,
        }
    ),
    "tool.local_exec": frozenset({Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}),
    "tool.python_exec": frozenset({Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}),
    "tool.file_read": frozenset(
        {
            Role.MEMBER,
            Role.SESSION_ADMIN,
            Role.SESSION_OWNER,
            Role.INSTANCE_OPERATOR,
            Role.OPERATOR,
            Role.ROOT,
        }
    ),
    "tool.file_write": frozenset({Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}),
    "tool.browser_control": frozenset(
        {Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}
    ),
    "tool.mcp_read": frozenset(
        {
            Role.MEMBER,
            Role.SESSION_ADMIN,
            Role.SESSION_OWNER,
            Role.INSTANCE_OPERATOR,
            Role.OPERATOR,
            Role.ROOT,
        }
    ),
    "tool.mcp_write": frozenset({Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}),
    "tool.computer_use": frozenset({Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}),
    "tool.function": frozenset(
        {
            Role.MEMBER,
            Role.SESSION_ADMIN,
            Role.SESSION_OWNER,
            Role.INSTANCE_OPERATOR,
            Role.OPERATOR,
            Role.ROOT,
        }
    ),
    "dashboard.account.manage": frozenset({Role.ROOT}),
}

_API_SCOPE_ACTIONS: dict[str, frozenset[str]] = {
    # API keys are capabilities, never implicit control-plane roles. The
    # historical provider scope can use configured models but cannot alter a
    # provider definition or its credentials.
    "provider": frozenset({"provider.read", "provider.use"}),
    "config": frozenset({"platform.manage", "provider.manage"}),
    "config:edit_admin": frozenset({"identity.manage"}),
    "chat": frozenset({"session.read", "session.manage", "provider.use"}),
    "chat:admin": frozenset({"chat.impersonate_admin"}),
    "persona": frozenset({"agent.manage"}),
    "plugin": frozenset({"extension.read", "extension.manage"}),
    "mcp": frozenset({"extension.manage", "tool.mcp_read", "tool.mcp_write"}),
    "skill": frozenset({"extension.manage"}),
    "kb": frozenset({"data.manage"}),
    "memory": frozenset({"data.manage"}),
    "data": frozenset({"data.manage", "data.export_all"}),
    "file": frozenset({"data.manage", "tool.file_read", "tool.file_write"}),
    "im": frozenset({"session.manage"}),
    "bot": frozenset({"platform.manage"}),
}


def api_key_scopes_allow_action(scopes: Iterable[str], action: str) -> bool:
    """Map scopes to action capability without creating an operator role."""

    if action in HIGH_RISK_ACTIONS and action != "chat.impersonate_admin":
        return False
    return any(action in _API_SCOPE_ACTIONS.get(scope, ()) for scope in set(scopes))


def _requires_step_up(action: str, context: AuthContext) -> bool:
    """Return whether this exact Dashboard request needs fresh proof."""

    return action in HIGH_RISK_ACTIONS or (
        context.source == "dashboard" and bool(context.metadata.get("dashboard_write"))
    )


def _sanitize_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize_metadata(item)
            for key, item in value.items()
            if str(key).lower() not in _SENSITIVE_KEYS
        }
    if isinstance(value, list | tuple):
        return [_sanitize_metadata(item) for item in value[:32]]
    if isinstance(value, str):
        return redact_sensitive_text(value)[:512]
    if isinstance(value, bool | int | float) or value is None:
        return value
    return redact_sensitive_text(str(value))[:512]


class AuthorizationService:
    """The single fail-closed authorization entry point for a runtime."""

    def __init__(self, db: DatabaseSessionStore) -> None:
        self._db = db
        self._audit_queue: asyncio.Queue[AuthAuditLog] = asyncio.Queue(
            _AUDIT_QUEUE_SIZE
        )
        self._audit_task: asyncio.Task[None] | None = None
        self._binding_mutation_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._audit_task is None:
            self._audit_task = asyncio.create_task(
                self._write_audit_loop(), name="auth-audit-writer"
            )

    async def close(self) -> None:
        await self.flush_audit()
        if self._audit_task is not None:
            self._audit_task.cancel()
            try:
                await self._audit_task
            except asyncio.CancelledError:
                pass
            self._audit_task = None

    async def _write_audit_loop(self) -> None:
        while True:
            record = await self._audit_queue.get()
            try:
                await self._write_audit_record(record)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Authorization audit write failed: %s",
                    redact_sensitive_text(str(exc)),
                )
            finally:
                self._audit_queue.task_done()

    async def flush_audit(self) -> None:
        if self._audit_task is not None:
            await self._audit_queue.join()
            return
        while not self._audit_queue.empty():
            record = self._audit_queue.get_nowait()
            try:
                await self._write_audit_record(record)
            finally:
                self._audit_queue.task_done()

    async def _write_audit_record(self, record: AuthAuditLog) -> None:
        async with self._db.get_db() as session:
            async with session.begin():
                session.add(record)

    def _audit(
        self,
        *,
        audit_id: str,
        subject: Subject,
        action: str,
        resource: Resource,
        context: AuthContext,
        decision: str,
        reason: str,
        effective_role: Role | None = None,
        step_up_id: str | None = None,
        elevation_id: str | None = None,
        approver_subject_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        record = AuthAuditLog(
            audit_id=audit_id,
            request_id=context.request_id,
            subject_id=subject.id,
            effective_role=effective_role.value if effective_role else None,
            source=context.source,
            platform=context.platform,
            config_id=resource.config_id or context.config_id,
            action=action,
            resource_id=resource.id,
            decision=decision,
            reason=reason,
            step_up_id=step_up_id,
            elevation_id=elevation_id,
            approver_subject_id=approver_subject_id,
            outcome=decision,
            metadata_json=_sanitize_metadata({**context.metadata, **(metadata or {})}),
        )
        try:
            self._audit_queue.put_nowait(record)
        except asyncio.QueueFull:
            logger.error("Authorization audit queue full; event id=%s", audit_id)

    async def migrate_legacy_admins(
        self, configs: Mapping[str, Mapping[str, Any]]
    ) -> int:
        """Import ``admins_id`` only as scoped instance_operator bindings."""

        created = 0
        migration_actor = Subject(
            id="system:migration", kind="system", authenticated=True
        )
        for config_id, config in configs.items():
            admins = config.get("admins_id", []) if isinstance(config, Mapping) else []
            if not isinstance(admins, list):
                continue
            for value in (str(item).strip() for item in admins):
                if not value:
                    continue
                binding = await self.grant_binding(
                    actor=migration_actor,
                    subject_id=Subject.legacy_admin(config_id, value).id,
                    role=Role.INSTANCE_OPERATOR,
                    scope_type="instance",
                    scope_id=config_id,
                    config_id=config_id,
                    source="migrated",
                    metadata={
                        "migration": "admins_id-v1",
                        "legacy_id_hash": hashlib.sha256(value.encode()).hexdigest()[
                            :16
                        ],
                    },
                    enforce_actor=False,
                )
                if binding.created_at == binding.updated_at:
                    created += 1
        return created

    async def migrate_legacy_tool_permissions(self, preferences: Any) -> int:
        """Import legacy tool permission preferences into narrow policy rows once.

        The historical map is treated solely as migration input.  Runtime
        authorization evaluates ``AuthPolicyOverride`` and tool action
        declarations; the preference is never consulted after the marker is
        written.
        """

        marker_key = "auth_tool_permissions_migrated_v1"
        if await preferences.global_get(marker_key, False):
            return 0
        raw = await preferences.global_get("tool_permissions", {})
        if not isinstance(raw, Mapping):
            await preferences.global_put(marker_key, True)
            return 0
        actor = Subject(id="system:migration", kind="system", authenticated=True)
        created = 0
        async with self._db.get_db() as session:
            async with session.begin():
                for scope_map in raw.values():
                    if not isinstance(scope_map, Mapping):
                        continue
                    for tool_name, legacy_role in scope_map.items():
                        if not isinstance(tool_name, str) or not tool_name:
                            continue
                        role = str(legacy_role).lower()
                        if role not in {"member", "admin"}:
                            continue
                        allowed_role = (
                            Role.MEMBER.value
                            if role == "member"
                            else Role.INSTANCE_OPERATOR.value
                        )
                        existing_rows = (
                            await session.execute(
                                select(AuthPolicyOverride).where(
                                    col(AuthPolicyOverride.action) == "tool.function",
                                    col(AuthPolicyOverride.resource_type) == "tool",
                                    col(AuthPolicyOverride.resource_id) == tool_name,
                                )
                            )
                        ).scalars()
                        exists = next(
                            (
                                row
                                for row in existing_rows
                                if (row.metadata_json or {}).get("migration")
                                == "tool_permissions-v1"
                            ),
                            None,
                        )
                        if exists is not None:
                            continue
                        session.add(
                            AuthPolicyOverride(
                                action="tool.function",
                                resource_type="tool",
                                resource_id=tool_name,
                                allowed_roles=[allowed_role],
                                created_by=actor.id,
                                metadata_json={
                                    "migration": "tool_permissions-v1",
                                    "legacy_role": role,
                                },
                            )
                        )
                        created += 1
        await preferences.global_put(marker_key, True)
        return created

    async def record_platform_membership(
        self,
        *,
        subject: Subject,
        resource: Resource,
        platform_instance: str,
        platform_role: str,
        source: str,
        ttl_seconds: int = 300,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Store a short-lived adapter fact. It is never a role binding."""

        if resource.type != "session" or not resource.config_id or not resource.umo:
            raise AuthorizationValueError("Platform facts require a session resource")
        if platform_role not in {"owner", "admin", "member", "unknown"}:
            raise AuthorizationValueError("Invalid platform member role")
        if not 0 < ttl_seconds <= 3600:
            raise AuthorizationValueError("Invalid platform role TTL")
        now = utc_now()
        async with self._db.get_db() as session:
            async with session.begin():
                query = select(AuthPlatformMembershipFact).where(
                    col(AuthPlatformMembershipFact.subject_id) == subject.id,
                    col(AuthPlatformMembershipFact.config_id) == resource.config_id,
                    col(AuthPlatformMembershipFact.platform_instance)
                    == platform_instance,
                    col(AuthPlatformMembershipFact.umo) == resource.umo,
                )
                fact = (await session.execute(query)).scalar_one_or_none()
                if fact is None:
                    session.add(
                        AuthPlatformMembershipFact(
                            subject_id=subject.id,
                            config_id=resource.config_id,
                            platform_instance=platform_instance,
                            umo=resource.umo,
                            platform_role=platform_role,
                            source=source,
                            observed_at=now,
                            expires_at=now + timedelta(seconds=ttl_seconds),
                            metadata_json=_sanitize_metadata(metadata or {}),
                        )
                    )
                else:
                    fact.platform_role = platform_role
                    fact.source = source
                    fact.observed_at = now
                    fact.expires_at = now + timedelta(seconds=ttl_seconds)
                    fact.metadata_json = _sanitize_metadata(metadata or {})

    async def grant_binding(
        self,
        *,
        actor: Subject,
        subject_id: str,
        role: Role,
        scope_type: str,
        scope_id: str,
        config_id: str | None,
        source: str = "explicit",
        expires_at=None,
        metadata: Mapping[str, Any] | None = None,
        context: AuthContext | None = None,
        enforce_actor: bool = True,
    ) -> AuthRoleBinding:
        """Create/revive one binding and reject scope/role escalation."""

        if scope_type not in {"global", "instance", "session", "resource"}:
            raise AuthorizationValueError("Invalid binding scope")
        if scope_type == "global" and scope_id != "global":
            raise AuthorizationValueError("Invalid global binding scope")
        if scope_type == "global":
            config_id = GLOBAL_SCOPE_ID
        if scope_type == "instance" and (not config_id or scope_id != config_id):
            raise AuthorizationValueError("Invalid instance binding scope")
        if scope_type == "session":
            canonical_session_resource(config_id or "", scope_id)
        if enforce_actor:
            await self._assert_binding_management_allowed(
                actor, role, scope_type, scope_id, config_id, context=context
            )
        async with self._db.get_db() as session:
            async with session.begin():
                query = select(AuthRoleBinding).where(
                    col(AuthRoleBinding.subject_id) == subject_id,
                    col(AuthRoleBinding.role) == role.value,
                    col(AuthRoleBinding.scope_type) == scope_type,
                    col(AuthRoleBinding.scope_id) == scope_id,
                    col(AuthRoleBinding.config_id) == config_id,
                )
                binding = (await session.execute(query)).scalar_one_or_none()
                if binding is None:
                    binding = AuthRoleBinding(
                        subject_id=subject_id,
                        role=role.value,
                        scope_type=scope_type,
                        scope_id=scope_id,
                        config_id=config_id,
                        source=source,
                        expires_at=expires_at,
                        created_by=actor.id,
                        metadata_json=_sanitize_metadata(metadata or {}),
                    )
                    session.add(binding)
                else:
                    binding.source = source
                    binding.expires_at = expires_at
                    binding.revoked_at = None
                    binding.revoked_by = None
                    binding.metadata_json = _sanitize_metadata(metadata or {})
                await session.flush()
                self._audit(
                    audit_id=str(uuid.uuid4()),
                    subject=actor,
                    action="identity.manage",
                    resource=Resource.named(
                        "identity",
                        subject_id,
                        config_id=(
                            None if config_id == GLOBAL_SCOPE_ID else config_id
                        ),
                    ),
                    context=AuthContext(
                        subject=actor,
                        source="system",
                        authenticated=True,
                        config_id=(
                            None if config_id == GLOBAL_SCOPE_ID else config_id
                        ),
                    ),
                    decision="allow",
                    reason="binding_granted",
                    effective_role=role,
                    metadata={
                        "target_subject_id": subject_id,
                        "scope_type": scope_type,
                        "scope_id": scope_id,
                    },
                )
                return binding

    async def _assert_binding_management_allowed(
        self,
        actor: Subject,
        role: Role,
        scope_type: str,
        scope_id: str,
        config_id: str | None,
        *,
        context: AuthContext | None = None,
    ) -> None:
        resource_config_id = None if config_id == GLOBAL_SCOPE_ID else config_id
        resource = (
            Resource.instance(resource_config_id)
            if resource_config_id
            else Resource.named("identity", actor.id)
        )
        decision_context = context or AuthContext(
            subject=actor,
            source="dashboard",
            authenticated=True,
            config_id=resource_config_id,
        )
        action = "identity.manage"
        if role is Role.ROOT:
            action = "identity.root.write"
        elif role is Role.OPERATOR or scope_type == "global":
            action = "identity.operator.write"
        decision = await self.authorize(actor, action, resource, decision_context)
        if not decision.allowed:
            raise PermissionError("Authorization denied")
        if (
            role in {Role.ROOT, Role.OPERATOR, Role.INSTANCE_OPERATOR}
            or scope_type == "global"
        ):
            if not await self._has_global_root(actor.id):
                raise PermissionError("Authorization denied")
        if role not in {
            Role.ROOT,
            Role.OPERATOR,
            Role.INSTANCE_OPERATOR,
            Role.SESSION_OWNER,
            Role.SESSION_ADMIN,
            Role.MEMBER,
        }:
            raise PermissionError("Authorization denied")
        if scope_type == "session" and config_id is None:
            raise PermissionError("Authorization denied")

    async def _has_global_root(self, subject_id: str) -> bool:
        async with self._db.get_db() as session:
            query = select(AuthRoleBinding).where(
                col(AuthRoleBinding.subject_id) == subject_id,
                col(AuthRoleBinding.role) == Role.ROOT.value,
                col(AuthRoleBinding.scope_type) == "global",
                col(AuthRoleBinding.revoked_at).is_(None),
            )
            return (await session.execute(query)).scalar_one_or_none() is not None

    async def revoke_binding(
        self,
        *,
        actor: Subject,
        binding_id: str,
        context: AuthContext | None = None,
    ) -> bool:
        """Revoke one binding while preserving at least one active root."""

        async with self._binding_mutation_lock:
            async with self._db.get_db() as session:
                binding = (
                    await session.execute(
                        select(AuthRoleBinding).where(
                            col(AuthRoleBinding.binding_id) == binding_id
                        )
                    )
                ).scalar_one_or_none()
            if binding is None or binding.revoked_at is not None:
                return False
            await self._assert_binding_management_allowed(
                actor,
                Role(binding.role),
                binding.scope_type,
                binding.scope_id,
                binding.config_id,
                context=context,
            )
            # SQLite serializes writers. The local lock prevents two requests
            # in this runtime from both observing two roots before either
            # conditional revocation is committed.
            now = utc_now()
            async with self._db.get_db() as session:
                async with session.begin():
                    if binding.role == Role.ROOT.value:
                        roots = await session.execute(
                            select(AuthRoleBinding.binding_id).where(
                                col(AuthRoleBinding.role) == Role.ROOT.value,
                                col(AuthRoleBinding.scope_type) == "global",
                                col(AuthRoleBinding.revoked_at).is_(None),
                            )
                        )
                        if len(list(roots.scalars())) <= 1:
                            raise ValueError("Cannot revoke the last root binding")
                    result = await session.execute(
                        update(AuthRoleBinding)
                        .where(
                            col(AuthRoleBinding.binding_id) == binding_id,
                            col(AuthRoleBinding.revoked_at).is_(None),
                        )
                        .values(revoked_at=now, revoked_by=actor.id)
                    )
                    return bool(result.rowcount)

    async def list_bindings(
        self,
        *,
        subject_id: str | None = None,
        config_id: str | None = None,
        include_revoked: bool = False,
    ) -> list[AuthRoleBinding]:
        async with self._db.get_db() as session:
            query = select(AuthRoleBinding)
            if subject_id:
                query = query.where(col(AuthRoleBinding.subject_id) == subject_id)
            if config_id:
                query = query.where(col(AuthRoleBinding.config_id) == config_id)
            if not include_revoked:
                query = query.where(col(AuthRoleBinding.revoked_at).is_(None))
            return list(
                (
                    await session.execute(
                        query.order_by(col(AuthRoleBinding.created_at).desc())
                    )
                ).scalars()
            )

    async def list_audit(
        self, *, limit: int = 100, subject_id: str | None = None
    ) -> list[AuthAuditLog]:
        async with self._db.get_db() as session:
            query = select(AuthAuditLog)
            if subject_id:
                query = query.where(col(AuthAuditLog.subject_id) == subject_id)
            return list(
                (
                    await session.execute(
                        query.order_by(col(AuthAuditLog.timestamp).desc()).limit(
                            max(1, min(limit, 500))
                        )
                    )
                ).scalars()
            )

    async def purge_expired_audit(self, *, retention_days: int = 90) -> int:
        async with self._db.get_db() as session:
            async with session.begin():
                result = await session.execute(
                    delete(AuthAuditLog).where(
                        col(AuthAuditLog.timestamp)
                        < utc_now() - timedelta(days=max(1, retention_days))
                    )
                )
                return int(result.rowcount or 0)

    async def authorize(
        self, subject: Subject, action: str, resource: Resource, context: AuthContext
    ) -> Decision:
        """Authorize exactly one normalized action/resource/context tuple."""

        audit_id = str(uuid.uuid4())
        try:
            decision = await self._authorize(
                subject, action, resource, context, audit_id
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Authorization evaluation failed: %s", redact_sensitive_text(str(exc))
            )
            decision = Decision(
                False,
                subject,
                action,
                resource,
                None,
                "authorization_unavailable",
                audit_id=audit_id,
            )
        if (
            not decision.allowed
            or _requires_step_up(action, context)
            or action.startswith("identity.")
        ):
            self._audit(
                audit_id=audit_id,
                subject=subject,
                action=action,
                resource=resource,
                context=context,
                decision="allow" if decision.allowed else "deny",
                reason=decision.reason,
                effective_role=decision.effective_role,
            )
        return decision

    async def _authorize(
        self,
        subject: Subject,
        action: str,
        resource: Resource,
        context: AuthContext,
        audit_id: str,
    ) -> Decision:
        if action not in ACTIONS and not action.startswith("plugin:"):
            return Decision(
                False,
                subject,
                action,
                resource,
                None,
                "unknown_action",
                audit_id=audit_id,
            )
        if context.subject.id != subject.id:
            return Decision(
                False,
                subject,
                action,
                resource,
                None,
                "subject_context_mismatch",
                audit_id=audit_id,
            )
        if (
            resource.config_id
            and context.config_id
            and resource.config_id != context.config_id
        ):
            return Decision(
                False,
                subject,
                action,
                resource,
                None,
                "cross_config_resource",
                audit_id=audit_id,
            )
        if action.startswith("plugin:"):
            parts = action.split(":")
            if len(parts) != 3 or not all(parts):
                return Decision(
                    False,
                    subject,
                    action,
                    resource,
                    None,
                    "invalid_plugin_action",
                    audit_id=audit_id,
                )
            allowed_roles = _ACTION_ROLES["session.manage"]
        else:
            allowed_roles = _ACTION_ROLES.get(action)
            if allowed_roles is None:
                return Decision(
                    False,
                    subject,
                    action,
                    resource,
                    None,
                    "unknown_action",
                    audit_id=audit_id,
                )
        api_key_capability = subject.kind == "api-key" and api_key_scopes_allow_action(
            context.api_scopes, action
        )
        if subject.kind == "api-key" and not api_key_capability:
            return Decision(
                False,
                subject,
                action,
                resource,
                None,
                "api_key_scope_denied",
                audit_id=audit_id,
            )
        if not subject.authenticated and action not in {"provider.use", "session.read"}:
            return Decision(
                False,
                subject,
                action,
                resource,
                Role.GUEST,
                "unauthenticated",
                audit_id=audit_id,
            )
        role = await self._resolve_role(subject, resource, context)
        override_allowed = await self._policy_override_allows(action, resource, role)
        if (
            role not in allowed_roles
            and not api_key_capability
            and not override_allowed
        ):
            return Decision(
                False,
                subject,
                action,
                resource,
                role,
                "role_scope_denied",
                audit_id=audit_id,
            )
        if _requires_step_up(action, context):
            if context.source == "dashboard":
                if not await self._consume_step_up(subject, action, resource, context):
                    return Decision(
                        False,
                        subject,
                        action,
                        resource,
                        role,
                        "step_up_required",
                        requires_step_up=True,
                        audit_id=audit_id,
                    )
            elif not await self._consume_elevation(subject, action, resource, context):
                return Decision(
                    False,
                    subject,
                    action,
                    resource,
                    role,
                    "elevation_required",
                    requires_elevation=True,
                    audit_id=audit_id,
                )
        return Decision(
            True, subject, action, resource, role, "allowed", audit_id=audit_id
        )

    async def _policy_override_allows(
        self, action: str, resource: Resource, role: Role
    ) -> bool:
        """Evaluate only structured, narrow allow-list overrides."""

        now = utc_now()
        async with self._db.get_db() as session:
            result = await session.execute(
                select(AuthPolicyOverride).where(
                    col(AuthPolicyOverride.action) == action,
                    col(AuthPolicyOverride.enabled).is_(True),
                    (col(AuthPolicyOverride.expires_at).is_(None))
                    | (col(AuthPolicyOverride.expires_at) > now),
                    (col(AuthPolicyOverride.config_id).is_(None))
                    | (col(AuthPolicyOverride.config_id) == resource.config_id),
                )
            )
            for override in result.scalars():
                if override.resource_type != resource.type:
                    continue
                if override.resource_id and override.resource_id != resource.id:
                    continue
                if role.value in {str(item) for item in (override.allowed_roles or [])}:
                    return True
        return False

    async def _resolve_role(
        self, subject: Subject, resource: Resource, context: AuthContext
    ) -> Role:
        candidates = [subject.id]
        if (
            context.principal_subject_id
            and context.principal_subject_id not in candidates
        ):
            candidates.append(context.principal_subject_id)
        # ``admins_id`` was historically a raw adapter sender ID. It cannot be
        # reconstructed by parsing a normalized principal because platform
        # identifiers may contain separators. The adapter-provided value is
        # retained only in trusted event metadata for this migration lookup.
        legacy_sender_id = context.metadata.get("legacy_sender_id")
        if (
            subject.kind == "im"
            and resource.config_id
            and isinstance(legacy_sender_id, str)
            and legacy_sender_id
        ):
            candidates.append(
                Subject.legacy_admin(resource.config_id, legacy_sender_id).id
            )
        roles = [Role.MEMBER if subject.authenticated else Role.GUEST]
        now = utc_now()
        async with self._db.get_db() as session:
            bindings = await session.execute(
                select(AuthRoleBinding).where(
                    col(AuthRoleBinding.subject_id).in_(candidates),
                    col(AuthRoleBinding.revoked_at).is_(None),
                )
            )
            for binding in bindings.scalars():
                if binding.expires_at is None or binding.expires_at > now:
                    if self._binding_matches_resource(binding, resource):
                        roles.append(Role(binding.role))
            if resource.type == "session" and resource.umo and resource.config_id:
                fact = (
                    await session.execute(
                        select(AuthPlatformMembershipFact).where(
                            col(AuthPlatformMembershipFact.subject_id) == subject.id,
                            col(AuthPlatformMembershipFact.config_id)
                            == resource.config_id,
                            col(AuthPlatformMembershipFact.umo) == resource.umo,
                            col(AuthPlatformMembershipFact.expires_at) > now,
                        )
                    )
                ).scalar_one_or_none()
                if fact is not None:
                    roles.append(
                        Role.SESSION_OWNER
                        if fact.platform_role == "owner"
                        else Role.SESSION_ADMIN
                        if fact.platform_role == "admin"
                        else Role.MEMBER
                    )
        if resource.type == "session" and context.platform_member_role in {
            "owner",
            "admin",
        }:
            if (
                context.platform_role_expires_at is None
                or context.platform_role_expires_at > now
            ):
                roles.append(
                    Role.SESSION_OWNER
                    if context.platform_member_role == "owner"
                    else Role.SESSION_ADMIN
                )
        return max(roles, key=lambda candidate: ROLE_ORDER[candidate])

    @staticmethod
    def _binding_matches_resource(binding: AuthRoleBinding, resource: Resource) -> bool:
        if binding.scope_type == "global":
            return binding.role in {Role.ROOT.value, Role.OPERATOR.value}
        if binding.scope_type == "instance":
            return resource.config_id == binding.config_id == binding.scope_id
        if binding.scope_type == "session":
            return (
                resource.type == "session"
                and resource.id == binding.scope_id
                and resource.config_id == binding.config_id
            )
        return binding.scope_id == resource.id and (
            binding.config_id is None or binding.config_id == resource.config_id
        )

    async def issue_step_up(
        self,
        *,
        subject: Subject,
        dashboard_session_id: str,
        action: str,
        resource: Resource,
        context: AuthContext,
        verified_method: str,
        ttl_seconds: int = _STEP_UP_TTL_SECONDS,
    ) -> tuple[str, str]:
        """Issue a short-lived, one-time Dashboard credential after reauthentication."""

        if (
            context.source != "dashboard"
            or not _requires_step_up(action, context)
            or not 0 < ttl_seconds <= 900
        ):
            raise AuthorizationValueError("Invalid step-up request")
        credential_id, secret = str(uuid.uuid4()), secrets.token_urlsafe(32)
        record = AuthStepUpCredential(
            credential_id=credential_id,
            subject_id=subject.id,
            dashboard_session_id=dashboard_session_id,
            action=action,
            resource_id=resource.id,
            context_digest=context.digest_for(action, resource),
            token_hash=hashlib.sha256(secret.encode()).hexdigest(),
            verified_method=verified_method,
            expires_at=utc_now() + timedelta(seconds=ttl_seconds),
        )
        async with self._db.get_db() as session:
            async with session.begin():
                session.add(record)
        self._audit(
            audit_id=str(uuid.uuid4()),
            subject=subject,
            action=action,
            resource=resource,
            context=context,
            decision="allow",
            reason="step_up_issued",
            step_up_id=credential_id,
        )
        return credential_id, f"{credential_id}.{secret}"

    async def _consume_step_up(
        self, subject: Subject, action: str, resource: Resource, context: AuthContext
    ) -> bool:
        token = context.step_up_token
        session_id = context.metadata.get("dashboard_session_id")
        if (
            not isinstance(token, str)
            or "." not in token
            or not isinstance(session_id, str)
        ):
            return False
        credential_id, secret = token.split(".", 1)
        now = utc_now()
        async with self._db.get_db() as session:
            async with session.begin():
                result = await session.execute(
                    update(AuthStepUpCredential)
                    .where(
                        col(AuthStepUpCredential.credential_id) == credential_id,
                        col(AuthStepUpCredential.subject_id) == subject.id,
                        col(AuthStepUpCredential.dashboard_session_id) == session_id,
                        col(AuthStepUpCredential.action) == action,
                        col(AuthStepUpCredential.resource_id) == resource.id,
                        col(AuthStepUpCredential.context_digest)
                        == context.digest_for(action, resource),
                        col(AuthStepUpCredential.token_hash)
                        == hashlib.sha256(secret.encode()).hexdigest(),
                        col(AuthStepUpCredential.expires_at) > now,
                        col(AuthStepUpCredential.consumed_at).is_(None),
                    )
                    .values(consumed_at=now)
                )
                return bool(result.rowcount)

    async def request_elevation(
        self, decision: Decision, context: AuthContext, *, approval_channel: str
    ) -> tuple[str, str]:
        """Create one private/dashboard/WebChat elevation request without retaining its nonce."""

        if not decision.requires_elevation or decision.effective_role not in {
            Role.SESSION_ADMIN,
            Role.SESSION_OWNER,
            Role.INSTANCE_OPERATOR,
            Role.OPERATOR,
            Role.ROOT,
        }:
            raise PermissionError("Elevation unavailable")
        if approval_channel not in {"private", "dashboard", "webchat"}:
            raise AuthorizationValueError("Unsafe elevation channel")
        request_id, nonce = str(uuid.uuid4()), secrets.token_urlsafe(32)
        record = AuthElevationRequest(
            request_id=request_id,
            subject_id=decision.subject.id,
            requested_action=decision.action,
            resource_id=decision.resource.id,
            config_id=decision.resource.config_id,
            requested_from=context.source,
            approval_channel=approval_channel,
            nonce_hash=hashlib.sha256(nonce.encode()).hexdigest(),
            request_context_digest=context.digest_for(
                decision.action, decision.resource
            ),
            expires_at=utc_now() + timedelta(seconds=_ELEVATION_TTL_SECONDS),
        )
        async with self._db.get_db() as session:
            async with session.begin():
                session.add(record)
        return request_id, nonce

    async def approve_elevation(
        self, *, request_id: str, nonce: str, approver: Subject, context: AuthContext
    ) -> bool:
        """Approve a request with a conditional update to prevent racing approvals."""

        now = utc_now()
        # Resolve and authorize outside the write transaction. _authorize()
        # owns its own short-lived DB session, and nesting it here can lock
        # SQLite while a long-running transaction is open.
        async with self._db.get_db() as session:
            request = (
                await session.execute(
                    select(AuthElevationRequest).where(
                        col(AuthElevationRequest.request_id) == request_id
                    )
                )
            ).scalar_one_or_none()
        if (
            request is None
            or request.status != "pending"
            or request.expires_at <= now
            or request.subject_id == approver.id
            or request.nonce_hash != hashlib.sha256(nonce.encode()).hexdigest()
        ):
            return False
        resource = self._resource_from_id(request.resource_id, request.config_id)
        decision = await self._authorize(
            approver, request.requested_action, resource, context, str(uuid.uuid4())
        )
        if not decision.allowed and decision.reason not in {
            "step_up_required",
            "elevation_required",
        }:
            return False
        async with self._db.get_db() as session:
            async with session.begin():
                result = await session.execute(
                    update(AuthElevationRequest)
                    .where(
                        col(AuthElevationRequest.request_id) == request_id,
                        col(AuthElevationRequest.status) == "pending",
                        col(AuthElevationRequest.expires_at) > now,
                    )
                    .values(
                        status="approved",
                        approver_subject_id=approver.id,
                        approved_at=now,
                    )
                )
                return bool(result.rowcount)

    async def _consume_elevation(
        self, subject: Subject, action: str, resource: Resource, context: AuthContext
    ) -> bool:
        token = context.elevation_token
        if not isinstance(token, str) or "." not in token:
            return False
        request_id, nonce = token.split(".", 1)
        now = utc_now()
        async with self._db.get_db() as session:
            async with session.begin():
                result = await session.execute(
                    update(AuthElevationRequest)
                    .where(
                        col(AuthElevationRequest.request_id) == request_id,
                        col(AuthElevationRequest.subject_id) == subject.id,
                        col(AuthElevationRequest.requested_action) == action,
                        col(AuthElevationRequest.resource_id) == resource.id,
                        col(AuthElevationRequest.request_context_digest)
                        == context.digest_for(action, resource),
                        col(AuthElevationRequest.nonce_hash)
                        == hashlib.sha256(nonce.encode()).hexdigest(),
                        col(AuthElevationRequest.status) == "approved",
                        col(AuthElevationRequest.expires_at) > now,
                    )
                    .values(status="consumed", consumed_at=now)
                )
                return bool(result.rowcount)

    @staticmethod
    def _resource_from_id(resource_id: str, config_id: str | None) -> Resource:
        if resource_id.startswith("session:v1:"):
            parsed_config_id, umo = parse_canonical_session_resource(resource_id)
            return Resource.session(parsed_config_id, umo)
        return Resource(type="resource", id=resource_id, config_id=config_id)
