import abc
from collections.abc import AsyncGenerator
from enum import Enum, auto
from typing import Any, Generic

from astrbot import logger
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.response import AgentResponse
from astrbot.core.agent.run_context import ContextWrapper, TContext
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.provider.provider import Provider


class AgentState(Enum):
    """Defines the state of the agent."""

    IDLE = auto()  # Initial state
    RUNNING = auto()  # Currently processing
    DONE = auto()  # Completed
    ERROR = auto()  # Error state


class BaseAgentRunner(Generic[TContext]):
    def __init__(
        self,
    ):
        self.tasks: set = set()

    @abc.abstractmethod
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
        """Reset the agent to its initial state.
        This method should be called before starting a new run.
        """
        ...

    @abc.abstractmethod
    async def step(self) -> AsyncGenerator[AgentResponse, None]:
        """Process a single step of the agent."""
        ...

    @abc.abstractmethod
    async def step_until_done(
        self, max_step: int
    ) -> AsyncGenerator[AgentResponse, None]:
        """Process steps until the agent is done."""
        ...

    @abc.abstractmethod
    def done(self) -> bool:
        """Check if the agent has completed its task.
        Returns True if the agent is done, False otherwise.
        """
        ...

    @abc.abstractmethod
    def get_final_llm_resp(self) -> LLMResponse | None:
        """Get the final observation from the agent.
        This method should be called after the agent is done.
        """
        ...

    def _transition_state(self, new_state: AgentState) -> None:
        """Transition the agent state."""
        if self._state != new_state:
            logger.debug(f"Agent state transition: {self._state} -> {new_state}")
            self._state = new_state
