"""Lifecycle contracts for the skills-like no-tool re-query fallback."""

from __future__ import annotations

from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp.types import CallToolResult, TextContent

from astrbot.core import astr_agent_hooks as agent_hooks_module
from astrbot.core.agent.message import TextPart
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_agent_hooks import MainAgentHooks
from astrbot.core.astr_agent_run_util import run_agent
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    InternalAgentSubStage,
)
from astrbot.core.pipeline.respond import stage as respond_stage_module
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.provider.provider import Provider
from astrbot.core.star.star_handler import EventType


class _SequenceProvider(Provider):
    """Return a deterministic sequence of model responses."""

    def __init__(
        self,
        responses: Iterable[LLMResponse] = (),
        error: Exception | None = None,
    ) -> None:
        super().__init__({"id": "contract-provider", "model": "contract-model"}, {})
        self._responses = iter(responses)
        self._error = error
        self.call_count = 0

    def get_current_key(self) -> str:
        """Return a placeholder key required by the provider interface."""
        return "contract-key"

    def set_key(self, key: str) -> None:
        """Accept provider key updates without external state."""
        del key

    async def get_models(self) -> list[str]:
        """Return the single fake model exposed by this provider."""
        return ["contract-model"]

    async def text_chat(self, **kwargs: Any) -> LLMResponse:
        """Return the next configured response or raise the configured error."""
        del kwargs
        self.call_count += 1
        if self._error is not None:
            raise self._error
        return next(self._responses)

    async def text_chat_stream(self, **kwargs: Any):
        """Expose the non-streaming response through the streaming interface."""
        yield await self.text_chat(**kwargs)


class _ToolExecutor:
    """Return a stable tool result without touching external systems."""

    @classmethod
    def execute(cls, tool, run_context, **tool_args):
        """Yield one text result for a tool invocation."""
        del cls, tool, run_context, tool_args

        async def _result():
            yield CallToolResult(
                content=[TextContent(type="text", text="contract tool result")]
            )

        return _result()


class _ContractEvent:
    """Provide the event surface used by run_agent and RespondStage."""

    def __init__(self, lifecycle: list[str]) -> None:
        self.unified_msg_origin = "contract:FriendMessage:session"
        self.plugins_name: list[str] = []
        self.trace = SimpleNamespace(record=lambda *args, **kwargs: None)
        self._extras: dict[str, Any] = {}
        self._result: MessageEventResult | None = None
        self._stopped = False
        self.lifecycle = lifecycle
        self.sent_texts: list[str] = []

    def get_extra(self, key: str, default=None):
        """Return an event extra value."""
        return self._extras.get(key, default)

    def set_extra(self, key: str, value: Any) -> None:
        """Store an event extra value."""
        self._extras[key] = value

    def set_result(self, result: MessageEventResult) -> None:
        """Set the current pipeline result."""
        self._result = result

    def get_result(self) -> MessageEventResult | None:
        """Return the current pipeline result."""
        return self._result

    def clear_result(self) -> None:
        """Clear the current pipeline result."""
        self._result = None

    def stop_event(self) -> None:
        """Stop event propagation."""
        self._stopped = True

    def is_stopped(self) -> bool:
        """Return whether event propagation has stopped."""
        return self._stopped

    def get_platform_name(self) -> str:
        """Return a platform name used by the runner and respond stage."""
        return "contract"

    def get_platform_id(self) -> str:
        """Return a platform identifier used by the runner and respond stage."""
        return "contract"

    def get_sender_name(self) -> str:
        """Return a sender name for respond-stage logging."""
        return "contract-user"

    def get_sender_id(self) -> str:
        """Return a sender identifier for respond-stage logging."""
        return "contract-user-id"

    def _outline_chain(self, chain) -> str:
        """Render the text portion of a message chain for logging."""
        return "".join(str(getattr(component, "text", "")) for component in chain)

    async def send(self, payload) -> None:
        """Capture the text that the real RespondStage attempted to send."""
        chain = getattr(payload, "chain", []) or []
        text = "".join(str(getattr(component, "text", "")) for component in chain)
        self.lifecycle.append("send")
        self.sent_texts.append(text)


class _ConversationManager:
    """Capture history persisted by the real internal-agent save method."""

    def __init__(self, lifecycle: list[str]) -> None:
        self.lifecycle = lifecycle
        self.saved_history: list[dict[str, Any]] | None = None

    async def update_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str,
        *,
        history: list[dict[str, Any]],
        token_usage: int | None,
    ) -> None:
        """Capture one framework history write without external persistence."""
        del unified_msg_origin, conversation_id, token_usage
        self.saved_history = history
        self.lifecycle.append("history_save")

    async def update_conversation_merged(
        self,
        unified_msg_origin: str,
        conversation_id: str,
        *,
        history: list[dict[str, Any]],
        token_usage: int | None,
    ) -> None:
        """Capture one framework history write without external persistence."""
        del unified_msg_origin, conversation_id, token_usage
        self.saved_history = history
        self.lifecycle.append("history_save")


class _RunnerStage:
    """Expose the real runner as an onion-style pipeline stage."""

    def __init__(
        self,
        runner: ToolLoopAgentRunner,
        request: ProviderRequest,
        lifecycle: list[str],
    ) -> None:
        self.runner = runner
        self.request = request
        self.lifecycle = lifecycle
        self.conversation_manager = _ConversationManager(lifecycle)

    @property
    def saved_tail_text(self) -> str | None:
        """Return the final text written through the real history-save path."""
        history = self.conversation_manager.saved_history
        if not history:
            return None
        content = history[-1]["content"]
        if not isinstance(content, list) or not content:
            return None
        return content[-1].get("text")

    async def process(self, event: _ContractEvent):
        """Run the agent and persist history after downstream stages return."""
        async for _ in run_agent(
            self.runner,
            max_step=8,
            show_tool_use=False,
            show_tool_call_result=False,
            buffer_intermediate_messages=False,
        ):
            yield

        final_response = self.runner.get_final_llm_resp()
        history_owner = SimpleNamespace(conv_manager=self.conversation_manager)
        await InternalAgentSubStage._save_to_history(
            history_owner,
            event,
            self.request,
            final_response,
            self.runner.run_context.messages,
            self.runner.stats,
        )


def _tool_call(name: str, call_id: str) -> LLMResponse:
    """Build a model response that requests one tool call."""
    return LLMResponse(
        role="assistant",
        completion_text="",
        tools_call_name=[name],
        tools_call_args=[{"query": call_id}],
        tools_call_ids=[call_id],
    )


def _final(text: str) -> LLMResponse:
    """Build a plain final assistant response."""
    return LLMResponse(role="assistant", completion_text=text)


async def _run_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    responses: Iterable[LLMResponse] = (),
    *,
    tool_schema_mode: str = "full",
    error: Exception | None = None,
) -> tuple[_ContractEvent, _RunnerStage, _SequenceProvider, list[str], list[str]]:
    """Run a real runner/scheduler/respond lifecycle with isolated fake I/O."""
    lifecycle: list[str] = []
    after_hook_texts: list[str] = []
    event = _ContractEvent(lifecycle)
    provider = _SequenceProvider(responses, error=error)

    tool = FunctionTool(
        name="contract_tool",
        description="Contract test tool",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=AsyncMock(),
    )
    request = ProviderRequest(
        prompt="Run the contract scenario",
        func_tool=ToolSet(tools=[tool]),
        contexts=[],
        conversation=SimpleNamespace(cid="contract-conversation", token_usage=0),
    )
    runner = ToolLoopAgentRunner()

    async def _agent_hook(event_arg, hook_type, *args, **kwargs):
        del event_arg, kwargs
        if hook_type == EventType.OnLLMResponseEvent:
            response = args[0]
            lifecycle.append("response_hook")
            if response.role == "assistant" and response.completion_text:
                response.completion_text = f"reviewed::{response.completion_text}"
        elif hook_type == EventType.OnAgentDoneEvent:
            run_context, response = args
            lifecycle.append("agent_done_hook")
            if response.role == "assistant" and response.completion_text:
                last_part = run_context.messages[-1].content[-1]
                assert isinstance(last_part, TextPart)
                last_part.text = response.completion_text
        return False

    async def _after_hook(event_arg, hook_type, *args, **kwargs):
        del args, kwargs
        assert hook_type == EventType.OnAfterMessageSentEvent
        result = event_arg.get_result()
        assert result is not None
        text = "".join(
            str(getattr(component, "text", "")) for component in result.chain
        )
        lifecycle.append("after_hook")
        after_hook_texts.append(text)
        return False

    monkeypatch.setattr(agent_hooks_module, "call_event_hook", _agent_hook)
    monkeypatch.setattr(respond_stage_module, "call_event_hook", _after_hook)

    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(context=SimpleNamespace(event=event)),
        tool_executor=_ToolExecutor(),
        agent_hooks=MainAgentHooks(),
        streaming=False,
        tool_schema_mode=tool_schema_mode,
        request_max_retries=0,
    )

    runner_stage = _RunnerStage(runner, request, lifecycle)
    respond_stage = RespondStage()
    respond_stage.config = {"provider_settings": {}}
    respond_stage.platform_settings = {"path_mapping": []}
    respond_stage.enable_seg = False

    scheduler = PipelineScheduler(SimpleNamespace())
    scheduler.stages = [runner_stage, respond_stage]
    await scheduler._process_stages(event)

    return event, runner_stage, provider, lifecycle, after_hook_texts


@pytest.mark.asyncio
async def test_skills_like_no_tool_requery_runs_hooks_before_send_and_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Send only the post-hook fallback text and persist the same text."""
    event, runner_stage, provider, lifecycle, after_texts = await _run_lifecycle(
        monkeypatch,
        [_tool_call("contract_tool", "select-1"), _final("fallback draft")],
        tool_schema_mode="skills_like",
    )

    assert provider.call_count == 2
    assert event.sent_texts == ["reviewed::fallback draft"]
    assert after_texts == event.sent_texts
    assert runner_stage.saved_tail_text == event.sent_texts[-1]
    assert lifecycle == [
        "response_hook",
        "agent_done_hook",
        "send",
        "after_hook",
        "history_save",
    ]


@pytest.mark.asyncio
async def test_plain_final_response_keeps_existing_hook_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the existing hook-before-send order for an ordinary final response."""
    event, runner_stage, provider, lifecycle, after_texts = await _run_lifecycle(
        monkeypatch,
        [_final("plain draft")],
    )

    assert provider.call_count == 1
    assert event.sent_texts == ["reviewed::plain draft"]
    assert after_texts == event.sent_texts
    assert runner_stage.saved_tail_text == event.sent_texts[-1]
    assert lifecycle == [
        "response_hook",
        "agent_done_hook",
        "send",
        "after_hook",
        "history_save",
    ]


@pytest.mark.asyncio
async def test_full_schema_tool_call_keeps_final_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep one normal tool call followed by one audited final response."""
    event, runner_stage, provider, lifecycle, after_texts = await _run_lifecycle(
        monkeypatch,
        [_tool_call("contract_tool", "full-1"), _final("tool final draft")],
    )

    assert provider.call_count == 2
    assert event.sent_texts == ["reviewed::tool final draft"]
    assert after_texts == event.sent_texts
    assert runner_stage.saved_tail_text == event.sent_texts[-1]
    assert lifecycle[-5:] == [
        "response_hook",
        "agent_done_hook",
        "send",
        "after_hook",
        "history_save",
    ]


@pytest.mark.asyncio
async def test_multiple_tool_calls_keep_final_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep a multi-step tool loop and audit only its final assistant response."""
    event, runner_stage, provider, lifecycle, after_texts = await _run_lifecycle(
        monkeypatch,
        [
            _tool_call("contract_tool", "multi-1"),
            _tool_call("contract_tool", "multi-2"),
            _final("multi final draft"),
        ],
    )

    assert provider.call_count == 3
    assert event.sent_texts == ["reviewed::multi final draft"]
    assert after_texts == event.sent_texts
    assert runner_stage.saved_tail_text == event.sent_texts[-1]
    assert lifecycle[-5:] == [
        "response_hook",
        "agent_done_hook",
        "send",
        "after_hook",
        "history_save",
    ]


@pytest.mark.asyncio
async def test_provider_error_does_not_create_assistant_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep provider failures out of assistant history while returning an error."""
    event, runner_stage, provider, lifecycle, after_texts = await _run_lifecycle(
        monkeypatch,
        error=RuntimeError("contract provider failure"),
    )

    assert provider.call_count == 1
    assert runner_stage.saved_tail_text is None
    assert len(event.sent_texts) == 1
    assert "contract provider failure" in event.sent_texts[0]
    assert after_texts == event.sent_texts
    assert "history_save" not in lifecycle
