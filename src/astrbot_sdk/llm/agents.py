from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from .entities import ProviderRequest

if TYPE_CHECKING:
    from ..context import Context


class AgentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    tool_names: list[str] = Field(default_factory=list)
    runner_class: str

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> AgentSpec:
        return cls.model_validate(payload)


class BaseAgentRunner(ABC):
    """P0.5 agent registration surface.

    P0.5 only supports agent registration metadata. Actual execution remains
    owned by the core tool loop and is not directly callable from SDK plugins.
    """

    @abstractmethod
    async def run(self, ctx: Context, request: ProviderRequest) -> Any:
        raise NotImplementedError
