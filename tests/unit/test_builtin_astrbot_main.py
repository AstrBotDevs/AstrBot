from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.message_components import Image
from astrbot.builtin_stars.astrbot.main import Main


@pytest.mark.asyncio
async def test_active_reply_passes_image_urls_to_llm(monkeypatch):
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
