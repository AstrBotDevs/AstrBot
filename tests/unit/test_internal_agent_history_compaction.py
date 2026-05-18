from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.message import Message, ToolCallMessageSegment
from astrbot.core.db.po import Conversation
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    InternalAgentSubStage,
    _count_conversation_turns,
    _history_exceeds_turn_limit,
)
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.provider.provider import Provider


class FakeSummaryProvider(Provider):
    def __init__(self) -> None:
        super().__init__({"id": "summary", "type": "test"}, {})
        self.text_chat_mock = AsyncMock(
            return_value=LLMResponse(role="assistant", completion_text="old summary")
        )

    def get_current_key(self) -> str:
        return "test-key"

    def set_key(self, key: str) -> None:
        pass

    async def get_models(self) -> list[str]:
        return ["test-model"]

    async def text_chat(self, **kwargs) -> LLMResponse:
        return await self.text_chat_mock(**kwargs)


def make_stage(
    *,
    provider: Provider | None = None,
    current_provider: Provider | None = None,
    max_turns: int = 3,
    provider_id: str | None = "summary",
):
    stage = InternalAgentSubStage()
    stage.max_context_length = max_turns
    stage.dequeue_context_length = 1
    stage.context_limit_reached_strategy = "llm_compress"
    stage.llm_compress_provider_id = provider_id or ""
    stage.llm_compress_keep_recent = 2
    stage.llm_compress_instruction = "Summarize history"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    plugin_context = SimpleNamespace(
        get_provider_by_id=MagicMock(return_value=provider),
        get_using_provider=MagicMock(return_value=current_provider),
    )
    stage.ctx = SimpleNamespace(plugin_manager=SimpleNamespace(context=plugin_context))
    return stage


def make_event():
    event = MagicMock()
    event.unified_msg_origin = "umo-1"
    event.get_extra.return_value = None
    return event


def make_request() -> ProviderRequest:
    return ProviderRequest(
        conversation=Conversation(platform_id="test", user_id="user", cid="cid-1")
    )


def make_plain_turns(count: int) -> list[Message]:
    messages: list[Message] = []
    for index in range(count):
        messages.append(Message(role="user", content=f"question {index}"))
        messages.append(Message(role="assistant", content=f"answer {index}"))
    return messages


def make_tool_turn() -> list[Message]:
    return [
        Message(role="user", content="use tool"),
        Message(
            role="assistant",
            content=None,
            tool_calls=[
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "search", "arguments": "{}"},
                }
            ],
        ),
        ToolCallMessageSegment(
            role="tool",
            tool_call_id="call-1",
            content="tool result",
        ),
        Message(role="assistant", content="final answer"),
    ]


@pytest.mark.parametrize("max_turns", [-1, 0])
def test_history_turn_limit_disabled(max_turns: int):
    assert not _history_exceeds_turn_limit(make_plain_turns(10), max_turns)


def test_conversation_turn_count_treats_tool_chain_as_one_turn():
    messages = make_plain_turns(2) + make_tool_turn()

    assert _count_conversation_turns(messages) == 3
    assert not _history_exceeds_turn_limit(messages, 3)
    assert _history_exceeds_turn_limit(messages, 2)


@pytest.mark.asyncio
async def test_save_history_does_not_summarize_below_turn_limit():
    provider = FakeSummaryProvider()
    stage = make_stage(provider=provider, max_turns=3)

    await stage._save_to_history(
        make_event(),
        make_request(),
        LLMResponse(role="assistant", completion_text="latest answer"),
        make_plain_turns(3),
        runner_stats=None,
    )

    provider.text_chat_mock.assert_not_called()
    saved_history = stage.conv_manager.update_conversation.await_args.kwargs["history"]
    assert len(saved_history) == 6
    assert saved_history[0]["content"] == "question 0"


@pytest.mark.asyncio
async def test_save_history_summarizes_only_after_turn_limit_exceeded():
    provider = FakeSummaryProvider()
    stage = make_stage(provider=provider, max_turns=3)

    await stage._save_to_history(
        make_event(),
        make_request(),
        LLMResponse(role="assistant", completion_text="latest answer"),
        make_plain_turns(4),
        runner_stats=None,
    )

    provider.text_chat_mock.assert_awaited_once()
    saved_history = stage.conv_manager.update_conversation.await_args.kwargs["history"]
    assert saved_history[0]["role"] == "user"
    assert saved_history[0]["content"].startswith(
        "Our previous history conversation summary:"
    )
    assert saved_history[-2]["content"] == "question 3"
    assert saved_history[-1]["content"] == "answer 3"


@pytest.mark.asyncio
async def test_save_history_uses_current_provider_when_compress_provider_id_empty():
    provider = FakeSummaryProvider()
    stage = make_stage(
        current_provider=provider,
        max_turns=3,
        provider_id="",
    )

    await stage._save_to_history(
        make_event(),
        make_request(),
        LLMResponse(role="assistant", completion_text="latest answer"),
        make_plain_turns(4),
        runner_stats=None,
    )

    stage.ctx.plugin_manager.context.get_provider_by_id.assert_not_called()
    stage.ctx.plugin_manager.context.get_using_provider.assert_called_once_with(
        umo="umo-1"
    )
    provider.text_chat_mock.assert_awaited_once()
    saved_history = stage.conv_manager.update_conversation.await_args.kwargs["history"]
    assert saved_history[0]["content"].startswith(
        "Our previous history conversation summary:"
    )


@pytest.mark.asyncio
async def test_save_history_falls_back_when_summary_returns_empty_text():
    provider = FakeSummaryProvider()
    provider.text_chat_mock.return_value = LLMResponse(
        role="assistant", completion_text=""
    )
    stage = make_stage(provider=provider, max_turns=3)

    await stage._save_to_history(
        make_event(),
        make_request(),
        LLMResponse(role="assistant", completion_text="latest answer"),
        make_plain_turns(4),
        runner_stats=None,
    )

    provider.text_chat_mock.assert_awaited_once()
    saved_history = stage.conv_manager.update_conversation.await_args.kwargs["history"]
    assert saved_history[0]["content"] == "question 1"
    assert saved_history[-1]["content"] == "answer 3"


@pytest.mark.asyncio
async def test_save_history_falls_back_when_summary_provider_raises():
    provider = FakeSummaryProvider()
    provider.text_chat_mock.side_effect = RuntimeError("boom")
    stage = make_stage(provider=provider, max_turns=3)

    await stage._save_to_history(
        make_event(),
        make_request(),
        LLMResponse(role="assistant", completion_text="latest answer"),
        make_plain_turns(4),
        runner_stats=None,
    )

    provider.text_chat_mock.assert_awaited_once()
    saved_history = stage.conv_manager.update_conversation.await_args.kwargs["history"]
    assert saved_history[0]["content"] == "question 1"
    assert saved_history[-1]["content"] == "answer 3"


@pytest.mark.asyncio
async def test_save_history_tool_chain_does_not_trigger_early_summary():
    provider = FakeSummaryProvider()
    stage = make_stage(provider=provider, max_turns=3)
    messages = make_plain_turns(2) + make_tool_turn()

    await stage._save_to_history(
        make_event(),
        make_request(),
        LLMResponse(role="assistant", completion_text="latest answer"),
        messages,
        runner_stats=None,
    )

    provider.text_chat_mock.assert_not_called()
    saved_history = stage.conv_manager.update_conversation.await_args.kwargs["history"]
    roles = [item["role"] for item in saved_history]
    assert roles == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
        "tool",
        "assistant",
    ]


@pytest.mark.asyncio
async def test_save_history_falls_back_to_turn_truncation_after_limit_exceeded():
    stage = make_stage(provider=None, max_turns=3)

    await stage._save_to_history(
        make_event(),
        make_request(),
        LLMResponse(role="assistant", completion_text="latest answer"),
        make_plain_turns(4),
        runner_stats=None,
    )

    saved_history = stage.conv_manager.update_conversation.await_args.kwargs["history"]
    assert saved_history[0]["content"] == "question 1"
    assert saved_history[-1]["content"] == "answer 3"
