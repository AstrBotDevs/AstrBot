import pytest

from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_adapter import (
    WecomAIBotAdapter,
)
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_event import (
    WecomAIBotMessageEvent,
)
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_queue_mgr import (
    WecomAIQueueMgr,
)

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_wecomai_group_message_includes_chat_id():
    adapter = WecomAIBotAdapter.__new__(WecomAIBotAdapter)
    adapter.bot_name = "AstrBot"
    adapter.encoding_aes_key = ""
    payload = {
        "message_data": {
            "chattype": "group",
            "chatid": "group-chat-1",
            "from": {"userid": "sender"},
            "msgtype": "text",
            "text": {"content": "hello"},
        },
        "session_id": "wecomai:group-chat-1",
    }

    message = await adapter.convert_message(payload)

    assert message.group is not None
    assert message.group.group_id == "group-chat-1"

    event = WecomAIBotMessageEvent(
        message_str=message.message_str,
        message_obj=message,
        platform_meta=PlatformMetadata(
            name="wecom_ai_bot",
            description="WeCom AI Bot",
            id="wecom-ai-bot",
        ),
        session_id=message.session_id,
        api_client=None,
        queue_mgr=WecomAIQueueMgr(),
    )
    assert await event.get_group() is message.group
