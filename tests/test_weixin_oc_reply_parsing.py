import asyncio
import time
from typing import Any

import pytest

from astrbot.api.message_components import Image, Plain, Reply
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
                            "from_user_id": "quoted_user",
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
    assert reply.sender_id == "quoted_user"
    assert reply.sender_nickname == "quoted_user"
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
async def test_weixin_oc_send_cache_uses_original_components_without_item_conversion():
    adapter = _make_adapter()
    adapter.token = "token"
    adapter.account_id = "bot_account"
    adapter._context_tokens["user_3"] = "ctx"

    called = {"request": 0, "convert": 0}

    async def fake_request_json(*args, **kwargs):
        called["request"] += 1
        return {}

    async def fail_if_convert(_item_list):
        called["convert"] += 1
        raise AssertionError("send-path cache should not convert outbound item_list")

    adapter.client.request_json = fake_request_json  # type: ignore[method-assign]
    adapter._item_list_to_components = fail_if_convert  # type: ignore[method-assign]

    media_component = Image(file="file:///tmp/fake-image.jpg")

    ok = await adapter._send_items_to_session(
        "user_3",
        [{"type": adapter.IMAGE_ITEM_TYPE, "image_item": {"media": {}}}],
        cache_components=[media_component],
        cache_message_str="[图片]",
    )

    assert ok is True
    assert called["request"] == 1
    assert called["convert"] == 0
    cached = adapter._recent_messages["user_3"].messages[-1]
    assert cached.components == [media_component]
    assert cached.message_str == "[图片]"


@pytest.mark.asyncio
async def test_weixin_oc_text_send_cache_preserves_plain_components_by_default():
    adapter = _make_adapter()
    adapter.token = "token"
    adapter.account_id = "bot_account"
    adapter._context_tokens["user_text"] = "ctx"

    async def fake_request_json(*args, **kwargs):
        return {}

    adapter.client.request_json = fake_request_json  # type: ignore[method-assign]

    ok = await adapter._send_items_to_session(
        "user_text",
        [adapter._build_plain_text_item("bot reply text")],
    )

    assert ok is True
    cached = adapter._recent_messages["user_text"].messages[-1]
    assert len(cached.components) == 1
    assert isinstance(cached.components[0], Plain)
    assert cached.components[0].text == "bot reply text"
    assert cached.message_kind == "text"
    assert cached.message_str == "bot reply text"


@pytest.mark.asyncio
async def test_weixin_oc_invalid_ref_msg_does_not_mark_message_as_reply():
    adapter = _make_adapter()
    captured_events: list[Any] = []
    adapter.commit_event = lambda event: captured_events.append(event)  # type: ignore[method-assign]

    await adapter._handle_inbound_message(
        {
            "from_user_id": "user_invalid",
            "message_id": "msg_invalid",
            "create_time_ms": 1775408782000,
            "item_list": [
                {
                    "type": 1,
                    "ref_msg": {"message_item": "not-a-dict"},
                    "text_item": {"text": "正文"},
                }
            ],
        }
    )

    assert len(captured_events) == 1
    event = captured_events[0]
    assert not any(isinstance(comp, Reply) for comp in event.message_obj.message)
    assert event.message_obj.is_reply is False
    assert event.message_obj.ref_msg == {"message_item": "not-a-dict"}
    assert event.message_obj.reply_to == {"matched": False}


@pytest.mark.asyncio
async def test_weixin_oc_non_numeric_quoted_type_does_not_crash():
    adapter = _make_adapter()
    captured_events: list[Any] = []
    adapter.commit_event = lambda event: captured_events.append(event)  # type: ignore[method-assign]

    await adapter._handle_inbound_message(
        {
            "from_user_id": "user_bad_type",
            "message_id": "msg_bad_type",
            "create_time_ms": 1775408782000,
            "item_list": [
                {
                    "type": 1,
                    "ref_msg": {
                        "message_item": {
                            "type": "bad-type",
                            "from_user_id": "quoted_user",
                            "create_time_ms": 1775408781000,
                        }
                    },
                    "text_item": {"text": "正文"},
                }
            ],
        }
    )

    assert len(captured_events) == 1
    event = captured_events[0]
    assert event.message_obj.message_str == "正文"
    assert event.message_obj.quoted_item_type is None
    assert (
        event.message_obj.reply_kind is None
        or event.message_obj.reply_kind == "unknown"
    )


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
