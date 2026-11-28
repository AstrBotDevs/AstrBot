"""Per-conversation ChatUI options: one path from the request to the event."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.webchat.webchat_adapter import WebChatAdapter
from astrbot.dashboard.schemas import ChatThreadMessageRequest
from astrbot.dashboard.services.chat_service import ChatService


def _event(payload):
    adapter = object.__new__(WebChatAdapter)
    adapter.metadata = PlatformMetadata(name="webchat", description="t", id="webchat")
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "webchat"
    message.session_id = "webchat!alice!options"
    message.message_id = "m1"
    message.sender = MessageMember("alice", "alice")
    message.message = []
    message.message_str = "hello"
    message.raw_message = ("alice", "options", payload)
    return adapter.create_event(message)


def test_adapter_puts_options_on_the_event():
    from astrbot.core.astr_agent_runtime.permission_mode import _conversation_modes

    try:
        assert _event({"permission_mode": "root"}).get_extra("permission_mode") is None
        event = _event({"permission_mode": "workspace"})
        assert event.get_extra("permission_mode") == "workspace"
    finally:
        _conversation_modes.clear()


def test_request_models_reject_unknown_options():
    with pytest.raises(ValidationError):
        ChatThreadMessageRequest(message="hi", permission_mode="root")


@pytest.mark.asyncio
async def test_regenerate_forwards_chat_options():
    service = object.__new__(ChatService)
    service.running_convs = {}
    service.conv_mgr = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value="c1")
    )
    service.db = SimpleNamespace(
        get_platform_session_by_id=AsyncMock(
            return_value=SimpleNamespace(
                creator="alice", platform_id="webchat", is_group=False, session_id="s1"
            )
        ),
        get_platform_message_history_by_id=AsyncMock(
            return_value=SimpleNamespace(
                platform_id="webchat", user_id="s1", content={"type": "bot"}
            )
        ),
        conversation_store=SimpleNamespace(
            read=AsyncMock(
                return_value=SimpleNamespace(
                    revision=SimpleNamespace(head_seq=2, leaf_event_id="e2")
                )
            ),
            rewind_webchat=AsyncMock(
                return_value=SimpleNamespace(
                    content={"message": ["original"]}, turn_id="turn"
                )
            ),
        ),
    )
    options = {"permission_mode": "workspace"}
    payload = await service.prepare_regenerate_message_payload(
        "alice", {"session_id": "s1", "message_id": 2, **options}
    )
    assert {key: payload[key] for key in options} == options
    assert payload["message"] == ["original"]
    service.db.conversation_store.rewind_webchat.assert_awaited_once_with(
        "c1", 2, expected_head=2, expected_leaf="e2"
    )


# Permission mode on the options path.


def test_only_a_request_that_states_the_mode_changes_the_live_mode():
    from astrbot.core.astr_agent_runtime.permission_mode import _conversation_modes

    try:
        event = _event({"permission_mode": "workspace"})
        assert _conversation_modes[event.session_id] == "workspace"
        # A thread button click or a plugin view action carries no mode.
        assert _event({}).get_extra("permission_mode") is None
        assert _conversation_modes[event.session_id] == "workspace"
        _event({"permission_mode": "ask"})
        assert _conversation_modes[event.session_id] == "ask"
    finally:
        _conversation_modes.clear()
