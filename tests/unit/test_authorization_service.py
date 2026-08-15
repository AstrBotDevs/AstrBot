"""Security-contract coverage for the unified authorization service."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlmodel import select

from astrbot.core.auth.models import AuthContext, Decision, Resource, Role, Subject
from astrbot.core.auth.service import AuthorizationService, api_key_scopes_allow_action
from astrbot.core.db.po import AuthAuditLog, AuthRoleBinding, DashboardAccount
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.star.plugin_context import AuthorizationCapability
from astrbot.core.utils.totp import TotpRuntimeState
from astrbot.dashboard.api.authorization import _resource
from astrbot.dashboard.services.auth_service import AuthService


@pytest_asyncio.fixture
async def authorization(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "authorization.db"))
    await db.initialize()
    service = AuthorizationService(db)
    await service.start()
    try:
        yield service
    finally:
        await service.close()
        await db.close()


def _context(subject: Subject, config_id: str, **metadata) -> AuthContext:
    return AuthContext(
        subject=subject,
        source="im",
        config_id=config_id,
        authenticated=subject.authenticated,
        metadata=metadata,
    )


def _session_context(subject: Subject, resource: Resource, **kwargs) -> AuthContext:
    """Create a trusted IM context bound to one inbound session."""

    return AuthContext(
        subject=subject,
        source="im",
        config_id=resource.config_id,
        authenticated=subject.authenticated,
        origin_session_resource_id=resource.id,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_instance_binding_never_crosses_config(authorization):
    subject = Subject.im(
        platform_instance="onebot", bot_account_id="bot", sender_id="42"
    )
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.INSTANCE_OPERATOR,
        scope_type="instance",
        scope_id="config-a",
        config_id="config-a",
        enforce_actor=False,
    )
    allowed = await authorization.authorize(
        subject,
        "provider.manage",
        Resource.instance("config-a"),
        _context(subject, "config-a"),
    )
    denied = await authorization.authorize(
        subject,
        "provider.manage",
        Resource.instance("config-b"),
        _context(subject, "config-b"),
    )
    assert allowed.allowed
    assert not denied.allowed


@pytest.mark.asyncio
async def test_platform_admin_is_session_scoped_and_expires(authorization):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    current = Resource.session("default", "napcat:GroupMessage:room-a")
    other = Resource.session("default", "napcat:GroupMessage:room-b")
    await authorization.record_platform_membership(
        subject=subject,
        resource=current,
        platform_instance="napcat",
        platform_role="admin",
        source="adapter",
        ttl_seconds=1,
    )
    assert (
        await authorization.authorize(
            subject, "session.manage", current, _context(subject, "default")
        )
    ).allowed
    assert not (
        await authorization.authorize(
            subject, "session.manage", other, _context(subject, "default")
        )
    ).allowed


@pytest.mark.asyncio
async def test_step_up_consumption_is_atomic(authorization):
    subject = Subject.dashboard_session("session-1")
    resource = Resource.named("provider", "model-a", config_id="default")
    issued_context = AuthContext(
        subject=subject,
        source="dashboard",
        config_id="default",
        authenticated=True,
        metadata={"dashboard_session_id": "session-1"},
    )
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.INSTANCE_OPERATOR,
        scope_type="instance",
        scope_id="default",
        config_id="default",
        enforce_actor=False,
    )
    _credential_id, token = await authorization.issue_step_up(
        subject=subject,
        dashboard_session_id="session-1",
        action="provider.credentials.write",
        resource=resource,
        context=issued_context,
        verified_method="password",
    )
    consuming_context = AuthContext(
        subject=subject,
        source="dashboard",
        config_id="default",
        authenticated=True,
        step_up_token=token,
        metadata={"dashboard_session_id": "session-1"},
    )
    decisions = await asyncio.gather(
        *(
            authorization.authorize(
                subject, "provider.credentials.write", resource, consuming_context
            )
            for _ in range(2)
        )
    )
    assert sum(decision.allowed for decision in decisions) == 1


def test_api_key_scopes_are_capabilities_not_roles():
    assert api_key_scopes_allow_action(["provider"], "provider.use")
    assert not api_key_scopes_allow_action(["provider"], "provider.manage")
    assert not api_key_scopes_allow_action(["config"], "provider.credentials.write")
    assert not api_key_scopes_allow_action(
        ["chat", "chat:admin"], "chat.impersonate_admin"
    )


def test_api_key_scopes_are_bound_to_resource_domains():
    assert api_key_scopes_allow_action(
        ["data"], "data.manage", Resource.named("file", "file-1")
    )
    assert not api_key_scopes_allow_action(
        ["provider"], "provider.use", Resource.named("file", "file-1")
    )


def test_dashboard_step_up_resource_parser_accepts_canonical_session_and_instance():
    session = Resource.session("default", "napcat:GroupMessage:room-a")
    parsed_session = _resource(
        SimpleNamespace(
            resource_type="session",
            resource_id=session.id,
            config_id="default",
        )
    )
    parsed_instance = _resource(
        SimpleNamespace(
            resource_type="instance",
            resource_id="default",
            config_id="default",
        )
    )
    assert parsed_session == session
    assert parsed_instance == Resource.instance("default")


@pytest.mark.asyncio
async def test_global_roles_require_an_active_dashboard_account(authorization):
    with pytest.raises(ValueError, match="Dashboard account"):
        await authorization.grant_binding(
            actor=Subject.system("test"),
            subject_id=Subject.im(
                platform_instance="onebot", bot_account_id="bot", sender_id="42"
            ).id,
            role=Role.ROOT,
            scope_type="global",
            scope_id="global",
            config_id=None,
            enforce_actor=False,
        )

    async with authorization._db.get_db() as session:
        async with session.begin():
            session.add(
                DashboardAccount(
                    account_id="active-account",
                    username="active-account",
                    password_hash="hash",
                )
            )

    binding = await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=Subject.dashboard_account("active-account").id,
        role=Role.ROOT,
        scope_type="global",
        scope_id="global",
        config_id=None,
        enforce_actor=False,
    )
    assert binding.role == Role.ROOT


@pytest.mark.asyncio
async def test_disabling_dashboard_account_revokes_its_authority(authorization):
    config = {"dashboard": {"jwt_secret": "test-secret"}}
    auth_service = AuthService(
        authorization._db,
        config,
        demo_mode=False,
        totp_runtime_state=TotpRuntimeState(),
    )
    account = await auth_service.create_dashboard_account(
        username="root-account",
        password="AstrbotSecure123!",
        created_by="test",
    )
    subject = Subject.dashboard_account(account.account_id)
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.OPERATOR,
        scope_type="global",
        scope_id="global",
        config_id=None,
        enforce_actor=False,
    )
    context = AuthContext(subject=subject, source="dashboard", authenticated=True)
    assert (
        await authorization.authorize(
            subject, "identity.read", Resource.named("identity", "accounts"), context
        )
    ).allowed

    await auth_service.update_dashboard_account(
        account_id=account.account_id, is_active=False
    )

    assert not (
        await authorization.authorize(
            subject, "identity.read", Resource.named("identity", "accounts"), context
        )
    ).allowed


@pytest.mark.asyncio
async def test_dashboard_account_mutation_can_commit_business_audit(authorization):
    config = {"dashboard": {"jwt_secret": "test-secret"}}
    auth_service = AuthService(
        authorization._db,
        config,
        demo_mode=False,
        totp_runtime_state=TotpRuntimeState(),
    )
    actor = Subject.dashboard_account("root-actor", "root-actor")
    context = AuthContext(subject=actor, source="dashboard", authenticated=True)
    decision = Decision(
        True,
        actor,
        "identity.root.write",
        Resource.named("dashboard-account", "new-account"),
        Role.ROOT,
        "allowed",
        step_up_id="step-up-1",
    )
    await auth_service.create_dashboard_account_with_role(
        username="new-account",
        password="AstrbotSecure123!",
        created_by=actor.id,
        role=Role.ROOT,
        actor=actor,
        audit_context=context,
        audit_decision=decision,
    )

    async with authorization._db.get_db() as session:
        rows = list((await session.execute(select(AuthAuditLog))).scalars())
    assert any(row.reason == "account_created" for row in rows)


@pytest.mark.asyncio
async def test_revoking_last_active_root_ignores_disabled_root_bindings(authorization):
    async with authorization._db.get_db() as session:
        async with session.begin():
            active = DashboardAccount(
                account_id="active-root",
                username="active-root",
                password_hash="hash",
                is_active=True,
            )
            disabled = DashboardAccount(
                account_id="disabled-root",
                username="disabled-root",
                password_hash="hash",
                is_active=False,
            )
            session.add_all(
                [
                    active,
                    disabled,
                    AuthRoleBinding(
                        subject_id="dashboard-account:active-root",
                        role=Role.ROOT.value,
                        scope_type="global",
                        scope_id="global",
                        config_id="__global__",
                    ),
                    AuthRoleBinding(
                        subject_id="dashboard-account:disabled-root",
                        role=Role.ROOT.value,
                        scope_type="global",
                        scope_id="global",
                        config_id="__global__",
                    ),
                ]
            )

    bindings = await authorization.list_bindings(
        subject_id="dashboard-account:active-root"
    )
    authorization._assert_binding_management_allowed = AsyncMock()
    with pytest.raises(ValueError, match="last root"):
        await authorization.revoke_binding(
            actor=Subject.system("test"),
            binding_id=bindings[0].binding_id,
        )


@pytest.mark.asyncio
async def test_audit_redacts_secrets(authorization):
    subject = Subject.guest("guest")
    resource = Resource.instance("default")
    await authorization.authorize(
        subject,
        "system.restart",
        resource,
        AuthContext(
            subject=subject,
            source="webchat",
            config_id="default",
            metadata={
                "token": "leak",
                "jwt_token": "eyJhbGciOiJIUzI1NiJ9.secret.signature",
                "authorization": "Bearer should-not-be-stored",
                "message": "full message",
                "url": "https://secret.example/a?token=leak",
            },
        ),
    )
    await authorization.flush_audit()
    records = await authorization.list_audit()
    assert records
    assert "token" not in records[0].metadata_json
    assert "jwt_token" not in records[0].metadata_json
    assert "authorization" not in records[0].metadata_json
    assert "message" not in records[0].metadata_json


@pytest.mark.asyncio
async def test_canonical_session_resource_is_config_isolated():
    first = Resource.session("config-a", "webchat:FriendMessage:session")
    second = Resource.session("config-b", "webchat:FriendMessage:session")
    assert first.id != second.id
    assert first.config_id != second.config_id


@pytest.mark.asyncio
async def test_new_session_binding_is_canonicalized_and_accepts_canonical_scope(
    authorization,
):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    resource = Resource.session("default", "napcat:GroupMessage:room-a")

    binding = await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.SESSION_ADMIN,
        scope_type="session",
        scope_id="napcat:GroupMessage:room-a",
        config_id="default",
        enforce_actor=False,
    )
    assert binding.scope_id == resource.id

    revived = await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.SESSION_ADMIN,
        scope_type="session",
        scope_id=resource.id,
        config_id="default",
        enforce_actor=False,
    )
    assert revived.binding_id == binding.binding_id
    assert (
        await authorization.authorize(
            subject, "session.manage", resource, _session_context(subject, resource)
        )
    ).allowed


@pytest.mark.asyncio
async def test_role_grant_replaces_the_active_binding_at_the_same_scope(authorization):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    resource = Resource.session("default", "napcat:GroupMessage:room-a")

    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.SESSION_OWNER,
        scope_type="session",
        scope_id=resource.id,
        config_id="default",
        enforce_actor=False,
    )
    binding = await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.MEMBER,
        scope_type="session",
        scope_id=resource.id,
        config_id="default",
        enforce_actor=False,
    )

    assert binding.role == Role.MEMBER
    bindings = await authorization.list_bindings(subject_id=subject.id)
    active = [item for item in bindings if item.revoked_at is None]
    assert [(item.scope_id, item.role) for item in active] == [
        (resource.id, Role.MEMBER.value)
    ]
    assert not (
        await authorization.authorize(
            subject,
            "session.manage",
            resource,
            _session_context(subject, resource),
        )
    ).allowed


@pytest.mark.asyncio
async def test_target_session_authorization_does_not_inherit_origin_owner(
    authorization,
):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    origin = Resource.session("default", "napcat:GroupMessage:room-a")
    target = Resource.session("default", "napcat:GroupMessage:room-b")
    event = SimpleNamespace(
        subject=subject,
        auth_context=_session_context(
            subject,
            origin,
            platform_member_role="owner",
            platform_role_source="adapter",
        ),
    )
    capability = AuthorizationCapability(authorization)

    denied = await capability.authorize_target_session(
        event,
        action="session.assign",
        umo=target.umo or "",
    )
    assert not denied.allowed
    assert denied.reason == "role_scope_denied"

    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.SESSION_OWNER,
        scope_type="session",
        scope_id=target.id,
        config_id="default",
        enforce_actor=False,
    )
    assert (
        await capability.authorize_target_session(
            event,
            action="session.assign",
            umo=target.umo or "",
        )
    ).allowed


@pytest.mark.asyncio
async def test_session_context_cannot_read_another_session_or_manage_named_data(
    authorization,
):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    current = Resource.session("default", "napcat:GroupMessage:room-a")
    other = Resource.session("default", "napcat:GroupMessage:room-b")
    context = _session_context(subject, current)

    assert (
        await authorization.authorize(subject, "session.read", current, context)
    ).allowed
    cross_session = await authorization.authorize(
        subject, "session.read", other, context
    )
    assert not cross_session.allowed
    assert cross_session.reason == "cross_session_resource"

    data_decision = await authorization.authorize(
        subject,
        "data.manage",
        Resource.named("data", "shared-kb", config_id="default"),
        context,
    )
    assert not data_decision.allowed


@pytest.mark.asyncio
async def test_session_owner_can_manage_current_members_but_not_delegate_ownership(
    authorization,
):
    owner = Subject.im(platform_instance="napcat", bot_account_id="bot", sender_id="42")
    target = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="84"
    )
    current = Resource.session("default", "napcat:GroupMessage:room-a")
    context = _session_context(
        owner,
        current,
        platform_member_role="owner",
        platform_role_source="adapter",
    )

    await authorization.grant_binding(
        actor=owner,
        subject_id=target.id,
        role=Role.SESSION_ADMIN,
        scope_type="session",
        scope_id=current.id,
        config_id="default",
        context=context,
    )
    assert (
        await authorization.authorize(
            target,
            "session.manage",
            current,
            _session_context(target, current),
        )
    ).allowed

    with pytest.raises(PermissionError):
        await authorization.grant_binding(
            actor=owner,
            subject_id=target.id,
            role=Role.SESSION_OWNER,
            scope_type="session",
            scope_id=current.id,
            config_id="default",
            context=context,
        )


@pytest.mark.asyncio
async def test_session_scoped_tool_role_cannot_cross_origin_session(authorization):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    current = Resource.session("default", "napcat:GroupMessage:room-a")
    other = Resource.session("default", "napcat:GroupMessage:room-b")
    tool = Resource.named("tool", "persona-editor", config_id="default")
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.SESSION_OWNER,
        scope_type="session",
        scope_id=current.id,
        config_id="default",
        enforce_actor=False,
    )

    assert (
        await authorization.authorize(
            subject, "agent.manage", tool, _session_context(subject, current)
        )
    ).allowed
    assert not (
        await authorization.authorize(
            subject, "agent.manage", tool, _session_context(subject, other)
        )
    ).allowed


@pytest.mark.asyncio
async def test_global_control_plane_role_is_not_an_im_session_role(authorization):
    account = DashboardAccount(
        account_id="root-account", username="root-account", password_hash="hash"
    )
    subject = Subject.dashboard_account(account.account_id)
    current = Resource.session("default", "napcat:GroupMessage:room-a")
    async with authorization._db.get_db() as session:
        async with session.begin():
            session.add(account)
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.ROOT,
        scope_type="global",
        scope_id="global",
        config_id=None,
        enforce_actor=False,
    )

    decision = await authorization.authorize(
        subject, "session.manage", current, _session_context(subject, current)
    )
    assert not decision.allowed


@pytest.mark.asyncio
async def test_high_risk_allow_fails_closed_when_audit_queue_is_full(authorization):
    await authorization.close()
    authorization._audit_queue = asyncio.Queue(maxsize=1)
    authorization._audit_queue.put_nowait(
        AuthAuditLog(
            audit_id="queued-audit",
            subject_id="system:test",
            source="system",
            action="identity.manage",
            resource_id="identity:v1::queued",
            decision="allow",
            reason="queued",
        )
    )
    owner = Subject.im(platform_instance="napcat", bot_account_id="bot", sender_id="42")
    current = Resource.session("default", "napcat:GroupMessage:room-a")
    decision = await authorization.authorize(
        owner,
        "identity.manage",
        current,
        _session_context(
            owner,
            current,
            platform_member_role="owner",
            platform_role_source="adapter",
        ),
    )
    assert not decision.allowed
    assert decision.reason == "audit_unavailable"


@pytest.mark.asyncio
async def test_binding_mutations_write_audit_records(authorization):
    owner = Subject.im(platform_instance="napcat", bot_account_id="bot", sender_id="42")
    target = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="84"
    )
    current = Resource.session("default", "napcat:GroupMessage:room-a")
    context = _session_context(
        owner,
        current,
        platform_member_role="owner",
        platform_role_source="adapter",
    )
    binding = await authorization.grant_binding(
        actor=owner,
        subject_id=target.id,
        role=Role.SESSION_ADMIN,
        scope_type="session",
        scope_id=current.id,
        config_id="default",
        context=context,
    )
    assert await authorization.revoke_binding(
        actor=owner, binding_id=binding.binding_id, context=context
    )

    records = await authorization.list_audit(subject_id=owner.id)
    assert {record.reason for record in records} >= {
        "binding_granted",
        "binding_revoked",
    }


@pytest.mark.asyncio
async def test_batch_revoke_consumes_one_exact_step_up_credential(authorization):
    account = DashboardAccount(
        account_id="root-account", username="root-account", password_hash="hash"
    )
    actor = Subject.dashboard_account(account.account_id)
    first_target = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    second_target = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="84"
    )
    first_session = Resource.session("default", "napcat:GroupMessage:room-a")
    second_session = Resource.session("default", "napcat:GroupMessage:room-b")
    async with authorization._db.get_db() as session:
        async with session.begin():
            session.add(account)
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=actor.id,
        role=Role.ROOT,
        scope_type="global",
        scope_id="global",
        config_id=None,
        enforce_actor=False,
    )
    first = await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=first_target.id,
        role=Role.SESSION_ADMIN,
        scope_type="session",
        scope_id=first_session.id,
        config_id="default",
        enforce_actor=False,
    )
    second = await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=second_target.id,
        role=Role.SESSION_ADMIN,
        scope_type="session",
        scope_id=second_session.id,
        config_id="default",
        enforce_actor=False,
    )
    binding_ids = [first.binding_id, second.binding_id]
    resource = await authorization.binding_revocation_batch_resource(binding_ids)
    issue_context = AuthContext(
        subject=actor,
        source="dashboard",
        config_id="default",
        authenticated=True,
        metadata={"dashboard_session_id": "session-1"},
    )
    assert (
        await authorization.authorize(actor, "identity.manage", resource, issue_context)
    ).reason == "step_up_required"
    credential_id, token = await authorization.issue_step_up(
        subject=actor,
        dashboard_session_id="session-1",
        action="identity.manage",
        resource=resource,
        context=issue_context,
        verified_method="password",
    )
    consuming_context = AuthContext(
        subject=actor,
        source="dashboard",
        config_id="default",
        authenticated=True,
        step_up_token=token,
        metadata={"dashboard_session_id": "session-1"},
    )

    assert (
        await authorization.revoke_bindings(
            actor=actor, binding_ids=binding_ids, context=consuming_context
        )
    ) == 2
    records = await authorization.list_audit(subject_id=actor.id)
    assert sum(record.step_up_id == credential_id for record in records) >= 2


@pytest.mark.asyncio
async def test_failed_step_up_factor_is_audited_without_secret_metadata(authorization):
    subject = Subject.dashboard_account("root-account")
    context = AuthContext(
        subject=subject,
        source="dashboard",
        authenticated=True,
        metadata={
            "dashboard_session_id": "session-1",
            "password": "must-not-be-stored",
        },
    )
    resource = Resource.named("system", "restart")

    assert authorization.record_step_up_failure(
        subject=subject,
        action="system.restart",
        resource=resource,
        context=context,
    )
    await authorization.flush_audit()

    records = await authorization.list_audit(subject_id=subject.id)
    record = next(
        item for item in records if item.reason == "step_up_verification_failed"
    )
    assert record.decision == "deny"
    assert "password" not in record.metadata_json
    assert "must-not-be-stored" not in str(record.metadata_json)
