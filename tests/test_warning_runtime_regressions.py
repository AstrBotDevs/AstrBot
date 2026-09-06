"""Runtime contracts protected while resolving core typing diagnostics."""

import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest
from shipyard import ShipyardClient
from shipyard.python import PythonComponent as ShipyardPythonComponent

from astrbot.core.agent.mcp_client import _validate_stdio_args
from astrbot.core.agent.runners.deerflow.deerflow_stream_utils import (
    extract_latest_ai_message,
    extract_latest_ai_text,
    extract_latest_clarification_text,
)
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.computer.booters.shipyard import ShipyardPythonWrapper
from astrbot.core.provider.sources.dashscope_embedding_source import (
    _make_multimodal_text_item,
)


class FutureAwaitable:
    def __init__(self, future: asyncio.Future[int]) -> None:
        self.future = future

    def __await__(self) -> Generator[object, None, int]:
        return self.future.__await__()


def _runner() -> ToolLoopAgentRunner[object]:
    runner = ToolLoopAgentRunner[object]()
    runner._abort_signal = asyncio.Event()
    return runner


@pytest.mark.asyncio
@pytest.mark.parametrize("wrap", [False, True])
async def test_await_or_stop_accepts_non_coroutine_awaitables(wrap: bool) -> None:
    loop = asyncio.get_running_loop()
    future: asyncio.Future[int] = loop.create_future()
    loop.call_soon(future.set_result, 42)
    operation = FutureAwaitable(future) if wrap else future
    assert await _runner()._await_or_stop(operation) == 42


@pytest.mark.asyncio
async def test_await_or_stop_cancels_future_on_stop() -> None:
    runner = _runner()
    loop = asyncio.get_running_loop()
    future: asyncio.Future[int] = loop.create_future()
    loop.call_soon(runner.request_stop)
    assert await runner._await_or_stop(future) is None
    assert future.cancelled()


@pytest.mark.asyncio
async def test_await_or_stop_cleans_up_on_outer_cancellation() -> None:
    loop = asyncio.get_running_loop()
    future: asyncio.Future[int] = loop.create_future()
    task = asyncio.create_task(_runner()._await_or_stop(future))
    loop.call_soon(task.cancel)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert future.cancelled()


@pytest.mark.parametrize(
    ("command", "args"),
    [
        ("python", ["-c", "print('blocked')"]),
        ("python3", ["-Ic", "print('blocked')"]),
        ("node", ["--eval", "console.log('blocked')"]),
        ("bun", ["-p", "1 + 1"]),
        ("docker", ["run", "--privileged", "server"]),
        ("docker", ["run", "--network", "host", "server"]),
        ("python", ["server.py\n"]),
        ("python", ["server.py\x00"]),
        ("python", ["server.py", 7]),
        ("python", "server.py"),
    ],
)
def test_stdio_narrowing_preserves_security_rejections(
    command: str, args: object
) -> None:
    with pytest.raises(ValueError):
        _validate_stdio_args(command, args)


@pytest.mark.parametrize(
    ("command", "args"),
    [("python", ["-m", "mcp_server"]), ("node", ["server.js"]), ("uv", None)],
)
def test_stdio_narrowing_accepts_valid_launches(command: str, args: object) -> None:
    _validate_stdio_args(command, args)


def test_deerflow_extractors_keep_message_identity_and_skip_non_objects() -> None:
    assistant = {"role": "assistant", "content": [{"type": "text", "text": "answer"}]}
    clarification = {
        "type": "tool",
        "name": "ask_clarification",
        "content": "Which workspace?",
    }
    messages: list[object] = [None, 3, assistant, clarification, "not a message"]
    assert extract_latest_ai_message(iter(messages)) is assistant
    assert extract_latest_ai_text(messages) == "answer"
    assert extract_latest_clarification_text(messages) == "Which workspace?"


@pytest.mark.asyncio
async def test_shipyard_python_adapter_uses_actual_sdk_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ShipyardClient(endpoint_url="http://localhost:8123", access_token="test")
    execute = AsyncMock(return_value={"output": "2"})
    monkeypatch.setattr(client, "_exec_operation", execute)
    python = ShipyardPythonWrapper(ShipyardPythonComponent(client, "ship", "session"))
    assert await python.exec("1 + 1", cwd=None) == {"output": "2"}
    execute.assert_awaited_once_with(
        "ship",
        "ipython/exec",
        {"code": "1 + 1", "kernel_id": None, "timeout": 30, "silent": False},
        "session",
    )
    with pytest.raises(NotImplementedError, match="cwd"):
        await python.exec("1 + 1", cwd="/workspace")
    assert execute.await_count == 1


def test_dashscope_sdk_payload_preserves_text_only_wire_format() -> None:
    assert _make_multimodal_text_item("hello") == {"text": "hello"}
