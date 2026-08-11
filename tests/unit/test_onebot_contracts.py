from __future__ import annotations

import subprocess
import sys

import pytest

from astrbot.api.onebot import (
    NAPCAT_QQ_ACTIONS,
    ONEBOT_V11_ACTIONS,
    OneBotActionResult,
    OneBotEvent,
    OneBotMessageEvent,
    OneBotNoticeEvent,
    OneBotRequestEvent,
    OneBotSegment,
)


def test_onebot_import_does_not_load_concrete_sources() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import astrbot.api.onebot; print(any(m.startswith('astrbot.core.platform.sources.') for m in sys.modules))",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "False"


def test_message_dto_normalizes_ids_and_preserves_unknown_payload() -> None:
    event = OneBotEvent.from_payload(
        {
            "post_type": "message",
            "self_id": 10001,
            "time": 10,
            "message_type": "group",
            "message_id": 42,
            "real_id": 43,
            "message_seq": 44,
            "group_id": 123,
            "user_id": 456,
            "sender": {"user_id": 456, "nickname": "A", "future_sender_field": True},
            "message": [{"type": "future_segment", "data": {"x": 1}}],
            "future_event_field": {"enabled": True},
        }
    )
    assert isinstance(event, OneBotMessageEvent)
    assert event.self_id == "10001"
    assert event.message_id == "42"
    assert event.group_id == "123"
    assert event.segments == (OneBotSegment("future_segment", {"x": 1}),)
    assert event.payload["future_event_field"] == {"enabled": True}
    with pytest.raises(TypeError):
        event.payload["future_event_field"] = {}  # type: ignore[index]


def test_payload_nested_values_are_defensive_and_string_messages_are_segments() -> None:
    source = {"post_type": "message", "message": "hello", "nested": {"items": [1]}}
    event = OneBotEvent.from_payload(source)

    source["nested"]["items"].append(2)  # type: ignore[index]
    assert event.payload["nested"] == {"items": (1,)}
    assert isinstance(event, OneBotMessageEvent)
    assert event.segments == (OneBotSegment("text", {"text": "hello"}),)


def test_subclass_payloads_and_results_are_immutable() -> None:
    notice = OneBotEvent.from_payload(
        {"post_type": "notice", "notice_type": "group_upload", "user_id": 1}
    )
    assert isinstance(notice, OneBotNoticeEvent)
    with pytest.raises(TypeError):
        notice.notice_ids["user_id"] = "2"  # type: ignore[index]

    result = OneBotActionResult("get_status", data={"nested": {"ok": True}})
    with pytest.raises(TypeError):
        result.data["nested"]["ok"] = False  # type: ignore[index]


def test_capability_descriptor_catalog_covers_standard_and_napcat_actions() -> None:
    standard = {descriptor.name: descriptor for descriptor in ONEBOT_V11_ACTIONS}
    extensions = {descriptor.name: descriptor for descriptor in NAPCAT_QQ_ACTIONS}

    assert {
        "send",
        "send_private",
        "send_group",
        "delete",
        "get_message",
        "get_status",
        "set_group_ban",
        "set_friend_add_request",
        "get_group_msg_history",
    } <= standard.keys()
    assert {
        "send_like",
        "friend_poke",
        "group_poke",
        "send_group_notice",
        "get_online_file_messages",
        "send_group_ai_record",
    } <= extensions.keys()
    assert standard["delete"].wire_action == "delete_msg"
    assert extensions["send_group_notice"].wire_action == "_send_group_notice"
    assert standard["set_group_ban"].destructive is True
    assert standard["get_status"].read_only is True
    assert all(
        descriptor.input_model.fields
        for descriptor in standard.values()
        if descriptor.name not in {"get_login_info", "get_status", "get_version_info"}
    )
    assert all(descriptor.input_model is not None for descriptor in extensions.values())


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "post_type": "notice",
                "self_id": 1,
                "notice_type": "future",
                "group_id": 2,
            },
            OneBotNoticeEvent,
        ),
        (
            {
                "post_type": "request",
                "self_id": 1,
                "request_type": "future",
                "user_id": 2,
                "flag": 3,
            },
            OneBotRequestEvent,
        ),
    ],
)
def test_unknown_event_types_are_representable(payload: dict, expected: type) -> None:
    assert isinstance(OneBotEvent.from_payload(payload), expected)
