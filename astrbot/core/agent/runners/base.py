import abc
import typing as T
from enum import Enum, auto

from astrbot import logger
from astrbot.core.provider.entities import LLMResponse

from ..hooks import BaseAgentRunHooks
from ..response import AgentResponse
from ..run_context import ContextWrapper, TContext


class AgentState(Enum):
    """Defines the state of the agent."""

    IDLE = auto()  # Initial state
    RUNNING = auto()  # Currently processing
    DONE = auto()  # Completed
    ERROR = auto()  # Error state


class BaseAgentRunner(T.Generic[TContext]):
    @abc.abstractmethod
    async def reset(
        self,
        run_context: ContextWrapper[TContext],
        agent_hooks: BaseAgentRunHooks[TContext],
        **kwargs: T.Any,
    ) -> None:
        """Reset the agent to its initial state.
        This method should be called before starting a new run.
        """
        ...

    @abc.abstractmethod
    async def step(self) -> T.AsyncGenerator[AgentResponse, None]:
        """Process a single step of the agent."""
        ...

    @abc.abstractmethod
    async def step_until_done(
        self, max_step: int
    ) -> T.AsyncGenerator[AgentResponse, None]:
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
