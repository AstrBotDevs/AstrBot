import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import astrbot.core.astr_agent_run_util as util
from astrbot.core.message.components import Json
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)


class FakeEvent:
    def __init__(self, *, platform_name: str = "test", platform_id: str = "test"):
        self._platform_name = platform_name
        self._platform_id = platform_id
        self._extras: dict[str, object] = {}
        self.trace = MagicMock()
        self.trace.record = MagicMock()
        self.send = AsyncMock()
        self.result_history: list[MessageEventResult] = []
        self.clear_result_calls = 0
        self.track_temporary_local_file = MagicMock()
        self._stopped = False

    def is_stopped(self) -> bool:
        return self._stopped

    def get_extra(self, key: str):
        return self._extras.get(key)

    def set_extra(self, key: str, value) -> None:
        self._extras[key] = value

    def get_platform_name(self) -> str:
        return self._platform_name

    def get_platform_id(self) -> str:
        return self._platform_id

    def set_result(self, result: MessageEventResult) -> None:
        self.result_history.append(result)

    def clear_result(self) -> None:
        self.clear_result_calls += 1


class FakeRunner:
    def __init__(self, responses, *, event: FakeEvent, streaming: bool = False):
        self._responses = responses
        self._done = False
        self.streaming = streaming
        self.req = SimpleNamespace(func_tool="toolset")
        self.run_context = SimpleNamespace(
            context=SimpleNamespace(event=event),
            messages=[],
        )
        self.stats = SimpleNamespace(to_dict=lambda: {"steps": len(responses)})
        self.agent_hooks = SimpleNamespace(on_agent_done=AsyncMock())
        self.provider = SimpleNamespace(get_model=lambda: "fake-model")
        self.stop_requested = False

    def done(self) -> bool:
        return self._done

    def request_stop(self) -> None:
        self.stop_requested = True

    async def step(self):
        if isinstance(self._responses, Exception):
            raise self._responses

        for response in self._responses:
            yield response

        self._done = True


@pytest.mark.asyncio
async def test_run_agent_replaces_streaming_provider_error():
    error_text = "LLM response error: model was not found or permission was denied"
    runner = FakeRunner(
        [
            SimpleNamespace(
                type="err",
                data={"chain": MessageChain().message(error_text)},
            )
        ],
        event=FakeEvent(),
        streaming=True,
    )

    chains = [chain async for chain in util.run_agent(runner)]

    assert len(chains) == 1
    assert chains[0].get_plain_text() == "Error occurred during AI execution."
    assert error_text not in chains[0].get_plain_text()


@pytest.mark.asyncio
async def test_run_agent_replaces_malformed_streaming_provider_error():
    runner = FakeRunner(
        [SimpleNamespace(type="err", data={})],
        event=FakeEvent(),
        streaming=True,
    )

    chains = [chain async for chain in util.run_agent(runner)]

    assert len(chains) == 1
    assert chains[0].get_plain_text() == "Error occurred during AI execution."


@pytest.mark.asyncio
async def test_run_agent_replaces_non_streaming_provider_error():
    provider_error = "https://provider.example/v1?api_key=provider-secret"
    event = FakeEvent()
    runner = FakeRunner(
        [
            SimpleNamespace(
                type="err",
                data={"chain": MessageChain().message(provider_error)},
            )
        ],
        event=event,
    )

    chains = [chain async for chain in util.run_agent(runner)]

    assert [chain.get_plain_text() for chain in chains] == [
        "Error occurred during AI execution."
    ]
    assert event.result_history[0].get_plain_text() == (
        "Error occurred during AI execution."
    )
    assert "provider-secret" not in chains[0].get_plain_text()


class MultiStepRunner(FakeRunner):
    def __init__(self, step_responses, *, event: FakeEvent, streaming: bool = False):
        super().__init__([], event=event, streaming=streaming)
        self._step_responses = step_responses
        self.step_calls = 0

    async def step(self):
        responses = self._step_responses[self.step_calls]
        self.step_calls += 1
        for response in responses:
            yield response
        if self.step_calls >= len(self._step_responses):
            self._done = True


def _response(resp_type: str, chain: MessageChain | None = None):
    return SimpleNamespace(type=resp_type, data={"chain": chain or MessageChain()})


def _stats_response(stats: dict):
    return _response(
        "agent_stats",
        MessageChain(type="agent_stats", chain=[Json(data=stats)]),
    )


def test_should_buffer_llm_result_only_when_non_streaming_general_buffering_enabled():
    runner = SimpleNamespace(streaming=False)

    assert (
        util._should_buffer_llm_result(
            buffer_intermediate_messages=True,
            stream_to_general=False,
            agent_runner=runner,
        )
        is True
    )
    assert (
        util._should_buffer_llm_result(
            buffer_intermediate_messages=False,
            stream_to_general=False,
            agent_runner=runner,
        )
        is False
    )
    assert (
        util._should_buffer_llm_result(
            buffer_intermediate_messages=True,
            stream_to_general=True,
            agent_runner=runner,
        )
        is False
    )
    assert (
        util._should_buffer_llm_result(
            buffer_intermediate_messages=True,
            stream_to_general=False,
            agent_runner=SimpleNamespace(streaming=True),
        )
        is False
    )


def test_merge_buffered_llm_chains_merges_then_clears_source_list():
    buffered = [
        MessageChain().message("hello "),
        MessageChain().message("world"),
    ]

    merged = util._merge_buffered_llm_chains(buffered)

    assert merged is not None
    assert merged.get_plain_text() == "hello  world"
    assert buffered == []
    assert util._merge_buffered_llm_chains([]) is None


def test_truncate_tool_result_respects_zero_and_small_limits():
    assert util._truncate_tool_result("abcdef", limit=0) == ""
    assert util._truncate_tool_result("abcdef", limit=2) == "ab"
    assert util._truncate_tool_result("abcdef", limit=5) == "ab..."


@pytest.mark.asyncio
async def test_run_agent_buffers_llm_results_until_done():
    event = FakeEvent()
    runner = FakeRunner(
        [
            _response("llm_result", MessageChain().message("hello")),
            _response("llm_result", MessageChain().message("world")),
        ],
        event=event,
    )

    outputs = [
        chain
        async for chain in util.run_agent(
            runner,
            buffer_intermediate_messages=True,
        )
    ]

    assert [chain.get_plain_text() for chain in outputs] == ["hello world"]
    assert len(event.result_history) == 1
    assert event.result_history[0].result_content_type == ResultContentType.LLM_RESULT
    assert event.clear_result_calls == 1


@pytest.mark.asyncio
async def test_run_agent_discards_buffer_when_user_aborts():
    event = FakeEvent()
    runner = FakeRunner(
        [
            _response("llm_result", MessageChain().message("partial")),
            _response("aborted"),
        ],
        event=event,
    )

    outputs = [
        chain
        async for chain in util.run_agent(
            runner,
            buffer_intermediate_messages=True,
        )
    ]

    assert outputs == []
    assert event.get_extra("agent_user_aborted") is True
    assert event.get_extra("agent_stop_requested") is False
    assert event.clear_result_calls == 0


@pytest.mark.asyncio
async def test_run_agent_marks_user_aborted_without_buffered_output():
    event = FakeEvent()
    runner = FakeRunner(
        [_response("aborted")],
        event=event,
    )

    outputs = [chain async for chain in util.run_agent(runner)]

    assert outputs == []
    assert event.get_extra("agent_user_aborted") is True
    assert event.get_extra("agent_stop_requested") is False
    assert event.result_history == []
    assert event.clear_result_calls == 0


@pytest.mark.asyncio
async def test_run_agent_closing_generator_cancels_and_awaits_stop_watcher(
    monkeypatch,
):
    watcher_cancelled = asyncio.Event()

    async def fake_stop_watcher(_runner, _event):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            watcher_cancelled.set()
            raise

    monkeypatch.setattr(util, "_watch_agent_stop_signal", fake_stop_watcher)
    runner = FakeRunner(
        [_response("llm_result", MessageChain().message("first"))],
        event=FakeEvent(),
    )

    generator = util.run_agent(runner)
    await anext(generator)
    await asyncio.sleep(0)
    await generator.aclose()

    await asyncio.wait_for(watcher_cancelled.wait(), timeout=1)


@pytest.mark.asyncio
async def test_run_agent_sends_tool_result_status_after_recorded_tool_call():
    event = FakeEvent()
    runner = FakeRunner(
        [
            _response(
                "tool_call",
                MessageChain(chain=[Json(data={"id": "call-1", "name": "search"})]),
            ),
            _response(
                "tool_call_result",
                MessageChain(
                    chain=[Json(data={"id": "call-1", "result": "x" * 100})],
                ),
            ),
        ],
        event=event,
    )

    outputs = [
        chain
        async for chain in util.run_agent(
            runner,
            show_tool_use=True,
            show_tool_call_result=True,
        )
    ]

    assert outputs == []
    assert event.send.await_count == 1
    sent_chain = event.send.await_args.args[0]
    assert sent_chain.type == "tool_call"
    assert "search" in sent_chain.get_plain_text()
    assert "..." in sent_chain.get_plain_text()


@pytest.mark.asyncio
async def test_run_agent_tool_result_status_send_failure_reports_execution_error(
    monkeypatch,
):
    monkeypatch.setattr(
        util,
        "get_agent_error_message",
        lambda event: "Error occurred during AI execution.",
    )
    event = FakeEvent()
    event.send.side_effect = RuntimeError("tool result status failed")
    runner = FakeRunner(
        [
            _response(
                "tool_call",
                MessageChain(chain=[Json(data={"id": "call-1", "name": "search"})]),
            ),
            _response(
                "tool_call_result",
                MessageChain(
                    chain=[Json(data={"id": "call-1", "result": "final result"})],
                ),
            ),
        ],
        event=event,
    )

    outputs = [
        chain
        async for chain in util.run_agent(
            runner,
            show_tool_use=True,
            show_tool_call_result=True,
        )
    ]

    assert outputs == []
    assert len(event.result_history) == 1
    assert (
        event.result_history[0].get_plain_text()
        == "Error occurred during AI execution."
    )
    runner.agent_hooks.on_agent_done.assert_awaited_once()
    llm_response = runner.agent_hooks.on_agent_done.await_args.args[1]
    assert llm_response.role == "err"
    assert llm_response.completion_text == "Error occurred during AI execution."


@pytest.mark.asyncio
async def test_run_agent_converts_step_exception_to_error_result(monkeypatch):
    monkeypatch.setattr(
        util,
        "get_agent_error_message",
        lambda event: "Error occurred during AI execution.",
    )
    event = FakeEvent()
    runner = FakeRunner(RuntimeError("boom"), event=event)

    outputs = [chain async for chain in util.run_agent(runner)]

    assert outputs == []
    assert len(event.result_history) == 1
    assert (
        event.result_history[0].get_plain_text()
        == "Error occurred during AI execution."
    )
    runner.agent_hooks.on_agent_done.assert_awaited_once()
    llm_response = runner.agent_hooks.on_agent_done.await_args.args[1]
    assert llm_response.role == "err"
    assert llm_response.completion_text == "Error occurred during AI execution."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_text", "secret"),
    [
        ("Authorization: Bearer bearer-secret-token", "bearer-secret-token"),
        ("api_key=api-secret-value", "api-secret-value"),
        (
            "https://provider.example/v1?access_token=query-secret&model=test",
            "query-secret",
        ),
        ("ordinary provider failure", "ordinary provider failure"),
    ],
)
async def test_run_agent_exception_details_never_reach_user_and_logs_redact_secrets(
    monkeypatch,
    error_text: str,
    secret: str,
):
    logger_error = MagicMock()
    monkeypatch.setattr(util.logger, "error", logger_error)
    event = FakeEvent()
    runner = FakeRunner(RuntimeError(error_text), event=event, streaming=True)

    outputs = [chain async for chain in util.run_agent(runner)]

    assert [chain.get_plain_text() for chain in outputs] == [
        "Error occurred during AI execution."
    ]
    assert secret not in outputs[0].get_plain_text()
    if secret != "ordinary provider failure":
        assert secret not in str(logger_error.call_args_list)


@pytest.mark.asyncio
async def test_run_agent_streaming_tool_call_yields_break_and_sends_status():
    event = FakeEvent()
    runner = FakeRunner(
        [
            _response(
                "tool_call",
                MessageChain(chain=[Json(data={"id": "call-1", "name": "search"})]),
            ),
        ],
        event=event,
        streaming=True,
    )

    outputs = [
        chain
        async for chain in util.run_agent(
            runner,
            show_tool_use=True,
            show_tool_call_result=False,
        )
    ]

    assert len(outputs) == 1
    assert outputs[0].type == "break"
    assert outputs[0].chain == []
    event.send.assert_awaited_once()
    sent_chain = event.send.await_args.args[0]
    assert sent_chain.type == "tool_call"
    assert "search" in sent_chain.get_plain_text()


@pytest.mark.asyncio
async def test_run_agent_streaming_tool_call_status_send_failure_yields_break_then_error(
    monkeypatch,
):
    monkeypatch.setattr(
        util,
        "get_agent_error_message",
        lambda event: "Error occurred during AI execution.",
    )
    event = FakeEvent()
    event.send.side_effect = RuntimeError("tool status failed")
    runner = FakeRunner(
        [
            _response(
                "tool_call",
                MessageChain(chain=[Json(data={"id": "call-1", "name": "search"})]),
            ),
        ],
        event=event,
        streaming=True,
    )

    outputs = [
        chain
        async for chain in util.run_agent(
            runner,
            show_tool_use=True,
            show_tool_call_result=False,
        )
    ]

    assert len(outputs) == 2
    assert outputs[0].type == "break"
    assert outputs[0].chain == []
    assert outputs[1].get_plain_text() == "Error occurred during AI execution."
    assert event.result_history == []
    runner.agent_hooks.on_agent_done.assert_awaited_once()
    llm_response = runner.agent_hooks.on_agent_done.await_args.args[1]
    assert llm_response.role == "err"
    assert llm_response.completion_text == "Error occurred during AI execution."


@pytest.mark.asyncio
async def test_run_agent_streaming_tool_call_without_status_does_not_yield_break_or_send():
    event = FakeEvent()
    runner = FakeRunner(
        [
            _response(
                "tool_call",
                MessageChain(chain=[Json(data={"id": "call-1", "name": "search"})]),
            ),
        ],
        event=event,
        streaming=True,
    )

    outputs = [
        chain
        async for chain in util.run_agent(
            runner,
            show_tool_use=False,
            show_tool_call_result=False,
        )
    ]

    assert outputs == []
    event.send.assert_not_awaited()
    assert event.result_history == []


@pytest.mark.asyncio
async def test_run_agent_sends_generic_tool_call_status_for_unstructured_payload():
    event = FakeEvent()
    runner = FakeRunner(
        [_response("tool_call", MessageChain().message("raw tool payload"))],
        event=event,
    )

    outputs = [
        chain
        async for chain in util.run_agent(
            runner,
            show_tool_use=True,
            show_tool_call_result=True,
        )
    ]

    assert outputs == []
    event.send.assert_awaited_once()
    sent_chain = event.send.await_args.args[0]
    assert sent_chain.type == "tool_call"
    assert sent_chain.get_plain_text() == "🔨 调用工具..."


@pytest.mark.asyncio
async def test_run_agent_tool_direct_result_sends_chain_immediately():
    event = FakeEvent()
    direct_chain = MessageChain(type="tool_direct_result").message("direct reply")
    runner = FakeRunner(
        [_response("tool_call_result", direct_chain)],
        event=event,
    )

    outputs = [chain async for chain in util.run_agent(runner)]

    assert outputs == []
    event.send.assert_awaited_once_with(direct_chain)
    assert event.result_history == []


@pytest.mark.asyncio
async def test_run_agent_tool_direct_result_send_failure_reports_execution_error(
    monkeypatch,
):
    monkeypatch.setattr(
        util,
        "get_agent_error_message",
        lambda event: "Error occurred during AI execution.",
    )
    event = FakeEvent()
    event.send.side_effect = RuntimeError("direct send failed")
    direct_chain = MessageChain(type="tool_direct_result").message("direct reply")
    runner = FakeRunner(
        [_response("tool_call_result", direct_chain)],
        event=event,
    )

    outputs = [chain async for chain in util.run_agent(runner)]

    assert outputs == []
    assert len(event.result_history) == 1
    assert (
        event.result_history[0].get_plain_text()
        == "Error occurred during AI execution."
    )
    runner.agent_hooks.on_agent_done.assert_awaited_once()
    llm_response = runner.agent_hooks.on_agent_done.await_args.args[1]
    assert llm_response.role == "err"
    assert llm_response.completion_text == "Error occurred during AI execution."


@pytest.mark.asyncio
async def test_run_agent_hides_tool_result_when_only_tool_call_status_is_enabled():
    event = FakeEvent(platform_id="qq")
    runner = FakeRunner(
        [
            _response(
                "tool_call",
                MessageChain(chain=[Json(data={"id": "call-1", "name": "search"})]),
            ),
            _response(
                "tool_call_result",
                MessageChain(chain=[Json(data={"id": "call-1", "result": "hidden"})]),
            ),
        ],
        event=event,
    )

    outputs = [
        chain
        async for chain in util.run_agent(
            runner,
            show_tool_use=True,
            show_tool_call_result=False,
        )
    ]

    assert outputs == []
    event.send.assert_awaited_once()
    sent_chain = event.send.await_args.args[0]
    assert sent_chain.type == "tool_call"
    assert sent_chain.get_plain_text() == "🔨 调用工具: search"


@pytest.mark.asyncio
async def test_run_agent_max_step_disables_tools_and_injects_summary_prompt():
    event = FakeEvent()
    runner = MultiStepRunner(
        [
            [],
            [_response("llm_result", MessageChain().message("final"))],
        ],
        event=event,
    )

    outputs = [chain async for chain in util.run_agent(runner, max_step=1)]

    assert [chain.get_plain_text() for chain in outputs] == ["final"]
    assert runner.req.func_tool is None
    assert len(runner.run_context.messages) == 1
    assert "工具调用次数已达到上限" in runner.run_context.messages[0].content


@pytest.mark.asyncio
async def test_run_agent_streaming_uses_persona_custom_error_message(monkeypatch):
    monkeypatch.setattr(
        util,
        "get_agent_error_message",
        lambda event: "persona error",
    )
    event = FakeEvent()
    runner = FakeRunner(RuntimeError("boom"), event=event, streaming=True)

    outputs = [chain async for chain in util.run_agent(runner)]

    assert len(outputs) == 1
    assert outputs[0].get_plain_text() == "persona error"
    assert event.result_history == []
    runner.agent_hooks.on_agent_done.assert_awaited_once()
    llm_response = runner.agent_hooks.on_agent_done.await_args.args[1]
    assert llm_response.completion_text == "persona error"


@pytest.mark.asyncio
async def test_run_agent_non_streaming_uses_persona_custom_error_message(monkeypatch):
    monkeypatch.setattr(
        util,
        "get_agent_error_message",
        lambda event: "persona error",
    )
    event = FakeEvent()
    runner = FakeRunner(RuntimeError("boom"), event=event)

    outputs = [chain async for chain in util.run_agent(runner)]

    assert outputs == []
    assert len(event.result_history) == 1
    assert event.result_history[0].get_plain_text() == "persona error"
    runner.agent_hooks.on_agent_done.assert_awaited_once()
    llm_response = runner.agent_hooks.on_agent_done.await_args.args[1]
    assert llm_response.completion_text == "persona error"


@pytest.mark.asyncio
async def test_run_agent_non_streaming_webchat_sends_agent_stats_after_completion():
    event = FakeEvent(platform_name="webchat")
    runner = FakeRunner(
        [
            _stats_response({"steps": 1}),
            _response("llm_result", MessageChain().message("done")),
        ],
        event=event,
    )

    outputs = [chain async for chain in util.run_agent(runner)]

    assert [chain.get_plain_text() for chain in outputs] == ["done"]
    assert len(event.result_history) == 1
    assert event.result_history[0].result_content_type == ResultContentType.LLM_RESULT
    assert event.clear_result_calls == 1
    event.send.assert_awaited_once()
    assert event.send.await_args.args[0].type == "agent_stats"
    assert event.send.await_args.args[0].chain[0].data == {"steps": 1}


@pytest.mark.asyncio
async def test_run_agent_webchat_stats_send_failure_preserves_model_response(
    monkeypatch,
):
    event = FakeEvent(platform_name="webchat")
    event.send.side_effect = RuntimeError("stats send failed")
    runner = FakeRunner(
        [
            _stats_response({"steps": 1}),
            _response("llm_result", MessageChain().message("done")),
        ],
        event=event,
    )
    logger_error = MagicMock()
    monkeypatch.setattr(util.logger, "error", logger_error)

    outputs = [chain async for chain in util.run_agent(runner)]

    assert [chain.get_plain_text() for chain in outputs] == ["done"]
    assert len(event.result_history) == 1
    assert event.result_history[0].get_plain_text() == "done"
    runner.agent_hooks.on_agent_done.assert_not_awaited()
    logger_error.assert_called_once()
    assert "Failed to send agent statistics" in logger_error.call_args.args[0]


@pytest.mark.asyncio
async def test_run_agent_streaming_can_yield_reasoning_when_enabled():
    event = FakeEvent()
    reasoning = MessageChain(type="reasoning").message("thinking")
    runner = FakeRunner(
        [_response("streaming_delta", reasoning)],
        event=event,
        streaming=True,
    )

    outputs = [chain async for chain in util.run_agent(runner, show_reasoning=True)]

    assert len(outputs) == 1
    assert outputs[0].type == "reasoning"
    assert outputs[0].get_plain_text() == "thinking"


@pytest.mark.asyncio
async def test_run_agent_stream_to_general_suppresses_streaming_delta_outputs():
    event = FakeEvent()
    runner = FakeRunner(
        [_response("streaming_delta", MessageChain().message("delta"))],
        event=event,
        streaming=True,
    )

    outputs = [
        chain
        async for chain in util.run_agent(
            runner,
            stream_to_general=True,
        )
    ]

    assert outputs == []
    assert event.result_history == []


@pytest.mark.asyncio
async def test_run_agent_ignores_reasoning_llm_result_in_non_streaming_mode():
    event = FakeEvent()
    runner = FakeRunner(
        [_response("llm_result", MessageChain(type="reasoning").message("thinking"))],
        event=event,
    )

    outputs = [chain async for chain in util.run_agent(runner)]

    assert outputs == []
    assert event.result_history == []
    assert event.clear_result_calls == 0


@pytest.mark.asyncio
async def test_run_agent_stream_to_general_emits_llm_result_chain():
    event = FakeEvent()
    runner = FakeRunner(
        [_response("llm_result", MessageChain().message("final answer"))],
        event=event,
        streaming=True,
    )

    outputs = [
        chain
        async for chain in util.run_agent(
            runner,
            stream_to_general=True,
        )
    ]

    assert [chain.get_plain_text() for chain in outputs] == ["final answer"]
    assert len(event.result_history) == 1
    assert event.result_history[0].result_content_type == ResultContentType.LLM_RESULT
    assert event.clear_result_calls == 1


@pytest.mark.asyncio
async def test_run_agent_midstream_stop_request_suppresses_later_outputs():
    event = FakeEvent()
    runner = FakeRunner(
        [
            _response("llm_result", MessageChain().message("first")),
            _response("llm_result", MessageChain().message("second")),
        ],
        event=event,
    )

    agen = util.run_agent(runner)
    first = await anext(agen)
    event.set_extra("agent_stop_requested", True)
    remaining = [chain async for chain in agen]

    assert first.get_plain_text() == "first"
    assert remaining == []
    assert runner.stop_requested is True
    assert event.clear_result_calls == 1


@pytest.mark.asyncio
async def test_run_agent_requests_stop_when_agent_stop_flag_is_pre_set():
    event = FakeEvent()
    event.set_extra("agent_stop_requested", True)
    runner = FakeRunner(
        [_response("llm_result", MessageChain().message("ignored"))],
        event=event,
    )

    outputs = [chain async for chain in util.run_agent(runner)]

    assert outputs == []
    assert runner.stop_requested is True
    assert event.result_history == []


@pytest.mark.asyncio
async def test_run_agent_sends_tool_result_status_with_unknown_name_when_untracked():
    event = FakeEvent()
    runner = FakeRunner(
        [
            _response(
                "tool_call_result",
                MessageChain(chain=[Json(data={"id": "missing", "result": "done"})]),
            ),
        ],
        event=event,
    )

    outputs = [
        chain
        async for chain in util.run_agent(
            runner,
            show_tool_use=True,
            show_tool_call_result=True,
        )
    ]

    assert outputs == []
    event.send.assert_awaited_once()
    assert "unknown" in event.send.await_args.args[0].get_plain_text()


@pytest.mark.asyncio
async def test_run_agent_tool_result_status_falls_back_to_plain_text_without_json_result():
    event = FakeEvent()
    runner = FakeRunner(
        [
            _response(
                "tool_call",
                MessageChain(chain=[Json(data={"id": "call-1", "name": "search"})]),
            ),
            _response("tool_call_result", MessageChain().message("plain tool output")),
        ],
        event=event,
    )

    outputs = [
        chain
        async for chain in util.run_agent(
            runner,
            show_tool_use=True,
            show_tool_call_result=True,
        )
    ]

    assert outputs == []
    event.send.assert_awaited_once()
    sent_text = event.send.await_args.args[0].get_plain_text()
    assert "unknown" in sent_text
    assert "plain tool output" in sent_text


@pytest.mark.asyncio
async def test_run_agent_sends_raw_tool_call_for_webchat_platform_name():
    event = FakeEvent(platform_name="webchat")
    tool_chain = MessageChain(chain=[Json(data={"id": "call-1", "name": "search"})])
    runner = FakeRunner(
        [_response("tool_call", tool_chain)],
        event=event,
    )

    outputs = [chain async for chain in util.run_agent(runner, show_tool_use=False)]

    assert outputs == []
    event.send.assert_any_await(tool_chain)


@pytest.mark.asyncio
async def test_run_agent_webchat_tool_result_is_sent_directly():
    event = FakeEvent(platform_id="webchat")
    tool_result = MessageChain().message("tool output")
    runner = FakeRunner(
        [_response("tool_call_result", tool_result)],
        event=event,
    )

    outputs = [chain async for chain in util.run_agent(runner)]

    assert outputs == []
    event.send.assert_awaited_once_with(tool_result)


@pytest.mark.asyncio
async def test_run_agent_ignores_hook_failure_when_step_raises(monkeypatch):
    monkeypatch.setattr(
        util,
        "get_agent_error_message",
        lambda event: "Error occurred during AI execution.",
    )
    event = FakeEvent()
    runner = FakeRunner(RuntimeError("boom"), event=event)
    runner.agent_hooks.on_agent_done = AsyncMock(
        side_effect=RuntimeError("hook failed")
    )

    outputs = [chain async for chain in util.run_agent(runner)]

    assert outputs == []
    assert len(event.result_history) == 1
    assert (
        event.result_history[0].get_plain_text()
        == "Error occurred during AI execution."
    )
    runner.agent_hooks.on_agent_done.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_agent_swallows_tool_result_when_status_display_disabled():
    event = FakeEvent(platform_id="qq")
    tool_result = MessageChain().message("tool output")
    runner = FakeRunner(
        [_response("tool_call_result", tool_result)],
        event=event,
    )

    outputs = [
        chain
        async for chain in util.run_agent(
            runner,
            show_tool_use=False,
            show_tool_call_result=False,
        )
    ]

    assert outputs == []
    event.send.assert_not_awaited()
    assert event.result_history == []


@pytest.mark.asyncio
async def test_watch_agent_stop_signal_returns_immediately_when_runner_done():
    event = FakeEvent()
    runner = SimpleNamespace(done=lambda: True, request_stop=MagicMock())

    await util._watch_agent_stop_signal(runner, event)

    runner.request_stop.assert_not_called()


@pytest.mark.asyncio
async def test_watch_agent_stop_signal_requests_stop_once_flag_appears():
    event = FakeEvent()
    runner = FakeRunner([], event=event)

    async def set_flag():
        await asyncio.sleep(0)
        event.set_extra("agent_stop_requested", True)

    toggle_task = asyncio.create_task(set_flag())
    await util._watch_agent_stop_signal(runner, event)
    await toggle_task

    assert runner.stop_requested is True


@pytest.mark.asyncio
async def test_watch_agent_stop_signal_requests_stop_when_event_is_already_stopped():
    event = FakeEvent()
    event._stopped = True
    runner = FakeRunner([], event=event)

    await util._watch_agent_stop_signal(runner, event)

    assert runner.stop_requested is True
