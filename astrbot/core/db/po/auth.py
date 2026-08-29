import uuid
from datetime import UTC, datetime

from sqlmodel import JSON, Field, Index, SQLModel, Text, UniqueConstraint

from astrbot.core.db.po.mixins import TimestampMixin


class DashboardAccount(TimestampMixin, SQLModel, table=True):
    """Stable Dashboard identity independent from a mutable username."""

    __tablename__ = "dashboard_accounts"  # type: ignore

    account_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    username: str = Field(nullable=False, unique=True, index=True, max_length=255)
    password_hash: str = Field(nullable=False, sa_type=Text)
    is_active: bool = Field(default=True, nullable=False, index=True)
    created_by: str | None = Field(default=None, index=True, max_length=512)
    last_login_at: datetime | None = Field(default=None, index=True)
    # TOTP belongs to this immutable account identity; a username rename must
    # never transfer a second factor to a different account.
    totp_enabled: bool = Field(default=False, nullable=False)
    totp_secret: str = Field(default="", nullable=False, sa_type=Text)
    totp_recovery_code_hash: str = Field(default="", nullable=False, sa_type=Text)


class AuthRoleBinding(TimestampMixin, SQLModel, table=True):
    """An explicit role binding. The authorization service enforces scope."""

    __tablename__ = "auth_role_bindings"  # type: ignore

    binding_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    subject_id: str = Field(nullable=False, index=True, max_length=512)
    role: str = Field(nullable=False, index=True, max_length=64)
    scope_type: str = Field(nullable=False, index=True, max_length=32)
    scope_id: str = Field(nullable=False, max_length=4096)
    config_id: str = Field(nullable=False, index=True, max_length=128)
    source: str = Field(nullable=False, default="explicit", max_length=64)
    expires_at: datetime | None = Field(default=None, index=True)
    created_by: str | None = Field(default=None, max_length=512)
    revoked_at: datetime | None = Field(default=None, index=True)
    revoked_by: str | None = Field(default=None, max_length=512)
    metadata_json: dict = Field(default_factory=dict, sa_type=JSON)

    __table_args__ = (
        UniqueConstraint(
            "subject_id",
            "scope_type",
            "scope_id",
            "config_id",
            name="uix_auth_role_binding_scope",
        ),
        Index(
            "ix_auth_role_bindings_active_scope",
            "subject_id",
            "config_id",
            "revoked_at",
            "expires_at",
        ),
        Index(
            "ix_auth_role_bindings_relation_lookup",
            "subject_id",
            "scope_type",
            "scope_id",
            "role",
            "revoked_at",
        ),
    )


class AuthPlatformMembershipFact(TimestampMixin, SQLModel, table=True):
    """Short-lived adapter role observation, never an explicit role binding."""

    __tablename__ = "auth_platform_membership_facts"  # type: ignore

    fact_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    subject_id: str = Field(nullable=False, index=True, max_length=512)
    config_id: str = Field(nullable=False, index=True, max_length=128)
    platform_instance: str = Field(nullable=False, index=True, max_length=255)
    umo: str = Field(nullable=False, max_length=2048)
    platform_role: str = Field(nullable=False, max_length=32)
    source: str = Field(nullable=False, max_length=32)
    observed_at: datetime = Field(nullable=False, index=True)
    expires_at: datetime = Field(nullable=False, index=True)
    metadata_json: dict = Field(default_factory=dict, sa_type=JSON)

    __table_args__ = (
        UniqueConstraint(
            "subject_id",
            "config_id",
            "platform_instance",
            "umo",
            name="uix_auth_platform_fact_scope",
        ),
        Index(
            "ix_auth_platform_facts_active",
            "config_id",
            "umo",
            "subject_id",
            "expires_at",
        ),
    )


class AuthStepUpCredential(SQLModel, table=True):
    """One-time Dashboard proof. Only a secret hash is stored."""

    __tablename__ = "auth_step_up_credentials"  # type: ignore

    credential_id: str = Field(primary_key=True, max_length=64)
    subject_id: str = Field(nullable=False, index=True, max_length=512)
    dashboard_session_id: str = Field(nullable=False, index=True, max_length=512)
    action: str = Field(nullable=False, max_length=128)
    resource_id: str = Field(nullable=False, max_length=4096)
    context_digest: str = Field(nullable=False, max_length=128)
    token_hash: str = Field(nullable=False, max_length=128)
    verified_method: str = Field(nullable=False, max_length=32)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    expires_at: datetime = Field(nullable=False, index=True)
    consumed_at: datetime | None = Field(default=None, index=True)

    __table_args__ = (
        Index(
            "ix_auth_step_up_consume",
            "subject_id",
            "action",
            "resource_id",
            "expires_at",
            "consumed_at",
        ),
    )


class AuthAuditLog(SQLModel, table=True):
    """Append-only, redacted authorization decision history."""

    __tablename__ = "auth_audit_log"  # type: ignore

    audit_id: str = Field(primary_key=True, max_length=64)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    request_id: str | None = Field(default=None, index=True, max_length=128)
    subject_id: str = Field(nullable=False, index=True, max_length=512)
    effective_role: str | None = Field(default=None, max_length=64)
    source: str = Field(nullable=False, max_length=64)
    platform: str | None = Field(default=None, max_length=255)
    config_id: str | None = Field(default=None, index=True, max_length=128)
    action: str = Field(nullable=False, index=True, max_length=128)
    resource_id: str = Field(nullable=False, max_length=4096)
    decision: str = Field(nullable=False, index=True, max_length=32)
    reason: str = Field(nullable=False, max_length=128)
    step_up_id: str | None = Field(default=None, index=True, max_length=64)
    outcome: str | None = Field(default=None, max_length=64)
    latency_ms: int | None = Field(default=None)
    metadata_json: dict = Field(default_factory=dict, sa_type=JSON)

    __table_args__ = (
        Index(
            "ix_auth_audit_config_action_timestamp", "config_id", "action", "timestamp"
        ),
    )


class AuthPolicyOverride(TimestampMixin, SQLModel, table=True):
    """A structured allow-list override for a fixed action and narrow scope."""

    __tablename__ = "auth_policy_overrides"  # type: ignore

    override_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), primary_key=True
    )
    action: str = Field(nullable=False, index=True, max_length=128)
    resource_type: str = Field(nullable=False, max_length=64)
    resource_id: str | None = Field(default=None, max_length=4096)
    config_id: str | None = Field(default=None, index=True, max_length=128)
    allowed_roles: list = Field(default_factory=list, sa_type=JSON)
    enabled: bool = Field(default=True, nullable=False, index=True)
    expires_at: datetime | None = Field(default=None, index=True)
    created_by: str | None = Field(default=None, max_length=512)
    metadata_json: dict = Field(default_factory=dict, sa_type=JSON)


class AuthCapability(TimestampMixin, SQLModel, table=True):
    """Explicit API-key capability. Never a wildcard or implicit operator."""

    __tablename__ = "auth_capabilities"  # type: ignore

    capability_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), primary_key=True
    )
    subject_id: str = Field(nullable=False, index=True, max_length=512)
    action: str = Field(nullable=False, index=True, max_length=128)
    resource_type: str = Field(nullable=False, max_length=64)
    resource_id: str = Field(nullable=False, max_length=4096)
    config_id: str = Field(nullable=False, index=True, max_length=128)
    expires_at: datetime | None = Field(default=None, index=True)
    created_by: str | None = Field(default=None, max_length=512)
    revoked_at: datetime | None = Field(default=None, index=True)

    __table_args__ = (
        UniqueConstraint(
            "subject_id",
            "action",
            "resource_type",
            "resource_id",
            "config_id",
            name="uix_auth_capability_scope",
        ),
        Index(
            "ix_auth_capabilities_lookup",
            "subject_id",
            "action",
            "resource_type",
            "resource_id",
            "revoked_at",
        ),
    )


class DashboardTrustedDevice(TimestampMixin, SQLModel, table=True):
    """Trusted dashboard device token used to skip TOTP for a limited time."""

    __tablename__ = "dashboard_trusted_devices"  # type: ignore

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    token_hash: str = Field(max_length=64, nullable=False, unique=True, index=True)
    account_id: str = Field(nullable=False, index=True, max_length=64)
    totp_secret_hash: str = Field(max_length=64, nullable=False, index=True)
    expires_at: datetime = Field(nullable=False, index=True)
