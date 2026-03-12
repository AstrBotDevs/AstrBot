from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .descriptors import CapabilityDescriptor, HandlerDescriptor


class _MessageBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorPayload(_MessageBase):
    code: str
    message: str
    hint: str = ""
    retryable: bool = False


class PeerInfo(_MessageBase):
    name: str
    role: Literal["plugin", "core"]
    version: str | None = None


class InitializeMessage(_MessageBase):
    type: Literal["initialize"] = "initialize"
    id: str
    protocol_version: str
    peer: PeerInfo
    handlers: list[HandlerDescriptor] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InitializeOutput(_MessageBase):
    peer: PeerInfo
    capabilities: list[CapabilityDescriptor] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResultMessage(_MessageBase):
    type: Literal["result"] = "result"
    id: str
    kind: str | None = None
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: ErrorPayload | None = None


class InvokeMessage(_MessageBase):
    type: Literal["invoke"] = "invoke"
    id: str
    capability: str
    input: dict[str, Any] = Field(default_factory=dict)
    stream: bool = False


class EventMessage(_MessageBase):
    type: Literal["event"] = "event"
    id: str
    phase: Literal["started", "delta", "completed", "failed"]
    data: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: ErrorPayload | None = None

    @model_validator(mode="after")
    def validate_phase_constraints(self) -> "EventMessage":
        """验证各 phase 的字段约束。

        - started: 所有字段必须为空
        - delta: 必须有 data，output/error 必须为空
        - completed: 必须有 output，data/error 必须为空
        - failed: 必须有 error，data/output 必须为空
        """
        phase = self.phase
        if phase == "started":
            if self.data or self.output or self.error:
                raise ValueError("started phase 必须所有字段为空")
        elif phase == "delta":
            if not self.data:
                raise ValueError("delta phase 需要 data")
            if self.output or self.error:
                raise ValueError("delta phase 的 output/error 必须为空")
        elif phase == "completed":
            if not self.output:
                raise ValueError("completed phase 需要 output")
            if self.data or self.error:
                raise ValueError("completed phase 的 data/error 必须为空")
        elif phase == "failed":
            if self.error is None:
                raise ValueError("failed phase 需要 error")
            if self.data or self.output:
                raise ValueError("failed phase 的 data/output 必须为空")
        return self


class CancelMessage(_MessageBase):
    type: Literal["cancel"] = "cancel"
    id: str
    reason: str = "user_cancelled"


ProtocolMessage = (
    InitializeMessage | ResultMessage | InvokeMessage | EventMessage | CancelMessage
)


def parse_message(payload: str | bytes | dict[str, Any]) -> ProtocolMessage:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        payload = json.loads(payload)
    message_type = payload.get("type")
    if message_type == "initialize":
        return InitializeMessage.model_validate(payload)
    if message_type == "result":
        return ResultMessage.model_validate(payload)
    if message_type == "invoke":
        return InvokeMessage.model_validate(payload)
    if message_type == "event":
        return EventMessage.model_validate(payload)
    if message_type == "cancel":
        return CancelMessage.model_validate(payload)
    raise ValueError(f"未知消息类型：{message_type}")
