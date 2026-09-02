"""Security-contract coverage for the unified authorization service."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlmodel import select

from astrbot.core.auth.models import (
    WEBCHAT_INSTANCE_TOOL_ACTIONS,
    AuthContext,
    Decision,
    Resource,
    Role,
    Subject,
    utc_now,
)
from astrbot.core.auth.service import AuthorizationService
from astrbot.core.db.po import (
    AuthAuditLog,
    AuthRoleBinding,
    AuthStepUpCredential,
    DashboardAccount,
)
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.star.plugin_context import AuthorizationCapability
from astrbot.core.utils.totp import TotpRuntimeState
from astrbot.dashboard.api.auth import object_resource
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
            subject,
            "session.manage",
            current,
            _session_context(subject, current),
        )
    ).allowed
    assert not (
        await authorization.authorize(
            subject,
            "session.manage",
            other,
            _session_context(subject, other),
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


@pytest.mark.asyncio
async def test_dashboard_step_up_uses_the_resource_config_scope(authorization):
    account = DashboardAccount(
        account_id="dashboard-root",
        username="dashboard-root",
        password_hash="hash",
    )
    async with authorization._db.get_db() as session:
        async with session.begin():
            session.add(account)

    subject = Subject.dashboard_account(account.account_id, account.username)
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.ROOT,
        scope_type="global",
        scope_id="global",
        config_id=None,
        enforce_actor=False,
    )
    resource = Resource.session("default", "napcat:GroupMessage:room-a")
    issued_context = AuthContext(
        subject=subject,
        source="dashboard",
        config_id="default",
        authenticated=True,
        metadata={"dashboard_session_id": "session-1"},
    )
    _credential_id, token = await authorization.issue_step_up(
        subject=subject,
        dashboard_session_id="session-1",
        action="identity.manage",
        resource=resource,
        context=issued_context,
        verified_method="password",
    )

    decision = await authorization.authorize(
        subject,
        "identity.manage",
        resource,
        AuthContext(
            subject=subject,
            source="dashboard",
            authenticated=True,
            step_up_token=token,
            metadata={"dashboard_session_id": "session-1"},
        ),
    )

    assert decision.allowed


def test_api_key_scope_helpers_reject_wildcard_and_null():
    from astrbot.dashboard.services.api_key_scopes import (
        api_key_has_scope,
        effective_api_key_scopes,
    )

    assert effective_api_key_scopes(None) == []
    assert effective_api_key_scopes(["*"]) == []
    assert effective_api_key_scopes(["chat", "*"]) == ["chat"]
    assert api_key_has_scope(["chat"], "chat")
    assert not api_key_has_scope(["*"], "chat")


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


def test_dashboard_step_up_resource_parser_hashes_bot_ids_like_bot_routes():
    parsed_bot = _resource(
        SimpleNamespace(
            resource_type="bot",
            resource_id="napcat",
            config_id=None,
        )
    )

    assert parsed_bot == object_resource("bot", "napcat")


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
                "webchat_step_up_tokens": {"tool.local_exec": "raw-proof"},
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
    assert "webchat_step_up_tokens" not in records[0].metadata_json


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
    assert denied.reason == "cross_session_resource"

    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.SESSION_OWNER,
        scope_type="session",
        scope_id=target.id,
        config_id="default",
        enforce_actor=False,
    )
    still_denied = await capability.authorize_target_session(
        event,
        action="session.assign",
        umo=target.umo or "",
    )
    assert not still_denied.allowed
    assert still_denied.reason == "cross_session_resource"


@pytest.mark.asyncio
async def test_dashboard_cross_session_assign_requires_step_up(authorization):
    subject = Subject.dashboard_session("session-1")
    target = Resource.session("default", "napcat:GroupMessage:room-b")
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.INSTANCE_OPERATOR,
        scope_type="instance",
        scope_id="default",
        config_id="default",
        enforce_actor=False,
    )
    context = AuthContext(
        subject=subject,
        source="dashboard",
        config_id="default",
        authenticated=True,
        metadata={"dashboard_session_id": "session-1"},
    )
    denied = await authorization.authorize(subject, "session.assign", target, context)
    assert not denied.allowed
    assert denied.requires_step_up
    assert denied.reason == "step_up_required"

    _credential_id, token = await authorization.issue_step_up(
        subject=subject,
        dashboard_session_id="session-1",
        action="session.assign",
        resource=target,
        context=context,
        verified_method="password",
    )
    allowed = await authorization.authorize(
        subject,
        "session.assign",
        target,
        AuthContext(
            subject=subject,
            source="dashboard",
            config_id="default",
            authenticated=True,
            step_up_token=token,
            metadata={"dashboard_session_id": "session-1"},
        ),
    )
    assert allowed.allowed


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
async def test_private_im_origin_is_session_owner_of_that_session_only(authorization):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    current = Resource.session("default", "napcat:FriendMessage:user-42")
    other = Resource.session("default", "napcat:FriendMessage:user-99")
    context = _session_context(subject, current, message_type="FriendMessage")

    allowed = await authorization.authorize(subject, "session.manage", current, context)
    assert allowed.allowed
    assert allowed.effective_role is Role.SESSION_OWNER
    assert "private_session" in allowed.relation_sources

    denied = await authorization.authorize(subject, "session.manage", other, context)
    assert not denied.allowed
    assert denied.reason == "cross_session_resource"


@pytest.mark.asyncio
async def test_group_origin_including_unique_session_stays_member(authorization):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    group = Resource.session("default", "napcat:GroupMessage:room-a")
    unique = Resource.session("default", "napcat:GroupMessage:42_room-a")
    for resource in (group, unique):
        decision = await authorization.authorize(
            subject,
            "session.manage",
            resource,
            _session_context(subject, resource, message_type="GroupMessage"),
        )
        assert not decision.allowed
        assert decision.effective_role is Role.MEMBER
        assert "private_session" not in decision.relation_sources


@pytest.mark.asyncio
@pytest.mark.parametrize("message_type", ["GroupMessage", None, "friend"])
async def test_friendmessage_umo_does_not_promote_without_friend_type(
    authorization, message_type
):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    resource = Resource.session("default", "napcat:FriendMessage:user-42")
    kwargs = {} if message_type is None else {"message_type": message_type}
    decision = await authorization.authorize(
        subject,
        "session.manage",
        resource,
        _session_context(subject, resource, **kwargs),
    )
    assert not decision.allowed
    assert decision.effective_role is Role.MEMBER
    assert "private_session" not in decision.relation_sources


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_member_role", ["owner", "admin"])
async def test_friendmessage_ignores_context_platform_elevation(
    authorization, platform_member_role
):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    current = Resource.session("default", "napcat:FriendMessage:user-42")
    decision = await authorization.authorize(
        subject,
        "session.manage",
        current,
        _session_context(
            subject,
            current,
            message_type="FriendMessage",
            platform_member_role=platform_member_role,
            platform_role_source="adapter",
        ),
    )
    assert decision.allowed
    assert decision.effective_role is Role.SESSION_OWNER
    assert "private_session" in decision.relation_sources
    assert "adapter" not in decision.relation_sources
    assert "platform" not in decision.relation_sources


@pytest.mark.asyncio
async def test_friendmessage_ignores_persisted_platform_owner_fact(authorization):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    current = Resource.session("default", "napcat:FriendMessage:user-42")
    await authorization.record_platform_membership(
        subject=subject,
        resource=current,
        platform_instance="napcat",
        platform_role="owner",
        source="adapter",
    )
    decision = await authorization.authorize(
        subject,
        "session.manage",
        current,
        _session_context(
            subject,
            current,
            message_type="FriendMessage",
            platform_member_role="unknown",
            platform_role_source="none",
        ),
    )
    assert decision.allowed
    assert decision.effective_role is Role.SESSION_OWNER
    assert "private_session" in decision.relation_sources
    assert "platform" not in decision.relation_sources
    assert "adapter" not in decision.relation_sources


@pytest.mark.asyncio
async def test_guest_webchat_friendmessage_is_not_private_session_owner(authorization):
    guest = Subject.guest("webchat-alice")
    current = Resource.session(
        "default", "webchat:FriendMessage:webchat!alice!session-1"
    )
    decision = await authorization.authorize(
        guest, "session.manage", current, _webchat_context(guest, current)
    )
    assert not decision.allowed
    assert "private_session" not in decision.relation_sources


@pytest.mark.asyncio
async def test_authenticated_webchat_is_not_private_session_owner(authorization):
    subject = Subject.dashboard_account("webchat-alice", "alice")
    current = Resource.session(
        "default", "webchat:FriendMessage:webchat!alice!session-1"
    )
    decision = await authorization.authorize(
        subject, "session.manage", current, _webchat_context(subject, current)
    )
    assert not decision.allowed
    assert "private_session" not in decision.relation_sources


@pytest.mark.asyncio
async def test_dashboard_source_friendmessage_is_not_private_session_owner(
    authorization,
):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    current = Resource.session("default", "napcat:FriendMessage:user-42")
    context = AuthContext(
        subject=subject,
        source="dashboard",
        config_id="default",
        authenticated=True,
        origin_session_resource_id=current.id,
        message_type="FriendMessage",
    )
    decision = await authorization.authorize(
        subject, "session.manage", current, context
    )
    assert "private_session" not in decision.relation_sources


@pytest.mark.asyncio
async def test_friendmessage_type_does_not_own_groupmessage_origin(authorization):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    group = Resource.session("default", "napcat:GroupMessage:room-a")
    decision = await authorization.authorize(
        subject,
        "session.manage",
        group,
        _session_context(subject, group, message_type="FriendMessage"),
    )
    assert not decision.allowed
    assert decision.effective_role is Role.MEMBER
    assert "private_session" not in decision.relation_sources


@pytest.mark.asyncio
async def test_friendmessage_type_does_not_own_othermessage_origin(authorization):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    other = Resource.session("default", "napcat:OtherMessage:notice-1")
    decision = await authorization.authorize(
        subject,
        "session.manage",
        other,
        _session_context(subject, other, message_type="FriendMessage"),
    )
    assert not decision.allowed
    assert "private_session" not in decision.relation_sources


@pytest.mark.asyncio
async def test_friendmessage_type_on_group_umo_keeps_platform_owner_fact(
    authorization,
):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    group = Resource.session("default", "napcat:GroupMessage:room-a")
    decision = await authorization.authorize(
        subject,
        "session.manage",
        group,
        _session_context(
            subject,
            group,
            message_type="FriendMessage",
            platform_member_role="owner",
            platform_role_source="adapter",
        ),
    )
    assert decision.allowed
    assert decision.effective_role is Role.SESSION_OWNER
    assert "private_session" not in decision.relation_sources
    assert "adapter" in decision.relation_sources


@pytest.mark.asyncio
async def test_friendmessage_type_on_group_umo_keeps_persisted_platform_owner(
    authorization,
):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    group = Resource.session("default", "napcat:GroupMessage:room-a")
    await authorization.record_platform_membership(
        subject=subject,
        resource=group,
        platform_instance="napcat",
        platform_role="owner",
        source="adapter",
    )
    decision = await authorization.authorize(
        subject,
        "session.manage",
        group,
        _session_context(
            subject,
            group,
            message_type="FriendMessage",
            platform_member_role="unknown",
            platform_role_source="none",
        ),
    )
    assert decision.allowed
    assert decision.effective_role is Role.SESSION_OWNER
    assert "private_session" not in decision.relation_sources
    assert "platform" in decision.relation_sources


@pytest.mark.asyncio
async def test_private_session_owner_can_manage_current_members_but_not_delegate(
    authorization,
):
    owner = Subject.im(platform_instance="napcat", bot_account_id="bot", sender_id="42")
    target = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="84"
    )
    current = Resource.session("default", "napcat:FriendMessage:user-42")
    other = Resource.session("default", "napcat:FriendMessage:user-99")
    context = _session_context(owner, current, message_type="FriendMessage")

    manage = await authorization.authorize(owner, "identity.manage", current, context)
    assert manage.allowed
    assert manage.effective_role is Role.SESSION_OWNER
    assert "private_session" in manage.relation_sources

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
    await authorization.grant_binding(
        actor=owner,
        subject_id=target.id,
        role=Role.MEMBER,
        scope_type="session",
        scope_id=current.id,
        config_id="default",
        context=context,
    )

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
    with pytest.raises(PermissionError):
        await authorization.grant_binding(
            actor=owner,
            subject_id=target.id,
            role=Role.SESSION_ADMIN,
            scope_type="session",
            scope_id=other.id,
            config_id="default",
            context=context,
        )
    cross = await authorization.authorize(owner, "identity.manage", other, context)
    assert not cross.allowed
    assert cross.reason == "cross_session_resource"


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


def _webchat_context(subject: Subject, resource: Resource, **kwargs) -> AuthContext:
    """Create a WebChat pipeline context bound to one inbound session."""

    kwargs.setdefault("platform", "webchat")
    kwargs.setdefault("message_type", "FriendMessage")
    kwargs.setdefault("platform_member_role", "member")
    kwargs.setdefault("platform_role_source", "none")

    return AuthContext(
        subject=subject,
        source="webchat",
        config_id=resource.config_id,
        authenticated=subject.authenticated,
        origin_session_resource_id=resource.id,
        principal_subject_id=(
            subject.id if subject.kind == "dashboard-account" else None
        ),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_authenticated_webchat_uses_dashboard_account_global_role(authorization):
    account = DashboardAccount(
        account_id="webchat-root", username="alice", password_hash="hash"
    )
    subject = Subject.dashboard_account(account.account_id, account.username)
    current = Resource.session(
        "default", "webchat:FriendMessage:webchat!alice!session-1"
    )
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
        subject, "session.manage", current, _webchat_context(subject, current)
    )
    assert decision.allowed
    assert decision.effective_role == Role.ROOT


@pytest.mark.asyncio
async def test_guest_webchat_does_not_inherit_homonymous_account_role(authorization):
    account = DashboardAccount(
        account_id="webchat-root", username="alice", password_hash="hash"
    )
    account_subject = Subject.dashboard_account(account.account_id, account.username)
    guest = Subject.guest("webchat-alice")
    current = Resource.session(
        "default", "webchat:FriendMessage:webchat!alice!session-1"
    )
    async with authorization._db.get_db() as session:
        async with session.begin():
            session.add(account)
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=account_subject.id,
        role=Role.ROOT,
        scope_type="global",
        scope_id="global",
        config_id=None,
        enforce_actor=False,
    )

    decision = await authorization.authorize(
        guest,
        "session.manage",
        current,
        _webchat_context(guest, current, caller_declared_username="alice"),
    )
    assert not decision.allowed


@pytest.mark.asyncio
async def test_authenticated_webchat_high_risk_remains_dashboard_only(authorization):
    account = DashboardAccount(
        account_id="webchat-root", username="alice", password_hash="hash"
    )
    subject = Subject.dashboard_account(account.account_id, account.username)
    resource = Resource.named("system", "restart")
    current = Resource.session(
        "default", "webchat:FriendMessage:webchat!alice!session-1"
    )
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
        subject,
        "system.restart",
        resource,
        _webchat_context(subject, current, auth_strength="password"),
    )
    assert not decision.allowed
    assert decision.reason == "high_risk_dashboard_only"


@pytest.mark.asyncio
async def test_authenticated_webchat_instance_tools_require_fresh_proof(authorization):
    account = DashboardAccount(
        account_id="webchat-operator", username="alice", password_hash="hash"
    )
    subject = Subject.dashboard_account(account.account_id, account.username)
    current = Resource.session(
        "default", "webchat:FriendMessage:webchat!alice!session-tools"
    )
    async with authorization._db.get_db() as session:
        async with session.begin():
            session.add(account)
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.INSTANCE_OPERATOR,
        scope_type="instance",
        scope_id="default",
        config_id="default",
        enforce_actor=False,
    )
    context = _webchat_context(
        subject,
        current,
        metadata={"dashboard_session_id": "sid-tools"},
    )
    for action in WEBCHAT_INSTANCE_TOOL_ACTIONS:
        tool = Resource.named("tool", action, config_id="default")
        denied = await authorization.authorize(subject, action, tool, context)
        assert not denied.allowed
        assert denied.reason == "step_up_required"
        _credential_id, token = await authorization.issue_step_up(
            subject=subject,
            dashboard_session_id="sid-tools",
            action=action,
            resource=current,
            context=context,
            verified_method="password",
        )
        allowed_context = _webchat_context(
            subject,
            current,
            step_up_token=token,
            metadata={"dashboard_session_id": "sid-tools"},
        )
        allowed = await authorization.authorize(subject, action, tool, allowed_context)
        assert allowed.allowed


@pytest.mark.asyncio
async def test_webchat_step_up_proof_supports_multiple_tools_in_one_event(
    authorization,
):
    account = DashboardAccount(
        account_id="webchat-operator-run", username="alice", password_hash="hash"
    )
    subject = Subject.dashboard_account(account.account_id, account.username)
    current = Resource.session(
        "default", "webchat:FriendMessage:webchat!alice!session-run"
    )
    async with authorization._db.get_db() as session:
        async with session.begin():
            session.add(account)
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.INSTANCE_OPERATOR,
        scope_type="instance",
        scope_id="default",
        config_id="default",
        enforce_actor=False,
    )
    issued_context = _webchat_context(
        subject,
        current,
        metadata={"dashboard_session_id": "sid-run"},
    )
    tokens = {}
    for action in ("tool.local_exec", "tool.python_exec"):
        _credential_id, tokens[action] = await authorization.issue_step_up(
            subject=subject,
            dashboard_session_id="sid-run",
            action=action,
            resource=current,
            context=issued_context,
            verified_method="totp",
        )
    context = _webchat_context(
        subject,
        current,
        metadata={
            "dashboard_session_id": "sid-run",
            "webchat_step_up_tokens": tokens,
        },
    )
    for action in tokens:
        assert (
            await authorization.authorize(
                subject,
                action,
                Resource.named("tool", action, config_id="default"),
                context,
            )
        ).allowed
        # The cached, trusted event proof permits another invocation of the
        # same action without replaying the raw one-time token.
        assert (
            await authorization.authorize(
                subject,
                action,
                Resource.named("tool", f"{action}-again", config_id="default"),
                context,
            )
        ).allowed


@pytest.mark.asyncio
async def test_webchat_consumed_proof_cache_expires_with_the_step_up_ttl(
    authorization,
):
    account = DashboardAccount(
        account_id="webchat-proof-cache-expiry", username="alice", password_hash="hash"
    )
    subject = Subject.dashboard_account(account.account_id, account.username)
    current = Resource.session(
        "default", "webchat:FriendMessage:webchat!alice!cache-expiry"
    )
    async with authorization._db.get_db() as session:
        async with session.begin():
            session.add(account)
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.INSTANCE_OPERATOR,
        scope_type="instance",
        scope_id="default",
        config_id="default",
        enforce_actor=False,
    )
    issued_context = _webchat_context(
        subject, current, metadata={"dashboard_session_id": "sid-cache-expiry"}
    )
    _credential_id, token = await authorization.issue_step_up(
        subject=subject,
        dashboard_session_id="sid-cache-expiry",
        action="tool.local_exec",
        resource=current,
        context=issued_context,
        verified_method="password",
    )
    context = _webchat_context(
        subject,
        current,
        metadata={
            "dashboard_session_id": "sid-cache-expiry",
            "webchat_step_up_tokens": {"tool.local_exec": token},
        },
    )
    tool = Resource.named("tool", "shell", config_id="default")
    assert (
        await authorization.authorize(subject, "tool.local_exec", tool, context)
    ).allowed
    context.metadata["_webchat_step_up_consumed"]["tool.local_exec"]["expires_at"] = 0
    denied = await authorization.authorize(subject, "tool.local_exec", tool, context)
    assert not denied.allowed
    assert denied.reason == "step_up_required"


@pytest.mark.asyncio
async def test_webchat_step_up_proof_rejects_binding_mismatches_and_expiry(
    authorization,
):
    account = DashboardAccount(
        account_id="webchat-proof-bindings", username="alice", password_hash="hash"
    )
    subject = Subject.dashboard_account(account.account_id, account.username)
    current = Resource.session(
        "default", "webchat:FriendMessage:webchat!alice!session-proof"
    )
    other_session = Resource.session(
        "default", "webchat:FriendMessage:webchat!alice!other-session"
    )
    other_config = Resource.session(
        "config-b", "webchat:FriendMessage:webchat!alice!session-proof"
    )
    async with authorization._db.get_db() as session:
        async with session.begin():
            session.add(account)
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.INSTANCE_OPERATOR,
        scope_type="instance",
        scope_id="default",
        config_id="default",
        enforce_actor=False,
    )
    issued_context = _webchat_context(
        subject,
        current,
        metadata={"dashboard_session_id": "sid-proof"},
    )
    credential_id, token = await authorization.issue_step_up(
        subject=subject,
        dashboard_session_id="sid-proof",
        action="tool.local_exec",
        resource=current,
        context=issued_context,
        verified_method="password",
    )

    async def decide(
        candidate_subject: Subject,
        candidate_resource: Resource,
        *,
        sid: str = "sid-proof",
        action: str = "tool.local_exec",
        token_map: dict[str, str] | None = None,
    ):
        return await authorization.authorize(
            candidate_subject,
            action,
            Resource.named("tool", "shell", config_id=candidate_resource.config_id),
            _webchat_context(
                candidate_subject,
                candidate_resource,
                metadata={
                    "dashboard_session_id": sid,
                    "webchat_step_up_tokens": token_map or {"tool.local_exec": token},
                },
            ),
        )

    assert not (await decide(subject, current, sid="other-dashboard-sid")).allowed
    assert not (
        await decide(
            Subject.dashboard_account("other-account", "alice"),
            current,
        )
    ).allowed
    assert not (await decide(subject, other_session)).allowed
    assert not (await decide(subject, other_config)).allowed
    assert not (
        await decide(
            subject,
            current,
            action="tool.python_exec",
            token_map={"tool.local_exec": token},
        )
    ).allowed

    concurrent = await asyncio.gather(
        decide(subject, current),
        decide(subject, current),
    )
    assert sum(item.allowed for item in concurrent) == 1

    async with authorization._db.get_db() as session:
        async with session.begin():
            credential = (
                await session.execute(
                    select(AuthStepUpCredential).where(
                        AuthStepUpCredential.credential_id == credential_id
                    )
                )
            ).scalar_one()
            credential.expires_at = utc_now() - timedelta(seconds=1)
    assert not (await decide(subject, current)).allowed


@pytest.mark.asyncio
async def test_webchat_session_roles_do_not_gain_instance_tools(authorization):
    account = DashboardAccount(
        account_id="webchat-member", username="alice", password_hash="hash"
    )
    subject = Subject.dashboard_account(account.account_id, account.username)
    current = Resource.session(
        "default", "webchat:FriendMessage:webchat!alice!session-member"
    )
    async with authorization._db.get_db() as session:
        async with session.begin():
            session.add(account)
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.SESSION_ADMIN,
        scope_type="session",
        scope_id=current.id,
        config_id="default",
        enforce_actor=False,
    )
    decision = await authorization.authorize(
        subject,
        "tool.local_exec",
        Resource.named("tool", "shell", config_id="default"),
        _webchat_context(
            subject,
            current,
            metadata={"dashboard_session_id": "sid-member"},
        ),
    )
    assert not decision.allowed
    assert decision.reason == "role_scope_denied"


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


def test_action_registry_covers_frozen_actions():
    from astrbot.core.auth.models import ACTIONS, HIGH_RISK_ACTIONS
    from astrbot.core.auth.registry import (
        ACTION_POLICIES,
        ACTION_ROLE_GRANTS,
        policy_for,
    )

    assert set(ACTION_ROLE_GRANTS) == set(ACTIONS)
    assert set(ACTION_POLICIES) == set(ACTIONS)
    for action in HIGH_RISK_ACTIONS:
        policy = policy_for(action)
        assert policy is not None
        assert policy.risk == "high"
        assert policy.requires_step_up
    assert policy_for("plugin:example:publish") is not None
    assert policy_for("provider.credentials.read") is None
    assert policy_for("tool.file.write") is None


def test_mcp_dashboard_collection_routes_are_valid_resources():
    from astrbot.core.auth.registry import policy_for

    for action in ("tool.mcp_read", "tool.mcp_write"):
        policy = policy_for(action)
        assert policy is not None
        assert "dashboard-api" in policy.resource_types


def test_filesystem_actions_have_expected_roles_and_risk():
    from astrbot.core.auth.models import HIGH_RISK_ACTIONS
    from astrbot.core.auth.registry import ACTION_ROLE_GRANTS, policy_for

    assert ACTION_ROLE_GRANTS["filesystem.read"] == frozenset(
        {Role.OPERATOR, Role.ROOT}
    )
    assert ACTION_ROLE_GRANTS["filesystem.write"] == frozenset(
        {Role.OPERATOR, Role.ROOT}
    )
    assert ACTION_ROLE_GRANTS["filesystem.manage"] == frozenset({Role.ROOT})
    assert "filesystem.manage" in HIGH_RISK_ACTIONS
    assert "filesystem.read" not in HIGH_RISK_ACTIONS
    assert "filesystem.write" not in HIGH_RISK_ACTIONS
    for action in ("filesystem.read", "filesystem.write", "filesystem.manage"):
        policy = policy_for(action)
        assert policy is not None
        assert "filesystem" in policy.resource_types


def test_filesystem_object_resource_handles_unicode_and_dots():
    resource = object_resource("filesystem", "配置/空间 文件.json")
    assert resource.type == "filesystem"
    assert resource.id.startswith("filesystem:v1::")
    assert "配置" not in resource.id


def test_filesystem_collection_resource_is_stable_for_step_up():
    from astrbot.dashboard.api.authorization import _resource

    payload = type(
        "Payload",
        (),
        {"resource_type": "filesystem", "resource_id": "collection", "config_id": None},
    )()
    assert _resource(payload).id == Resource.named("filesystem", "collection").id


def test_plugin_and_agent_subjects_are_execution_components():
    plugin = Subject.plugin("weather")
    agent = Subject.agent("sub-1")
    assert plugin.kind == "plugin"
    assert agent.kind == "agent"
    assert plugin.id == "plugin:weather"
    assert not plugin.id.startswith("dashboard-account:")
    assert not agent.id.startswith("im:")


@pytest.mark.asyncio
async def test_plugin_subject_cannot_inherit_root_or_forge_system(authorization):
    plugin = Subject.plugin("weather")
    resource = Resource.named("system", "restart")
    context = AuthContext(
        subject=plugin,
        source="plugin",
        config_id="default",
        authenticated=True,
    )
    decision = await authorization.authorize(
        plugin, "system.restart", resource, context
    )
    assert not decision.allowed
    assert decision.effective_role not in {Role.ROOT, Role.OPERATOR}


@pytest.mark.asyncio
async def test_v2_shadow_matches_v1_for_session_and_api_key_boundaries(authorization):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    current = Resource.session("default", "napcat:GroupMessage:room-a")
    other = Resource.session("default", "napcat:GroupMessage:room-b")
    await authorization.record_platform_membership(
        subject=subject,
        resource=current,
        platform_instance="napcat",
        platform_role="owner",
        source="adapter",
    )
    current_ok = await authorization.authorize(
        subject,
        "session.manage",
        current,
        _session_context(
            subject,
            current,
            platform_member_role="owner",
            platform_role_source="adapter",
        ),
    )
    cross = await authorization.authorize(
        subject, "session.manage", other, _session_context(subject, current)
    )
    assert current_ok.allowed
    assert not cross.allowed
    key = Subject.api_key("key-1")
    key_context = AuthContext(
        subject=key,
        source="api_key",
        config_id="default",
        authenticated=True,
        api_scopes=("*",),
    )
    wildcard = await authorization.authorize(key, "session.read", current, key_context)
    assert not wildcard.allowed
    assert wildcard.reason == "api_key_capability_denied"


@pytest.mark.asyncio
async def test_api_key_capability_is_exact_and_rejects_high_risk(authorization):
    from astrbot.core.db.po import AuthCapability

    key = Subject.api_key("cap-key")
    resource = Resource.session("default", "webchat:FriendMessage:user-1")
    async with authorization._db.get_db() as session:
        async with session.begin():
            session.add(
                AuthCapability(
                    subject_id=key.id,
                    action="session.read",
                    resource_type=resource.type,
                    resource_id=resource.id,
                    config_id="default",
                )
            )
    assert await authorization._capability_allows(key, "session.read", resource)
    assert not (
        await authorization._capability_allows(key, "data.export_all", resource)
    )
    other = Resource.session("default", "webchat:FriendMessage:other")
    assert not await authorization._capability_allows(key, "session.read", other)
    allowed = await authorization.authorize(
        key,
        "session.read",
        resource,
        AuthContext(
            subject=key, source="api_key", config_id="default", authenticated=True
        ),
    )
    assert allowed.allowed
    assert allowed.matched_relations == ("capability",)


@pytest.mark.asyncio
async def test_grant_capability_uses_store_upsert_and_revives(authorization):
    key = Subject.api_key("store-cap")
    resource = Resource.named("provider", "schema", config_id="default")
    first = await authorization.grant_capability(
        subject=key,
        action="provider.read",
        resource=resource,
        created_by="alice",
    )
    second = await authorization.grant_capability(
        subject=key,
        action="provider.read",
        resource=resource,
        created_by="bob",
    )

    assert first.capability_id == second.capability_id
    assert second.created_by == "bob"
    assert second.revoked_at is None
    assert await authorization._capability_allows(key, "provider.read", resource)


@pytest.mark.asyncio
async def test_upgrade_preflight_blocks_wildcard_and_unmapped_bindings(authorization):
    from astrbot.core.auth.preflight import inspect_authorization_upgrade
    from astrbot.core.db.po import ApiKey

    async with authorization._db.get_db() as session:
        async with session.begin():
            session.add(
                ApiKey(
                    key_id="wild-1",
                    name="wild",
                    key_hash="hash-wild",
                    key_prefix="sk-wild",
                    scopes=["*"],
                    created_by="test",
                )
            )
    report = await inspect_authorization_upgrade(authorization._db)
    assert not report.ok
    assert any(item.startswith("api_key_wildcard:") for item in report.blocking)

    async with authorization._db.get_db() as session:
        async with session.begin():
            session.add(
                ApiKey(
                    key_id="null-1",
                    name="null",
                    key_hash="hash-null",
                    key_prefix="sk-null",
                    scopes=None,
                    created_by="test",
                )
            )
    report = await inspect_authorization_upgrade(authorization._db)
    assert any(item.startswith("api_key_null_scope:") for item in report.blocking)

    async with authorization._db.get_db() as session:
        async with session.begin():
            session.add(
                ApiKey(
                    key_id="legacy-chat",
                    name="legacy-chat",
                    key_hash="hash-chat",
                    key_prefix="sk-chat",
                    scopes=["chat"],
                    created_by="test",
                )
            )
    report = await inspect_authorization_upgrade(authorization._db)
    assert any(
        item.startswith("api_key_missing_capabilities:") for item in report.blocking
    )
    assert "legacy-chat" in report.rebuild_api_keys


@pytest.mark.asyncio
async def test_im_session_binding_requires_full_im_context(authorization):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    resource = Resource.session("default", "napcat:GroupMessage:room-a")
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.SESSION_ADMIN,
        scope_type="session",
        scope_id=resource.id,
        config_id="default",
        enforce_actor=False,
    )
    denied = await authorization.authorize(
        subject,
        "session.manage",
        resource,
        AuthContext(subject=subject, source="im", authenticated=True),
    )
    assert not denied.allowed
    assert denied.reason in {
        "missing_context_config",
        "missing_context_origin_session",
    }
    assert (
        await authorization.authorize(
            subject,
            "session.manage",
            resource,
            _session_context(subject, resource),
        )
    ).allowed


@pytest.mark.asyncio
async def test_preflight_parses_canonical_session_bindings(authorization):
    from astrbot.core.auth.preflight import inspect_authorization_upgrade
    from astrbot.core.db.po import AuthRoleBinding

    resource = Resource.session("default", "napcat:GroupMessage:room-a")
    async with authorization._db.get_db() as session:
        async with session.begin():
            session.add(
                AuthRoleBinding(
                    subject_id="im:napcat:bot:1",
                    role=Role.SESSION_ADMIN.value,
                    scope_type="session",
                    scope_id="session:v1:not-valid",
                    config_id="default",
                    source="explicit",
                )
            )
            session.add(
                AuthRoleBinding(
                    subject_id="im:napcat:bot:2",
                    role=Role.SESSION_ADMIN.value,
                    scope_type="session",
                    scope_id=resource.id,
                    config_id="other",
                    source="explicit",
                )
            )
    report = await inspect_authorization_upgrade(authorization._db)
    assert any(item.startswith("non_canonical_session:") for item in report.blocking)
    assert any(item.startswith("session_config_mismatch:") for item in report.blocking)


def test_chat_scope_emits_webchat_socket_capability():
    from astrbot.core.auth.registry import dashboard_api_capability_specs

    socket = Resource.named("webchat", "socket")
    specs = dashboard_api_capability_specs(["chat"])
    assert ("session.read", "webchat", socket.id) in specs


def test_provider_scope_capabilities_use_the_default_config_resource():
    from astrbot.core.auth.registry import dashboard_api_capability_specs

    schema = Resource.named("provider", "schema", config_id="default")
    sources = Resource.named("provider-source", "collection", config_id="default")
    specs = dashboard_api_capability_specs(["provider"])
    assert ("provider.read", schema.type, schema.id) in specs
    assert ("provider.read", sources.type, sources.id) in specs


@pytest.mark.asyncio
async def test_action_policy_rejects_wrong_resource_type_and_missing_im_context(
    authorization,
):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    session = Resource.session("default", "napcat:GroupMessage:room-a")
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.INSTANCE_OPERATOR,
        scope_type="instance",
        scope_id="default",
        config_id="default",
        enforce_actor=False,
    )
    wrong_type = await authorization.authorize(
        subject,
        "provider.manage",
        session,
        _session_context(subject, session),
    )
    assert not wrong_type.allowed
    assert wrong_type.reason == "resource_type_denied"

    missing = await authorization.authorize(
        subject,
        "session.manage",
        session,
        AuthContext(
            subject=subject,
            source="im",
            authenticated=True,
            platform_member_role="owner",
            platform_role_source="adapter",
        ),
    )
    assert not missing.allowed
    assert missing.reason in {
        "missing_context_config",
        "missing_context_origin_session",
    }


@pytest.mark.asyncio
async def test_decisions_keep_all_matched_relations_not_only_highest_role(
    authorization,
):
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    session = Resource.session("default", "napcat:GroupMessage:room-a")
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.INSTANCE_OPERATOR,
        scope_type="instance",
        scope_id="default",
        config_id="default",
        enforce_actor=False,
    )
    await authorization.record_platform_membership(
        subject=subject,
        resource=session,
        platform_instance="napcat",
        platform_role="owner",
        source="adapter",
    )
    decision = await authorization.authorize(
        subject,
        "session.manage",
        session,
        _session_context(
            subject,
            session,
            platform_member_role="owner",
            platform_role_source="adapter",
        ),
    )
    assert decision.allowed
    assert "instance_operator" in decision.matched_relations
    assert "owner" in decision.matched_relations
    assert "binding" in decision.relation_sources
    assert decision.effective_role == Role.INSTANCE_OPERATOR


@pytest.mark.asyncio
async def test_start_blocks_when_preflight_finds_wildcard_key(tmp_path):
    from astrbot.core.auth.preflight import inspect_authorization_upgrade
    from astrbot.core.db.po import ApiKey
    from astrbot.core.db.sqlite import SQLiteDatabase

    db = SQLiteDatabase(str(tmp_path / "preflight-start.db"))
    await db.initialize()
    async with db.get_db() as session:
        async with session.begin():
            session.add(
                ApiKey(
                    key_id="wild-start",
                    name="wild",
                    key_hash="hash-start",
                    key_prefix="sk-start",
                    scopes=["*"],
                    created_by="test",
                )
            )
    service = AuthorizationService(db)
    with pytest.raises(RuntimeError, match="preflight"):
        await service.start()
    report = await inspect_authorization_upgrade(db)
    assert any(item.startswith("api_key_wildcard:") for item in report.blocking)
    await db.close()


@pytest.mark.asyncio
async def test_start_blocks_legacy_scoped_key_without_capabilities(tmp_path):
    from astrbot.core.auth.preflight import inspect_authorization_upgrade
    from astrbot.core.db.po import ApiKey
    from astrbot.core.db.sqlite import SQLiteDatabase

    db = SQLiteDatabase(str(tmp_path / "preflight-legacy.db"))
    await db.initialize()
    async with db.get_db() as session:
        async with session.begin():
            session.add(
                ApiKey(
                    key_id="legacy-chat-start",
                    name="legacy-chat",
                    key_hash="hash-legacy",
                    key_prefix="sk-legacy",
                    scopes=["chat"],
                    created_by="test",
                )
            )
    service = AuthorizationService(db)
    with pytest.raises(RuntimeError, match="preflight"):
        await service.start()
    report = await inspect_authorization_upgrade(db)
    assert any(
        item == "api_key_missing_capabilities:legacy-chat-start"
        for item in report.blocking
    )
    await db.close()
