import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from astrbot.core.agent.tool_call_approval import (
    ToolCallApprovalContext,
    ToolCallApprovalResult,
    request_tool_call_approval,
)


class DummyEvent:
    def __init__(self) -> None:
        self.unified_msg_origin = "test:friend:test_user"
        self.sent_messages = []
        self.message_str = ""

    async def send(self, message) -> None:
        self.sent_messages.append(message)


@pytest.mark.asyncio
async def test_request_tool_call_approval_disabled_returns_approved():
    event = DummyEvent()
    result = await request_tool_call_approval(
        config={"enable": False},
        ctx=ToolCallApprovalContext(
            event=event,
            tool_name="test_tool",
            tool_args={},
            tool_call_id="call_1",
        ),
    )
    assert result.approved is True
    assert result.reason == "approved"
    assert len(event.sent_messages) == 0


@pytest.mark.asyncio
async def test_dynamic_code_approval_passed(monkeypatch):
    async def _mock_wait(*args, **kwargs):
        return ToolCallApprovalResult(approved=True, reason="approved")

    monkeypatch.setattr(
        "astrbot.core.agent.tool_call_approval._wait_for_code_input",
        _mock_wait,
    )

    event = DummyEvent()
    result = await request_tool_call_approval(
        config={"enable": True, "strategy": "dynamic_code"},
        ctx=ToolCallApprovalContext(
            event=event,
            tool_name="test_tool",
            tool_args={"query": "hello"},
            tool_call_id="call_2",
        ),
    )
    assert result.approved is True
    assert result.reason == "approved"
    assert len(event.sent_messages) == 1


@pytest.mark.asyncio
async def test_dynamic_code_approval_rejected(monkeypatch):
    async def _mock_wait(*args, **kwargs):
        return ToolCallApprovalResult(
            approved=False,
            reason="rejected",
            detail="not_code",
        )

    monkeypatch.setattr(
        "astrbot.core.agent.tool_call_approval._wait_for_code_input",
        _mock_wait,
    )

    event = DummyEvent()
    result = await request_tool_call_approval(
        config={"enable": True, "strategy": "dynamic_code"},
        ctx=ToolCallApprovalContext(
            event=event,
            tool_name="test_tool",
            tool_args={},
            tool_call_id="call_3",
        ),
    )
    assert result.approved is False
    assert result.reason == "rejected"
    assert len(event.sent_messages) == 2


@pytest.mark.asyncio
async def test_request_tool_call_approval_unsupported_strategy():
    event = DummyEvent()
    result = await request_tool_call_approval(
        config={"enable": True, "strategy": "unknown_strategy"},
        ctx=ToolCallApprovalContext(
            event=event,
            tool_name="test_tool",
            tool_args={},
            tool_call_id="call_4",
        ),
    )
    assert result.approved is False
    assert result.reason == "unsupported_strategy"
    assert len(event.sent_messages) == 0
