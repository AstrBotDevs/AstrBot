"""Mock-based unit tests for LongTermMemory."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory
from astrbot.core.platform.message_type import MessageType


@pytest.fixture
def mock_acm():
    return MagicMock()


@pytest.fixture
def mock_context():
    return MagicMock()


@pytest.fixture
def ltm(mock_acm, mock_context):
    return LongTermMemory(mock_acm, mock_context)


@pytest.fixture
def mock_event():
    event = MagicMock()
    event.unified_msg_origin = "qq:group:123456"
    event.get_message_type.return_value = MessageType.GROUP_MESSAGE
    event.is_at_or_wake_command = False
    event.get_group_id.return_value = "123456"
    event.get_messages.return_value = []
    event.message_obj.sender.nickname = "TestUser"
    return event


class TestLongTermMemoryConstruction:
    """Construction and initial state."""

    def test_init_stores_deps(self, ltm, mock_acm, mock_context):
        assert ltm.acm is mock_acm
        assert ltm.context is mock_context

    def test_init_session_chats_is_defaultdict(self, ltm):
        assert ltm.session_chats["any_key"] == []

    @patch.object(LongTermMemory, "cfg", return_value={"max_cnt": 100, "image_caption": False, "enable_active_reply": False})
    def test_remove_session_returns_count(self, mock_cfg, ltm, mock_event):
        ltm.session_chats["qq:group:123456"] = ["msg1", "msg2"]
        cnt = 0
        import asyncio
        cnt = asyncio.run(ltm.remove_session(mock_event))
        assert cnt == 2
        assert "qq:group:123456" not in ltm.session_chats


class TestCfg:
    """Configuration extraction from context."""

    def test_cfg_reads_from_context(self, ltm, mock_context, mock_event):
        fake_ctx_cfg = {
            "provider_ltm_settings": {
                "group_message_max_cnt": "500",
                "image_caption": True,
                "image_caption_provider_id": "prov-1",
                "active_reply": {
                    "enable": True,
                    "method": "possibility_reply",
                    "possibility_reply": 0.5,
                    "whitelist": [],
                },
            },
            "provider_settings": {
                "image_caption_prompt": "Describe",
            },
        }
        mock_context.get_config.return_value = fake_ctx_cfg
        result = ltm.cfg(mock_event)
        assert result["max_cnt"] == 500
        assert result["image_caption"] is True
        assert result["enable_active_reply"] is True
        assert result["image_caption_prompt"] == "Describe"

    def test_cfg_handles_missing_max_cnt(self, ltm, mock_context, mock_event):
        mock_context.get_config.return_value = {
            "provider_ltm_settings": {},
            "provider_settings": {"image_caption_prompt": "x"},
        }
        result = ltm.cfg(mock_event)
        assert result["max_cnt"] == 300  # default fallback
        assert result["image_caption"] is False


class TestGetImageCaption:
    """Image caption fetching."""

    async def test_get_image_caption_uses_using_provider(self, ltm, mock_context):
        mock_provider = AsyncMock()
        mock_provider.text_chat = AsyncMock(return_value=MagicMock(completion_text="a cat"))
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_provider_by_id.return_value = None

        caption = await ltm.get_image_caption("http://img.jpg", "", "Describe")
        assert caption == "a cat"
        mock_provider.text_chat.assert_awaited_once()

    async def test_get_image_caption_uses_provider_by_id(self, ltm, mock_context):
        mock_provider = AsyncMock()
        mock_provider.text_chat = AsyncMock(return_value=MagicMock(completion_text="a dog"))
        mock_context.get_provider_by_id.return_value = mock_provider

        caption = await ltm.get_image_caption("http://img.jpg", "custom-provider", "Describe")
        assert caption == "a dog"

    async def test_get_image_caption_raises_on_missing_provider(self, ltm, mock_context):
        mock_context.get_provider_by_id.return_value = None
        with pytest.raises(Exception, match="没有找到 ID 为"):
            await ltm.get_image_caption("http://img.jpg", "missing-provider", "Describe")

    async def test_get_image_caption_raises_on_non_provider_type(self, ltm, mock_context):
        mock_context.get_provider_by_id.return_value = "not_a_provider"
        with pytest.raises(Exception, match="提供商类型错误"):
            await ltm.get_image_caption("http://img.jpg", "bad-provider", "Describe")


class TestNeedActiveReply:
    """Active reply decision logic."""

    async def test_need_active_reply_false_when_disabled(self, ltm, mock_event):
        with patch.object(LongTermMemory, "cfg", return_value={"enable_active_reply": False}):
            assert await ltm.need_active_reply(mock_event) is False

    async def test_need_active_reply_false_for_private(self, ltm, mock_event):
        mock_event.get_message_type.return_value = MessageType.FRIEND_MESSAGE
        with patch.object(LongTermMemory, "cfg", return_value={"enable_active_reply": True, "ar_whitelist": [], "ar_method": "possibility_reply", "ar_possibility": 1.0}):
            assert await ltm.need_active_reply(mock_event) is False

    async def test_need_active_reply_false_when_wake_command(self, ltm, mock_event):
        mock_event.is_at_or_wake_command = True
        with patch.object(LongTermMemory, "cfg", return_value={"enable_active_reply": True, "ar_whitelist": [], "ar_method": "possibility_reply", "ar_possibility": 1.0}):
            assert await ltm.need_active_reply(mock_event) is False

    async def test_need_active_reply_whitelist_filters(self, ltm, mock_event):
        with patch.object(LongTermMemory, "cfg", return_value={
            "enable_active_reply": True,
            "ar_whitelist": ["other:group:999"],
            "ar_method": "possibility_reply",
            "ar_possibility": 1.0,
        }):
            assert await ltm.need_active_reply(mock_event) is False

    async def test_need_active_reply_possibility_triggers(self, ltm, mock_event):
        with patch.object(LongTermMemory, "cfg", return_value={
            "enable_active_reply": True,
            "ar_whitelist": [],
            "ar_method": "possibility_reply",
            "ar_possibility": 1.0,
        }):
            assert await ltm.need_active_reply(mock_event) is True


class TestHandleMessage:
    """Message recording logic."""

    @patch.object(LongTermMemory, "get_image_caption", return_value="sunset")
    async def test_handle_message_plain_and_image(self, mock_get_caption, ltm, mock_event):
        from astrbot.api.message_components import Plain, Image

        mock_event.get_messages.return_value = [
            Plain(text="Hello "),
            Image(url="http://img.jpg"),
            Plain(text="world"),
        ]
        mock_event.get_message_type.return_value = MessageType.GROUP_MESSAGE
        with patch.object(LongTermMemory, "cfg", return_value={
            "max_cnt": 300,
            "image_caption": True,
            "image_caption_provider_id": "prov-1",
            "image_caption_prompt": "Describe",
            "enable_active_reply": False,
        }):
            await ltm.handle_message(mock_event)
            assert len(ltm.session_chats["qq:group:123456"]) == 1
            msg = ltm.session_chats["qq:group:123456"][0]
            assert "Hello" in msg
            assert "sunset" in msg
            assert "world" in msg

    async def test_handle_message_plain_only(self, ltm, mock_event):
        from astrbot.api.message_components import Plain

        mock_event.get_messages.return_value = [
            Plain(text="How are you?"),
        ]
        mock_event.get_message_type.return_value = MessageType.GROUP_MESSAGE
        with patch.object(LongTermMemory, "cfg", return_value={
            "max_cnt": 300,
            "image_caption": False,
            "enable_active_reply": False,
        }):
            await ltm.handle_message(mock_event)
            msg = ltm.session_chats["qq:group:123456"][0]
            assert "How are you?" in msg

    async def test_handle_message_ignores_private(self, ltm, mock_event):
        mock_event.get_message_type.return_value = MessageType.FRIEND_MESSAGE
        await ltm.handle_message(mock_event)
        assert "qq:group:123456" not in ltm.session_chats

    async def test_handle_message_trims_excess(self, ltm, mock_event):
        from astrbot.api.message_components import Plain

        mock_event.get_messages.return_value = [Plain(text="x")]
        with patch.object(LongTermMemory, "cfg", return_value={
            "max_cnt": 2,
            "image_caption": False,
            "enable_active_reply": False,
        }):
            ltm.session_chats["qq:group:123456"] = ["old1", "old2"]
            await ltm.handle_message(mock_event)
            msgs = ltm.session_chats["qq:group:123456"]
            assert len(msgs) == 2


class TestOnReqLLM:
    """LLM request modification."""

    async def test_on_req_llm_skips_when_no_history(self, ltm, mock_event):
        req = MagicMock()
        await ltm.on_req_llm(mock_event, req)
        req.assert_not_called()

    async def test_on_req_llm_adds_to_system_prompt(self, ltm, mock_event):
        ltm.session_chats["qq:group:123456"] = ["msg1", "msg2"]
        req = MagicMock()
        req.system_prompt = ""
        with patch.object(LongTermMemory, "cfg", return_value={"enable_active_reply": False}):
            await ltm.on_req_llm(mock_event, req)
            assert "msg1" in req.system_prompt
            assert "msg2" in req.system_prompt

    async def test_on_req_llm_active_reply_overrides_prompt(self, ltm, mock_event):
        ltm.session_chats["qq:group:123456"] = ["msg1"]
        req = MagicMock()
        req.prompt = "user query"
        req.contexts = ["old_ctx"]
        with patch.object(LongTermMemory, "cfg", return_value={"enable_active_reply": True}):
            await ltm.on_req_llm(mock_event, req)
            assert req.contexts == []
            assert "user query" in req.prompt


class TestAfterReqLLM:
    """Post-LLM response recording."""

    async def test_after_req_llm_records_response(self, ltm, mock_event):
        ltm.session_chats["qq:group:123456"] = []
        resp = MagicMock()
        resp.completion_text = "AI reply"
        with patch.object(LongTermMemory, "cfg", return_value={"max_cnt": 300}):
            await ltm.after_req_llm(mock_event, resp)
            stored = ltm.session_chats["qq:group:123456"]
            assert len(stored) == 1
            assert "AI reply" in stored[0]

    async def test_after_req_llm_skips_empty_response(self, ltm, mock_event):
        ltm.session_chats["qq:group:123456"] = ["existing"]
        resp = MagicMock()
        resp.completion_text = None
        await ltm.after_req_llm(mock_event, resp)
        assert len(ltm.session_chats["qq:group:123456"]) == 1

    async def test_after_req_llm_trims(self, ltm, mock_event):
        ltm.session_chats["qq:group:123456"] = ["m1", "m2", "m3"]
        resp = MagicMock()
        resp.completion_text = "new"
        with patch.object(LongTermMemory, "cfg", return_value={"max_cnt": 3}):
            await ltm.after_req_llm(mock_event, resp)
            assert len(ltm.session_chats["qq:group:123456"]) == 3
