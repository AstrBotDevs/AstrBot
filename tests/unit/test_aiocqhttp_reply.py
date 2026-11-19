"""测试 aiocqhttp 平台中私聊环境下引用回复（Reply）的消息发送行为。

Bug 背景：在私聊中引用上文消息时，OneBot 协议端返回
ActionFailed status='failed', retcode=100, wording='message not found'。

根因：Reply.toDict() 继承了 BaseMessageComponent.toDict()，
会将所有非 None 的默认字段（chain, sender_id, qq, seq 等）序列化到
OneBot 协议的 message 数组中。OneBot V11 标准只期望
{"type": "reply", "data": {"id": "..."}}，多余的字段可能导致
协议端（napcat/Lagrange）查找消息时失败。
"""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

import astrbot.core.message.components as Comp
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform", "quote_enabled", "include_unsupported_component", "should_quote"),
    [
        ("aiocqhttp", True, False, True),
        ("telegram", True, False, False),
        ("aiocqhttp", True, True, False),
        ("aiocqhttp", False, False, False),
    ],
)
async def test_dual_text_record_result_quote_eligibility(
    platform: str,
    quote_enabled: bool,
    include_unsupported_component: bool,
    should_quote: bool,
    monkeypatch: pytest.MonkeyPatch,
):
    stage = ResultDecorateStage()
    stage.reply_prefix = ""
    stage.content_safe_check_reply = False
    stage.enable_segmented_reply = False
    stage.only_llm_result = False
    stage.show_reasoning = False
    stage.tts_trigger_probability = 0
    stage.reply_with_mention = True
    stage.reply_with_quote = quote_enabled
    stage.forward_threshold = 1000
    stage.ctx = SimpleNamespace(
        plugin_manager=SimpleNamespace(
            context=SimpleNamespace(
                get_using_tts_provider_async=AsyncMock(return_value=None),
            ),
        ),
        astrbot_config={
            "provider_tts_settings": {
                "enable": False,
                "use_file_service": False,
                "dual_output": False,
            },
            "callback_api_base": "",
            "t2i": False,
        },
    )
    text = Comp.Plain("hello")
    voice = Comp.Record(file="voice.wav", url="voice.wav", text="hello")
    unsupported = Comp.At(qq="another-user")
    chain = [text, voice, *([unsupported] if include_unsupported_component else [])]
    original_chain = list(chain)
    result = MessageEventResult(
        chain=chain,
        result_content_type=ResultContentType.LLM_RESULT,
    )
    event = SimpleNamespace(
        plugins_name=None,
        unified_msg_origin=f"{platform}:group-1",
        message_obj=SimpleNamespace(message_id="user-message-1"),
        get_result=lambda: result,
        get_platform_name=lambda: platform,
        get_message_type=lambda: "GroupMessage",
        get_sender_id=lambda: "sender-1",
        get_sender_name=lambda: "sender",
        is_stopped=lambda: False,
        get_extra=lambda *_args, **_kwargs: None,
    )

    async for _ in stage.process(cast(Any, event)):
        pass

    if not should_quote:
        assert result.chain == original_chain
        return

    assert isinstance(result.chain[0], Comp.Reply)
    assert result.chain[0].id == "user-message-1"
    assert result.chain[1:] == original_chain
    monkeypatch.setattr(
        Comp.Record,
        "convert_to_base64",
        AsyncMock(return_value="YXVkaW8="),
    )
    segments = await AiocqhttpMessageEvent._parse_onebot_json(result)
    assert segments == [
        {"type": "reply", "data": {"id": "user-message-1"}},
        {"type": "text", "data": {"text": "hello"}},
        {"type": "record", "data": {"file": "base64://YXVkaW8="}},
    ]

    bot = AsyncMock()
    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=MessageChain(result.chain),
        event=None,
        is_group=True,
        session_id="123456",
    )
    bot.send_group_msg.assert_awaited_once()
    assert bot.send_group_msg.call_args.kwargs["message"] == segments
