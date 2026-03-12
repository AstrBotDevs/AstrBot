from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _DescriptorBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Permissions(_DescriptorBase):
    require_admin: bool = False
    level: int = 0


class CommandTrigger(_DescriptorBase):
    type: Literal["command"] = "command"
    command: str
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None


class MessageTrigger(_DescriptorBase):
    type: Literal["message"] = "message"
    regex: str | None = None
    keywords: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)


class EventTrigger(_DescriptorBase):
    type: Literal["event"] = "event"
    event_type: str


class ScheduleTrigger(_DescriptorBase):
    type: Literal["schedule"] = "schedule"
    cron: str | None = None
    interval_seconds: int | None = None

    @model_validator(mode="after")
    def validate_schedule(self) -> "ScheduleTrigger":
        has_cron = self.cron is not None
        has_interval = self.interval_seconds is not None
        if has_cron == has_interval:
            raise ValueError("cron 和 interval_seconds 必须且只能有一个非 null")
        return self


Trigger = Annotated[
    CommandTrigger | MessageTrigger | EventTrigger | ScheduleTrigger,
    Field(discriminator="type"),
]


class HandlerDescriptor(_DescriptorBase):
    id: str
    trigger: Trigger
    priority: int = 0
    permissions: Permissions = Field(default_factory=Permissions)


class CapabilityDescriptor(_DescriptorBase):
    name: str
    description: str
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    supports_stream: bool = False
    cancelable: bool = False
