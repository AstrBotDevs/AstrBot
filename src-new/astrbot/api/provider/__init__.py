"""旧版 ``astrbot.api.provider`` 导入路径兼容入口。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict

from astrbot_sdk.api.provider import LLMResponse


class ProviderType(str, Enum):
    CHAT_COMPLETION = "chat_completion"
    SPEECH_TO_TEXT = "speech_to_text"
    TEXT_TO_SPEECH = "text_to_speech"
    EMBEDDING = "embedding"
    RERANK = "rerank"


@dataclass(slots=True)
class ProviderMetaData:
    id: str
    model: str | None = None
    type: str = ""
    provider_type: ProviderType = ProviderType.CHAT_COMPLETION
    desc: str = ""
    cls_type: Any = None
    default_config_tmpl: dict[str, Any] | None = None
    provider_display_name: str | None = None


@dataclass(slots=True)
class ProviderRequest:
    prompt: str | None = None
    session_id: str | None = ""
    image_urls: list[str] = field(default_factory=list)
    contexts: list[dict[str, Any]] = field(default_factory=list)
    system_prompt: str = ""
    conversation: Any | None = None
    tool_calls_result: Any | None = None
    model: str | None = None


class Personality(TypedDict, total=False):
    prompt: str
    name: str
    begin_dialogs: list[str]
    mood_imitation_dialogs: list[str]
    tools: list[str] | None
    skills: list[str] | None
    custom_error_message: str | None


class Provider:
    """旧版 Provider 基类占位。"""


class STTProvider:
    """旧版 STTProvider 基类占位。"""


__all__ = [
    "LLMResponse",
    "Personality",
    "Provider",
    "ProviderMetaData",
    "ProviderRequest",
    "ProviderType",
    "STTProvider",
]
