from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _EntityModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ProviderType(str, enum.Enum):
    CHAT_COMPLETION = "chat_completion"
    SPEECH_TO_TEXT = "speech_to_text"
    TEXT_TO_SPEECH = "text_to_speech"
    EMBEDDING = "embedding"
    RERANK = "rerank"


class ProviderMeta(_EntityModel):
    id: str
    model: str | None = None
    type: str
    provider_type: ProviderType = ProviderType.CHAT_COMPLETION

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> ProviderMeta | None:
        if not isinstance(payload, dict):
            return None
        return cls.model_validate(payload)


class ToolCallsResult(_EntityModel):
    tool_call_id: str | None = None
    tool_name: str
    content: str
    success: bool = True

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ToolCallsResult:
        return cls.model_validate(payload)


class RerankResult(_EntityModel):
    index: int
    score: float
    document: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> RerankResult:
        return cls.model_validate(payload)


class LLMToolSpec(_EntityModel):
    name: str
    description: str = ""
    parameters_schema: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    handler_ref: str | None = Field(
        default=None,
        description="Worker-side handler reference used to resolve the tool callable.",
    )
    handler_capability: str | None = Field(
        default=None,
        description="Optional capability name override for executing this tool handler.",
    )
    active: bool = True

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> LLMToolSpec:
        return cls.model_validate(payload)


class ProviderRequest(_EntityModel):
    prompt: str | None = None
    system_prompt: str | None = None
    session_id: str | None = None
    contexts: list[dict[str, Any]] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)
    tool_names: list[str] | None = None
    tool_calls_result: list[ToolCallsResult] = Field(default_factory=list)
    provider_id: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_steps: int | None = None
    tool_call_timeout: int | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = super().to_payload()
        payload["tool_calls_result"] = [
            item.to_payload() for item in self.tool_calls_result
        ]
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ProviderRequest:
        normalized = dict(payload)
        raw_results = normalized.get("tool_calls_result")
        if isinstance(raw_results, list):
            normalized["tool_calls_result"] = [
                ToolCallsResult.from_payload(item)
                for item in raw_results
                if isinstance(item, dict)
            ]
        return cls.model_validate(normalized)
