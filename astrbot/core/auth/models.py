"""Pure authorization value objects and resource canonicalization."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from astrbot.core.platform.message_session import MessageSession

# Subject/resource identifiers may contain URL-safe JWT characters.  In
# particular, ``secrets.token_urlsafe`` can emit ``_`` in Dashboard session
# IDs, so rejecting it would turn otherwise valid authenticated requests into
# uncaught 500 responses during authorization context construction.
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/_-]{0,255}$")
_CONFIG_ID_RE = re.compile(r"^(?:default|[A-Za-z0-9][A-Za-z0-9._-]{0,127})$")


class Role(StrEnum):
    """The fixed role vocabulary. Roles never imply a scope on their own."""

    ROOT = "root"
    OPERATOR = "operator"
    INSTANCE_OPERATOR = "instance_operator"
    SESSION_OWNER = "session_owner"
    SESSION_ADMIN = "session_admin"
    MEMBER = "member"
    GUEST = "guest"


ROLE_ORDER: dict[Role, int] = {
    Role.GUEST: 0,
    Role.MEMBER: 1,
    Role.SESSION_ADMIN: 2,
    Role.SESSION_OWNER: 3,
    Role.INSTANCE_OPERATOR: 4,
    Role.OPERATOR: 5,
    Role.ROOT: 6,
}

ACTIONS = frozenset(
    {
        "session.read",
        "session.manage",
        "session.assign",
        "provider.read",
        "provider.use",
        "platform.read",
        "provider.manage",
        "provider.credentials.write",
        "platform.manage",
        "agent.manage",
        "extension.read",
        "extension.manage",
        "extension.plugin_install",
        "data.manage",
        "data.export_all",
        "system.manage",
        "system.update",
        "system.restart",
        "system.pip_install",
        "identity.read",
        "identity.manage",
        "identity.operator.write",
        "identity.root.write",
        "tool.local_exec",
        "tool.python_exec",
        "tool.file_read",
        "tool.file_write",
        "tool.browser_control",
        "tool.mcp_read",
        "tool.mcp_write",
        "tool.computer_use",
        "dashboard.account.manage",
        "filesystem.read",
        "filesystem.write",
        "filesystem.manage",
    }
)

GLOBAL_SCOPE_ID = "__global__"
ANY_CONFIG_SCOPE_ID = "__any_config__"


def persist_capability_config_id(config_id: str | None) -> str:
    """Normalize a domain config id for capability uniqueness.

    Args:
        config_id: Domain config id, or None when the capability applies to every
            config.

    Returns:
        A non-null persistence key. Unspecified domain config becomes
        ``ANY_CONFIG_SCOPE_ID``.
    """
    if config_id is None:
        return ANY_CONFIG_SCOPE_ID
    return config_id


def restore_capability_config_id(config_id: str | None) -> str | None:
    """Restore a persisted capability config key to domain meaning.

    Args:
        config_id: Stored config key, including ``ANY_CONFIG_SCOPE_ID``.

    Returns:
        The concrete config id, or None when the capability applies to every
        config.
    """
    if config_id is None or config_id == ANY_CONFIG_SCOPE_ID:
        return None
    return config_id


HIGH_RISK_ACTIONS = frozenset(
    {
        "identity.operator.write",
        "identity.root.write",
        "system.update",
        "system.restart",
        "system.pip_install",
        "extension.plugin_install",
        "tool.local_exec",
        "tool.python_exec",
        "tool.file_write",
        "tool.browser_control",
        "tool.mcp_write",
        "tool.computer_use",
        "data.export_all",
        "provider.credentials.write",
        "identity.manage",
        "dashboard.account.manage",
        "filesystem.manage",
    }
)

# WebChat may use only these instance-scoped tools after a fresh Dashboard
# factor verification.  Keep this separate from HIGH_RISK_ACTIONS: global
# control-plane mutations must remain Dashboard-only.
WEBCHAT_INSTANCE_TOOL_ACTIONS = frozenset(
    {
        "tool.local_exec",
        "tool.python_exec",
        "tool.file_write",
        "tool.browser_control",
        "tool.mcp_write",
        "tool.computer_use",
    }
)


class AuthorizationValueError(ValueError):
    """Raised for invalid authorization value objects before policy evaluation."""


def _validate_identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise AuthorizationValueError(f"Invalid {label}")
    return value


def normalize_subject_component(value: object, label: str) -> str:
    """Return a stable safe component for arbitrary platform supplied IDs."""

    text = str(value).strip()
    if not text:
        raise AuthorizationValueError(f"Invalid {label}")
    if _ID_RE.fullmatch(text):
        return text
    return f"b64-{_encode_component(text)}"


def _encode_component(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_component(value: str) -> str:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode("utf-8")
    except (UnicodeDecodeError, ValueError) as exc:
        raise AuthorizationValueError("Invalid canonical resource") from exc


def canonical_session_resource(config_id: str, umo: str) -> str:
    """Return a v1 resource wrapper without changing platform UMO routing."""

    if not isinstance(config_id, str) or not _CONFIG_ID_RE.fullmatch(config_id):
        raise AuthorizationValueError("Invalid config id")
    if not isinstance(umo, str) or not umo or "://" in umo or len(umo) > 2048:
        raise AuthorizationValueError("Invalid session origin")
    try:
        normalized_umo = str(MessageSession.from_str(umo))
    except Exception as exc:
        raise AuthorizationValueError("Invalid session origin") from exc
    return (
        f"session:v1:{_encode_component(config_id)}:{_encode_component(normalized_umo)}"
    )


def parse_canonical_session_resource(value: str) -> tuple[str, str]:
    """Parse a canonical v1 session resource and validate both components."""

    parts = value.split(":", 3) if isinstance(value, str) else []
    if len(parts) != 4 or parts[:2] != ["session", "v1"]:
        raise AuthorizationValueError("Invalid canonical resource")
    config_id, umo = _decode_component(parts[2]), _decode_component(parts[3])
    if canonical_session_resource(config_id, umo) != value:
        raise AuthorizationValueError("Invalid canonical resource")
    return config_id, umo


def context_digest(
    *, subject_id: str, action: str, resource_id: str, context: dict[str, Any]
) -> str:
    """Create a stable non-secret digest for a one-time credential binding."""

    safe_context = {
        key: value
        for key, value in context.items()
        if key
        not in {
            "jwt",
            "token",
            "api_key",
            "nonce",
            "password",
            "message",
        }
    }
    payload = json.dumps(
        {
            "subject": subject_id,
            "action": action,
            "resource": resource_id,
            "context": safe_context,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Subject:
    """A normalized actor identity, never a caller-declared display name."""

    id: str
    kind: str
    display_name: str | None = None
    authenticated: bool = False

    def __post_init__(self) -> None:
        _validate_identifier(self.id, "subject id")
        _validate_identifier(self.kind, "subject kind")
        if not self.id.startswith(f"{self.kind}:"):
            raise AuthorizationValueError("Subject namespace mismatch")

    @classmethod
    def im(
        cls,
        *,
        platform_instance: str,
        bot_account_id: str,
        sender_id: str,
        display_name: str | None = None,
    ) -> Subject:
        return cls(
            id=f"im:{normalize_subject_component(platform_instance, 'platform instance')}:{normalize_subject_component(bot_account_id, 'bot account id')}:{normalize_subject_component(sender_id, 'sender id')}",
            kind="im",
            display_name=display_name,
            authenticated=True,
        )

    @classmethod
    def dashboard_session(
        cls, session_id: str, display_name: str | None = None
    ) -> Subject:
        return cls(
            id=f"dashboard-session:{_validate_identifier(session_id, 'session id')}",
            kind="dashboard-session",
            display_name=display_name,
            authenticated=True,
        )

    @classmethod
    def dashboard_account(
        cls, account_id: str, display_name: str | None = None
    ) -> Subject:
        return cls(
            id=f"dashboard-account:{_validate_identifier(account_id, 'account id')}",
            kind="dashboard-account",
            display_name=display_name,
            authenticated=True,
        )

    @classmethod
    def api_key(cls, key_id: str) -> Subject:
        return cls(
            id=f"api-key:{_validate_identifier(key_id, 'api key id')}",
            kind="api-key",
            authenticated=True,
        )

    @classmethod
    def system(cls, component: str) -> Subject:
        """Return a runtime-owned component identity."""

        return cls(
            id=f"system:{_validate_identifier(component, 'system component')}",
            kind="system",
            authenticated=True,
        )

    @classmethod
    def plugin(cls, plugin_id: str) -> Subject:
        """Return an execution-component identity. It never inherits caller root."""

        return cls(
            id=f"plugin:{_validate_identifier(plugin_id, 'plugin id')}",
            kind="plugin",
            authenticated=True,
        )

    @classmethod
    def agent(cls, agent_id: str) -> Subject:
        """Return an execution-component identity. It never inherits caller root."""

        return cls(
            id=f"agent:{_validate_identifier(agent_id, 'agent id')}",
            kind="agent",
            authenticated=True,
        )

    @classmethod
    def guest(cls, label: str = "anonymous") -> Subject:
        return cls(
            id=f"guest:{_validate_identifier(label, 'guest id')}",
            kind="guest",
            authenticated=False,
        )

    @classmethod
    def from_id(cls, subject_id: str) -> Subject:
        """Validate a persisted subject ID without inferring an authority role."""

        kind, separator, _ = subject_id.partition(":")
        if not separator:
            raise AuthorizationValueError("Subject id must include a namespace")
        return cls(id=subject_id, kind=kind, authenticated=True)


@dataclass(frozen=True, slots=True)
class Resource:
    """A structured protected resource with a canonical resource id."""

    type: str
    id: str
    config_id: str | None = None
    umo: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.type, "resource type")
        if not isinstance(self.id, str) or not self.id or len(self.id) > 4096:
            raise AuthorizationValueError("Invalid resource id")
        if self.config_id is not None and not _CONFIG_ID_RE.fullmatch(self.config_id):
            raise AuthorizationValueError("Invalid resource config id")
        if self.type == "session":
            if self.config_id is None or self.umo is None:
                raise AuthorizationValueError(
                    "Session resource requires config id and UMO"
                )
            if self.id != canonical_session_resource(self.config_id, self.umo):
                raise AuthorizationValueError("Non-canonical session resource")

    @classmethod
    def session(cls, config_id: str, umo: str) -> Resource:
        canonical = canonical_session_resource(config_id, umo)
        _, normalized_umo = parse_canonical_session_resource(canonical)
        return cls(
            type="session", id=canonical, config_id=config_id, umo=normalized_umo
        )

    @classmethod
    def instance(cls, config_id: str) -> Resource:
        if not _CONFIG_ID_RE.fullmatch(config_id):
            raise AuthorizationValueError("Invalid config id")
        return cls(
            type="instance",
            id=f"instance:v1:{_encode_component(config_id)}",
            config_id=config_id,
        )

    @classmethod
    def named(
        cls, resource_type: str, resource_id: str, *, config_id: str | None = None
    ) -> Resource:
        _validate_identifier(resource_type, "resource type")
        _validate_identifier(resource_id, "resource id")
        if config_id is not None and not _CONFIG_ID_RE.fullmatch(config_id):
            raise AuthorizationValueError("Invalid config id")
        canonical = f"{resource_type}:v1:{_encode_component(config_id or '')}:{_encode_component(resource_id)}"
        return cls(type=resource_type, id=canonical, config_id=config_id)


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Trusted request facts. Caller-declared names are explicitly separate."""

    subject: Subject
    source: str
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    config_id: str | None = None
    platform: str | None = None
    message_type: str | None = None
    platform_member_role: str = "unknown"
    platform_role_source: str = "none"
    platform_role_expires_at: datetime | None = None
    authenticated: bool = False
    principal_subject_id: str | None = None
    api_scopes: tuple[str, ...] = ()
    auth_strength: str = "none"
    authenticated_at: datetime | None = None
    step_up_token: str | None = None
    origin_session_resource_id: str | None = None
    caller_declared_username: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_identifier(self.source, "authorization source")
        if self.config_id is not None and not _CONFIG_ID_RE.fullmatch(self.config_id):
            raise AuthorizationValueError("Invalid context config id")
        if self.platform_member_role not in {"owner", "admin", "member", "unknown"}:
            raise AuthorizationValueError("Invalid platform member role")
        if self.principal_subject_id is not None:
            _validate_identifier(self.principal_subject_id, "principal subject id")
        if self.auth_strength not in {"none", "password", "totp", "step_up"}:
            raise AuthorizationValueError("Invalid authentication strength")
        if self.origin_session_resource_id is not None:
            origin_config_id, _ = parse_canonical_session_resource(
                self.origin_session_resource_id
            )
            if self.config_id is not None and origin_config_id != self.config_id:
                raise AuthorizationValueError("Origin session config mismatch")

    def digest_for(self, action: str, resource: Resource) -> str:
        """Return policy facts that bind a Dashboard step-up credential.

        Transport-only request metadata cannot participate: issuing and using a
        credential are different HTTP requests and must bind to the same
        authorization tuple.
        """
        return context_digest(
            subject_id=self.subject.id,
            action=action,
            resource_id=resource.id,
            context={
                "source": self.source,
                "config_id": self.config_id,
                "platform": self.platform,
                "message_type": self.message_type,
                "platform_member_role": self.platform_member_role,
                "platform_role_source": self.platform_role_source,
                "principal_subject_id": self.principal_subject_id,
                "origin_session_resource_id": self.origin_session_resource_id,
                "caller_declared_username": self.caller_declared_username,
            },
        )


@dataclass(frozen=True, slots=True)
class Decision:
    """The full fail-closed result of one authorization evaluation."""

    allowed: bool
    subject: Subject
    action: str
    resource: Resource
    effective_role: Role | None
    reason: str
    requires_step_up: bool = False
    audit_id: str | None = None
    step_up_id: str | None = None
    matched_relations: tuple[str, ...] = ()
    relation_sources: tuple[str, ...] = ()


def utc_now() -> datetime:
    return datetime.now(UTC)
