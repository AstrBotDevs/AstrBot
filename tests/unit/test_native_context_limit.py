from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.astr_agent_runtime import execution
from astrbot.core.astr_agent_runtime.main_agent import providers
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils import llm_metadata


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("selected", "expected"), [("big-model", 1_000_000), (None, 32_000)]
)
async def test_context_limit_follows_selected_model(monkeypatch, selected, expected):
    monkeypatch.setitem(
        llm_metadata.LLM_METADATAS, "small-default", {"limit": {"context": 32_000}}
    )
    monkeypatch.setitem(
        llm_metadata.LLM_METADATAS, "big-model", {"limit": {"context": 1_000_000}}
    )
    monkeypatch.setattr(
        providers, "resolve_compression_provider", AsyncMock(return_value=None)
    )
    reset = AsyncMock()
    monkeypatch.setattr(ToolLoopAgentRunner, "reset", reset)
    provider = SimpleNamespace(
        provider_config={"id": "p1"}, get_model=lambda: "small-default"
    )
    config = SimpleNamespace(
        fallback_max_context_tokens=128_000,
        context_limit_reached_strategy="truncate_by_turns",
        tool_call_timeout=60,
        streaming_response=False,
        llm_compress_instruction="",
        llm_compress_keep_recent_ratio=0.15,
        dequeue_context_length=1,
        max_context_length=-1,
        tool_schema_mode="full",
        request_max_retries=1,
    )
    await execution.create_native_runner(
        SimpleNamespace(),
        provider,
        ProviderRequest(prompt="hi", model=selected),
        config,
        # A plain message event: no ChatUI options are set.
        SimpleNamespace(
            event=SimpleNamespace(get_extra=lambda key, default=None: None)
        ),
        fallback_providers=[],
    )
    assert reset.call_args.kwargs["max_context_tokens"] == expected
