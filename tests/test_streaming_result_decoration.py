"""流式输出的发送期装饰（引用 / @）回归测试。

背景：result_decorate 在流式场景下无法修改 result.chain —— respond 阶段直接使用
result.async_stream，且流式结果的 chain 恒为空。此前 STREAMING_RESULT 分支位于
「chain 判空」之后，导致装饰决策无处安放，开启流式后 reply_with_quote /
reply_with_mention 全部失效。

修复：把决策记录提前到 chain 判空之前，写入 event 扩展字段，由平台适配器在
send_streaming 的首个分片上按需应用。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain, Reply
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    PatchedGroupMessage,
)

REF_IDX = "REFIDX_streaming+/=="


def _make_stage(quote: bool = True, mention: bool = False) -> ResultDecorateStage:
    """只构造判定装饰所需的属性，避免拉起完整流水线。"""
    stage = object.__new__(ResultDecorateStage)
    stage.reply_with_quote = quote
    stage.reply_with_mention = mention
    return stage


def _make_event() -> QQOfficialMessageEvent:
    data: dict = {
        "id": "ROBOT1.0_message-id",
        "author": {"member_openid": "member-1"},
        "group_openid": "group-1",
        "content": "ping",
        "timestamp": "0",
        "message_scene": {"source": "default", "ext": [f"msg_idx={REF_IDX}"]},
    }
    raw = PatchedGroupMessage(api=None, event_id="event-1", data=data)

    abm = AstrBotMessage()
    abm.message_id = "ROBOT1.0_message-id"
    abm.session_id = "group-1"
    abm.group_id = "group-1"
    abm.self_id = "bot-1"
    abm.sender = MessageMember(user_id="member-1", nickname="u")
    abm.type = MessageType.GROUP_MESSAGE
    abm.message_str = "ping"
    abm.message = []
    abm.raw_message = raw
    meta = PlatformMetadata(name="qq_official", description="t", id="qq_official")
    bot = SimpleNamespace(api=SimpleNamespace(post_group_message=AsyncMock()))
    return QQOfficialMessageEvent(
        message_str="ping",
        message_obj=abm,
        platform_meta=meta,
        session_id="group-1",
        bot=bot,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_decorations_stashed_for_streaming_result_with_empty_chain() -> None:
    """核心回归：流式结果 chain 为空时也必须记录装饰决策。"""
    event = _make_event()
    result = MessageEventResult().set_result_content_type(
        ResultContentType.STREAMING_RESULT
    )
    assert not result.chain
    event.set_result(result)

    async for _ in _make_stage(quote=True).process(event):
        pass

    assert event.get_extra("_streaming_decorations") == {
        "quote": True,
        "mention": False,
    }


@pytest.mark.asyncio
async def test_decorations_stashed_for_streaming_finish() -> None:
    event = _make_event()
    result = MessageEventResult().set_result_content_type(
        ResultContentType.STREAMING_FINISH
    )
    event.set_result(result)

    async for _ in _make_stage(quote=True).process(event):
        pass

    assert (event.get_extra("_streaming_decorations") or {}).get("quote") is True


@pytest.mark.asyncio
async def test_decoration_flags_follow_config() -> None:
    event = _make_event()
    event.set_result(
        MessageEventResult().set_result_content_type(ResultContentType.STREAMING_RESULT)
    )

    async for _ in _make_stage(quote=False, mention=False).process(event):
        pass

    decorations = event.get_extra("_streaming_decorations")
    assert decorations == {"quote": False, "mention": False}


def test_apply_inserts_reply_at_chain_head() -> None:
    """首个分片应被插入 Reply；决策被取走，避免后续分片重复引用。"""
    event = _make_event()
    event.set_extra("_streaming_decorations", {"quote": True, "mention": False})
    chain = MessageChain(chain=[Plain("hi")])

    event._apply_streaming_decorations(chain)

    assert isinstance(chain.chain[0], Reply)
    assert chain.chain[0].id == "ROBOT1.0_message-id"
    assert event.get_extra("_streaming_decorations") is None


def test_apply_is_noop_without_stashed_decorations() -> None:
    event = _make_event()
    chain = MessageChain(chain=[Plain("hi")])

    event._apply_streaming_decorations(chain)

    assert len(chain.chain) == 1
    assert isinstance(chain.chain[0], Plain)


def test_apply_skips_chain_with_non_plain_components() -> None:
    """与 result_decorate 的非流式路径一致：仅纯文本 / 图文消息可装饰。"""

    event = _make_event()
    event.set_extra("_streaming_decorations", {"quote": True, "mention": False})
    chain = MessageChain(chain=[Reply(id="ROBOT1.0_other"), Plain("hi")])

    event._apply_streaming_decorations(chain)

    assert len(chain.chain) == 2
    assert chain.chain[0].id == "ROBOT1.0_other"
