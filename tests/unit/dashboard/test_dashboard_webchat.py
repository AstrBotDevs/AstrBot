from __future__ import annotations

import pytest

from tests.unit.dashboard.dashboard_lifecycle_support import *  # noqa: F403


@pytest.mark.asyncio
async def test_webchat_step_up_issues_session_bound_tool_bundle(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
    authenticated_header: dict,
):
    test_client = DashboardTestClient(app)
    session_response = await test_client.get(
        "/api/v1/chat/sessions/new", headers=authenticated_header
    )
    assert session_response.status_code == 200
    session_id = (await session_response.get_json())["data"]["session_id"]

    failed = await test_client.post(
        "/api/v1/authorization/webchat-step-up",
        json={"session_id": session_id, "password": "wrong-password"},
        headers=authenticated_header,
    )
    assert failed.status_code == 401
    assert "password" not in (await failed.get_json())["message"].lower()

    response = await test_client.post(
        "/api/v1/authorization/webchat-step-up",
        json={
            "session_id": session_id,
            "password": _resolve_dashboard_password(core_lifecycle_td),
        },
        headers=authenticated_header,
    )
    assert response.status_code == 200
    payload = await response.get_json()
    tokens = payload["data"]["tokens"]
    assert set(tokens) == {
        "tool.local_exec",
        "tool.python_exec",
        "tool.file_write",
        "tool.browser_control",
        "tool.mcp_write",
        "tool.computer_use",
    }
    assert all(isinstance(token, str) and token for token in tokens.values())

    async with core_lifecycle_td.db.get_db() as session:
        rows = list((await session.execute(select(AuthStepUpCredential))).scalars())
    assert len(rows) >= 6
    assert all(row.token_hash not in tokens.values() for row in rows[-6:])
    assert all(row.resource_id.startswith("session:v1:") for row in rows[-6:])


@pytest.mark.asyncio
async def test_webchat_step_up_recovers_unpersisted_dashboard_session(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
    authenticated_header: dict,
):
    """A new chat route may be visible before its platform session is stored."""

    session_id = str(uuid.uuid4())
    test_client = DashboardTestClient(app)
    response = await test_client.post(
        "/api/v1/authorization/webchat-step-up",
        json={
            "session_id": session_id,
            "password": _resolve_dashboard_password(core_lifecycle_td),
        },
        headers=authenticated_header,
    )
    assert response.status_code == 200
    platform_session = await core_lifecycle_td.db.get_platform_session_by_id(session_id)
    assert platform_session is not None
    assert platform_session.platform_id == "webchat"
    assert (
        platform_session.creator
        == core_lifecycle_td.astrbot_config["dashboard"]["username"]
    )


@pytest.mark.asyncio
async def test_webchat_step_up_accepts_fresh_totp_factor(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
    authenticated_header: dict,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    _, recovery_code_hash = generate_recovery_code()
    secret = pyotp.random_base32()
    try:
        await _set_dashboard_account_totp(core_lifecycle_td, secret, recovery_code_hash)
        session_response = await test_client.get(
            "/api/v1/chat/sessions/new", headers=authenticated_header
        )
        session_id = (await session_response.get_json())["data"]["session_id"]
        response = await test_client.post(
            "/api/v1/authorization/webchat-step-up",
            json={"session_id": session_id, "code": pyotp.TOTP(secret).now()},
            headers=authenticated_header,
        )
        assert response.status_code == 200
        assert set((await response.get_json())["data"]["tokens"]) == {
            "tool.local_exec",
            "tool.python_exec",
            "tool.file_write",
            "tool.browser_control",
            "tool.mcp_write",
            "tool.computer_use",
        }
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_webchat_step_up_http_chat_pipeline_context_matches_authorization(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
    authenticated_header: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Exercise endpoint issuance through ChatService and WakingCheck facts."""

    session_response = await DashboardTestClient(app).get(
        "/api/v1/chat/sessions/new",
        headers=authenticated_header,
    )
    session_id = (await session_response.get_json())["data"]["session_id"]
    client = DashboardTestClient(app)
    issued = await client.post(
        "/api/v1/authorization/webchat-step-up",
        json={
            "session_id": session_id,
            "password": _resolve_dashboard_password(core_lifecycle_td),
        },
        headers=authenticated_header,
    )
    assert issued.status_code == 200
    tokens = (await issued.get_json())["data"]["tokens"]

    captured: dict[str, object] = {}

    async def fake_build_chat_stream(username, post_data, **kwargs):
        captured["username"] = username
        captured["post_data"] = post_data
        captured["dashboard_principal"] = kwargs.get("dashboard_principal")

        async def empty_stream():
            if False:
                yield ""

        return empty_stream()

    monkeypatch.setattr(
        app.state.services.chat,
        "build_chat_stream",
        fake_build_chat_stream,
    )
    response = await client.post(
        "/api/v1/chat",
        json={
            "session_id": session_id,
            "message": [{"type": "plain", "text": "run"}],
            "_webchat_step_up_tokens": tokens,
        },
        headers=authenticated_header,
    )
    assert response.status_code == 200
    principal = captured["dashboard_principal"]
    assert isinstance(principal, dict)
    assert principal["step_up_tokens"] == tokens

    from astrbot.core.auth.models import Resource
    from astrbot.core.pipeline.waking_check.stage import WakingCheckStage
    from astrbot.core.platform.message_type import MessageType

    username = core_lifecycle_td.astrbot_config["dashboard"]["username"]
    umo = f"webchat:FriendMessage:webchat!{username}!{session_id}"

    class PipelineEvent:
        message_obj = type("Message", (), {"type": MessageType.FRIEND_MESSAGE})()
        platform_member_role = "member"
        platform_role_source = "none"

        def __init__(self):
            self._extras: dict[str, object] = {
                "_dashboard_principal": principal,
            }

        def get_extra(self, key=None, default=None):
            return self._extras if key is None else self._extras.get(key, default)

        def set_extra(self, key, value):
            self._extras[key] = value

        def get_platform_name(self):
            return "webchat"

        def get_sender_id(self):
            return username

        def get_sender_name(self):
            return username

        def get_self_id(self):
            return "webchat"

        def get_session_id(self):
            return umo

        def get_message_type(self):
            return MessageType.FRIEND_MESSAGE

    stage = WakingCheckStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "platform_settings": {
                    "friend_message_needs_wake_prefix": False,
                    "ignore_bot_self_message": False,
                    "ignore_at_all": False,
                    "unique_session": False,
                    "group_wake_policy": {},
                },
                "plugin_set": ["*"],
            },
            astrbot_config_id="default",
            plugin_catalog=SimpleNamespace(
                get_command_catalog=lambda *_args: SimpleNamespace(),
            ),
            preferences=SimpleNamespace(),
            plugins=SimpleNamespace(),
            handlers=SimpleNamespace(),
        )
    )
    event = PipelineEvent()
    await stage._attach_authorization(event)
    context = event.get_extra("auth_context")
    assert context.source == "webchat"
    assert context.message_type == "FriendMessage"
    assert context.platform_member_role == "member"
    assert context.platform_role_source == "none"
    assert context.config_id == "default"
    assert context.origin_session_resource_id == Resource.session("default", umo).id

    authorization = core_lifecycle_td.runtime.services.authorization
    subject = event.get_extra("auth_subject")
    for action, token in tokens.items():
        decision = await authorization.authorize(
            subject,
            action,
            Resource.named("tool", action, config_id="default"),
            context,
        )
        assert decision.allowed, (action, decision.reason)
