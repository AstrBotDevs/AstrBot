import asyncio
from types import SimpleNamespace

import mcp
import pytest
from pydantic import Field

from astrbot.core.agent.evidence_store import AgentEvidenceStore
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.agent.tool_gateway import ToolContractError, ToolGateway


class _Event:
    def __init__(self) -> None:
        self.extras: dict[str, str] = {}

    def get_extra(self, key: str, default=None):
        return self.extras.get(key, default)

    def set_extra(self, key: str, value) -> None:
        self.extras[key] = value


def _tool() -> FunctionTool:
    return FunctionTool(
        name="read_price",
        description="Read a current price from an approved source.",
        parameters={
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
            "additionalProperties": False,
        },
        read_only=True,
        idempotent=True,
        risk="R0",
        resource_group="realtime_search",
    )


def test_tool_descriptor_rejects_empty_description() -> None:
    tool = _tool()
    tool.description = ""
    with pytest.raises(ToolContractError):
        ToolGateway.describe(tool)


def test_tool_descriptor_tolerates_legacy_fieldinfo_metadata() -> None:
    tool = _tool()
    # Older plugin instances can retain the class-level Pydantic FieldInfo
    # instead of materializing the newer optional metadata field.
    tool.evidence_requirements = Field()

    descriptor = ToolGateway.describe(tool)

    assert descriptor.evidence_requirements == []


def test_tool_gateway_validates_required_and_unknown_arguments() -> None:
    tool = _tool()
    with pytest.raises(ToolContractError):
        ToolGateway.validate_arguments(tool, {})
    with pytest.raises(ToolContractError):
        ToolGateway.validate_arguments(tool, {"symbol": "gold", "extra": True})


@pytest.mark.asyncio
async def test_tool_gateway_normalizes_empty_and_records_trace(
    tmp_path, monkeypatch
) -> None:
    event = _Event()
    context = ContextWrapper(context=SimpleNamespace(event=event))
    store = AgentEvidenceStore(tmp_path / "evidence.db")
    monkeypatch.setattr(
        "astrbot.core.agent.tool_gateway.get_agent_evidence_store", lambda: store
    )
    event.set_extra("agent_trace_id", "trace-test")
    store.start_run(
        trace_id="trace-test",
        session_id="private:test",
        principal_id="qq:test",
        goal="read price",
        route="standard",
    )

    async def executor(tool, run_context, **arguments):
        yield None

    outcomes = [
        outcome
        async for outcome in ToolGateway.invoke(
            executor, _tool(), context, symbol="gold"
        )
    ]
    assert len(outcomes) == 1
    assert outcomes[0].status == "empty"
    trace = store.get_trace("trace-test")
    assert trace is not None
    assert trace["attempts"][0]["status"] == "empty"
    assert trace["evidence"] == []


@pytest.mark.asyncio
async def test_tool_gateway_records_success_evidence(tmp_path, monkeypatch) -> None:
    event = _Event()
    context = ContextWrapper(context=SimpleNamespace(event=event))
    store = AgentEvidenceStore(tmp_path / "evidence.db")
    monkeypatch.setattr(
        "astrbot.core.agent.tool_gateway.get_agent_evidence_store", lambda: store
    )
    event.set_extra("agent_trace_id", "trace-success")
    store.start_run(
        trace_id="trace-success",
        session_id="private:test",
        principal_id="qq:test",
        goal="read price",
        route="standard",
    )

    async def executor(tool, run_context, **arguments):
        yield mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text="gold: 700")],
            structuredContent={"source_url": "https://example.test/gold"},
        )

    outcomes = [
        outcome
        async for outcome in ToolGateway.invoke(
            executor, _tool(), context, symbol="gold"
        )
    ]
    assert outcomes[0].status == "success"
    assert outcomes[0].evidence_ids
    assert outcomes[0].trace_id == "trace-success"
    assert outcomes[0].attempt_id.startswith("attempt-")
    assert outcomes[0].arguments_hash
    assert outcomes[0].elapsed_ms >= 0
    trace = store.get_trace("trace-success")
    assert trace is not None
    assert trace["attempts"][0]["status"] == "success"
    assert trace["evidence"][0]["source_url"] == "https://example.test/gold"
    assert "gold: 700" not in (tmp_path / "evidence.db").read_bytes().decode(
        "utf-8", errors="ignore"
    )


@pytest.mark.asyncio
async def test_tool_gateway_breaks_repeated_failures(tmp_path, monkeypatch) -> None:
    event = _Event()
    context = ContextWrapper(context=SimpleNamespace(event=event))
    event.set_extra("agent_trace_id", "trace-breaker")
    tool = _tool()
    tool.name = "breaker_test_tool"
    store = AgentEvidenceStore(tmp_path / "evidence.db")
    monkeypatch.setattr(
        "astrbot.core.agent.tool_gateway.get_agent_evidence_store", lambda: store
    )
    store.start_run(
        trace_id="trace-breaker",
        session_id="private:test",
        principal_id="qq:test",
        goal="breaker",
        route="standard",
    )

    async def executor(tool, run_context, **arguments):
        yield mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text="failure")],
            isError=True,
        )

    first = [
        item
        async for item in ToolGateway.invoke(executor, tool, context, symbol="gold")
    ]
    second = [
        item
        async for item in ToolGateway.invoke(executor, tool, context, symbol="gold")
    ]
    third = [
        item
        async for item in ToolGateway.invoke(executor, tool, context, symbol="gold")
    ]
    assert first[0].status == "failed"
    assert second[0].status == "failed"
    assert third[0].error_code == "tool_circuit_open"


@pytest.mark.asyncio
async def test_tool_gateway_bounds_fifty_plugin_calls(tmp_path, monkeypatch) -> None:
    store = AgentEvidenceStore(tmp_path / "evidence.db")
    monkeypatch.setattr(
        "astrbot.core.agent.tool_gateway.get_agent_evidence_store", lambda: store
    )
    active = 0
    peak = 0

    async def executor(tool, run_context, **arguments):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        yield "ok"

    async def invoke_one(index: int) -> None:
        event = _Event()
        event.unified_msg_origin = f"private:{index}"
        context = ContextWrapper(context=SimpleNamespace(event=event))
        tool = _tool()
        tool.name = f"bounded_tool_{index}"
        [
            item
            async for item in ToolGateway.invoke(executor, tool, context, symbol="gold")
        ]

    await asyncio.gather(*(invoke_one(index) for index in range(50)))
    assert peak <= ToolGateway.scheduler.LIMITS["realtime_search"]


@pytest.mark.asyncio
async def test_scheduler_timeout_does_not_release_another_session_lock() -> None:
    scheduler = ToolGateway.scheduler
    tool = _tool()
    session_id = "private:lock-owner"
    lock = scheduler._session_locks.setdefault(session_id, asyncio.Lock())
    await lock.acquire()
    try:
        with pytest.raises(asyncio.TimeoutError):
            async with scheduler.lease(tool, session_id, timeout=0.1):
                raise AssertionError("the timed-out waiter must not enter the lease")
        assert lock.locked()
    finally:
        lock.release()


@pytest.mark.asyncio
async def test_tool_gateway_cancels_hung_executor_with_execution_deadline(
    tmp_path, monkeypatch
) -> None:
    store = AgentEvidenceStore(tmp_path / "evidence.db")
    monkeypatch.setattr(
        "astrbot.core.agent.tool_gateway.get_agent_evidence_store", lambda: store
    )
    event = _Event()
    event.unified_msg_origin = "private:hung"
    context = ContextWrapper(context=SimpleNamespace(event=event))
    tool = _tool()
    tool.name = "hung_tool"
    tool.timeout_seconds = 0.05

    async def executor(tool, run_context, **arguments):
        await asyncio.sleep(1)
        yield "never"

    outcomes = [
        item
        async for item in ToolGateway.invoke(executor, tool, context, symbol="gold")
    ]
    assert outcomes[0].status == "timeout"
    assert outcomes[0].error_code == "tool_timeout"


@pytest.mark.asyncio
async def test_tool_gateway_bounds_executor_initialization_wait(
    tmp_path, monkeypatch
) -> None:
    """Bound legacy executors that wait before returning an async stream."""
    store = AgentEvidenceStore(tmp_path / "evidence.db")
    monkeypatch.setattr(
        "astrbot.core.agent.tool_gateway.get_agent_evidence_store", lambda: store
    )
    event = _Event()
    event.unified_msg_origin = "private:executor-init"
    context = ContextWrapper(context=SimpleNamespace(event=event))
    tool = _tool()
    tool.name = "slow_executor_initialization"
    tool.timeout_seconds = 0.05

    async def executor(tool, run_context, **arguments):
        await asyncio.sleep(1)

        async def stream():
            yield "never"

        return stream()

    outcomes = [
        item
        async for item in ToolGateway.invoke(executor, tool, context, symbol="gold")
    ]
    assert outcomes[0].status == "timeout"
    assert outcomes[0].error_code == "tool_timeout"


@pytest.mark.asyncio
async def test_tool_gateway_rejects_invalid_structured_output(
    tmp_path, monkeypatch
) -> None:
    store = AgentEvidenceStore(tmp_path / "evidence.db")
    monkeypatch.setattr(
        "astrbot.core.agent.tool_gateway.get_agent_evidence_store", lambda: store
    )
    event = _Event()
    event.unified_msg_origin = "private:output"
    context = ContextWrapper(context=SimpleNamespace(event=event))
    tool = _tool()
    tool.name = "structured_tool"
    tool.output_schema = {
        "type": "object",
        "required": ["value"],
        "properties": {"value": {"type": "number"}},
    }

    async def executor(tool, run_context, **arguments):
        yield mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text="bad")],
            structuredContent={"value": "not-a-number"},
        )

    outcomes = [
        item
        async for item in ToolGateway.invoke(executor, tool, context, symbol="gold")
    ]
    assert outcomes[0].status == "failed"
    assert outcomes[0].error_code == "invalid_output"


def test_evidence_store_persists_terminal_phase_and_checkpoint(tmp_path) -> None:
    store = AgentEvidenceStore(tmp_path / "evidence.db")
    store.start_run(
        trace_id="trace-terminal",
        session_id="private:test",
        principal_id="qq:test",
        goal="test",
        route="fast",
    )
    store.update_phase("trace-terminal", "RUNNING_MODEL", step=1)
    store.save_checkpoint("trace-terminal", {"step": 1, "tool": "read_price"})
    store.finish_run(
        "trace-terminal",
        "success",
        reason="assistant_response",
        final_response="done",
    )

    trace = store.get_trace("trace-terminal")
    assert trace is not None
    assert trace["run"]["final_status"] == "COMPLETED"
    assert trace["run"]["run_phase"] == "COMPLETED"
    assert trace["run"]["checkpoint_json"]
    assert trace["run"]["final_response_hash"]
