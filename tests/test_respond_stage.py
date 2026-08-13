"""RespondStage 对空消息链的处理。

背景：stop_event() 在 _result 为 None 时会新建一个空结果，而 RespondStage 结尾刚好
清过结果；再加上调度器会在生成器阶段耗尽后把后续阶段重走一遍，插件「yield 结果后再
stop_event」就会多出一条内容为空的 Prepare to send 与一次多余的 after_message_sent。
"""

from typing import Any

import pytest

import astrbot.core.message.components as Comp
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.respond import stage as respond_stage


class FakeEvent:
    """够 RespondStage 走完前半段的最小事件。"""

    def __init__(self, result: MessageEventResult | None) -> None:
        self._result = result
        self._extras: dict[str, Any] = {}
        self.sent: list[Any] = []
        self.streamed: list[Any] = []

    def get_result(self) -> MessageEventResult | None:
        return self._result

    def clear_result(self) -> None:
        self._result = None

    def get_extra(self, key: str | None = None, default=None) -> Any:
        if key is None:
            return self._extras
        return self._extras.get(key, default)

    def set_extra(self, key: str, value: Any) -> None:
        self._extras[key] = value

    def get_sender_name(self) -> str:
        return "時"

    def get_sender_id(self) -> str:
        return "U1"

    def get_platform_id(self) -> str:
        return "line"

    def _outline_chain(self, chain) -> str:
        return " ".join(getattr(comp, "text", "") for comp in chain or [])

    async def send(self, chain) -> None:
        self.sent.append(chain)

    async def send_streaming(self, stream, realtime_segmenting) -> None:
        self.streamed.append(stream)


@pytest.fixture
def captured_logs(monkeypatch):
    """收集 respond stage 打出的 info 日志。"""
    logs: list[str] = []
    monkeypatch.setattr(
        respond_stage.logger,
        "info",
        lambda message, *args, **kwargs: logs.append(str(message)),
    )
    return logs


@pytest.fixture
def hook_calls(monkeypatch):
    """替换 after_message_sent 钩子入口，记录调用次数。"""
    calls: list[Any] = []

    async def fake_hook(event, hook_type):
        calls.append(hook_type)
        return False

    monkeypatch.setattr(respond_stage, "call_event_hook", fake_hook)
    return calls


@pytest.mark.asyncio
async def test_empty_chain_result_is_skipped_silently(captured_logs, hook_calls):
    """stop_event() 造出的空结果不该产生日志、发送或 after_message_sent。"""
    result = MessageEventResult().stop_event()
    assert result.chain == []

    event = FakeEvent(result)
    await respond_stage.RespondStage().process(event)

    assert captured_logs == []
    assert event.sent == []
    assert hook_calls == []
    # 提前返回不清结果：停止传播靠的是 _force_stopped，这里无需也不该改动它。
    assert event.get_result() is result


@pytest.mark.asyncio
async def test_streaming_result_with_empty_chain_still_delivered(captured_logs):
    """流式结果的内容在 async_stream 上，chain 为空属正常，不得被空链短路吃掉。"""

    async def stream():
        yield MessageChainStub()

    class MessageChainStub:
        pass

    generator = stream()
    result = MessageEventResult()
    result.result_content_type = ResultContentType.STREAMING_RESULT
    result.async_stream = generator

    event = FakeEvent(result)
    stage = respond_stage.RespondStage()
    stage.config = {"provider_settings": {}}

    await stage.process(event)

    assert event.streamed == [generator]
    assert any("Prepare to send" in line for line in captured_logs)


@pytest.mark.asyncio
async def test_non_empty_chain_is_not_skipped(captured_logs, hook_calls):
    """有内容的结果照常走完发送与 after_message_sent。"""
    event = FakeEvent(MessageEventResult(chain=[Comp.Plain("hi")]))

    stage = respond_stage.RespondStage()
    stage.platform_settings = {}
    stage.is_seg_reply_required = lambda event: False

    async def not_empty(chain):
        return False

    stage._is_empty_message_chain = not_empty

    await stage.process(event)

    assert len(event.sent) == 1
    assert len(hook_calls) == 1
    assert any("Prepare to send" in line for line in captured_logs)
    assert event.get_result() is None
