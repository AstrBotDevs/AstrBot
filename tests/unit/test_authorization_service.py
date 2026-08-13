"""Security-contract coverage for the unified authorization service."""

import asyncio

import pytest
import pytest_asyncio

from astrbot.core.auth.models import AuthContext, Resource, Role, Subject
from astrbot.core.auth.service import AuthorizationService, api_key_scopes_allow_action
from astrbot.core.db.sqlite import SQLiteDatabase


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
    assert api_key_scopes_allow_action(["chat", "chat:admin"], "chat.impersonate_admin")


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
async def test_legacy_tool_permission_migration_is_idempotent(authorization):
    class Preferences:
        def __init__(self):
            self.values = {
                "tool_permissions": {
                    "_default": {"safe_tool": "member", "danger_tool": "admin"}
                }
            }

        async def global_get(self, key, default=None):
            return self.values.get(key, default)

        async def global_put(self, key, value):
            self.values[key] = value

    preferences = Preferences()
    assert await authorization.migrate_legacy_tool_permissions(preferences) == 2
    assert await authorization.migrate_legacy_tool_permissions(preferences) == 0


@pytest.mark.asyncio
async def test_canonical_session_resource_is_config_isolated():
    first = Resource.session("config-a", "webchat:FriendMessage:session")
    second = Resource.session("config-b", "webchat:FriendMessage:session")
    assert first.id != second.id
    assert first.config_id != second.config_id
