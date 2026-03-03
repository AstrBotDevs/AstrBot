from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from astrbot.core.agent.handoff import HandoffTool

_TOOL_SAFE_CHARS = re.compile(r"[^a-z0-9_-]+")
_TOOL_ALLOWED = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ToolsScope(str, Enum):
    ALL = "all"
    NONE = "none"
    LIST = "list"
    PERSONA = "persona"


def build_safe_handoff_agent_name(display_name: str) -> str:
    raw = str(display_name or "").strip()
    if not raw:
        raise ValueError("Subagent name cannot be empty.")
    lowered = raw.lower()
    slug = _TOOL_SAFE_CHARS.sub("_", lowered).strip("_")
    if not slug:
        slug = "subagent"
    candidate = slug
    tool_name = f"transfer_to_{candidate}"
    if _TOOL_ALLOWED.match(tool_name):
        return candidate

    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]  # noqa: S324
    max_base_len = max(1, 64 - len("transfer_to__") - len(digest))
    trimmed = slug[:max_base_len].strip("_") or "subagent"
    candidate = f"{trimmed}_{digest}"
    tool_name = f"transfer_to_{candidate}"
    if not _TOOL_ALLOWED.match(tool_name):
        raise ValueError(
            f"Invalid subagent name '{display_name}', cannot derive a safe handoff tool name."
        )
    return candidate


class SubagentAgentSpec(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    enabled: bool = True
    persona_id: str | None = None
    provider_id: str | None = None
    public_description: str = ""
    tools_scope: ToolsScope = ToolsScope.ALL
    tools: list[str] | None = None
    instructions: str = ""
    max_steps: int | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        _ = build_safe_handoff_agent_name(value)
        return value.strip()

    @property
    def handoff_agent_name(self) -> str:
        return build_safe_handoff_agent_name(self.name)


class SubagentConfig(BaseModel):
    main_enable: bool = False
    remove_main_duplicate_tools: bool = False
    router_system_prompt: str = ""
    agents: list[SubagentAgentSpec] = Field(default_factory=list)
    max_concurrent_subagent_runs: int = 8
    max_nested_depth: int = 2
    extensions: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    @field_validator("max_concurrent_subagent_runs")
    @classmethod
    def _validate_max_concurrent(cls, value: int) -> int:
        if value < 1:
            return 1
        if value > 64:
            return 64
        return value

    @field_validator("max_nested_depth")
    @classmethod
    def _validate_max_nested_depth(cls, value: int) -> int:
        if value < 1:
            return 1
        if value > 8:
            return 8
        return value


@dataclass(slots=True)
class SubagentMountPlan:
    handoffs: list[HandoffTool] = field(default_factory=list)
    handoff_by_tool_name: dict[str, HandoffTool] = field(default_factory=dict)
    main_tool_exclude_set: set[str] = field(default_factory=set)
    router_prompt: str | None = None
    diagnostics: list[str] = field(default_factory=list)


class SubagentTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass(slots=True)
class SubagentTaskData:
    task_id: str
    idempotency_key: str
    umo: str
    subagent_name: str
    handoff_tool_name: str
    status: SubagentTaskStatus | str
    attempt: int
    max_attempts: int
    next_run_at: datetime | None
    payload_json: str
    error_class: str | None
    last_error: str | None
    result_text: str | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
