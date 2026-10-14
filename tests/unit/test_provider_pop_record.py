"""Tests for Provider.pop_record tool-call pairing (#7225)."""

import pytest
import pytest_asyncio

from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial


@pytest_asyncio.fixture
async def provider() -> ProviderOpenAIOfficial:
    """A minimal OpenAI-compatible provider, closed after each test."""
    instance = ProviderOpenAIOfficial(
        provider_config={
            "id": "test-openai",
            "type": "openai_chat_completion",
            "model": "gpt-4o-mini",
            "key": ["test-key"],
        },
        provider_settings={},
    )
    try:
        yield instance
    finally:
        await instance.terminate()


def _assistant_with_tool_call(*call_ids: str) -> dict:
    """Build an assistant record carrying the given tool calls."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": "demo", "arguments": "{}"},
            }
            for call_id in call_ids
        ],
    }


def _tool_result(call_id: str) -> dict:
    """Build a tool record answering the given tool call."""
    return {"role": "tool", "tool_call_id": call_id, "content": "ok"}


def _roles(context: list) -> list[str]:
    return [record["role"] for record in context]


class TestPopRecordToolCallPairing:
    """pop_record must never leave an orphaned tool record behind (#7225)."""

    @pytest.mark.asyncio
    async def test_pops_oldest_two_non_system_records(self, provider):
        """Plain records are still popped two at a time, system is preserved."""
        context = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
        ]

        await provider.pop_record(context)

        assert context == [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u2"},
        ]

    @pytest.mark.asyncio
    async def test_drops_tool_record_orphaned_by_pop(self, provider):
        """The reported 400 case: pop removes assistant(tool_calls) only."""
        context = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u1"},
            _assistant_with_tool_call("call_1"),
            _tool_result("call_1"),
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
        ]

        await provider.pop_record(context)

        assert _roles(context) == ["system", "user", "assistant"]
        assert all(record["role"] != "tool" for record in context)

    @pytest.mark.asyncio
    async def test_drops_whole_tool_block_orphaned_by_pop(self, provider):
        """Every tool record of the popped assistant(tool_calls) is removed."""
        context = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u1"},
            _assistant_with_tool_call("call_1", "call_2"),
            _tool_result("call_1"),
            _tool_result("call_2"),
            {"role": "user", "content": "u2"},
        ]

        await provider.pop_record(context)

        assert _roles(context) == ["system", "user"]

    @pytest.mark.asyncio
    async def test_keeps_complete_tool_pair(self, provider):
        """A tool pair that survives the pop is left untouched."""
        context = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            _assistant_with_tool_call("call_1"),
            _tool_result("call_1"),
        ]

        await provider.pop_record(context)

        assert _roles(context) == ["system", "user", "assistant", "tool"]

    @pytest.mark.asyncio
    async def test_drops_partial_tool_block_orphaned_by_pop(self, provider):
        """A half-popped tool block never leaves a stray tool record behind."""
        context = [
            {"role": "system", "content": "sys"},
            _assistant_with_tool_call("call_1", "call_2"),
            _tool_result("call_1"),
            _tool_result("call_2"),
            {"role": "user", "content": "u2"},
        ]

        await provider.pop_record(context)

        assert _roles(context) == ["system", "user"]

    @pytest.mark.asyncio
    async def test_system_only_context_is_untouched(self, provider):
        """A context without non-system records stays as is."""
        context = [{"role": "system", "content": "sys"}]

        await provider.pop_record(context)

        assert context == [{"role": "system", "content": "sys"}]
