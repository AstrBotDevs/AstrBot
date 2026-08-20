import asyncio
import threading
from collections.abc import AsyncGenerator
from types import SimpleNamespace

import pytest
from dashscope.app.application_response import ApplicationOutput, ApplicationResponse

from astrbot.core.agent.llm_types import ProviderRequest
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.base import AgentState
from astrbot.core.agent.runners.dashscope import dashscope_agent_runner as runner_module
from astrbot.core.agent.runners.dashscope.dashscope_agent_runner import (
    DashscopeAgentRunner,
)

pytestmark = pytest.mark.provider

_PUBLIC_FAILURE = "阿里云百炼请求失败，请稍后重试。"


class _Preferences:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str, str], object] = {}
        self.put_calls: list[dict] = []

    async def get_async(self, *, scope, scope_id, key, default):
        return self.values.get((scope, scope_id, key), default)

    async def put_async(self, *, scope, scope_id, key, value):
        self.put_calls.append(
            {"scope": scope, "scope_id": scope_id, "key": key, "value": value}
        )
        self.values[(scope, scope_id, key)] = value


class _Hooks:
    def __init__(self, *, begin_error: Exception | None = None, done_error=None):
        self.begin_error = begin_error
        self.done_error = done_error
        self.begin_calls = 0
        self.done_calls = []

    async def on_agent_begin(self, _context) -> None:
        self.begin_calls += 1
        if self.begin_error:
            raise self.begin_error

    async def on_agent_done(self, _context, result) -> None:
        self.done_calls.append(result)
        if self.done_error:
            raise self.done_error


class _SdkStub:
    """Offline Dashscope request double for both SDK execution paths."""

    def __init__(
        self,
        responses: list[ApplicationResponse] | None = None,
        *,
        error: Exception | None = None,
        block: bool = False,
    ) -> None:
        self.responses = responses or []
        self.error = error
        self.block = block
        self.sync_payloads: list[dict] = []
        self.async_builds: list[dict] = []
        self.sync_used = False
        self.async_used = False
        self.loop = asyncio.get_running_loop()
        self.started = asyncio.Event()
        self.finished = asyncio.Event()
        self.sync_release = threading.Event()
        self.async_release = asyncio.Event()

    def call(self, **payload):
        self.sync_used = True
        self.sync_payloads.append(payload)
        if self.error:
            raise self.error
        if payload["stream"]:
            return self._sync_stream()
        return self.responses[0]

    def build_request(self, **kwargs):
        self.async_builds.append(kwargs)
        return SimpleNamespace(aio_call=self._aio_call)

    async def _aio_call(self):
        self.async_used = True
        if self.error:
            raise self.error
        if self.async_builds[-1]["stream"]:
            return self._async_stream()
        return self.responses[0]

    def _sync_stream(self):
        try:
            if self.block:
                self.loop.call_soon_threadsafe(self.started.set)
                self.sync_release.wait()
            yield from self.responses
        finally:
            self.loop.call_soon_threadsafe(self.finished.set)

    async def _async_stream(self) -> AsyncGenerator[ApplicationResponse]:
        try:
            if self.block:
                self.started.set()
                await self.async_release.wait()
            for response in self.responses:
                yield response
        finally:
            self.finished.set()

    async def release(self) -> None:
        self.sync_release.set()
        self.async_release.set()


def _response(
    text: str = "",
    *,
    status_code: int = 200,
    message: str = "",
    session_id: str | None = None,
    doc_references: list[dict] | None = None,
) -> ApplicationResponse:
    output = None
    if status_code == 200:
        output = ApplicationOutput(
            text=text,
            session_id=session_id,
            doc_references=doc_references,
        )
    return ApplicationResponse(
        status_code=status_code,
        request_id="request-id",
        message=message,
        output=output,
    )


def _config(**overrides) -> dict:
    config = {
        "dashscope_api_key": "dashscope-key",
        "dashscope_app_id": "app-id",
        "dashscope_app_type": "agent",
        "variables": {"configured": "value"},
        "rag_options": {},
        "timeout": 7,
    }
    config.update(overrides)
    return config


async def _runner(
    *,
    streaming: bool = True,
    config: dict | None = None,
    preferences: _Preferences | None = None,
    hooks: _Hooks | None = None,
) -> tuple[DashscopeAgentRunner, _Preferences, _Hooks]:
    preferences = preferences or _Preferences()
    hooks = hooks or _Hooks()
    runner = DashscopeAgentRunner()
    await runner.reset(
        ProviderRequest(
            prompt="hello",
            session_id="session-1",
            contexts=[{"role": "user", "content": "history"}],
            system_prompt="system prompt",
        ),
        ContextWrapper(context=None),
        hooks,
        config or _config(),
        streaming=streaming,
        preferences=preferences,
    )
    return runner, preferences, hooks


def _install_sdk_stub(monkeypatch, stub: _SdkStub) -> None:
    monkeypatch.setattr(runner_module.Application, "call", stub.call)
    # The native asynchronous bridge is intentionally patched with the same
    # offline response source. `raising=False` keeps this test red before the
    # bridge is introduced.
    monkeypatch.setattr(
        runner_module,
        "_build_api_request",
        stub.build_request,
        raising=False,
    )


async def _collect(runner: DashscopeAgentRunner):
    return [response async for response in runner.step()]


def _response_text(response) -> str:
    return response.data["chain"].get_plain_text()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"dashscope_api_key": ""}, "API Key"),
        ({"dashscope_app_id": ""}, "APP ID"),
        ({"dashscope_app_type": ""}, "APP 类型"),
        ({"variables": []}, "variables"),
        ({"rag_options": []}, "rag_options"),
        ({"timeout": 0}, "timeout"),
        ({"timeout": True}, "timeout"),
        ({"timeout": 1.5}, "timeout"),
        ({"timeout": "not-a-number"}, "timeout"),
    ],
)
async def test_dashscope_reset_rejects_missing_identity_and_invalid_timeout(
    override, message
):
    config = _config(**override)
    runner = DashscopeAgentRunner()

    with pytest.raises(ValueError, match=message):
        await runner.reset(
            ProviderRequest(prompt="hello", session_id="session-1"),
            ContextWrapper(context=None),
            _Hooks(),
            config,
            streaming=True,
            preferences=_Preferences(),
        )


@pytest.mark.asyncio
async def test_dashscope_payload_preserves_session_variables_and_request_timeout():
    preferences = _Preferences()
    preferences.values[("umo", "session-1", "dashscope_conversation_id")] = (
        "dashscope-session"
    )
    preferences.values[("umo", "session-1", "session_variables")] = {
        "per_session": "value"
    }
    config = _config(timeout="13")
    runner, _, _ = await _runner(config=config, preferences=preferences)

    payload = await runner._build_request_payload(
        "hello", "session-1", [], "ignored by Dashscope applications"
    )

    assert payload == {
        "app_id": "app-id",
        "api_key": "dashscope-key",
        "prompt": "hello",
        "biz_params": {"configured": "value", "per_session": "value"},
        "stream": True,
        "incremental_output": True,
        "session_id": "dashscope-session",
        "request_timeout": 13,
    }


@pytest.mark.asyncio
async def test_dashscope_rag_payload_does_not_reuse_conversation_session():
    preferences = _Preferences()
    preferences.values[("umo", "session-1", "dashscope_conversation_id")] = (
        "must-not-be-sent"
    )
    config = _config(
        rag_options={
            "pipeline_ids": ["pipeline-1"],
            "output_reference": True,
        }
    )
    runner, _, _ = await _runner(config=config, preferences=preferences)

    payload = await runner._build_request_payload("hello", "session-1", [], "")

    assert "session_id" not in payload
    assert payload["rag_options"] == {"pipeline_ids": ["pipeline-1"]}
    assert config["rag_options"] == {
        "pipeline_ids": ["pipeline-1"],
        "output_reference": True,
    }


@pytest.mark.asyncio
async def test_dashscope_streaming_saves_session_and_appends_rag_references(
    monkeypatch,
):
    stub = _SdkStub(
        [
            _response(
                "hello <ref>[1]</ref>",
                session_id="provider-session",
                doc_references=[{"index_id": "1", "title": "Reference document"}],
            ),
            _response(" world"),
        ]
    )
    _install_sdk_stub(monkeypatch, stub)
    runner, preferences, hooks = await _runner(
        config=_config(rag_options={"output_reference": True})
    )

    responses = await _collect(runner)

    assert [response.type for response in responses] == [
        "streaming_delta",
        "streaming_delta",
        "streaming_delta",
        "llm_result",
    ]
    assert (
        _response_text(responses[-1])
        == "hello [1] world\n\n回答来源:\n1. Reference document\n"
    )
    assert preferences.put_calls == [
        {
            "scope": "umo",
            "scope_id": "session-1",
            "key": "dashscope_conversation_id",
            "value": "provider-session",
        }
    ]
    assert runner._state is AgentState.DONE
    assert hooks.begin_calls == 1
    assert hooks.done_calls == [runner.final_llm_resp]


@pytest.mark.asyncio
async def test_dashscope_non_streaming_returns_only_final_result(monkeypatch):
    stub = _SdkStub([_response("complete answer", session_id="provider-session")])
    _install_sdk_stub(monkeypatch, stub)
    runner, preferences, _ = await _runner(streaming=False)

    responses = await _collect(runner)

    assert [response.type for response in responses] == ["llm_result"]
    assert _response_text(responses[0]) == "complete answer"
    assert preferences.put_calls[0]["value"] == "provider-session"
    assert stub.async_builds[0]["stream"] is False
    assert stub.async_builds[0]["incremental_output"] is False
    assert stub.async_builds[0]["request_timeout"] == 7


@pytest.mark.asyncio
async def test_dashscope_sdk_failure_is_generic_and_redacted(caplog, monkeypatch):
    secret = (
        "api_key=super-secret Bearer provider-token password=hunter2 "
        "https://internal.example/v1 C:\\private\\config.json"
    )
    stub = _SdkStub(error=RuntimeError(secret))
    _install_sdk_stub(monkeypatch, stub)
    runner, _, _ = await _runner()

    responses = await _collect(runner)

    assert [response.type for response in responses] == ["err"]
    assert _response_text(responses[0]) == _PUBLIC_FAILURE
    assert runner.final_llm_resp.completion_text == _PUBLIC_FAILURE
    for sensitive_value in (
        "super-secret",
        "provider-token",
        "hunter2",
        "internal.example",
        "C:\\private",
    ):
        assert sensitive_value not in caplog.text


@pytest.mark.asyncio
async def test_dashscope_hook_failures_do_not_break_success_or_leak_details(
    caplog, monkeypatch
):
    secret = (
        "api_key=super-secret Bearer provider-token password=hunter2 "
        "https://internal.example/v1 C:\\private\\config.json"
    )
    stub = _SdkStub([_response("complete answer")])
    _install_sdk_stub(monkeypatch, stub)
    hooks = _Hooks(
        begin_error=RuntimeError(secret),
        done_error=RuntimeError(secret),
    )
    runner, _, _ = await _runner(hooks=hooks)

    responses = await _collect(runner)

    assert [response.type for response in responses] == [
        "streaming_delta",
        "llm_result",
    ]
    assert _response_text(responses[-1]) == "complete answer"
    assert runner._state is AgentState.DONE
    assert hooks.begin_calls == 1
    assert hooks.done_calls == [runner.final_llm_resp]
    for sensitive_value in (
        "super-secret",
        "provider-token",
        "hunter2",
        "internal.example",
        "C:\\private",
    ):
        assert sensitive_value not in caplog.text


@pytest.mark.asyncio
async def test_dashscope_provider_status_error_is_generic_and_redacted(
    caplog, monkeypatch
):
    secret = "Bearer provider-token https://internal.example/v1 password=hunter2"
    stub = _SdkStub([_response(status_code=500, message=secret)])
    _install_sdk_stub(monkeypatch, stub)
    runner, _, _ = await _runner()

    responses = await _collect(runner)
    async with asyncio.timeout(0.2):
        await stub.finished.wait()

    assert [response.type for response in responses] == ["err"]
    assert _response_text(responses[0]) == _PUBLIC_FAILURE
    for sensitive_value in ("provider-token", "internal.example", "hunter2"):
        assert sensitive_value not in caplog.text


@pytest.mark.asyncio
async def test_dashscope_timeout_finishes_request_and_closes_stream(monkeypatch):
    stub = _SdkStub(block=True)
    _install_sdk_stub(monkeypatch, stub)
    runner, _, _ = await _runner()
    # A zero deadline makes the timeout transition deterministic without a
    # real sleep. Reset validates production configuration as positive.
    runner.timeout = 0

    try:
        async with asyncio.timeout(0.2):
            responses = await _collect(runner)
        async with asyncio.timeout(0.2):
            await stub.finished.wait()
    finally:
        await stub.release()

    assert [response.type for response in responses] == ["err"]
    assert _response_text(responses[0]) == _PUBLIC_FAILURE
    assert runner._state is AgentState.ERROR


@pytest.mark.asyncio
async def test_dashscope_completed_request_never_uses_an_executor(monkeypatch):
    stub = _SdkStub([_response("complete answer")])
    _install_sdk_stub(monkeypatch, stub)
    runner, _, _ = await _runner()
    loop = asyncio.get_running_loop()

    def _unexpected_executor(*_args, **_kwargs):
        raise AssertionError("Dashscope runner must not create executor work")

    monkeypatch.setattr(loop, "run_in_executor", _unexpected_executor)

    responses = await _collect(runner)

    assert [response.type for response in responses] == [
        "streaming_delta",
        "llm_result",
    ]
    assert stub.async_used is True
    assert stub.sync_used is False


@pytest.mark.asyncio
async def test_dashscope_cancellation_closes_async_stream_without_executor(monkeypatch):
    stub = _SdkStub(block=True)
    _install_sdk_stub(monkeypatch, stub)
    runner, _, _ = await _runner()
    task = asyncio.create_task(_collect(runner))
    try:
        async with asyncio.timeout(1):
            await stub.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with asyncio.timeout(0.2):
            await stub.finished.wait()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await stub.release()

    assert stub.async_used is True
    assert stub.sync_used is False
