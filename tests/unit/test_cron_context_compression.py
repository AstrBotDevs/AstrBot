"""Compression settings used by main-agent construction."""

from dataclasses import replace

from astrbot.core.astr_agent_runtime.main_agent import MainAgentBuildConfig
from astrbot.core.config.agent_runner import (
    resolve_context_compression_config,
)


def test_explicit_build_settings_and_per_request_overrides_are_preserved():
    """Keep direct callers and dataclasses.replace independent of raw settings."""
    defaults = MainAgentBuildConfig(tool_call_timeout=60)
    assert defaults.max_context_length == 50
    assert defaults.dequeue_context_length == 10
    direct = MainAgentBuildConfig(
        tool_call_timeout=60, max_context_length=7, dequeue_context_length=2
    )
    assert direct.max_context_length == 7
    assert direct.dequeue_context_length == 2

    source = {"max_turns": 12, "trim_turns": 3, "provider_id": "summary-model"}
    configured = MainAgentBuildConfig(
        tool_call_timeout=60, **resolve_context_compression_config(source)
    )
    source["max_turns"] = 99
    per_request = replace(configured, streaming_response=False, max_context_length=8)
    assert configured.max_context_length == 12
    assert per_request.max_context_length == 8
    assert per_request.dequeue_context_length == 3
    assert per_request.llm_compress_provider_id == "summary-model"
    assert per_request.streaming_response is False
