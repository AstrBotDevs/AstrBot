from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.message_components import Image
from astrbot.builtin_stars.astrbot.main import Main


def _active_reply_main():
    main = Main.__new__(Main)
    main.ltm = MagicMock()
    main.ltm.need_active_reply = AsyncMock(return_value=True)

    context = MagicMock()
    context.get_config.return_value = {
        "provider_ltm_settings": {
            "active_reply": {"enable": True},
            "group_icl_enable": False,
        },
    }
    context.get_using_provider.return_value = MagicMock()
    context.conversation_manager.get_curr_conversation_id = AsyncMock(
        return_value="conv-id",
    )
    conversation = MagicMock()
    context.conversation_manager.get_conversation = AsyncMock(
        return_value=conversation,
    )
    main.context = context
    return main, conversation


@pytest.mark.asyncio
async def test_active_reply_passes_image_urls_to_llm(monkeypatch):
    main, conversation = _active_reply_main()

    async def convert_to_file_path(self):
        return "/tmp/picture.png"

    monkeypatch.setattr(Image, "convert_to_file_path", convert_to_file_path)
    image = Image(file="file:///tmp/picture.png")
    event = MagicMock()
    event.message_obj.message = [image]
    event.message_str = ""
    event.session_id = "session-id"
    event.unified_msg_origin = "platform:group:123"
    request = object()
    event.request_llm.return_value = request

    results = [item async for item in main.on_message(event)]

    assert results == [request]
    event.request_llm.assert_called_once_with(
        prompt="",
        session_id="session-id",
        image_urls=["/tmp/picture.png"],
        conversation=conversation,
    )


@pytest.mark.asyncio
async def test_active_reply_skips_failed_image_conversion(monkeypatch):
    main, conversation = _active_reply_main()

    async def convert_to_file_path(self):
        raise RuntimeError("broken image")

    mock_logger = MagicMock()
    monkeypatch.setattr(
        "astrbot.builtin_stars.astrbot.main.logger",
        mock_logger,
    )
    monkeypatch.setattr(Image, "convert_to_file_path", convert_to_file_path)
    image = Image(file="file:///tmp/picture.png")
    event = MagicMock()
    event.message_obj.message = [image]
    event.message_str = ""
    event.session_id = "session-id"
    event.unified_msg_origin = "platform:group:123"
    request = object()
    event.request_llm.return_value = request

    results = [item async for item in main.on_message(event)]

    assert results == [request]
    mock_logger.exception.assert_called_once_with(
        "主动回复处理图片失败",
    )
    event.request_llm.assert_called_once_with(
        prompt="",
        session_id="session-id",
        image_urls=[],
        conversation=conversation,
    )


@pytest.mark.asyncio
async def test_active_reply_ignores_non_iterable_messages():
    main, _ = _active_reply_main()
    event = MagicMock()
    event.message_obj.message = None
    event.unified_msg_origin = "platform:group:123"

    results = [item async for item in main.on_message(event)]

    assert results == []
    event.request_llm.assert_not_called()
