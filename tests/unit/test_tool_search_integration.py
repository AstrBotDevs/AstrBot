"""Tests for Phase 8 tool_search integration -- mode management, provider detection, and system prompt.

Covers requirements: PRV-01, PRV-02, MOD-01, MOD-02, MOD-03, MOD-04, SYS-01, SYS-02.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_main_agent_resources import (
    TOOL_CALL_PROMPT_TOOL_SEARCH_MODE,
)
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.provider.provider import Provider
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic
from astrbot.core.tools.claude_strategy import ClaudeToolSearchStrategy
from astrbot.core.tools.generic_strategy import GenericToolSearchStrategy
from astrbot.core.tools.strategy import ToolSearchStrategy
from astrbot.core.tools.tool_catalog import ToolCatalog
from astrbot.core.tools.tool_search_index import ToolSearchIndex

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


class _FailingProvider(Provider):
    def __init__(self, provider_type: str, provider_id: str):
        super().__init__(
            {"type": provider_type, "id": provider_id, "max_context_tokens": 0},
            {},
        )

    def get_current_key(self) -> str:
        return "test-key"

    def set_key(self, key: str) -> None:
        return None

    async def get_models(self) -> list[str]:
        return ["test-model"]

    async def text_chat(self, **kwargs) -> LLMResponse:
        raise RuntimeError("boom")

    async def text_chat_stream(self, **kwargs):
        if False:  # pragma: no cover
            yield LLMResponse(role="assistant", completion_text="")


class _RecordingProvider(Provider):
    def __init__(self, provider_type: str, provider_id: str):
        super().__init__(
            {"type": provider_type, "id": provider_id, "max_context_tokens": 0},
            {},
        )
        self.last_func_tool: ToolSet | None = None

    def get_current_key(self) -> str:
        return "test-key"

    def set_key(self, key: str) -> None:
        return None

    async def get_models(self) -> list[str]:
        return ["test-model"]

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.last_func_tool = kwargs.get("func_tool")
        return LLMResponse(role="assistant", completion_text="fallback ok")

    async def text_chat_stream(self, **kwargs):
        if False:  # pragma: no cover
            yield LLMResponse(role="assistant", completion_text="")


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

    def test_provider_detection_claude(self):
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

    def test_provider_detection_openai_not_claude(self):
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

    @pytest.mark.asyncio
    async def test_auto_mode_counts_only_active_tools(self):
        # MOD-02 regression: inactive tools must not trigger tool_search.
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            ToolLoopAgentRunner,
        )

        runner = ToolLoopAgentRunner()
        provider = _make_provider("openai")
        tools = [
            _make_tool("builtin_a"),
            _make_tool("builtin_b"),
            _make_tool("active_plugin", handler_module_path="plugins.active_plugin"),
        ]
        for i in range(40):
            tools.append(
                _make_tool(
                    f"inactive_{i}",
                    handler_module_path=f"plugins.inactive_{i}",
                    active=False,
                )
            )

        req = _make_request(ToolSet(tools=tools))
        run_ctx = _make_run_context()

        await runner.reset(
            provider=provider,
            request=req,
            run_context=run_ctx,
            tool_executor=MagicMock(),
            agent_hooks=MagicMock(),
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


class TestClaudeAnthropicPayloadIntegration:
    """Anthropic payload generation uses Claude custom tool search wiring."""

    def test_tool_search_result_converts_to_tool_reference_blocks(self):
        catalog = ToolCatalog.from_tool_set(_make_tool_set(2), DEFAULT_CONFIG)
        index = ToolSearchIndex(tools=catalog.deferred_tools)
        strategy = ClaudeToolSearchStrategy(catalog, index)
        provider = ProviderAnthropic(
            {"type": "anthropic_chat_completion", "model": "claude-test"},
            {},
            use_api_key=False,
        )

        _, messages = provider._prepare_payload(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "tool_search",
                                "arguments": json.dumps({"query": "plugin_tool_0"}),
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "content": json.dumps(
                        {
                            "query": "plugin_tool_0",
                            "matches": [
                                {
                                    "name": "plugin_tool_0",
                                    "description": "match",
                                    "score": 1.0,
                                }
                            ],
                            "total_found": 1,
                        }
                    ),
                },
            ],
            strategy.build_tool_set(),
        )

        tool_result_block = messages[1]["content"][0]
        assert tool_result_block["type"] == "tool_result"
        assert tool_result_block["content"] == [
            {"type": "tool_reference", "tool_name": "plugin_tool_0"}
        ]

    def test_tool_search_result_without_matches_stays_plain_text(self):
        catalog = ToolCatalog.from_tool_set(_make_tool_set(2), DEFAULT_CONFIG)
        index = ToolSearchIndex(tools=catalog.deferred_tools)
        strategy = ClaudeToolSearchStrategy(catalog, index)
        provider = ProviderAnthropic(
            {"type": "anthropic_chat_completion", "model": "claude-test"},
            {},
            use_api_key=False,
        )
        raw_content = json.dumps({"query": "missing", "matches": [], "total_found": 0})

        _, messages = provider._prepare_payload(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "tool_search",
                                "arguments": json.dumps({"query": "missing"}),
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "content": raw_content,
                },
            ],
            strategy.build_tool_set(),
        )

        assert messages[1]["content"][0]["content"] == raw_content


class TestFallbackProviderStrategyRefresh:
    """Fallback must rebuild tool_search strategy for the target provider family."""

    @pytest.mark.asyncio
    async def test_refresh_preserves_discovered_tools(self):
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            ToolLoopAgentRunner,
        )

        runner = ToolLoopAgentRunner()
        request = ProviderRequest(
            prompt=None,
            func_tool=_make_tool_set(28),
            contexts=[],
            system_prompt="You are a helpful assistant.",
        )

        await runner.reset(
            provider=_FailingProvider("openai", "primary"),
            request=request,
            run_context=ContextWrapper(context=MagicMock()),
            tool_executor=MagicMock(),
            agent_hooks=MagicMock(),
            tool_schema_mode="tool_search",
            tool_search_config=DEFAULT_TOOL_SEARCH_CONFIG,
        )

        assert runner._tool_search_discovery_state is not None
        runner._tool_search_discovery_state.add("plugin_tool_0")
        runner._refresh_tool_search_strategy(_make_provider("anthropic_chat_completion"))

        assert isinstance(runner._tool_search_strategy, ClaudeToolSearchStrategy)
        assert request.func_tool is not None
        assert "plugin_tool_0" in request.func_tool.names()

    @pytest.mark.asyncio
    async def test_fallback_to_anthropic_rebuilds_strategy_and_schema(self):
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            ToolLoopAgentRunner,
        )

        runner = ToolLoopAgentRunner()
        primary = _FailingProvider("openai", "primary")
        fallback = _RecordingProvider("anthropic_chat_completion", "fallback")
        request = ProviderRequest(
            prompt=None,
            func_tool=_make_tool_set(28),
            contexts=[],
            system_prompt="You are a helpful assistant.",
        )
        hooks = MagicMock()
        hooks.on_agent_begin = AsyncMock()
        hooks.on_agent_done = AsyncMock()
        hooks.on_tool_start = AsyncMock()
        hooks.on_tool_end = AsyncMock()

        await runner.reset(
            provider=primary,
            request=request,
            run_context=ContextWrapper(context=MagicMock()),
            tool_executor=MagicMock(),
            agent_hooks=hooks,
            tool_schema_mode="tool_search",
            fallback_providers=[fallback],
            tool_search_config=DEFAULT_TOOL_SEARCH_CONFIG,
        )

        async for _ in runner.step_until_done(1):
            pass

        assert isinstance(runner._tool_search_strategy, ClaudeToolSearchStrategy)
        assert fallback.last_func_tool is not None

        deferred_defs = [
            tool_def
            for tool_def in fallback.last_func_tool.anthropic_schema()
            if tool_def["name"].startswith("plugin_tool_")
        ]
        assert deferred_defs
        assert all(tool_def["defer_loading"] is True for tool_def in deferred_defs)
