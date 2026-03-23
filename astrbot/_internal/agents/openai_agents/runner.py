"""OpenAI Agents SDK Runner for AstrBot.

This module provides an integration layer between AstrBot's agent system
and the openai-agents library from OpenAI.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncGenerator
from typing import Any

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

from agents import Agent as OpenAIAgent
from agents import Model, Runner, RunResult
from agents.run_config import RunConfig

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.response import AgentResponse, AgentResponseData
from astrbot.core.agent.run_context import ContextWrapper, TContext
from astrbot.core.agent.runners.base import AgentState, BaseAgentRunner
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.provider.provider import Provider

from .tool_adapter import astrbot_tool_to_agents_tool


class OpenAIAgentsRunner(BaseAgentRunner[TContext]):
    """An agent runner that uses the openai-agents library.

    This runner wraps the openai-agents Agent and integrates it with
    AstrBot's existing infrastructure including tools, hooks, and context.
    """

    def __init__(
        self,
        model: Model | str,
        instructions: str | None = None,
        tools: list[FunctionTool] | None = None,
        tool_manager: FunctionToolManager | None = None,
        agent_name: str = "AstrBotAgent",
        **openai_agents_kwargs: Any,
    ) -> None:
        """Initialize the openai-agents runner.

        Args:
            model: The model to use (either a Model instance or a model name string)
            instructions: System prompt/instructions for the agent
            tools: List of AstrBot FunctionTool instances
            tool_manager: Optional FunctionToolManager for tool resolution
            agent_name: Name of the agent
            **openai_agents_kwargs: Additional arguments passed to openai-agents Agent
        """
        super().__init__()
        self._model = model
        self._instructions = instructions
        self._tools = tools or []
        self._tool_manager = tool_manager
        self._agent_name = agent_name
        self._openai_agents_kwargs = openai_agents_kwargs

        self._agent: OpenAIAgent[Any] | None = None
        self._run_result: RunResult | None = None
        self._run_context: ContextWrapper[TContext] | None = None
        self._agent_hooks: BaseAgentRunHooks[TContext] | None = None
        self._state = AgentState.IDLE

    def _create_agents_tools(self) -> list[Any]:
        """Convert AstrBot tools to openai-agents tools."""
        agents_tools = []
        for tool in self._tools:
            handler = self._get_tool_handler(tool.name)
            agents_tool = astrbot_tool_to_agents_tool(tool, handler)
            agents_tools.append(agents_tool)
        return agents_tools

    def _get_tool_handler(self, tool_name: str) -> Any:
        """Get the handler function for a tool by name."""
        if self._tool_manager:
            tool = self._tool_manager.get_func(tool_name)
            if tool and tool.handler:
                return tool.handler
        for tool in self._tools:
            if tool.name == tool_name and hasattr(tool, "handler"):
                return tool.handler
        raise ValueError(f"Tool handler not found for: {tool_name}")

    @override
    async def reset(
        self,
        provider: Provider,
        request: ProviderRequest,
        run_context: ContextWrapper[TContext],
        tool_executor: BaseFunctionToolExecutor[TContext],
        agent_hooks: BaseAgentRunHooks[TContext],
        streaming: bool = False,
        enforce_max_turns: int = -1,
        llm_compress_instruction: str | None = None,
        llm_compress_keep_recent: int = 0,
        llm_compress_provider: Provider | None = None,
        truncate_turns: int = 1,
        custom_token_counter: Any = None,
        custom_compressor: Any = None,
        tool_schema_mode: str | None = "full",
        fallback_providers: list[Provider] | None = None,
        provider_config: dict | None = None,
        **kwargs: Any,
    ) -> None:
        """Reset the agent to its initial state."""
        self._run_context = run_context
        self._agent_hooks = agent_hooks
        self._state = AgentState.IDLE
        self._run_result = None

        agents_tools = self._create_agents_tools()

        self._agent = OpenAIAgent(
            name=self._agent_name,
            instructions=self._instructions,
            tools=agents_tools,
            **self._openai_agents_kwargs,
        )

    @override
    async def step(self) -> AsyncGenerator[AgentResponse, None]:
        """Process a single step of the agent (not directly supported)."""
        raise NotImplementedError(
            "step() is not directly supported. Use step_until_done() instead."
        )

    @override
    async def step_until_done(
        self, max_step: int
    ) -> AsyncGenerator[AgentResponse, None]:
        """Run the agent until completion or max steps."""
        if not self._agent or not self._run_context:
            raise RuntimeError("Agent not initialized. Call reset() first.")

        self._state = AgentState.RUNNING

        run_config = RunConfig(max_turns=max_step)

        try:
            self._run_result = await Runner.run(
                self._agent,
                input=self._run_context.messages,
                run_config=run_config,
            )
            self._state = AgentState.DONE

            if self._run_result:
                chain = MessageChain().message(self._run_result.final_output)
                yield AgentResponse(
                    type="llm_result",
                    data=AgentResponseData(chain=chain),
                )
        except Exception:
            self._state = AgentState.ERROR
            raise

    def done(self) -> bool:
        """Check if the agent has completed its task."""
        return self._state == AgentState.DONE

    def get_final_llm_resp(self) -> LLMResponse | None:
        """Get the final LLM response from the agent run."""
        if not self._run_result:
            return None
        return LLMResponse(
            role="assistant",
            completion_text=self._run_result.final_output,
        )
