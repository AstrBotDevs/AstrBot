"""Explicit authorization doubles for component-level tests.

These helpers model a trusted, already-authorized runtime caller. They are for
component tests that exercise code after authorization has been covered
separately; production code always uses the runtime-owned service.
"""

from types import SimpleNamespace

from astrbot.core.auth.models import AuthContext, Resource, Subject


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
