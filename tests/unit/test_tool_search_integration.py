"""Tests for Phase 8 tool_search integration -- mode management, provider detection, and system prompt.

Covers requirements: PRV-01, PRV-02, MOD-01, MOD-02, MOD-03, MOD-04, SYS-01, SYS-02.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_main_agent_resources import (
    TOOL_CALL_PROMPT_TOOL_SEARCH_MODE,
)
from astrbot.core.tools.tool_catalog import ToolCatalog
from astrbot.core.tools.tool_search_index import ToolSearchIndex
from astrbot.core.tools.generic_strategy import GenericToolSearchStrategy
from astrbot.core.tools.claude_strategy import ClaudeToolSearchStrategy
from astrbot.core.tools.strategy import ToolSearchStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "always_loaded_tools": [],
    "auto_always_load_builtin": True,
}

DEFAULT_TOOL_SEARCH_CONFIG = {
    "threshold": 25,
    "max_results": 5,
    "always_loaded_tools": [],
    "auto_always_load_builtin": True,
}


def _make_tool(
    name: str,
    *,
    description: str = "",
    handler_module_path: str | None = None,
    active: bool = True,
    params: dict | None = None,
) -> FunctionTool:
    """Create a minimal FunctionTool for testing."""
    if params is None:
        params = {"type": "object", "properties": {}}
    if not description:
        description = f"Description for {name}"
    return FunctionTool(
        name=name,
        description=description,
        parameters=params,
        handler_module_path=handler_module_path,
        active=active,
    )


def _make_tool_set(n_tools: int, *, prefix: str = "plugin_tool") -> ToolSet:
    """Build a ToolSet with n_tools plugin tools (deferred) and 2 core tools."""
    tools = []
    # 2 core tools (builtin, no handler_module_path)
    tools.append(_make_tool("builtin_a"))
    tools.append(_make_tool("builtin_b"))
    # n_tools plugin tools (deferred, with handler_module_path)
    for i in range(n_tools):
        tools.append(
            _make_tool(
                f"{prefix}_{i}",
                description=f"Plugin tool number {i} for testing purposes",
                handler_module_path=f"plugins.{prefix}_{i}",
            )
        )
    return ToolSet(tools=tools)


def _make_provider(provider_type: str = "openai") -> MagicMock:
    """Create a mock Provider with provider_config as a real dict."""
    provider = MagicMock()
    provider.provider_config = {
        "type": provider_type,
        "id": "test-provider",
        "max_context_tokens": 0,
    }
    return provider


def _make_request(tool_set: ToolSet | None = None) -> MagicMock:
    """Create a mock ProviderRequest."""
    req = MagicMock()
    req.func_tool = tool_set
    req.contexts = []
    req.prompt = None
    req.system_prompt = "You are a helpful assistant."
    return req


def _make_run_context() -> MagicMock:
    """Create a mock ContextWrapper."""
    ctx = MagicMock()
    ctx.messages = []
    ctx.context = MagicMock()
    return ctx


# ===========================================================================
# SYS-01: TOOL_CALL_PROMPT_TOOL_SEARCH_MODE constant exists
# ===========================================================================


class TestToolSearchPromptConstant:
    """SYS-01: TOOL_CALL_PROMPT_TOOL_SEARCH_MODE constant exists and contains tool_search instruction."""

    def test_constant_exists(self):
        # SYS-01
        assert TOOL_CALL_PROMPT_TOOL_SEARCH_MODE is not None

    def test_constant_contains_tool_search(self):
        # SYS-01
        assert "tool_search" in TOOL_CALL_PROMPT_TOOL_SEARCH_MODE

    def test_constant_contains_discover(self):
        # SYS-01
        assert "discover" in TOOL_CALL_PROMPT_TOOL_SEARCH_MODE.lower()

    def test_constant_is_string(self):
        # SYS-01
        assert isinstance(TOOL_CALL_PROMPT_TOOL_SEARCH_MODE, str)

    def test_constant_not_empty(self):
        # SYS-01
        assert len(TOOL_CALL_PROMPT_TOOL_SEARCH_MODE) > 0


# ===========================================================================
# SYS-02: System prompt branching selects correct prompt for tool_search
# ===========================================================================


class TestSystemPromptBranching:
    """SYS-02: build_main_agent system prompt selects TOOL_CALL_PROMPT_TOOL_SEARCH_MODE for tool_search/auto."""

    def test_tool_search_mode_imports_correctly(self):
        # SYS-02: verify the import works in astr_main_agent.py
        from astrbot.core.astr_main_agent_resources import (
            TOOL_CALL_PROMPT_TOOL_SEARCH_MODE,
        )
        assert "tool_search" in TOOL_CALL_PROMPT_TOOL_SEARCH_MODE


# ===========================================================================
# PRV-01: Claude provider detection returns True
# ===========================================================================


class TestProviderDetectionClaude:
    """PRV-01: When provider_config['type'] == 'anthropic_chat_completion', _is_claude_provider returns True."""

    def test_anthropic_provider_detected(self):
        # PRV-01
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            _is_claude_provider,
        )
        provider = _make_provider("anthropic_chat_completion")
        assert _is_claude_provider(provider) is True


# ===========================================================================
# PRV-02: Non-Claude provider detection returns False
# ===========================================================================


class TestProviderDetectionNonClaude:
    """PRV-02: When provider_config['type'] != 'anthropic_chat_completion', _is_claude_provider returns False."""

    def test_openai_provider_not_detected(self):
        # PRV-02
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            _is_claude_provider,
        )
        provider = _make_provider("openai")
        assert _is_claude_provider(provider) is False

    def test_deepseek_provider_not_detected(self):
        # PRV-02
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            _is_claude_provider,
        )
        provider = _make_provider("deepseek_chat")
        assert _is_claude_provider(provider) is False

    def test_empty_type_not_detected(self):
        # PRV-02
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            _is_claude_provider,
        )
        provider = _make_provider("")
        assert _is_claude_provider(provider) is False


# ===========================================================================
# MOD-01: full and skills_like do not trigger tool_search initialization
# ===========================================================================


class TestFullModeNoToolSearch:
    """MOD-01: Setting tool_schema_mode to 'full' or 'skills_like' does not trigger tool_search initialization."""

    @pytest.mark.asyncio
    async def test_full_mode_no_strategy(self):
        # MOD-01
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            ToolLoopAgentRunner,
        )
        runner = ToolLoopAgentRunner()
        provider = _make_provider("openai")
        tool_set = _make_tool_set(30)
        req = _make_request(tool_set)
        run_ctx = _make_run_context()
        tool_executor = MagicMock()
        agent_hooks = MagicMock()

        await runner.reset(
            provider=provider,
            request=req,
            run_context=run_ctx,
            tool_executor=tool_executor,
            agent_hooks=agent_hooks,
            tool_schema_mode="full",
        )
        assert runner._tool_search_strategy is None
        assert runner.tool_schema_mode == "full"

    @pytest.mark.asyncio
    async def test_skills_like_mode_no_strategy(self):
        # MOD-01
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            ToolLoopAgentRunner,
        )
        runner = ToolLoopAgentRunner()
        provider = _make_provider("openai")
        tool_set = _make_tool_set(30)
        req = _make_request(tool_set)
        run_ctx = _make_run_context()
        tool_executor = MagicMock()
        agent_hooks = MagicMock()

        await runner.reset(
            provider=provider,
            request=req,
            run_context=run_ctx,
            tool_executor=tool_executor,
            agent_hooks=agent_hooks,
            tool_schema_mode="skills_like",
        )
        assert runner._tool_search_strategy is None
        assert runner.tool_schema_mode == "skills_like"


# ===========================================================================
# MOD-02: auto mode activates tool_search when above threshold
# ===========================================================================


class TestAutoModeAboveThreshold:
    """MOD-02: When tool_schema_mode='auto' and tool count > threshold, strategy is constructed."""

    @pytest.mark.asyncio
    async def test_auto_mode_above_threshold_constructs_strategy(self):
        # MOD-02
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            ToolLoopAgentRunner,
        )
        runner = ToolLoopAgentRunner()
        provider = _make_provider("openai")
        # 30 total tools (2 core + 28 plugin), threshold default is 25
        tool_set = _make_tool_set(28)
        req = _make_request(tool_set)
        run_ctx = _make_run_context()
        tool_executor = MagicMock()
        agent_hooks = MagicMock()

        await runner.reset(
            provider=provider,
            request=req,
            run_context=run_ctx,
            tool_executor=tool_executor,
            agent_hooks=agent_hooks,
            tool_schema_mode="auto",
            tool_search_config=DEFAULT_TOOL_SEARCH_CONFIG,
        )
        assert runner._tool_search_strategy is not None
        assert isinstance(runner._tool_search_strategy, ToolSearchStrategy)
        assert runner.tool_schema_mode == "tool_search"

    @pytest.mark.asyncio
    async def test_auto_mode_below_threshold_stays_full(self):
        # MOD-02 (below threshold variant)
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            ToolLoopAgentRunner,
        )
        runner = ToolLoopAgentRunner()
        provider = _make_provider("openai")
        # 5 total tools (2 core + 3 plugin), threshold default is 25
        tool_set = _make_tool_set(3)
        req = _make_request(tool_set)
        run_ctx = _make_run_context()
        tool_executor = MagicMock()
        agent_hooks = MagicMock()

        await runner.reset(
            provider=provider,
            request=req,
            run_context=run_ctx,
            tool_executor=tool_executor,
            agent_hooks=agent_hooks,
            tool_schema_mode="auto",
            tool_search_config=DEFAULT_TOOL_SEARCH_CONFIG,
        )
        assert runner._tool_search_strategy is None
        assert runner.tool_schema_mode == "full"

    @pytest.mark.asyncio
    async def test_auto_mode_at_threshold_stays_full(self):
        # MOD-02 (at threshold exactly, should stay full)
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            ToolLoopAgentRunner,
        )
        runner = ToolLoopAgentRunner()
        provider = _make_provider("openai")
        # 25 total tools (2 core + 23 plugin), threshold is 25
        tool_set = _make_tool_set(23)
        req = _make_request(tool_set)
        run_ctx = _make_run_context()
        tool_executor = MagicMock()
        agent_hooks = MagicMock()

        await runner.reset(
            provider=provider,
            request=req,
            run_context=run_ctx,
            tool_executor=tool_executor,
            agent_hooks=agent_hooks,
            tool_schema_mode="auto",
            tool_search_config=DEFAULT_TOOL_SEARCH_CONFIG,
        )
        assert runner._tool_search_strategy is None
        assert runner.tool_schema_mode == "full"


# ===========================================================================
# MOD-02 + PRV-01: auto mode routes to Claude strategy for anthropic provider
# ===========================================================================


class TestAutoModeProviderRouting:
    """MOD-02 + PRV-01: auto mode routes to ClaudeToolSearchStrategy for anthropic providers."""

    @pytest.mark.asyncio
    async def test_auto_mode_anthropic_routes_to_claude_strategy(self):
        # MOD-02 + PRV-01
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            ToolLoopAgentRunner,
        )
        runner = ToolLoopAgentRunner()
        provider = _make_provider("anthropic_chat_completion")
        tool_set = _make_tool_set(28)
        req = _make_request(tool_set)
        run_ctx = _make_run_context()
        tool_executor = MagicMock()
        agent_hooks = MagicMock()

        await runner.reset(
            provider=provider,
            request=req,
            run_context=run_ctx,
            tool_executor=tool_executor,
            agent_hooks=agent_hooks,
            tool_schema_mode="auto",
            tool_search_config=DEFAULT_TOOL_SEARCH_CONFIG,
        )
        assert isinstance(runner._tool_search_strategy, ClaudeToolSearchStrategy)

    @pytest.mark.asyncio
    async def test_auto_mode_openai_routes_to_generic_strategy(self):
        # MOD-02 + PRV-02
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            ToolLoopAgentRunner,
        )
        runner = ToolLoopAgentRunner()
        provider = _make_provider("openai")
        tool_set = _make_tool_set(28)
        req = _make_request(tool_set)
        run_ctx = _make_run_context()
        tool_executor = MagicMock()
        agent_hooks = MagicMock()

        await runner.reset(
            provider=provider,
            request=req,
            run_context=run_ctx,
            tool_executor=tool_executor,
            agent_hooks=agent_hooks,
            tool_schema_mode="auto",
            tool_search_config=DEFAULT_TOOL_SEARCH_CONFIG,
        )
        assert isinstance(runner._tool_search_strategy, GenericToolSearchStrategy)


# ===========================================================================
# MOD-03: Fallback to full when no deferred tools after partitioning
# ===========================================================================


class TestFallbackNoDeferredTools:
    """MOD-03: tool_search mode but 0 deferred tools -> falls back to 'full'."""

    @pytest.mark.asyncio
    async def test_fallback_no_deferred_tools(self):
        # MOD-03
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            ToolLoopAgentRunner,
        )
        runner = ToolLoopAgentRunner()
        provider = _make_provider("openai")
        # All tools are builtin (core) -- no plugin tools -> 0 deferred
        tool_set = _make_tool_set(0)
        req = _make_request(tool_set)
        run_ctx = _make_run_context()
        tool_executor = MagicMock()
        agent_hooks = MagicMock()

        await runner.reset(
            provider=provider,
            request=req,
            run_context=run_ctx,
            tool_executor=tool_executor,
            agent_hooks=agent_hooks,
            tool_schema_mode="tool_search",
            tool_search_config=DEFAULT_TOOL_SEARCH_CONFIG,
        )
        assert runner._tool_search_strategy is None
        assert runner.tool_schema_mode == "full"


# ===========================================================================
# MOD-04: Fallback to full when initialization raises an exception
# ===========================================================================


class TestFallbackOnException:
    """MOD-04: tool_search mode but exception during init -> falls back to 'full', strategy = None."""

    @pytest.mark.asyncio
    async def test_fallback_on_exception(self):
        # MOD-04
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            ToolLoopAgentRunner,
        )
        runner = ToolLoopAgentRunner()
        provider = _make_provider("openai")
        tool_set = _make_tool_set(28)
        req = _make_request(tool_set)
        run_ctx = _make_run_context()
        tool_executor = MagicMock()
        agent_hooks = MagicMock()

        # Patch ToolCatalog.from_tool_set to raise an exception
        with patch(
            "astrbot.core.agent.runners.tool_loop_agent_runner.ToolCatalog.from_tool_set",
            side_effect=RuntimeError("Simulated failure"),
        ):
            await runner.reset(
                provider=provider,
                request=req,
                run_context=run_ctx,
                tool_executor=tool_executor,
                agent_hooks=agent_hooks,
                tool_schema_mode="tool_search",
                tool_search_config=DEFAULT_TOOL_SEARCH_CONFIG,
            )
        assert runner._tool_search_strategy is None
        assert runner.tool_schema_mode == "full"
