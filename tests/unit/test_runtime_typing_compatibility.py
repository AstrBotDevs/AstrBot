"""Public typing values retain their Python 3.12 runtime contracts."""

import json
from typing import Any, get_args

import pytest
from pydantic import TypeAdapter, ValidationError

from astrbot.core.agent.agent import Agent
from astrbot.core.agent.events import JsonObject, TurnStatus
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.input import InputComponent, PlainInput
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.output import ImageOutput, OutputComponent, PathMedia
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.base import BaseAgentRunner
from astrbot.core.agent.runtime import AgentRole, SessionState
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
from astrbot.core.astr_agent_runtime.subagents.store import AgentState, DeliveryStage


@pytest.mark.parametrize(
    "generic",
    [
        Agent,
        HandoffTool,
        BaseAgentRunHooks,
        ContextWrapper,
        BaseAgentRunner,
        BaseFunctionToolExecutor,
        MCPTool,
    ],
)
def test_sdk_generic_context_keeps_its_optional_default(generic):
    parameter = generic.__parameters__[0]
    assert parameter.__default__ is Any
    assert get_args(generic[()]) == (Any,)


@pytest.mark.parametrize(
    "member,value",
    [
        (TurnStatus.COMPLETED, "completed"),
        (AgentRole.ADMIN, "admin"),
        (SessionState.RUNNING, "running"),
        (AgentState.TIMED_OUT, "timed_out"),
        (DeliveryStage.COMMITTED, "committed"),
    ],
)
def test_string_enums_preserve_display_format_and_wire_values(member, value):
    display = f"{type(member).__name__}.{member.name}"
    assert str(member) == display
    assert f"{member:>30}" == f"{display:>30}"
    assert member == value and hash(member) == hash(value)
    assert json.dumps({"state": member}) == json.dumps({"state": value})


def test_exported_aliases_remain_eager_runtime_values():
    assert JsonObject() == {}
    assert isinstance(PlainInput(text="hello"), InputComponent)
    image = TypeAdapter(OutputComponent).validate_python(
        {"type": "image", "source": {"kind": "path", "path": "/work/image.png"}}
    )
    assert isinstance(image, ImageOutput)
    assert isinstance(image.source, PathMedia)
    assert image.model_dump() == {
        "type": "image",
        "source": {"kind": "path", "path": "/work/image.png", "mime_type": None},
    }


def test_parameterized_context_still_validates_its_concrete_type():
    adapter = TypeAdapter(ContextWrapper[int])
    context = adapter.validate_python({"context": "7"})
    assert context.context == 7 and isinstance(context.context, int)
    with pytest.raises(ValidationError):
        adapter.validate_python({"context": "not an integer"})
