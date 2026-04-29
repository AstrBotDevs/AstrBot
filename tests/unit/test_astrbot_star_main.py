"""Mock-based unit tests for AstrBot builtin star (Main)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Plain
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.builtin_stars.astrbot.main import Main


@pytest.fixture
def mock_star_context():
    ctx = MagicMock()
    ctx.astrbot_config_mgr = MagicMock()
    return ctx


@pytest.fixture
def star(mock_star_context):
    return Main(mock_star_context)


class TestMainConstruction:
    """Construction and LTM initialisation."""

    def test_init_stores_context(self, star, mock_star_context):
        assert star.context is mock_star_context

    @patch("astrbot.builtin_stars.astrbot.main.LongTermMemory")
    def test_init_creates_ltm(self, mock_ltm_cls, mock_star_context):
        mock_ltm_instance = MagicMock()
        mock_ltm_cls.return_value = mock_ltm_instance
        s = Main(mock_star_context)
        mock_ltm_cls.assert_called_once_with(
            mock_star_context.astrbot_config_mgr, mock_star_context
        )
        assert s.ltm is mock_ltm_instance

    @patch("astrbot.builtin_stars.astrbot.main.logger")
    @patch("astrbot.builtin_stars.astrbot.main.LongTermMemory", side_effect=ValueError("fail"))
    def test_init_handles_ltm_failure(self, mock_ltm_cls, mock_logger, mock_star_context):
        s = Main(mock_star_context)
        assert s.ltm is None
        mock_logger.error.assert_called()


class TestLtmEnabled:
    """ltm_enabled helper."""

    def test_ltm_enabled_true_when_group_icl(self, star):
        event = MagicMock()
        event.unified_msg_origin = "qq:group:1"
        star.context.get_config.return_value = {
            "provider_ltm_settings": {
                "group_icl_enable": True,
                "active_reply": {"enable": False},
            },
        }
        assert star.ltm_enabled(event) is True

    def test_ltm_enabled_true_when_active_reply(self, star):
        event = MagicMock()
        event.unified_msg_origin = "qq:group:1"
        star.context.get_config.return_value = {
            "provider_ltm_settings": {
                "group_icl_enable": False,
                "active_reply": {"enable": True},
            },
        }
        assert star.ltm_enabled(event) is True

    def test_ltm_enabled_false_when_both_disabled(self, star):
        event = MagicMock()
        event.unified_msg_origin = "qq:group:1"
        star.context.get_config.return_value = {
            "provider_ltm_settings": {
                "group_icl_enable": False,
                "active_reply": {"enable": False},
            },
        }
        assert star.ltm_enabled(event) is False


class TestOnMessage:
    """on_message handler."""

    @pytest.mark.asyncio
    async def test_on_message_skips_when_no_plain_or_image(self, star):
        event = MagicMock()
        event.message_obj.message = [MagicMock(spec=object)]  # neither Plain nor Image
        gen = star.on_message(event)
        items = [item async for item in gen]
        assert items == []

    @pytest.mark.asyncio
    async def test_on_message_skips_when_ltm_disabled(self, star):
        event = MagicMock()
        event.message_obj.message = [Plain(text="hello")]
        star.ltm_enabled = MagicMock(return_value=False)
        gen = star.on_message(event)
        items = [item async for item in gen]
        assert items == []

    @pytest.mark.asyncio
    @patch.object(Main, "ltm_enabled", return_value=True)
    async def test_on_message_records_context(self, mock_enabled, star):
        event = MagicMock()
        event.message_obj.message = [Plain(text="hello")]
        star.ltm = MagicMock()
        star.ltm.need_active_reply = AsyncMock(return_value=False)
        star.ltm.handle_message = AsyncMock()

        star.context.get_config.return_value = {
            "provider_ltm_settings": {"group_icl_enable": True, "active_reply": {"enable": False}},
        }
        gen = star.on_message(event)
        items = [item async for item in gen]
        star.ltm.handle_message.assert_awaited_once()

    @pytest.mark.asyncio
    @patch.object(Main, "ltm_enabled", return_value=True)
    async def test_on_message_active_reply_triggers_llm(self, mock_enabled, star):
        event = MagicMock()
        event.message_obj.message = [Plain(text="hello")]
        event.message_str = "hello"
        event.session_id = "sess-1"
        event.unified_msg_origin = "qq:group:1"

        star.ltm = MagicMock()
        star.ltm.need_active_reply = AsyncMock(return_value=True)
        star.ltm.handle_message = AsyncMock()

        awaitables = []

        def request_llm(prompt, session_id, conversation):
            nonlocal awaitables
            awaitables.append((prompt, session_id, conversation))
            return MagicMock()

        event.request_llm = MagicMock(side_effect=request_llm)

        provider = MagicMock()
        provider.text_chat = AsyncMock()
        star.context.get_using_provider.return_value = provider
        star.context.conversation_manager.get_curr_conversation_id = AsyncMock(return_value="cid-1")
        conv = MagicMock()
        star.context.conversation_manager.get_conversation = AsyncMock(return_value=conv)

        star.context.get_config.return_value = {
            "provider_ltm_settings": {"group_icl_enable": True, "active_reply": {"enable": True}},
        }

        gen = star.on_message(event)
        items = [item async for item in gen]
        assert len(awaitables) == 1
        assert awaitables[0][0] == "hello"

    @pytest.mark.asyncio
    @patch.object(Main, "ltm_enabled", return_value=True)
    async def test_on_message_logs_when_no_provider(self, mock_enabled, star):
        event = MagicMock()
        event.message_obj.message = [Plain(text="hi")]
        star.ltm = MagicMock()
        star.ltm.need_active_reply = AsyncMock(return_value=True)
        star.ltm.handle_message = AsyncMock()
        star.context.get_using_provider.return_value = None
        star.context.get_config.return_value = {
            "provider_ltm_settings": {"group_icl_enable": True, "active_reply": {"enable": True}},
        }
        gen = star.on_message(event)
        items = [item async for item in gen]
        assert items == []


class TestDecorateLlmReq:
    """Decorating LLM requests."""

    @pytest.mark.asyncio
    async def test_decorate_llm_req_calls_ltm(self, star):
        event = MagicMock()
        req = ProviderRequest(prompt="test")
        star.ltm = MagicMock()
        star.ltm.on_req_llm = AsyncMock()
        star.ltm_enabled = MagicMock(return_value=True)
        await star.decorate_llm_req(event, req)
        star.ltm.on_req_llm.assert_awaited_once_with(event, req)

    @pytest.mark.asyncio
    async def test_decorate_llm_req_skips_when_disabled(self, star):
        event = MagicMock()
        req = MagicMock()
        star.ltm = MagicMock()
        star.ltm_enabled = MagicMock(return_value=False)
        await star.decorate_llm_req(event, req)
        star.ltm.on_req_llm.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_decorate_llm_req_skips_when_ltm_none(self, star):
        star.ltm = None
        event = MagicMock()
        req = MagicMock()
        await star.decorate_llm_req(event, req)


class TestRecordLlmResp:
    """Recording LLM responses."""

    @pytest.mark.asyncio
    async def test_record_llm_resp_calls_ltm(self, star):
        event = MagicMock()
        resp = MagicMock(spec=LLMResponse)
        star.ltm = MagicMock()
        star.ltm.after_req_llm = AsyncMock()
        star.ltm_enabled = MagicMock(return_value=True)
        await star.record_llm_resp_to_ltm(event, resp)
        star.ltm.after_req_llm.assert_awaited_once_with(event, resp)

    @pytest.mark.asyncio
    async def test_record_llm_resp_skips_when_disabled(self, star):
        event = MagicMock()
        resp = MagicMock(spec=LLMResponse)
        star.ltm = MagicMock()
        star.ltm_enabled = MagicMock(return_value=False)
        await star.record_llm_resp_to_ltm(event, resp)
        star.ltm.after_req_llm.assert_not_awaited()


class TestAfterMessageSent:
    """After-message-sent handler."""

    @pytest.mark.asyncio
    async def test_after_message_sent_cleans_session(self, star):
        event = MagicMock()
        event.get_extra.return_value = True
        star.ltm = MagicMock()
        star.ltm.remove_session = AsyncMock(return_value=3)
        star.ltm_enabled = MagicMock(return_value=True)
        await star.after_message_sent(event)
        event.get_extra.assert_called_with("_clean_ltm_session", False)
        star.ltm.remove_session.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_after_message_sent_skips_when_not_flagged(self, star):
        event = MagicMock()
        event.get_extra.return_value = False
        star.ltm = MagicMock()
        star.ltm_enabled = MagicMock(return_value=True)
        await star.after_message_sent(event)
        star.ltm.remove_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_after_message_sent_skips_when_ltm_disabled(self, star):
        event = MagicMock()
        star.ltm = MagicMock()
        star.ltm_enabled = MagicMock(return_value=False)
        await star.after_message_sent(event)
        star.ltm.remove_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_after_message_sent_skips_when_ltm_none(self, star):
        star.ltm = None
        event = MagicMock()
        await star.after_message_sent(event)
