"""Security-contract coverage for the unified authorization service."""

import asyncio
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from astrbot.core.auth.models import AuthContext, Resource, Role, Subject
from astrbot.core.auth.service import AuthorizationService, api_key_scopes_allow_action
from astrbot.core.db.po import AuthRoleBinding, DashboardAccount
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.utils.totp import TotpRuntimeState
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


@pytest.mark.asyncio
async def test_instance_binding_never_crosses_config(authorization):
    subject = Subject.im(platform_instance="onebot", bot_account_id="bot", sender_id="42")
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
    subject = Subject.im(platform_instance="napcat", bot_account_id="bot", sender_id="42")
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
        await authorization.authorize(subject, "session.manage", current, _context(subject, "default"))
    ).allowed
    assert not (
        await authorization.authorize(subject, "session.manage", other, _context(subject, "default"))
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
    assert not api_key_scopes_allow_action(["chat", "chat:admin"], "chat.impersonate_admin")


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

    await auth_service.update_dashboard_account(account_id=account.account_id, is_active=False)

    assert not (
        await authorization.authorize(
            subject, "identity.read", Resource.named("identity", "accounts"), context
        )
    ).allowed


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
            metadata={"token": "leak", "message": "full message", "url": "https://secret.example/a?token=leak"},
        ),
    )
    await authorization.flush_audit()
    records = await authorization.list_audit()
    assert records
    assert "token" not in records[0].metadata_json
    assert "message" not in records[0].metadata_json


@pytest.mark.asyncio
async def test_canonical_session_resource_is_config_isolated():
    first = Resource.session("config-a", "webchat:FriendMessage:session")
    second = Resource.session("config-b", "webchat:FriendMessage:session")
    assert first.id != second.id
    assert first.config_id != second.config_id
