"""Regression coverage for platform acceptance receipts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.message.components import At, AtAll, Plain, Record, Reply
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.platform.send_result import (
    DeliveryAttempt,
    DeliveryReceipt,
    PlatformSendResult,
)


class _Event:
    def __init__(self, result: MessageEventResult, send_results) -> None:
        self._result = result
        self._extras = {}
        self._send_results = iter(send_results)
        self.unified_msg_origin = "test:FriendMessage:user"
        self.plugins_name = []
        self.send = AsyncMock(side_effect=self._send)
        self.send_streaming = AsyncMock()
        self.stop_typing = AsyncMock()

    async def _send(self, _chain):
        next_result = next(self._send_results)
        if isinstance(next_result, BaseException):
            raise next_result
        return next_result

    def get_result(self):
        return self._result

    def clear_result(self):
        self._result = None

    def get_extra(self, key, default=None):
        return self._extras.get(key, default)

    def set_extra(self, key, value):
        self._extras[key] = value

    def get_platform_id(self):
        return "test"

    def get_platform_name(self):
        return "test"

    def get_sender_name(self):
        return "tester"

    def get_sender_id(self):
        return "user"

    def _outline_chain(self, _chain):
        return "test"

    def is_stopped(self):
        return False


def _stage() -> RespondStage:
    stage = RespondStage()
    stage.config = {"provider_settings": {}}
    stage.platform_settings = {"path_mapping": []}
    stage.enable_seg = False
    stage.ctx = SimpleNamespace(
        astrbot_config={},
        file_token_service=MagicMock(),
        handlers=SimpleNamespace(
            get_handlers_by_event_type=lambda *_args, **_kwargs: []
        ),
        plugins=SimpleNamespace(),
        execution_context=SimpleNamespace(
            persist_accepted_group_response=AsyncMock(),
        ),
    )
    return stage


def _success() -> PlatformSendResult:
    return PlatformSendResult(
        platform_id="test",
        success=True,
        target="target",
        message_count=1,
        message_id="platform-message-1",
    )


@pytest.mark.asyncio
async def test_standard_receipt_uses_platform_acceptance_and_excludes_headers():
    event = _Event(
        MessageEventResult(
            chain=[At(qq="1"), AtAll(), Reply(id="2"), Plain("hello")],
        ),
        [_success()],
    )

    await _stage().process(event)

    receipt = event.get_extra("delivery_receipt")
    assert receipt.status == "accepted"
    assert receipt.message_ids == ("platform-message-1",)
    assert receipt.history_text == "hello"


@pytest.mark.asyncio
async def test_standard_response_persists_after_platform_acceptance():
    stage = _stage()
    event = _Event(MessageEventResult(chain=[Plain("hello")]), [_success()])

    await stage.process(event)

    receipt = event.get_extra("delivery_receipt")
    stage.ctx.execution_context.persist_accepted_group_response.assert_awaited_once_with(
        event,
        receipt,
    )


@pytest.mark.asyncio
async def test_standard_record_and_text_failures_aggregate_to_partial():
    event = _Event(
        MessageEventResult(chain=[Record(file="file:///tmp/audio.wav"), Plain("text")]),
        [
            _success(),
            PlatformSendResult(
                platform_id="test",
                success=False,
                target="target",
                message_count=1,
                error_message="adapter rejected",
            ),
        ],
    )

    await _stage().process(event)

    receipt = event.get_extra("delivery_receipt")
    assert receipt.status == "partial"
    assert receipt.history_text == ""


@pytest.mark.asyncio
async def test_standard_record_failure_keeps_accepted_text_projection():
    event = _Event(
        MessageEventResult(chain=[Record(file="file:///tmp/audio.wav"), Plain("text")]),
        [
            PlatformSendResult(
                platform_id="test",
                success=False,
                target="target",
                message_count=1,
                error_message="adapter rejected",
            ),
            _success(),
        ],
    )

    await _stage().process(event)

    receipt = event.get_extra("delivery_receipt")
    assert receipt.status == "partial"
    assert receipt.history_text == "text"


@pytest.mark.asyncio
async def test_segmented_receipt_keeps_only_accepted_fragment():
    event = _Event(
        MessageEventResult(chain=[Plain("first"), Plain("second")]),
        [
            _success(),
            PlatformSendResult(
                platform_id="test",
                success=False,
                target="target",
                message_count=1,
                error_message="adapter rejected",
            ),
        ],
    )
    stage = _stage()
    stage.enable_seg = True
    stage.only_llm_result = False
    stage._calc_comp_interval = AsyncMock(return_value=0)

    await stage.process(event)

    receipt = event.get_extra("delivery_receipt")
    assert receipt.status == "partial"
    assert receipt.history_text == "first"


@pytest.mark.asyncio
async def test_send_exception_is_unknown_not_success():
    event = _Event(MessageEventResult().message("hello"), [TimeoutError("timeout")])

    await _stage().process(event)

    assert event.get_extra("delivery_receipt").status == "unknown"


@pytest.mark.asyncio
async def test_empty_message_is_skipped():
    event = _Event(MessageEventResult(chain=[]), [])
    stage = _stage()

    await stage.process(event)

    event.send.assert_not_awaited()
    stage.ctx.execution_context.persist_accepted_group_response.assert_not_awaited()
    assert event.get_extra("delivery_receipt") is None
    assert event.get_result() is not None


@pytest.mark.asyncio
async def test_streaming_receipt_captures_accepted_text():
    async def stream():
        yield MessageChain(chain=[Plain("first ")])
        yield MessageChain(chain=[Plain("second")])

    event = _Event(
        MessageEventResult(
            result_content_type=ResultContentType.STREAMING_RESULT,
            async_stream=stream(),
        ),
        [],
    )

    async def send_streaming(generator, _fallback):
        async for _ in generator:
            pass
        return _success()

    event.send_streaming.side_effect = send_streaming
    await _stage().process(event)

    receipt = event.get_extra("delivery_receipt")
    assert receipt.status == "accepted"
    assert receipt.history_text == "first second"


@pytest.mark.asyncio
async def test_streaming_rejection_does_not_project_text():
    async def stream():
        yield MessageChain(chain=[Plain("not accepted")])

    event = _Event(
        MessageEventResult(
            result_content_type=ResultContentType.STREAMING_RESULT,
            async_stream=stream(),
        ),
        [],
    )

    async def send_streaming(generator, _fallback):
        async for _ in generator:
            pass
        return PlatformSendResult(
            platform_id="test",
            success=False,
            target="target",
            error_message="adapter rejected",
        )

    event.send_streaming.side_effect = send_streaming
    await _stage().process(event)

    receipt = event.get_extra("delivery_receipt")
    assert receipt.status == "failed"
    assert receipt.history_text == ""


def test_delivery_receipt_preserves_partial_and_failed_semantics():
    partial = DeliveryReceipt.aggregate(
        [
            DeliveryAttempt(status="accepted", semantic_text="first"),
            DeliveryAttempt(status="failed", semantic_text="second"),
        ]
    )
    failed = DeliveryReceipt.aggregate([DeliveryAttempt(status="failed")])

    assert partial.status == "partial"
    assert partial.history_text == "first"
    assert failed.status == "failed"


@pytest.mark.asyncio
async def test_respond_stage_still_sends_empty_streaming_result():
    async def stream():
        if False:
            yield None

    event = _Event(
        MessageEventResult(
            result_content_type=ResultContentType.STREAMING_RESULT,
            async_stream=stream(),
        ),
        [],
    )
    event._result.chain = []

    async def send_streaming(generator, _fallback):
        async for _ in generator:
            pass
        return _success()

    event.send_streaming.side_effect = send_streaming
    await _stage().process(event)

    event.send_streaming.assert_awaited_once()
    assert event.get_extra("delivery_receipt") is not None
