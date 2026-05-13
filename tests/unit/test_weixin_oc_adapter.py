import asyncio

import pytest

from astrbot.core.message.components import File
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_session import MessageSesion
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter import WeixinOCAdapter


def _make_adapter() -> WeixinOCAdapter:
    return WeixinOCAdapter(
        {"id": "weixin_personal", "weixin_oc_token": "token"},
        {},
        asyncio.Queue(),
    )


@pytest.mark.asyncio
async def test_send_by_session_raises_when_media_segment_fails(monkeypatch):
    adapter = _make_adapter()

    async def fail_media_segment(*args, **kwargs):
        del args, kwargs
        return False

    monkeypatch.setattr(adapter, "_send_media_segment", fail_media_segment)

    session = MessageSesion(
        platform_name="weixin_personal",
        message_type=MessageType.FRIEND_MESSAGE,
        session_id="user@im.wechat",
    )
    chain = MessageChain(chain=[File(name="report.pdf", file="report.pdf")])

    with pytest.raises(RuntimeError, match="failed to send 1 message segment"):
        await adapter.send_by_session(session, chain)
