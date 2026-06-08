from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OpenModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ConfigProfileCreateRequest(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None


class RenameRequest(BaseModel):
    name: str | None = None


class EnabledPatch(BaseModel):
    enabled: bool


class BotConfigRequest(OpenModel):
    id: str | None = None
    name: str | None = None
    type: str | None = None
    enabled: bool | None = None
    enable: bool | None = None
    config: dict[str, Any] | None = None

    def to_legacy_config(self, *, fallback_id: str | None = None) -> dict[str, Any]:
        config = dict(
            self.config
            or self.model_dump(
                exclude={"config", "enabled"},
                exclude_none=True,
            )
        )
        if fallback_id and "id" not in config:
            config["id"] = fallback_id
        if self.type and "type" not in config:
            config["type"] = self.type
        if self.id and "id" not in config:
            config["id"] = self.id
        if self.enabled is not None:
            config["enable"] = self.enabled
        elif self.enable is not None:
            config["enable"] = self.enable
        elif "enable" not in config:
            config["enable"] = True
        return config


class ProviderSourceRequest(OpenModel):
    id: str | None = None
    config: dict[str, Any] | None = None

    def to_legacy_config(self, *, fallback_id: str | None = None) -> dict[str, Any]:
        config = dict(
            self.config or self.model_dump(exclude={"config"}, exclude_none=True)
        )
        if fallback_id:
            config["id"] = fallback_id
        elif self.id and "id" not in config:
            config["id"] = self.id
        return config


class ProviderConfigRequest(OpenModel):
    id: str | None = None
    provider_source_id: str | None = None
    capability: str | None = None
    enabled: bool | None = None
    enable: bool | None = None
    config: dict[str, Any] | None = None

    def to_legacy_config(
        self,
        *,
        fallback_id: str | None = None,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        config = dict(
            self.config
            or self.model_dump(
                exclude={"config", "capability", "enabled"},
                exclude_none=True,
            )
        )
        if fallback_id and "id" not in config:
            config["id"] = fallback_id
        if self.id and "id" not in config:
            config["id"] = self.id
        if source_id:
            config["provider_source_id"] = source_id
        elif self.provider_source_id and "provider_source_id" not in config:
            config["provider_source_id"] = self.provider_source_id
        if self.enabled is not None:
            config["enable"] = self.enabled
        elif self.enable is not None:
            config["enable"] = self.enable
        elif "enable" not in config:
            config["enable"] = True
        if self.capability and "provider_type" not in config:
            capability_map = {
                "chat": "chat_completion",
                "agent": "agent_runner",
                "stt": "speech_to_text",
                "tts": "text_to_speech",
                "embedding": "embedding",
                "rerank": "rerank",
            }
            config["provider_type"] = capability_map.get(
                self.capability, self.capability
            )
        return config


class ProviderListQuery(BaseModel):
    capability: str | None = None
    source_id: str | None = None
    enabled: bool | None = None


class ConfigRoutesReplaceRequest(BaseModel):
    routing: dict[str, str]


class ConfigRouteUpsertRequest(BaseModel):
    config_id: str = Field(..., min_length=1)


class SessionRuleRequest(OpenModel):
    umo: str | None = None
    rule_key: str | None = None
    rule_value: Any = None


class UmoListRequest(OpenModel):
    umo: str | None = None
    umos: list[str] | None = None
    scope: Literal["all", "group", "private", "custom_group"] | None = None
    group_id: str | None = None
    rule_key: str | None = None


class BatchSessionProviderRequest(UmoListRequest):
    provider_id: str | None = None
    provider_type: (
        Literal[
            "chat_completion",
            "speech_to_text",
            "text_to_speech",
        ]
        | None
    ) = None


class BatchSessionServiceRequest(UmoListRequest):
    session_enabled: bool | None = None
    llm_enabled: bool | None = None
    tts_enabled: bool | None = None


class SessionGroupRequest(OpenModel):
    id: str | None = None
    name: str | None = None
    umos: list[str] | None = None
    add_umos: list[str] | None = None
    remove_umos: list[str] | None = None
