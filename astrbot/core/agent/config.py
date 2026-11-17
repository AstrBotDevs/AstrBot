"""Portable agent configuration, independent of its execution role."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class AgentConfig(BaseModel):
    """Select a runtime and its own configuration."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    runtime: str = Field(min_length=1)
    config: dict[str, JsonValue] = Field(default_factory=dict)


class StoredAgentConfig(AgentConfig):
    """A reusable configuration addressed independently of running agent sessions."""

    config_id: str
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    enabled: bool = True
