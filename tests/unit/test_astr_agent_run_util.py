from types import SimpleNamespace

import pytest

from astrbot.core.astr_agent_run_util import run_agent
from astrbot.core.message.message_event_result import MessageChain


def _llm_result_response(text: str):
    return SimpleNamespace(
        type="llm_result",
        data={"chain": MessageChain().message(text)},
    )


class _DummyTrace:
    def record(self, *args, **kwargs) -> None:
        return None


class _DummyEvent:
    def __init__(self) -> None:
        self._extras: dict = {}
        self._stopped = False
        self.result_texts: list[str] = []
        self.trace = _DummyTrace()

    def is_stopped(self) -> bool:
        return self._stopped

    def get_extra(self, key: str, default=None):
        return self._extras.get(key, default)

    def set_extra(self, key: str, value) -> None:
        self._extras[key] = value

    def set_result(self, result) -> None:
        self.result_texts.append(result.get_plain_text(with_other_comps_mark=True))

    def clear_result(self) -> None:
        return None

    def get_platform_name(self) -> str:
        return "slack"

    def get_platform_id(self) -> str:
        return "slack"

    async def send(self, _msg_chain) -> None:
        return None


class _FakeRunner:
    def __init__(self, steps: list[list[SimpleNamespace]]) -> None:
        self._steps = steps
        self._step_idx = 0
        self._done = False
        self.streaming = False
        self.req = SimpleNamespace(func_tool=object())
        self.run_context = SimpleNamespace(
            context=SimpleNamespace(event=_DummyEvent()),
            messages=[],
        )
        self.stats = SimpleNamespace(to_dict=lambda: {})

    def done(self) -> bool:
        return self._done

    def request_stop(self) -> None:
        self.run_context.context.event.set_extra("agent_stop_requested", True)

    def was_aborted(self) -> bool:
        return False

    async def step(self):
        if self._step_idx >= len(self._steps):
            self._done = True
            return

        current = self._steps[self._step_idx]
        self._step_idx += 1
        for resp in current:
            yield resp

        if self._step_idx >= len(self._steps):
            self._done = True


@pytest.mark.asyncio
async def test_repeat_reply_guard_forces_convergence():
    runner = _FakeRunner(
        [
            [_llm_result_response("重复输出")],
            [_llm_result_response("重复输出")],
            [_llm_result_response("重复输出")],
            [_llm_result_response("最终答案")],
        ]
    )

    async for _ in run_agent(
        runner,
        max_step=8,
        show_tool_use=False,
        show_tool_call_result=False,
        repeat_reply_guard_threshold=3,
    ):
        pass

    assert runner.run_context.context.event.result_texts == [
        "重复输出",
        "重复输出",
        "最终答案",
    ]
    assert runner.req.func_tool is None
    assert any(
        msg.role == "user"
        and "You have repeated the same reply multiple times." in str(msg.content)
        for msg in runner.run_context.messages
    )


@pytest.mark.asyncio
async def test_repeat_reply_guard_can_be_disabled_with_zero_threshold():
    runner = _FakeRunner(
        [
            [_llm_result_response("重复输出")],
            [_llm_result_response("重复输出")],
            [_llm_result_response("重复输出")],
            [_llm_result_response("最终答案")],
        ]
    )
    original_func_tool = runner.req.func_tool

    async for _ in run_agent(
        runner,
        max_step=8,
        show_tool_use=False,
        show_tool_call_result=False,
        repeat_reply_guard_threshold=0,
    ):
        pass

    assert runner.run_context.context.event.result_texts == [
        "重复输出",
        "重复输出",
        "重复输出",
        "最终答案",
    ]
    assert runner.req.func_tool is original_func_tool
