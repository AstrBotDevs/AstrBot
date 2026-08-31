import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.llm_types import LLMResponse, ProviderRequest, TokenUsage
from astrbot.core.agent.message import CheckpointData, Message
from astrbot.core.assistant_history import build_pending_assistant_history
from astrbot.core.message.components import Face, Image, Record, Reply
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import (
    internal,
    third_party,
)
from astrbot.core.platform.send_result import DeliveryAttempt, DeliveryReceipt
from astrbot.core.utils import task_utils


class FakeEvent:
    def __init__(self, *, extras: dict | None = None):
        self.unified_msg_origin = "webchat:FriendMessage:test-session"
        self._extras = extras or {}
        self.result_history: list[MessageEventResult] = []

    def get_extra(self, key: str):
        return self._extras.get(key)

    def set_extra(self, key: str, value) -> None:
        self._extras[key] = value

    def set_result(self, result: MessageEventResult) -> None:
        self.result_history.append(result)


class FakeInternalProcessEvent(FakeEvent):
    def __init__(
        self,
        *,
        message_str: str = "hello",
        extras: dict | None = None,
        message_components: list | None = None,
        stopped: bool = False,
    ):
        super().__init__(extras=extras)
        self.message_str = message_str
        self.message_obj = SimpleNamespace(message=message_components or [])
        self.platform_meta = SimpleNamespace(support_streaming_message=True)
        self.trace = MagicMock()
        self.trace.record = MagicMock()
        self.send = AsyncMock()
        self.send_typing = AsyncMock()
        self.stop_typing = AsyncMock()
        self._stopped = stopped

    def is_stopped(self) -> bool:
        return self._stopped


def _internal_plugin_context(tts_provider=None) -> SimpleNamespace:
    return SimpleNamespace(
        get_using_tts_provider=lambda _umo: tts_provider,
        database=SimpleNamespace(insert_provider_stat=AsyncMock()),
        session_lock_manager=SimpleNamespace(
            acquire_lock=lambda _umo: _AsyncLockContext()
        ),
        background_tasks=set(),
        follow_up_coordinator=SimpleNamespace(
            try_capture=MagicMock(return_value=None),
            prepare_capture=AsyncMock(),
            finalize_capture=AsyncMock(),
            register_active_runner=MagicMock(),
            unregister_active_runner=MagicMock(),
        ),
    )


def _pipeline_context(execution_context: SimpleNamespace) -> SimpleNamespace:
    if not hasattr(execution_context, "background_tasks"):
        execution_context.background_tasks = set()
    if not hasattr(execution_context, "metrics"):
        execution_context.metrics = SimpleNamespace(upload=AsyncMock())
    return SimpleNamespace(
        execution_context=execution_context,
        handlers=SimpleNamespace(
            get_handlers_by_event_type=lambda *_args, **_kwargs: []
        ),
        plugins=SimpleNamespace(),
    )


def _set_metrics_upload(stage, upload) -> None:
    """Replace only the telemetry port bound to this test runtime."""
    stage.ctx.execution_context.metrics.upload = upload


class FakeThirdPartyRunner:
    def __init__(
        self,
        responses=None,
        *,
        final_resp: LLMResponse | None = None,
        step_exception: Exception | None = None,
        done: bool = True,
    ):
        self._responses = responses or []
        self._final_resp = final_resp
        self._step_exception = step_exception
        self._done = done
        self.reset = AsyncMock()
        self.close = AsyncMock()

    async def step_until_done(self, max_step: int = 30):
        if self._step_exception is not None:
            raise self._step_exception

        for response in self._responses:
            yield response

    def get_final_llm_resp(self) -> LLMResponse | None:
        return self._final_resp

    def done(self) -> bool:
        return self._done


class FakeInternalRunner:
    def __init__(
        self,
        *,
        final_resp: LLMResponse | None = None,
        done: bool = True,
        aborted: bool = False,
    ):
        self._final_resp = final_resp or LLMResponse(
            role="assistant",
            completion_text="done",
        )
        self._done = done
        self._aborted = aborted
        self.run_context = SimpleNamespace(
            messages=[Message(role="assistant", content="done")]
        )
        self.stats = SimpleNamespace(
            to_dict=lambda: {"steps": 1},
            token_usage=TokenUsage(output=1),
        )
        self.provider = SimpleNamespace(
            get_model=lambda: "fake-model",
            meta=lambda: SimpleNamespace(type="fake-provider", id="fake-provider"),
            provider_config={"id": "provider-1"},
        )

    def done(self) -> bool:
        return self._done

    def was_aborted(self) -> bool:
        return self._aborted

    def get_final_llm_resp(self) -> LLMResponse | None:
        return self._final_resp


def _fake_build_cfg(**kwargs):
    return SimpleNamespace(**kwargs)


def _runner_response(resp_type: str, text: str):
    return SimpleNamespace(
        type=resp_type,
        data={"chain": MessageChain().message(text)},
    )


class _AsyncLockContext:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _AwaitableFlag:
    def __init__(self):
        self.awaited = False

    def __await__(self):
        async def _inner():
            self.awaited = True
            return None

        return _inner().__await__()


__all__ = [name for name in globals() if not name.startswith("__")]
