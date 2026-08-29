"""Runtime-owned authorization, audit, and Dashboard step-up service."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import update
from sqlmodel import col, delete, select

from astrbot import logger
from astrbot.core.auth.models import (
    GLOBAL_SCOPE_ID,
    HIGH_RISK_ACTIONS,
    ROLE_ORDER,
    WEBCHAT_INSTANCE_TOOL_ACTIONS,
    AuthContext,
    AuthorizationValueError,
    Decision,
    Resource,
    Role,
    Subject,
    canonical_session_resource,
    parse_canonical_session_resource,
    restore_capability_config_id,
    utc_now,
)
from astrbot.core.auth.registry import ActionPolicy, policy_for
from astrbot.core.db.po import (
    AuthAuditLog,
    AuthCapability,
    AuthPlatformMembershipFact,
    AuthPolicyOverride,
    AuthRoleBinding,
    AuthStepUpCredential,
    DashboardAccount,
)
from astrbot.core.db.protocols import ApiKeyStore, DatabaseSessionStore
from astrbot.core.utils.error_redaction import redact_sensitive_text

_AUDIT_QUEUE_SIZE = 2048
_STEP_UP_TTL_SECONDS = 300
_SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "auth_token",
        "authorization",
        "jwt",
        "jwt_token",
        "token",
        "api_key",
        "key",
        "nonce",
        "password",
        "refresh_token",
        "session_id",
        "webchat_step_up_tokens",
        "_webchat_step_up_consumed",
        "credential",
        "secret",
        "message",
        "content",
    }
)


def _missing_policy_context(policy: ActionPolicy, context: AuthContext) -> str | None:
    required = policy.required_context
    if "source" in required and not context.source:
        return "missing_context_source"
    if (
        "config" in required
        and context.source in {"im", "webchat"}
        and not context.config_id
    ):
        return "missing_context_config"
    if (
        "origin_session" in required
        and context.source in {"im", "webchat"}
        and not context.origin_session_resource_id
    ):
        return "missing_context_origin_session"
    return None


def _webchat_step_up_binding_resource(
    action: str, resource: Resource, context: AuthContext
) -> Resource:
    """Bind WebChat tool proofs to the current session, not a tool name.

    Agent tool names are implementation details and a single run may invoke
    several tools.  The proof is still exact-action and exact-session-bound;
    the session resource is the trusted parent for all tool/file/MCP resources
    reached from this event.
    """

    if (
        context.source != "webchat"
        or action not in WEBCHAT_INSTANCE_TOOL_ACTIONS
        or resource.type not in {"session", "tool", "file", "mcp"}
    ):
        return resource
    origin = AuthorizationService._origin_session_resource(context)
    if origin is None or resource.config_id != origin.config_id:
        return resource
    return origin


def _webchat_step_up_cached(context: AuthContext, action: str) -> str | None:
    """Return a proof consumed earlier in this trusted event/run, if any."""

    cached = context.metadata.get("_webchat_step_up_consumed")
    if not isinstance(cached, dict):
        return None
    entry = cached.get(action)
    if isinstance(entry, str):
        # Do not grant an unbounded legacy cache entry.  Entries written by
        # the current implementation always carry an explicit expiry.
        cached.pop(action, None)
        return None
    if not isinstance(entry, dict):
        return None
    credential_id = entry.get("credential_id")
    expires_at = entry.get("expires_at")
    if (
        not isinstance(credential_id, str)
        or not isinstance(expires_at, int | float)
        or expires_at <= utc_now().timestamp()
    ):
        cached.pop(action, None)
        return None
    return credential_id


def _control_plane_bindings_apply(subject: Subject, context: AuthContext) -> bool:
    """Return whether global root/operator bindings apply in this context."""

    if context.source == "dashboard":
        return True
    return (
        context.source == "webchat"
        and subject.kind == "dashboard-account"
        and context.authenticated
    )


def _requires_step_up(action: str, resource: Resource, context: AuthContext) -> bool:
    """Return whether a fixed high-risk capability needs fresh proof."""

    # A session owner can manage members in the session from which the request
    # originated. This narrow IM path cannot affect another session, instance,
    # or global identity. Dashboard mutations always require fresh proof,
    # including mutations of session bindings.
    if (
        action == "identity.manage"
        and resource.type == "session"
        and context.source != "dashboard"
        and context.origin_session_resource_id == resource.id
    ):
        return False
    if action == "platform.manage" and resource.type == "bot":
        return True
    if (
        action == "session.assign"
        and resource.type == "session"
        and context.origin_session_resource_id != resource.id
    ):
        return True
    return action in HIGH_RISK_ACTIONS


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
        from astrbot.core.auth.preflight import inspect_authorization_upgrade

        report = await inspect_authorization_upgrade(self._db)
        if not report.ok:
            raise RuntimeError(
                "Authorization upgrade preflight failed: "
                + ",".join(report.blocking[:8])
            )
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

    def _audit_record(
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
        metadata: Mapping[str, Any] | None = None,
    ) -> AuthAuditLog:
        return AuthAuditLog(
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
            outcome=decision,
            metadata_json=_sanitize_metadata({**context.metadata, **(metadata or {})}),
        )

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
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        """Queue a redacted audit record and report whether it was retained."""

        record = self._audit_record(
            audit_id=audit_id,
            subject=subject,
            action=action,
            resource=resource,
            context=context,
            decision=decision,
            reason=reason,
            effective_role=effective_role,
            step_up_id=step_up_id,
            metadata=metadata,
        )
        try:
            self._audit_queue.put_nowait(record)
            return True
        except asyncio.QueueFull:
            logger.error("Authorization audit queue full; event id=%s", audit_id)
            return False

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
        Subject.from_id(subject_id)
        if expires_at is not None:
            if not isinstance(expires_at, datetime):
                raise AuthorizationValueError("Invalid binding expiry")
            expires_at = (
                expires_at.replace(tzinfo=UTC)
                if expires_at.tzinfo is None
                else expires_at.astimezone(UTC)
            )
        valid_scope_roles = {
            "global": {Role.ROOT, Role.OPERATOR},
            "instance": {Role.INSTANCE_OPERATOR},
            "session": {Role.SESSION_OWNER, Role.SESSION_ADMIN, Role.MEMBER},
            "resource": {Role.MEMBER},
        }
        if role not in valid_scope_roles[scope_type]:
            raise AuthorizationValueError("Role is not valid for binding scope")
        if scope_type == "global" and scope_id != "global":
            raise AuthorizationValueError("Invalid global binding scope")
        if scope_type == "global":
            config_id = GLOBAL_SCOPE_ID
        if scope_type == "instance" and (not config_id or scope_id != config_id):
            raise AuthorizationValueError("Invalid instance binding scope")
        if scope_type == "session":
            scope_id = self._normalize_session_binding_scope(config_id, scope_id)
        if role in {Role.ROOT, Role.OPERATOR}:
            await self._require_active_dashboard_account(subject_id)
        management_decision: Decision | None = None
        if enforce_actor:
            management_decision = await self._assert_binding_management_allowed(
                actor,
                subject_id,
                role,
                scope_type,
                scope_id,
                config_id,
                context=context,
            )
        async with self._binding_mutation_lock:
            async with self._db.get_db() as session:
                async with session.begin():
                    if role in {Role.ROOT, Role.OPERATOR}:
                        account_id = subject_id.removeprefix("dashboard-account:")
                        account = (
                            await session.execute(
                                select(DashboardAccount).where(
                                    col(DashboardAccount.account_id) == account_id,
                                    col(DashboardAccount.is_active).is_(True),
                                )
                            )
                        ).scalar_one_or_none()
                        if account is None:
                            raise AuthorizationValueError(
                                "Global control-plane roles require an active Dashboard account"
                            )
                    if not config_id:
                        raise AuthorizationValueError("Binding requires a config id")
                    binding = (
                        await session.execute(
                            select(AuthRoleBinding).where(
                                col(AuthRoleBinding.subject_id) == subject_id,
                                col(AuthRoleBinding.scope_type) == scope_type,
                                col(AuthRoleBinding.scope_id) == scope_id,
                                col(AuthRoleBinding.config_id) == config_id,
                            )
                        )
                    ).scalar_one_or_none()
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
                        binding.role = role.value
                        binding.source = source
                        binding.expires_at = expires_at
                        binding.revoked_at = None
                        binding.revoked_by = None
                        binding.metadata_json = _sanitize_metadata(metadata or {})
                    await session.flush()
                    audit_context = context or AuthContext(
                        subject=actor,
                        source="system",
                        authenticated=True,
                        config_id=(None if config_id == GLOBAL_SCOPE_ID else config_id),
                    )
                    session.add(
                        self._audit_record(
                            audit_id=str(uuid.uuid4()),
                            subject=actor,
                            action="identity.manage",
                            resource=self._binding_resource(
                                subject_id, scope_type, scope_id, config_id
                            ),
                            context=audit_context,
                            decision="allow",
                            reason="binding_granted",
                            effective_role=role,
                            step_up_id=(
                                management_decision.step_up_id
                                if isinstance(management_decision, Decision)
                                else None
                            ),
                            metadata={
                                "target_subject_id": subject_id,
                                "scope_type": scope_type,
                                "scope_id": scope_id,
                            },
                        )
                    )
                    return binding

    @staticmethod
    def _normalize_session_binding_scope(config_id: str | None, scope_id: str) -> str:
        """Store every session binding in the one canonical resource format."""

        if not config_id:
            raise AuthorizationValueError("Session bindings require a config id")
        try:
            scoped_config_id, _ = parse_canonical_session_resource(scope_id)
        except AuthorizationValueError:
            return canonical_session_resource(config_id, scope_id)
        if scoped_config_id != config_id:
            raise AuthorizationValueError("Session binding config mismatch")
        return scope_id

    @staticmethod
    def _binding_resource(
        subject_id: str,
        scope_type: str,
        scope_id: str,
        config_id: str | None,
    ) -> Resource:
        """Return the exact resource whose binding is being changed."""

        if scope_type == "session":
            canonical_scope_id = AuthorizationService._normalize_session_binding_scope(
                config_id, scope_id
            )
            resolved_config_id, umo = parse_canonical_session_resource(
                canonical_scope_id
            )
            if resolved_config_id != config_id:
                raise AuthorizationValueError("Session binding config mismatch")
            return Resource.session(resolved_config_id, umo)
        if scope_type == "instance":
            if not config_id:
                raise AuthorizationValueError("Instance bindings require a config id")
            return Resource.instance(config_id)
        return Resource.named(
            "identity",
            subject_id,
            config_id=None if config_id == GLOBAL_SCOPE_ID else config_id,
        )

    @staticmethod
    def _binding_failure_resource(binding_id: str) -> Resource:
        """Return a non-enumerating audit resource for an invalid binding ID."""

        binding_digest = hashlib.sha256(binding_id.encode()).hexdigest()
        return Resource.named("identity", f"binding-{binding_digest}")

    @staticmethod
    def _binding_audit_context(
        actor: Subject, context: AuthContext | None, config_id: str | None = None
    ) -> AuthContext:
        """Use the caller context or a safe internal context for mutation audit."""

        if context is not None:
            return context
        return AuthContext(
            subject=actor,
            source="system",
            authenticated=True,
            config_id=None if config_id == GLOBAL_SCOPE_ID else config_id,
        )

    async def _require_active_dashboard_account(self, subject_id: str) -> None:
        """Limit global control-plane roles to active Dashboard identities."""

        prefix = "dashboard-account:"
        if not subject_id.startswith(prefix):
            raise AuthorizationValueError(
                "Global control-plane roles require a Dashboard account"
            )
        account_id = subject_id.removeprefix(prefix)
        Subject.dashboard_account(account_id)
        async with self._db.get_db() as session:
            account = (
                await session.execute(
                    select(DashboardAccount).where(
                        col(DashboardAccount.account_id) == account_id,
                        col(DashboardAccount.is_active).is_(True),
                    )
                )
            ).scalar_one_or_none()
        if account is None:
            raise AuthorizationValueError(
                "Global control-plane roles require an active Dashboard account"
            )

    async def _assert_binding_management_allowed(
        self,
        actor: Subject,
        subject_id: str,
        role: Role,
        scope_type: str,
        scope_id: str,
        config_id: str | None,
        *,
        context: AuthContext | None = None,
    ) -> Decision:
        resource_config_id = None if config_id == GLOBAL_SCOPE_ID else config_id
        resource = self._binding_resource(subject_id, scope_type, scope_id, config_id)
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
        await self._validate_binding_management_decision(
            actor=actor,
            role=role,
            scope_type=scope_type,
            config_id=config_id,
            resource=resource,
            context=decision_context,
            decision=decision,
        )
        return decision

    async def _validate_binding_management_decision(
        self,
        *,
        actor: Subject,
        role: Role,
        scope_type: str,
        config_id: str | None,
        resource: Resource,
        context: AuthContext,
        decision: Decision,
    ) -> None:
        """Apply role-delegation rules after a binding mutation is authorized."""

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
        if decision.effective_role is Role.SESSION_OWNER and (
            scope_type != "session"
            or role not in {Role.SESSION_ADMIN, Role.MEMBER}
            or context.origin_session_resource_id != resource.id
        ):
            # A current session owner may manage members, but cannot delegate
            # ownership or use a session-scoped fact to alter another scope.
            raise PermissionError("Authorization denied")

    @staticmethod
    def _normalize_binding_ids(binding_ids: Iterable[str]) -> tuple[str, ...]:
        """Return a bounded, deterministic binding ID set for a batch action."""

        provided = tuple(binding_ids)
        normalized = tuple(sorted({item for item in provided if isinstance(item, str)}))
        if not 1 <= len(normalized) <= 100:
            raise AuthorizationValueError(
                "A batch must contain between 1 and 100 bindings"
            )
        if any(not item or len(item) > 128 for item in normalized):
            raise AuthorizationValueError("Invalid binding id")
        if len(normalized) != len(provided):
            raise AuthorizationValueError("Binding IDs must be unique strings")
        return normalized

    async def _active_bindings_for_ids(
        self, binding_ids: Iterable[str]
    ) -> list[AuthRoleBinding]:
        """Load exactly the requested active bindings or fail without enumeration."""

        binding_id_set = self._normalize_binding_ids(binding_ids)
        async with self._db.get_db() as session:
            result = await session.execute(
                select(AuthRoleBinding).where(
                    col(AuthRoleBinding.binding_id).in_(binding_id_set),
                    col(AuthRoleBinding.revoked_at).is_(None),
                )
            )
            found = {binding.binding_id: binding for binding in result.scalars()}
        if len(found) != len(binding_id_set):
            raise AuthorizationValueError("Binding batch is no longer current")
        return [found[binding_id] for binding_id in binding_id_set]

    @staticmethod
    def _binding_batch_resource(bindings: Iterable[AuthRoleBinding]) -> Resource:
        """Bind a batch credential to its exact active binding snapshots."""

        snapshots = [
            {
                "binding_id": binding.binding_id,
                "subject_id": binding.subject_id,
                "role": binding.role,
                "scope_type": binding.scope_type,
                "scope_id": binding.scope_id,
                "config_id": binding.config_id,
                "expires_at": binding.expires_at.isoformat()
                if binding.expires_at is not None
                else None,
                "revoked_at": binding.revoked_at.isoformat()
                if binding.revoked_at is not None
                else None,
            }
            for binding in bindings
        ]
        if not snapshots:
            raise AuthorizationValueError("Binding batch is empty")
        config_ids = {
            str(item["config_id"])
            for item in snapshots
            if item["config_id"] not in {None, GLOBAL_SCOPE_ID}
        }
        has_global_scope = any(
            item["config_id"] in {None, GLOBAL_SCOPE_ID} for item in snapshots
        )
        config_id = (
            next(iter(config_ids))
            if len(config_ids) == 1 and not has_global_scope
            else None
        )
        batch_digest = hashlib.sha256(repr(snapshots).encode("utf-8")).hexdigest()
        return Resource.named(
            "identity-batch", f"revoke-{batch_digest}", config_id=config_id
        )

    async def binding_revocation_batch_resource(
        self, binding_ids: Iterable[str]
    ) -> Resource:
        """Resolve the one resource that represents an exact revoke batch."""

        return self._binding_batch_resource(
            await self._active_bindings_for_ids(binding_ids)
        )

    async def _has_global_root(self, subject_id: str) -> bool:
        now = utc_now()
        async with self._db.get_db() as session:
            query = select(AuthRoleBinding).where(
                col(AuthRoleBinding.subject_id) == subject_id,
                col(AuthRoleBinding.role) == Role.ROOT.value,
                col(AuthRoleBinding.scope_type) == "global",
                col(AuthRoleBinding.scope_id) == "global",
                col(AuthRoleBinding.config_id) == GLOBAL_SCOPE_ID,
                col(AuthRoleBinding.revoked_at).is_(None),
                (col(AuthRoleBinding.expires_at).is_(None))
                | (col(AuthRoleBinding.expires_at) > now),
            )
            binding = (await session.execute(query)).scalar_one_or_none()
            if binding is None or not subject_id.startswith("dashboard-account:"):
                return False
            account_id = subject_id.removeprefix("dashboard-account:")
            account = (
                await session.execute(
                    select(DashboardAccount.account_id).where(
                        col(DashboardAccount.account_id) == account_id,
                        col(DashboardAccount.is_active).is_(True),
                    )
                )
            ).scalar_one_or_none()
            return account is not None

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
                self._audit(
                    audit_id=str(uuid.uuid4()),
                    subject=actor,
                    action="identity.manage",
                    resource=self._binding_failure_resource(binding_id),
                    context=self._binding_audit_context(actor, context),
                    decision="deny",
                    reason="binding_not_found",
                    metadata={
                        "binding_id_digest": hashlib.sha256(
                            binding_id.encode()
                        ).hexdigest()
                    },
                )
                return False
            try:
                binding_role = Role(binding.role)
            except ValueError:
                self._audit(
                    audit_id=str(uuid.uuid4()),
                    subject=actor,
                    action="identity.manage",
                    resource=self._binding_failure_resource(binding_id),
                    context=self._binding_audit_context(
                        actor, context, binding.config_id
                    ),
                    decision="deny",
                    reason="invalid_binding_role",
                    metadata={"binding_id": binding.binding_id},
                )
                return False
            management_decision = await self._assert_binding_management_allowed(
                actor,
                binding.subject_id,
                binding_role,
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
                        now = utc_now()
                        roots = await session.execute(
                            select(AuthRoleBinding.binding_id).where(
                                col(AuthRoleBinding.role) == Role.ROOT.value,
                                col(AuthRoleBinding.scope_type) == "global",
                                col(AuthRoleBinding.scope_id) == "global",
                                col(AuthRoleBinding.config_id) == GLOBAL_SCOPE_ID,
                                col(AuthRoleBinding.revoked_at).is_(None),
                                (col(AuthRoleBinding.expires_at).is_(None))
                                | (col(AuthRoleBinding.expires_at) > now),
                            )
                        )
                        root_ids = list(roots.scalars())
                        active_accounts = set(
                            (
                                await session.execute(
                                    select(DashboardAccount.account_id).where(
                                        col(DashboardAccount.is_active).is_(True)
                                    )
                                )
                            ).scalars()
                        )
                        active_root_count = sum(
                            binding_subject.removeprefix("dashboard-account:")
                            in active_accounts
                            for binding_subject in (
                                (
                                    await session.execute(
                                        select(AuthRoleBinding.subject_id).where(
                                            col(AuthRoleBinding.binding_id).in_(
                                                root_ids
                                            )
                                        )
                                    )
                                ).scalars()
                            )
                        )
                        if active_root_count <= 1:
                            self._audit(
                                audit_id=str(uuid.uuid4()),
                                subject=actor,
                                action="identity.root.write",
                                resource=self._binding_resource(
                                    binding.subject_id,
                                    binding.scope_type,
                                    binding.scope_id,
                                    binding.config_id,
                                ),
                                context=self._binding_audit_context(
                                    actor, context, binding.config_id
                                ),
                                decision="deny",
                                reason="last_root_protected",
                                effective_role=Role.ROOT,
                                step_up_id=(
                                    management_decision.step_up_id
                                    if isinstance(management_decision, Decision)
                                    else None
                                ),
                                metadata={"binding_id": binding.binding_id},
                            )
                            raise ValueError("Cannot revoke the last root binding")
                    result = await session.execute(
                        update(AuthRoleBinding)
                        .where(
                            col(AuthRoleBinding.binding_id) == binding_id,
                            col(AuthRoleBinding.revoked_at).is_(None),
                        )
                        .values(revoked_at=now, revoked_by=actor.id)
                    )
                    revoked = bool(getattr(result, "rowcount", 0))
                    if revoked:
                        audit_context = self._binding_audit_context(
                            actor, context, binding.config_id
                        )
                        session.add(
                            self._audit_record(
                                audit_id=str(uuid.uuid4()),
                                subject=actor,
                                action="identity.manage",
                                resource=self._binding_resource(
                                    binding.subject_id,
                                    binding.scope_type,
                                    binding.scope_id,
                                    binding.config_id,
                                ),
                                context=audit_context,
                                decision="allow",
                                reason="binding_revoked",
                                effective_role=binding_role,
                                step_up_id=(
                                    management_decision.step_up_id
                                    if isinstance(management_decision, Decision)
                                    else None
                                ),
                                metadata={"binding_id": binding.binding_id},
                            )
                        )
                    return revoked

    async def revoke_bindings(
        self,
        *,
        actor: Subject,
        binding_ids: Iterable[str],
        context: AuthContext | None = None,
    ) -> int:
        """Atomically revoke an exact, step-up-bound set of active bindings."""

        async with self._binding_mutation_lock:
            bindings = await self._active_bindings_for_ids(binding_ids)
            batch_resource = self._binding_batch_resource(bindings)
            decision_context = context or AuthContext(
                subject=actor,
                source="dashboard",
                authenticated=True,
                config_id=batch_resource.config_id,
            )
            decision = await self.authorize(
                actor, "identity.manage", batch_resource, decision_context
            )
            if not decision.allowed:
                raise PermissionError("Authorization denied")
            binding_roles: dict[str, Role] = {}
            for binding in bindings:
                try:
                    binding_role = Role(binding.role)
                except ValueError as exc:
                    raise AuthorizationValueError("Invalid binding role") from exc
                binding_resource = self._binding_resource(
                    binding.subject_id,
                    binding.scope_type,
                    binding.scope_id,
                    binding.config_id,
                )
                await self._validate_binding_management_decision(
                    actor=actor,
                    role=binding_role,
                    scope_type=binding.scope_type,
                    config_id=binding.config_id,
                    resource=binding_resource,
                    context=decision_context,
                    decision=decision,
                )
                binding_roles[binding.binding_id] = binding_role

            now = utc_now()
            binding_id_set = tuple(binding_roles)
            async with self._db.get_db() as session:
                async with session.begin():
                    selected_root_ids = {
                        binding.binding_id
                        for binding in bindings
                        if binding.role == Role.ROOT.value
                    }
                    if selected_root_ids:
                        roots = await session.execute(
                            select(AuthRoleBinding.binding_id).where(
                                col(AuthRoleBinding.role) == Role.ROOT.value,
                                col(AuthRoleBinding.scope_type) == "global",
                                col(AuthRoleBinding.scope_id) == "global",
                                col(AuthRoleBinding.config_id) == GLOBAL_SCOPE_ID,
                                col(AuthRoleBinding.revoked_at).is_(None),
                                (col(AuthRoleBinding.expires_at).is_(None))
                                | (col(AuthRoleBinding.expires_at) > now),
                            )
                        )
                        root_ids = list(roots.scalars())
                        active_accounts = set(
                            (
                                await session.execute(
                                    select(DashboardAccount.account_id).where(
                                        col(DashboardAccount.is_active).is_(True)
                                    )
                                )
                            ).scalars()
                        )
                        root_subjects = (
                            await session.execute(
                                select(
                                    AuthRoleBinding.binding_id,
                                    AuthRoleBinding.subject_id,
                                ).where(col(AuthRoleBinding.binding_id).in_(root_ids))
                            )
                        ).all()
                        remaining_root_count = sum(
                            binding_id not in selected_root_ids
                            and subject_id.removeprefix("dashboard-account:")
                            in active_accounts
                            for binding_id, subject_id in root_subjects
                        )
                        if remaining_root_count < 1:
                            self._audit(
                                audit_id=str(uuid.uuid4()),
                                subject=actor,
                                action="identity.root.write",
                                resource=batch_resource,
                                context=decision_context,
                                decision="deny",
                                reason="last_root_protected",
                                effective_role=Role.ROOT,
                                step_up_id=decision.step_up_id,
                                metadata={"binding_count": len(binding_id_set)},
                            )
                            raise ValueError("Cannot revoke the last root binding")
                    result = await session.execute(
                        update(AuthRoleBinding)
                        .where(
                            col(AuthRoleBinding.binding_id).in_(binding_id_set),
                            col(AuthRoleBinding.revoked_at).is_(None),
                        )
                        .values(revoked_at=now, revoked_by=actor.id)
                    )
                    if getattr(result, "rowcount", 0) != len(binding_id_set):
                        raise AuthorizationValueError(
                            "Binding batch is no longer current"
                        )
                    for binding in bindings:
                        session.add(
                            self._audit_record(
                                audit_id=str(uuid.uuid4()),
                                subject=actor,
                                action="identity.manage",
                                resource=self._binding_resource(
                                    binding.subject_id,
                                    binding.scope_type,
                                    binding.scope_id,
                                    binding.config_id,
                                ),
                                context=decision_context,
                                decision="allow",
                                reason="binding_revoked",
                                effective_role=binding_roles[binding.binding_id],
                                step_up_id=decision.step_up_id,
                                metadata={
                                    "binding_id": binding.binding_id,
                                    "batch_size": len(binding_id_set),
                                },
                            )
                        )
                    return len(binding_id_set)

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
                return int(getattr(result, "rowcount", 0) or 0)

    async def authorize(
        self, subject: Subject, action: str, resource: Resource, context: AuthContext
    ) -> Decision:
        """Authorize exactly one normalized action/resource/context tuple."""

        context = self._resource_scoped_dashboard_context(context, resource)
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
        needs_audit = (
            not decision.allowed
            or _requires_step_up(action, resource, context)
            or action.startswith("identity.")
        )
        if needs_audit:
            audit_written = self._audit(
                audit_id=audit_id,
                subject=subject,
                action=action,
                resource=resource,
                context=context,
                decision="allow" if decision.allowed else "deny",
                reason=decision.reason,
                effective_role=decision.effective_role,
                step_up_id=decision.step_up_id,
            )
            if decision.allowed and not audit_written:
                return Decision(
                    False,
                    subject,
                    action,
                    resource,
                    decision.effective_role,
                    "audit_unavailable",
                    audit_id=audit_id,
                )
        return decision

    @staticmethod
    def _resource_scoped_dashboard_context(
        context: AuthContext, resource: Resource
    ) -> AuthContext:
        """Add a trusted resource config scope to an unscoped Dashboard context.

        Dashboard principals start unscoped, while routes resolve the actual
        protected resource.  Step-up credentials include the context scope in
        their digest, so issuance and consumption must derive the same scope
        from that trusted resource.  Do not replace an explicit context scope:
        the normal cross-config check must still reject a mismatch.
        """

        if (
            context.source != "dashboard"
            or context.config_id is not None
            or resource.config_id is None
        ):
            return context
        return replace(context, config_id=resource.config_id)

    async def grant_capability(
        self,
        *,
        subject: Subject,
        action: str,
        resource: Resource,
        created_by: str | None = None,
        expires_at=None,
    ) -> AuthCapability:
        if subject.kind != "api-key":
            raise AuthorizationValueError("Capabilities are only issued to API keys")
        if action in HIGH_RISK_ACTIONS:
            raise AuthorizationValueError(
                "High-risk actions cannot be granted to API keys"
            )
        policy = policy_for(action)
        if policy is None:
            raise AuthorizationValueError("Unknown action")
        return await cast(ApiKeyStore, self._db).upsert_capability(
            subject_id=subject.id,
            action=action,
            resource_type=resource.type,
            resource_id=resource.id,
            config_id=resource.config_id,
            created_by=created_by,
            expires_at=expires_at,
        )

    async def _capability_allows(
        self, subject: Subject, action: str, resource: Resource
    ) -> bool:
        if action in HIGH_RISK_ACTIONS:
            return False
        now = utc_now()
        async with self._db.get_db() as session:
            result = await session.execute(
                select(AuthCapability).where(
                    col(AuthCapability.subject_id) == subject.id,
                    col(AuthCapability.action) == action,
                    col(AuthCapability.revoked_at).is_(None),
                )
            )
            for capability in result.scalars():
                if capability.expires_at is not None and capability.expires_at <= now:
                    continue
                if capability.resource_type != resource.type:
                    continue
                if capability.resource_id != resource.id:
                    continue
                capability_config_id = restore_capability_config_id(
                    capability.config_id
                )
                if (
                    capability_config_id is not None
                    and resource.config_id is not None
                    and capability_config_id != resource.config_id
                ):
                    continue
                return True
        return False

    async def _authorize(
        self,
        subject: Subject,
        action: str,
        resource: Resource,
        context: AuthContext,
        audit_id: str,
    ) -> Decision:
        from astrbot.core.auth.relationships import (
            evaluate_relations,
            tuples_from_roles,
        )

        policy = policy_for(action)
        if policy is None:
            return Decision(
                False,
                subject,
                action,
                resource,
                None,
                "unknown_action",
                audit_id=audit_id,
            )
        if resource.type not in policy.resource_types:
            return Decision(
                False,
                subject,
                action,
                resource,
                None,
                "resource_type_denied",
                audit_id=audit_id,
            )
        missing_context = _missing_policy_context(policy, context)
        if missing_context is not None:
            return Decision(
                False,
                subject,
                action,
                resource,
                None,
                missing_context,
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
        if (
            context.origin_session_resource_id is not None
            and resource.type == "session"
            and resource.id != context.origin_session_resource_id
        ):
            return Decision(
                False,
                subject,
                action,
                resource,
                None,
                "cross_session_resource",
                audit_id=audit_id,
            )
        if subject.kind == "api-key" or context.source == "api_key":
            capability_grant = await self._capability_allows(subject, action, resource)
            if not capability_grant:
                return Decision(
                    False,
                    subject,
                    action,
                    resource,
                    None,
                    "api_key_capability_denied",
                    audit_id=audit_id,
                )
            return Decision(
                True,
                subject,
                action,
                resource,
                None,
                "allowed",
                audit_id=audit_id,
                matched_relations=("capability",),
                relation_sources=("api_key",),
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
        from astrbot.core.auth.relationships import display_role

        facts = await self._collect_relation_facts(subject, resource, context)
        granted, matched = evaluate_relations(
            action=action,
            resource=resource,
            context=context,
            tuples=tuples_from_roles(subject_id=subject.id, roles=facts),
        )
        role = display_role(matched) or await self._resolve_role(
            subject, resource, context
        )
        if context.source == "webchat" and action in WEBCHAT_INSTANCE_TOOL_ACTIONS:
            if role not in {Role.INSTANCE_OPERATOR, Role.OPERATOR, Role.ROOT}:
                return Decision(
                    False,
                    subject,
                    action,
                    resource,
                    role,
                    "role_scope_denied",
                    audit_id=audit_id,
                    matched_relations=tuple(item.relation.value for item in matched),
                    relation_sources=tuple(item.source for item in matched),
                )
        override_allowed = await self._policy_override_allows(action, resource, role)
        if not granted and not override_allowed:
            return Decision(
                False,
                subject,
                action,
                resource,
                role,
                "role_scope_denied",
                audit_id=audit_id,
                matched_relations=tuple(item.relation.value for item in matched),
                relation_sources=tuple(item.source for item in matched),
            )
        step_up_id: str | None = None
        if _requires_step_up(action, resource, context):
            if context.source not in {"dashboard", "webchat"}:
                return Decision(
                    False,
                    subject,
                    action,
                    resource,
                    role,
                    "high_risk_dashboard_only",
                    audit_id=audit_id,
                    matched_relations=tuple(item.relation.value for item in matched),
                    relation_sources=tuple(item.source for item in matched),
                )
            if context.source == "webchat" and (
                subject.kind != "dashboard-account"
                or action not in WEBCHAT_INSTANCE_TOOL_ACTIONS
                or not context.authenticated
                or context.origin_session_resource_id is None
            ):
                return Decision(
                    False,
                    subject,
                    action,
                    resource,
                    role,
                    "high_risk_dashboard_only",
                    audit_id=audit_id,
                    matched_relations=tuple(item.relation.value for item in matched),
                    relation_sources=tuple(item.source for item in matched),
                )
            step_up_id = _webchat_step_up_cached(context, action)
            if step_up_id is None:
                step_up_id = await self._consume_step_up(
                    subject, action, resource, context
                )
            if step_up_id is None:
                return Decision(
                    False,
                    subject,
                    action,
                    resource,
                    role,
                    "step_up_required",
                    requires_step_up=True,
                    audit_id=audit_id,
                    matched_relations=tuple(item.relation.value for item in matched),
                    relation_sources=tuple(item.source for item in matched),
                )
        return Decision(
            True,
            subject,
            action,
            resource,
            role,
            "allowed",
            audit_id=audit_id,
            step_up_id=step_up_id,
            matched_relations=tuple(item.relation.value for item in matched),
            relation_sources=tuple(item.source for item in matched),
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

    @staticmethod
    def _origin_session_resource(context: AuthContext) -> Resource | None:
        if context.origin_session_resource_id is None:
            return None
        config_id, umo = parse_canonical_session_resource(
            context.origin_session_resource_id
        )
        return Resource.session(config_id, umo)

    @classmethod
    def _session_scope_resource(
        cls, resource: Resource, context: AuthContext
    ) -> Resource | None:
        """Return the current-session scope usable for a session-bound tool."""

        if resource.type == "session":
            return resource
        origin = cls._origin_session_resource(context)
        if (
            origin is not None
            and resource.type in {"tool", "file", "mcp"}
            and resource.config_id == origin.config_id
        ):
            return origin
        return None

    async def _collect_relation_facts(
        self, subject: Subject, resource: Resource, context: AuthContext
    ) -> list[tuple[Role, str, Resource]]:
        facts: list[tuple[Role, str, Resource]] = []
        candidates = [subject.id]
        if subject.kind not in {"plugin", "agent"} and (
            context.principal_subject_id
            and context.principal_subject_id not in candidates
        ):
            candidates.append(context.principal_subject_id)
        origin = self._origin_session_resource(context)
        session_scope = self._session_scope_resource(resource, context)
        origin_matches = (
            origin is not None
            and session_scope is not None
            and origin.id == session_scope.id
        )
        if (
            subject.kind not in {"plugin", "agent"}
            and subject.authenticated
            and origin_matches
            and session_scope is not None
        ):
            facts.append((Role.MEMBER, "default", session_scope))
        now = utc_now()
        async with self._db.get_db() as session:
            bindings = await session.execute(
                select(AuthRoleBinding).where(
                    col(AuthRoleBinding.subject_id).in_(candidates),
                    col(AuthRoleBinding.revoked_at).is_(None),
                )
            )
            for binding in bindings.scalars():
                if binding.expires_at is not None and binding.expires_at <= now:
                    continue
                try:
                    binding_role = Role(binding.role)
                except ValueError:
                    continue
                if binding.scope_type == "global" and binding.role in {
                    Role.ROOT.value,
                    Role.OPERATOR.value,
                }:
                    if not _control_plane_bindings_apply(subject, context):
                        continue
                    account_id = binding.subject_id.removeprefix("dashboard-account:")
                    if account_id == binding.subject_id:
                        continue
                    account = (
                        await session.execute(
                            select(DashboardAccount).where(
                                col(DashboardAccount.account_id) == account_id,
                                col(DashboardAccount.is_active).is_(True),
                            )
                        )
                    ).scalar_one_or_none()
                    if account is None:
                        continue
                    facts.append((binding_role, "binding", resource))
                    continue
                if binding.scope_type == "instance" and binding.config_id:
                    if resource.config_id != binding.config_id:
                        continue
                    facts.append(
                        (binding_role, "binding", Resource.instance(binding.config_id))
                    )
                    continue
                if binding.scope_type == "session" and binding.config_id:
                    try:
                        scoped = self._normalize_session_binding_scope(
                            binding.config_id, binding.scope_id
                        )
                        config_id, umo = parse_canonical_session_resource(scoped)
                        facts.append(
                            (binding_role, "binding", Resource.session(config_id, umo))
                        )
                    except AuthorizationValueError:
                        continue
                    continue
                if self._binding_matches_resource(binding, resource):
                    facts.append((binding_role, "binding", resource))
            if origin_matches and session_scope is not None and session_scope.umo:
                fact = (
                    await session.execute(
                        select(AuthPlatformMembershipFact).where(
                            col(AuthPlatformMembershipFact.subject_id) == subject.id,
                            col(AuthPlatformMembershipFact.config_id)
                            == session_scope.config_id,
                            col(AuthPlatformMembershipFact.umo) == session_scope.umo,
                            col(AuthPlatformMembershipFact.expires_at) > now,
                        )
                    )
                ).scalar_one_or_none()
                if fact is not None:
                    facts.append(
                        (
                            Role.SESSION_OWNER
                            if fact.platform_role == "owner"
                            else Role.SESSION_ADMIN
                            if fact.platform_role == "admin"
                            else Role.MEMBER,
                            "platform",
                            session_scope,
                        )
                    )
        if (
            origin_matches
            and session_scope is not None
            and context.platform_member_role in {"owner", "admin"}
            and context.platform_role_source in {"adapter", "api", "cache"}
            and (
                context.platform_role_expires_at is None
                or context.platform_role_expires_at > now
            )
        ):
            facts.append(
                (
                    Role.SESSION_OWNER
                    if context.platform_member_role == "owner"
                    else Role.SESSION_ADMIN,
                    context.platform_role_source,
                    session_scope,
                )
            )
        return facts

    async def _resolve_role(
        self, subject: Subject, resource: Resource, context: AuthContext
    ) -> Role:
        facts = await self._collect_relation_facts(subject, resource, context)
        roles = [Role.GUEST, *(role for role, _, _ in facts)]
        return max(roles, key=lambda candidate: ROLE_ORDER[candidate])

    @staticmethod
    def _binding_matches_resource(binding: AuthRoleBinding, resource: Resource) -> bool:
        if binding.scope_type == "global":
            return (
                binding.role in {Role.ROOT.value, Role.OPERATOR.value}
                and binding.scope_id == "global"
                and binding.config_id == GLOBAL_SCOPE_ID
            )
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
        """Issue a short-lived, one-time credential after reauthentication."""

        context = self._resource_scoped_dashboard_context(context, resource)
        if (
            context.source not in {"dashboard", "webchat"}
            or not _requires_step_up(action, resource, context)
            or not 0 < ttl_seconds <= 900
        ):
            raise AuthorizationValueError("Invalid step-up request")
        if context.source == "webchat":
            if (
                subject.kind != "dashboard-account"
                or action not in WEBCHAT_INSTANCE_TOOL_ACTIONS
                or not context.authenticated
                or context.origin_session_resource_id is None
                or not isinstance(context.metadata.get("dashboard_session_id"), str)
            ):
                raise AuthorizationValueError("Invalid WebChat step-up request")
            resource = _webchat_step_up_binding_resource(action, resource, context)
            if (
                resource.type != "session"
                or resource.id != context.origin_session_resource_id
            ):
                raise AuthorizationValueError(
                    "WebChat step-up must bind the current session"
                )
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
                session.add(
                    self._audit_record(
                        audit_id=str(uuid.uuid4()),
                        subject=subject,
                        action=action,
                        resource=resource,
                        context=context,
                        decision="allow",
                        reason="step_up_issued",
                        step_up_id=credential_id,
                    )
                )
        return credential_id, f"{credential_id}.{secret}"

    def record_step_up_failure(
        self,
        *,
        subject: Subject,
        action: str,
        resource: Resource,
        context: AuthContext,
    ) -> bool:
        """Record a failed Dashboard reauthentication attempt without secrets."""

        return self._audit(
            audit_id=str(uuid.uuid4()),
            subject=subject,
            action=action,
            resource=resource,
            context=context,
            decision="deny",
            reason="step_up_verification_failed",
        )

    def record_dashboard_operation(
        self,
        *,
        subject: Subject,
        action: str,
        resource: Resource,
        context: AuthContext,
        effective_role: Role | None,
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        """Record a completed Dashboard mutation without caller-controlled data."""
        return self._audit(
            audit_id=str(uuid.uuid4()),
            subject=subject,
            action=action,
            resource=resource,
            context=context,
            decision="allow",
            reason="operation_completed",
            effective_role=effective_role,
            metadata=metadata,
        )

    async def _consume_step_up(
        self, subject: Subject, action: str, resource: Resource, context: AuthContext
    ) -> str | None:
        token = context.step_up_token
        if context.source == "webchat":
            token_map = context.metadata.get("webchat_step_up_tokens")
            if isinstance(token_map, dict):
                candidate = token_map.get(action)
                if isinstance(candidate, str):
                    token = candidate
        session_id = context.metadata.get("dashboard_session_id")
        if (
            not isinstance(token, str)
            or "." not in token
            or not isinstance(session_id, str)
        ):
            if context.source == "webchat":
                logger.debug(
                    "WebChat step-up proof unavailable: action=%s token_present=%s sid_present=%s",
                    action,
                    isinstance(token, str) and bool(token),
                    isinstance(session_id, str) and bool(session_id),
                )
            return None
        credential_id, secret = token.split(".", 1)
        binding_resource = _webchat_step_up_binding_resource(action, resource, context)
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
                        col(AuthStepUpCredential.resource_id) == binding_resource.id,
                        col(AuthStepUpCredential.context_digest)
                        == context.digest_for(action, binding_resource),
                        col(AuthStepUpCredential.token_hash)
                        == hashlib.sha256(secret.encode()).hexdigest(),
                        col(AuthStepUpCredential.expires_at) > now,
                        col(AuthStepUpCredential.consumed_at).is_(None),
                    )
                    .values(consumed_at=now)
                    .returning(col(AuthStepUpCredential.expires_at))
                )
                expires_at = result.scalar_one_or_none()
                if expires_at is None:
                    if context.source == "webchat":
                        logger.debug(
                            "WebChat step-up proof binding rejected: action=%s resource_type=%s",
                            action,
                            binding_resource.type,
                        )
                    return None
                if context.source == "webchat":
                    cached = context.metadata.setdefault(
                        "_webchat_step_up_consumed", {}
                    )
                    if isinstance(cached, dict):
                        expires_at_utc = (
                            expires_at.replace(tzinfo=UTC)
                            if expires_at.tzinfo is None
                            else expires_at.astimezone(UTC)
                        )
                        cached[action] = {
                            "credential_id": credential_id,
                            "expires_at": expires_at_utc.timestamp(),
                        }
                return credential_id
