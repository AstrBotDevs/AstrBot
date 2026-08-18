"""Explicit authorization doubles for component-level tests.

These helpers model a trusted, already-authorized runtime caller. They are for
component tests that exercise code after authorization has been covered
separately; production code always uses the runtime-owned service.
"""

from types import SimpleNamespace

from astrbot.core.auth.models import AuthContext, Resource, Subject


def session_context(subject: Subject, resource: Resource, **kwargs) -> AuthContext:
    return AuthContext(
        subject=subject,
        source="im",
        config_id=resource.config_id,
        authenticated=subject.authenticated,
        origin_session_resource_id=resource.id,
        **kwargs,
    )


async def assert_platform_role_stays_in_session(
    authorization,
    *,
    platform_instance: str,
    sender_id: str,
    platform_role: str,
    current_umo: str,
    other_umo: str,
    config_id: str = "default",
    other_config_id: str = "other",
    bot_account_id: str = "bot",
) -> None:
    subject = Subject.im(
        platform_instance=platform_instance,
        bot_account_id=bot_account_id,
        sender_id=sender_id,
    )
    current = Resource.session(config_id, current_umo)
    other = Resource.session(config_id, other_umo)
    other_config = Resource.session(other_config_id, current_umo)
    await authorization.record_platform_membership(
        subject=subject,
        resource=current,
        platform_instance=platform_instance,
        platform_role=platform_role,
        source="adapter",
    )
    current_context = session_context(
        subject,
        current,
        platform=platform_instance,
        platform_member_role=platform_role,
        platform_role_source="adapter",
    )
    allowed = await authorization.authorize(
        subject, "session.manage", current, current_context
    )
    assert allowed.allowed is (platform_role in {"owner", "admin"})
    if platform_role in {"owner", "admin"}:
        assert allowed.effective_role is not None
        assert allowed.effective_role.value in {"session_owner", "session_admin"}
        assert allowed.effective_role.value not in {"operator", "root"}
    assert not (
        await authorization.authorize(
            subject,
            "session.manage",
            other,
            current_context,
        )
    ).allowed
    assert not (
        await authorization.authorize(
            subject,
            "session.manage",
            other,
            session_context(subject, other, platform=platform_instance),
        )
    ).allowed
    assert not (
        await authorization.authorize(
            subject,
            "session.manage",
            other_config,
            session_context(subject, other_config, platform=platform_instance),
        )
    ).allowed


class AuthorizationServiceStub:
    """Small action allow-list fake matching the runtime service interface."""

    __test__ = False

    def __init__(self, *allowed_actions: str) -> None:
        self.allowed_actions = frozenset(allowed_actions)

    async def authorize(self, _subject, action, _resource, _context):
        return SimpleNamespace(
            allowed=action in self.allowed_actions,
            requires_step_up=False,
        )


def attach_authorized_tool_context(
    event: object,
    runtime: object,
    *allowed_actions: str,
    config_id: str = "default",
) -> None:
    """Attach a trusted test principal and an explicit action allow-list."""

    subject = Subject.im(
        platform_instance="test-platform",
        bot_account_id="test-bot",
        sender_id="test-user",
    )
    setattr(event, "subject", subject)
    setattr(
        event,
        "resource",
        Resource.session(config_id, "webchat:FriendMessage:test-user"),
    )
    setattr(
        event,
        "auth_context",
        AuthContext(
            subject=subject,
            source="im",
            config_id=config_id,
            authenticated=True,
        ),
    )
    setattr(runtime, "authorization", AuthorizationServiceStub(*allowed_actions))


TestAuthorizationService = AuthorizationServiceStub
