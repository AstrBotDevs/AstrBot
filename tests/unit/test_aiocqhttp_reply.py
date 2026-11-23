"""测试 aiocqhttp 平台中私聊环境下引用回复（Reply）的消息发送行为。

Bug 背景：在私聊中引用上文消息时，OneBot 协议端返回
ActionFailed status='failed', retcode=100, wording='message not found'。

根因：Reply.toDict() 继承了 BaseMessageComponent.toDict()，
会将所有非 None 的默认字段（chain, sender_id, qq, seq 等）序列化到
OneBot 协议的 message 数组中。OneBot V11 标准只期望
{"type": "reply", "data": {"id": "..."}}，多余的字段可能导致
协议端（napcat/Lagrange）查找消息时失败。
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

import astrbot.core.message.components as Comp
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.pipeline.respond.stage import (
    RespondStage,  # noqa: F401 — 预加载避免循环导入
)
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

# ============================================================
# Reply.toDict() 输出格式测试
# ============================================================


@pytest.mark.asyncio
async def test_parse_onebot_json_reply_produces_extra_fields():
    """_parse_onebot_json 处理 Reply 时会输出多余字段。

    这验证了 bug 的链路：从 Reply 组件 → _parse_onebot_json →
    OneBot 协议 payload，多余字段一直传递到 send_private_msg。
    """
    chain = MessageChain([Comp.Reply(id="123456"), Comp.Plain("你好")])

    data = await AiocqhttpMessageEvent._parse_onebot_json(chain)

    assert len(data) == 2
    replySegment = data[0]
    assert replySegment["type"] == "reply"

    # 检查 reply 段的 data 中是否有多余字段
    extraFields = [k for k in replySegment["data"] if k != "id"]
    if extraFields:
        pytest.fail(
            f"_parse_onebot_json 输出的 reply 段包含了多余的 data 字段: "
            f"{extraFields}。这些字段可能被 OneBot 协议端误解析，"
            f"导致 message not found 错误。\n"
            f"完整 reply 段: {replySegment}"
        )


# ============================================================
# 私聊发送路径测试
# ============================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_group", "method_name", "target_key", "session_id"),
    [
        (False, "send_private_msg", "user_id", "987654"),
        (True, "send_group_msg", None, "123456"),
    ],
)
async def test_send_msg_with_reply_uses_standard_segment(
    is_group, method_name, target_key, session_id
):
    bot = AsyncMock()
    chain = MessageChain([Comp.Reply(id="123456"), Comp.Plain("你好")])

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=chain,
        event=None,
        is_group=is_group,
        session_id=session_id,
    )

    method = getattr(bot, method_name)
    method.assert_awaited_once()

    callArgs = method.call_args
    if target_key:
        assert callArgs.kwargs[target_key] == int(session_id)
    messages = callArgs.kwargs["message"]
    replySegment = messages[0]
    assert replySegment["type"] == "reply"
    assert replySegment["data"] == {"id": "123456"}


# ============================================================
# Reply 组件只传 id 时的正确 OneBot 格式测试
# ============================================================


def test_reply_to_dict_matches_onebot_v11_format():
    """OneBot V11 标准 reply 段格式：
    {"type": "reply", "data": {"id": "..."}}
    """
    expected = {
        "type": "reply",
        "data": {"id": "123456"},
    }

    reply = Comp.Reply(id="123456")
    actual = reply.toDict()

    assert actual == expected, (
        f"Reply.toDict() 输出不符合 OneBot V11 标准。\n期望: {expected}\n实际: {actual}"
    )


@pytest.fixture
def streaming_event(monkeypatch):
    event = object.__new__(AiocqhttpMessageEvent)
    event.send = AsyncMock()
    monkeypatch.setattr(AstrMessageEvent, "send_streaming", AsyncMock())
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    return event


@pytest.mark.asyncio
async def test_fallback_flushes_text_before_tool_status(streaming_event):
    async def generator():
        yield MessageChain([Comp.Plain("先行文本")])
        yield MessageChain(type="break")
        await streaming_event.send(MessageChain([Comp.Plain("调用工具")]))
        yield MessageChain([Comp.Plain("后续文本")])

    await streaming_event.send_streaming(generator(), use_fallback=True)

    sent_text = [
        call.args[0].chain[0].text
        for call in streaming_event.send.await_args_list
    ]
    assert sent_text == ["先行文本", "调用工具", "后续文本"]


@pytest.mark.asyncio
async def test_fallback_flushes_text_before_media(streaming_event):
    async def generator():
        yield MessageChain([Comp.Plain("说明文字")])
        yield MessageChain([Comp.Image(file="base64://c2FtcGxl")])

    await streaming_event.send_streaming(generator(), use_fallback=True)

    calls = streaming_event.send.await_args_list
    assert len(calls) == 2
    assert isinstance(calls[0].args[0].chain[0], Comp.Plain)
    assert calls[0].args[0].chain[0].text == "说明文字"
    assert isinstance(calls[1].args[0].chain[0], Comp.Image)


@pytest.mark.asyncio
async def test_fallback_pauses_after_break_and_pre_media_flushes(streaming_event):
    actions = []

    async def record_send(chain):
        component = chain.chain[0]
        label = (
            component.text
            if isinstance(component, Comp.Plain)
            else type(component).__name__
        )
        actions.append(("send", label))

    async def record_sleep(seconds):
        actions.append(("sleep", seconds))

    streaming_event.send.side_effect = record_send
    asyncio.sleep.side_effect = record_sleep

    async def generator():
        yield MessageChain([Comp.Plain("先行文本")])
        yield MessageChain(type="break")
        yield MessageChain([Comp.Plain("后续文本")])
        yield MessageChain([Comp.Image(file="base64://c2FtcGxl")])

    await streaming_event.send_streaming(generator(), use_fallback=True)

    assert actions == [
        ("send", "先行文本"),
        ("sleep", 1.5),
        ("send", "后续文本"),
        ("sleep", 1.5),
        ("send", "Image"),
        ("sleep", 1.5),
    ]
