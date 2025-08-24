import abc
import typing as T
from enum import Enum, auto
from ..run_context import ContextWrapper, TContext
from ..response import AgentResponse
from ..hooks import BaseAgentRunHooks
from ..tool_executor import BaseFunctionToolExecutor
from astrbot.core.provider import Provider
from astrbot.core.provider.entities import LLMResponse


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
        provider: Provider,
        run_context: ContextWrapper[TContext],
        tool_executor: BaseFunctionToolExecutor[TContext],
        agent_hooks: BaseAgentRunHooks[TContext],
        **kwargs: T.Any,
    ) -> None:
        """
        Reset the agent to its initial state.
        This method should be called before starting a new run.
        """
        ...

    @abc.abstractmethod
    async def step(self) -> T.AsyncGenerator[AgentResponse, None]:
        """
        Process a single step of the agent.
        """
        ...

    @abc.abstractmethod
    def done(self) -> bool:
        """
        Check if the agent has completed its task.
        Returns True if the agent is done, False otherwise.
        """
        ...

    @abc.abstractmethod
    def get_final_llm_resp(self) -> LLMResponse | None:
        """
        Get the final observation from the agent.
        This method should be called after the agent is done.
        """
        ...
