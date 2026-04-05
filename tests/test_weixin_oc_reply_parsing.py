import asyncio
import time
from typing import Any

import pytest

from astrbot.api.message_components import Plain, Reply
from astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter import WeixinOCAdapter


def _make_adapter() -> WeixinOCAdapter:
    return WeixinOCAdapter(
        platform_config={"id": "weixin_oc_test"},
        platform_settings={},
        event_queue=asyncio.Queue(),
    )


def test_weixin_oc_recent_message_cache_prunes_expired_sessions():
    adapter = _make_adapter()
    adapter._recent_session_cache_ttl_s = 1
    adapter._max_recent_message_sessions = 10

    adapter._get_recent_message_cache("expired_session")
    adapter._recent_messages["expired_session"].updated_at = time.monotonic() - 5

    active_cache = adapter._get_recent_message_cache("active_session")
    assert active_cache.maxlen == adapter._recent_message_cache_size

    adapter._prune_recent_message_caches(now=time.monotonic())

    assert "expired_session" not in adapter._recent_messages
    assert "active_session" in adapter._recent_messages


def test_weixin_oc_recent_message_cache_prunes_oldest_sessions_on_overflow():
    adapter = _make_adapter()
    adapter._recent_session_cache_ttl_s = 10**12
    adapter._max_recent_message_sessions = 2

    adapter._get_recent_message_cache("session_1")
    adapter._recent_messages["session_1"].updated_at = 1.0
    adapter._get_recent_message_cache("session_2")
    adapter._recent_messages["session_2"].updated_at = 2.0
    adapter._get_recent_message_cache("session_3")
    adapter._recent_messages["session_3"].updated_at = 3.0

    adapter._prune_recent_message_caches(now=4.0)

    assert "session_1" not in adapter._recent_messages
    assert "session_2" in adapter._recent_messages
    assert "session_3" in adapter._recent_messages


@pytest.mark.asyncio
async def test_weixin_oc_builds_reply_component_from_direct_ref_text():
    adapter = _make_adapter()
    captured_events: list[Any] = []
    adapter.commit_event = lambda event: captured_events.append(event)  # type: ignore[method-assign]

    await adapter._handle_inbound_message(
        {
            "from_user_id": "user_1",
            "message_id": "msg_1",
            "create_time_ms": 1775408782000,
            "item_list": [
                {
                    "type": 1,
                    "ref_msg": {
                        "message_item": {
                            "type": 1,
                            "create_time_ms": 1775408781000,
                            "update_time_ms": 1775408781000,
                            "is_completed": True,
                            "text_item": {"text": "你好"},
                        }
                    },
                    "text_item": {"text": "引用了“你好”"},
                }
            ],
        }
    )

    assert len(captured_events) == 1
    event = captured_events[0]
    reply = event.message_obj.message[0]
    assert isinstance(reply, Reply)
    assert reply.message_str == "你好"
    assert reply.chain and isinstance(reply.chain[0], Plain)
    assert reply.chain[0].text == "你好"
    assert event.message_obj.message_str == "引用了“你好”"
    assert event.message_obj.is_reply is True
    assert event.message_obj.reply_kind == "text"
    assert event.message_obj.quoted_item_type == 1
    assert event.message_obj.quoted_text == "你好"
    assert event.message_obj.reply_to["strategy"] == "direct-ref-msg"


@pytest.mark.asyncio
async def test_weixin_oc_matches_reply_from_recent_message_cache():
    adapter = _make_adapter()
    captured_events: list[Any] = []
    adapter.commit_event = lambda event: captured_events.append(event)  # type: ignore[method-assign]
    adapter._cache_recent_message(
        "user_2",
        message_id="bot_msg_1",
        sender_id="weixin_oc_test",
        sender_nickname="weixin_oc_test",
        timestamp=1775408790,
        components=[Plain("上一条 Bot 消息")],
        message_str="上一条 Bot 消息",
        message_kind="text",
    )

    await adapter._handle_inbound_message(
        {
            "from_user_id": "user_2",
            "message_id": "msg_2",
            "create_time_ms": 1775408796000,
            "item_list": [
                {
                    "type": 1,
                    "ref_msg": {
                        "message_item": {
                            "create_time_ms": 1775408793000,
                            "update_time_ms": 1775408793000,
                            "is_completed": True,
                        }
                    },
                    "text_item": {"text": "这是对上一条的回复"},
                }
            ],
        }
    )

    assert len(captured_events) == 1
    event = captured_events[0]
    reply = event.message_obj.message[0]
    assert isinstance(reply, Reply)
    assert reply.id == "bot_msg_1"
    assert reply.sender_id == "weixin_oc_test"
    assert reply.message_str == "上一条 Bot 消息"
    assert event.message_obj.message_str == "这是对上一条的回复"
    assert event.message_obj.reply_kind == "text"
    assert event.message_obj.quoted_text == "上一条 Bot 消息"
    assert event.message_obj.reply_to["strategy"] == "nearest-message-by-timestamp"
    assert event.message_obj.reply_to["matched_message_id"] == "bot_msg_1"


@pytest.mark.asyncio
async def test_weixin_oc_message_text_does_not_include_quoted_prefix():
    adapter = _make_adapter()

    text = adapter._message_text_from_item_list(
        [
            {
                "type": 1,
                "ref_msg": {
                    "message_item": {
                        "type": 1,
                        "create_time_ms": 1775408781000,
                        "text_item": {"text": "你好"},
                    }
                },
                "text_item": {"text": "新的正文"},
            }
        ],
        include_ref_text=False,
    )

    assert text == "新的正文"
