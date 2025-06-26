import abc
import typing as T
from dataclasses import dataclass
from astrbot.core.provider.entities import LLMResponse


@dataclass
class AgentResponse:
    type: str
    data: dict


class BaseAgentRunner:
    @abc.abstractmethod
    async def reset(self) -> None:
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
