from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.subagent.constants import (
    DEFAULT_AGENT_MAX_STEPS,
    DEFAULT_BASE_DELAY_MS,
    DEFAULT_BATCH_SIZE,
    DEFAULT_ERROR_CLASS,
    DEFAULT_ERROR_RETRY_MAX_INTERVAL,
    DEFAULT_FATAL_EXCEPTION_NAMES,
    DEFAULT_JITTER_RATIO,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MAX_CONCURRENT_TASKS,
    DEFAULT_MAX_DELAY_MS,
    DEFAULT_MAX_NESTED_HANDOFF_DEPTH,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_TRANSIENT_EXCEPTION_NAMES,
    MAX_CONCURRENT_TASKS,
    MAX_NESTED_DEPTH_LIMIT,
    MIN_ATTEMPTS,
    MIN_BASE_DELAY_MS,
    MIN_CONCURRENT_TASKS,
    MIN_NESTED_DEPTH_LIMIT,
    MIN_POLL_INTERVAL,
)

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

    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
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
    # None means unlimited steps for this subagent.
    max_steps: int | None = DEFAULT_AGENT_MAX_STEPS
    extensions: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        _ = build_safe_handoff_agent_name(value)
        return value.strip()

    @field_validator("max_steps")
    @classmethod
    def _validate_max_steps(cls, value: int | None) -> int | None:
        if value is None:
            return None
        parsed = int(value)
        return parsed if parsed > 0 else None

    @property
    def handoff_agent_name(self) -> str:
        return build_safe_handoff_agent_name(self.name)


class SubagentErrorClassifierConfig(BaseModel):
    type: str = "default"
    fatal_exceptions: list[str] = Field(
        default_factory=lambda: list(DEFAULT_FATAL_EXCEPTION_NAMES)
    )
    transient_exceptions: list[str] = Field(
        default_factory=lambda: list(DEFAULT_TRANSIENT_EXCEPTION_NAMES)
    )
    default_class: Literal["fatal", "transient", "retryable"] = DEFAULT_ERROR_CLASS

    model_config = ConfigDict(extra="allow")


class SubagentRuntimeConfig(BaseModel):
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    base_delay_ms: int = DEFAULT_BASE_DELAY_MS
    max_delay_ms: int = DEFAULT_MAX_DELAY_MS
    jitter_ratio: float = DEFAULT_JITTER_RATIO

    model_config = ConfigDict(extra="allow")

    @field_validator("max_attempts")
    @classmethod
    def _validate_max_attempts(cls, value: int) -> int:
        return max(MIN_ATTEMPTS, int(value))

    @field_validator("base_delay_ms")
    @classmethod
    def _validate_base_delay_ms(cls, value: int) -> int:
        return max(MIN_BASE_DELAY_MS, int(value))

    @field_validator("jitter_ratio")
    @classmethod
    def _validate_jitter_ratio(cls, value: float) -> float:
        return max(0.0, min(float(value), 1.0))

    @model_validator(mode="after")
    def _validate_max_delay_ms(self) -> SubagentRuntimeConfig:
        self.max_delay_ms = max(int(self.max_delay_ms), int(self.base_delay_ms))
        return self


class SubagentWorkerConfig(BaseModel):
    poll_interval: float = DEFAULT_POLL_INTERVAL
    batch_size: int = DEFAULT_BATCH_SIZE
    error_retry_max_interval: float = DEFAULT_ERROR_RETRY_MAX_INTERVAL

    model_config = ConfigDict(extra="allow")

    @field_validator("poll_interval")
    @classmethod
    def _validate_poll_interval(cls, value: float) -> float:
        return max(MIN_POLL_INTERVAL, float(value))

    @field_validator("batch_size")
    @classmethod
    def _validate_batch_size(cls, value: int) -> int:
        return max(1, int(value))

    @model_validator(mode="after")
    def _validate_error_retry_max_interval(self) -> SubagentWorkerConfig:
        self.error_retry_max_interval = max(
            float(self.error_retry_max_interval),
            float(self.poll_interval),
        )
        return self


class SubagentExecutionConfig(BaseModel):
    computer_use_runtime: str | None = None
    default_max_steps: int | None = None
    streaming_response: bool | None = None
    tool_call_timeout: int | None = None

    model_config = ConfigDict(extra="allow")

    @field_validator("computer_use_runtime")
    @classmethod
    def _normalize_runtime(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("default_max_steps", "tool_call_timeout")
    @classmethod
    def _validate_positive_ints(cls, value: int | None) -> int | None:
        if value is None:
            return None
        return max(1, int(value))


class SubagentConfig(BaseModel):
    main_enable: bool = False
    remove_main_duplicate_tools: bool = False
    router_system_prompt: str = ""
    agents: list[SubagentAgentSpec] = Field(default_factory=list)
    max_concurrent_subagent_runs: int = DEFAULT_MAX_CONCURRENT_TASKS
    max_nested_depth: int = DEFAULT_MAX_NESTED_HANDOFF_DEPTH
    error_classifier: SubagentErrorClassifierConfig = Field(
        default_factory=SubagentErrorClassifierConfig
    )
    runtime: SubagentRuntimeConfig = Field(default_factory=SubagentRuntimeConfig)
    worker: SubagentWorkerConfig = Field(default_factory=SubagentWorkerConfig)
    execution: SubagentExecutionConfig = Field(default_factory=SubagentExecutionConfig)
    extensions: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    @field_validator("max_concurrent_subagent_runs")
    @classmethod
    def _validate_max_concurrent(cls, value: int) -> int:
        if value < MIN_CONCURRENT_TASKS:
            return MIN_CONCURRENT_TASKS
        if value > MAX_CONCURRENT_TASKS:
            return MAX_CONCURRENT_TASKS
        return value

    @field_validator("max_nested_depth")
    @classmethod
    def _validate_max_nested_depth(cls, value: int) -> int:
        if value < MIN_NESTED_DEPTH_LIMIT:
            return MIN_NESTED_DEPTH_LIMIT
        if value > MAX_NESTED_DEPTH_LIMIT:
            return MAX_NESTED_DEPTH_LIMIT
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
