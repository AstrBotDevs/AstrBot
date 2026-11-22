"""Legacy `astrbot.api.agents` surface for isolated compat plugins.

Portable message, input, output, config, event, and tool DTOs execute cleanly
inside the Runner; in-process runtime singletons (`AgentRuntime`, `AgentService`,
`AgentSession`, `AgentTurn`, `AgentRun`) remain importable and raise
`IsolationUnsupportedError` loudly on instantiation.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import urlsplit

from .components import (
    BaseMessageComponent,
    ComponentTypes,
    File,
    Image,
    MessageChain,
    Plain,
    Record,
    Video,
)
from .errors import IsolationUnsupportedError
from .po import Conversation
from .tools import FunctionTool, ToolSet


def _unsupported_runtime(name: str) -> Any:
    def _init(self: Any, *args: Any, **kwargs: Any) -> None:
        raise IsolationUnsupportedError(
            f"{name} runs inside the Host agent pipeline and is unavailable "
            "directly in isolated legacy mode"
        )

    return _init


@dataclass
class AgentConfig:
    """Portable agent configuration DTO."""

    model: str = ""
    system_prompt: str = ""
    max_steps: int = 30
    extra: dict[str, Any] = field(default_factory=dict)

    def __init__(self, **kwargs: Any) -> None:
        self.model = str(kwargs.pop("model", ""))
        self.system_prompt = str(kwargs.pop("system_prompt", ""))
        self.max_steps = int(kwargs.pop("max_steps", 30))
        self.extra = dict(kwargs)


@dataclass
class StoredAgentConfig(AgentConfig):
    """Persisted variant of AgentConfig carrying an agent identifier."""

    agent_id: str = ""

    def __init__(self, **kwargs: Any) -> None:
        self.agent_id = str(kwargs.pop("agent_id", ""))
        super().__init__(**kwargs)


@dataclass
class AgentPermissions:
    """Portable agent capability permissions DTO."""

    tools: list[str] = field(default_factory=list)
    allow_handoff: bool = False


class AgentRole(StrEnum):
    MAIN = "main"
    SUBAGENT = "subagent"


class TurnStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionState(StrEnum):
    ACTIVE = "active"
    IDLE = "idle"
    CLOSED = "closed"


@dataclass
class AgentSessionRef:
    id: str = ""
    session_id: str = ""


@dataclass
class AgentSessionStatus:
    state: str = "active"
    active_turn_id: str | None = None


@dataclass
class RuntimeErrorInfo:
    code: str = ""
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeTokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


ContextUsage = RuntimeTokenUsage
TurnUsage = RuntimeTokenUsage


@dataclass
class ExecutionMetrics:
    duration_ms: float = 0.0
    step_count: int = 0
    usage: RuntimeTokenUsage = field(default_factory=RuntimeTokenUsage)


@dataclass
class InputReceipt:
    input_id: str = ""
    accepted: bool = True


@dataclass
class TurnResult:
    turn_id: str = ""
    status: str = "completed"
    output: tuple[OutputComponent, ...] = ()
    text: str = ""


@dataclass
class _GenericRecord:
    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


class TextDelta(_GenericRecord):
    pass


class ReasoningDelta(_GenericRecord):
    pass


class MessageCompleted(_GenericRecord):
    pass


class OutputReady(_GenericRecord):
    pass


class RequestStarted(_GenericRecord):
    pass


class RequestFinished(_GenericRecord):
    pass


class ToolStarted(_GenericRecord):
    pass


class ToolProgress(_GenericRecord):
    pass


class ToolFinished(_GenericRecord):
    pass


class ToolRejected(_GenericRecord):
    pass


class UsageUpdated(_GenericRecord):
    pass


class TurnStarted(_GenericRecord):
    pass


class TurnPrepared(_GenericRecord):
    pass


class TurnFinished(_GenericRecord):
    pass


class RuntimeEventPayload(_GenericRecord):
    pass


class RunnerEventPayload(_GenericRecord):
    pass


class RuntimeEvent(_GenericRecord):
    pass


# ---- Input / Output components (mirroring core astrbot.core.agent.output) --


@dataclass
class PlainInput:
    text: str
    kind: Literal["plain"] = "plain"


@dataclass
class ImageInput:
    url: str = ""
    path: str = ""
    kind: Literal["image"] = "image"


@dataclass
class FileInput:
    name: str = ""
    url: str = ""
    path: str = ""
    kind: Literal["file"] = "file"


InputComponent = PlainInput | ImageInput | FileInput


@dataclass
class PathMedia:
    path: str
    kind: Literal["path"] = "path"


@dataclass
class URLMedia:
    url: str
    kind: Literal["url"] = "url"


@dataclass
class InlineMedia:
    data: str
    mime_type: str = "application/octet-stream"
    kind: Literal["inline"] = "inline"


MediaReference = PathMedia | URLMedia | InlineMedia


@dataclass
class PlainOutput:
    text: str
    kind: Literal["plain"] = "plain"


@dataclass
class ReasoningOutput:
    text: str
    kind: Literal["reasoning"] = "reasoning"


@dataclass
class ImageOutput:
    source: MediaReference
    kind: Literal["image"] = "image"


@dataclass
class FileOutput:
    source: MediaReference
    name: str | None = None
    kind: Literal["file"] = "file"


@dataclass
class AudioOutput:
    source: MediaReference
    kind: Literal["audio"] = "audio"


@dataclass
class VideoOutput:
    source: MediaReference
    kind: Literal["video"] = "video"


@dataclass
class ExtensionOutput:
    namespace: str
    name: str
    value: Any = None
    kind: Literal["extension"] = "extension"


OutputComponent = (
    PlainOutput
    | ReasoningOutput
    | ImageOutput
    | FileOutput
    | AudioOutput
    | VideoOutput
    | ExtensionOutput
)


def chain_from_content(content: Sequence[OutputComponent]) -> MessageChain:
    """Restore a legacy MessageChain from portable OutputComponent items."""

    def restore(data: dict[str, Any]) -> Any:
        kind = str(data.get("type", "")).lower()
        cls = ComponentTypes.get(kind)
        if cls is None:
            raise ValueError(f"Unsupported platform component: {kind}")
        values = {k: v for k, v in data.items() if k != "type"}
        for key in ("content", "chain", "nodes"):
            if isinstance(values.get(key), list):
                values[key] = [
                    restore(item) if isinstance(item, dict) and "type" in item else item
                    for item in values[key]
                ]
        return cls(**values)

    components: list[BaseMessageComponent] = []
    for part in content:
        if isinstance(part, PlainOutput | ReasoningOutput):
            if part.text:
                components.append(Plain(part.text))
        elif isinstance(part, ExtensionOutput):
            if part.namespace != "astrbot.platform" or not isinstance(part.value, dict):
                raise ValueError(
                    f"Unsupported output extension: {part.namespace}/{part.name}"
                )
            components.append(restore(part.value))
        else:
            source = part.source
            raw = (
                source.path
                if isinstance(source, PathMedia)
                else source.url
                if isinstance(source, URLMedia)
                else f"base64://{source.data}"
            )
            if isinstance(part, ImageOutput):
                components.append(Image(file=raw))
            elif isinstance(part, AudioOutput):
                components.append(Record(file=raw))
            elif isinstance(part, VideoOutput):
                components.append(Video(file=raw))
            else:
                components.append(
                    File(
                        name=part.name or "file",
                        file=raw if not isinstance(source, URLMedia) else "",
                        url=raw if isinstance(source, URLMedia) else "",
                    )
                )
    return MessageChain(chain=components)


def content_from_chain(chain: MessageChain | None) -> tuple[OutputComponent, ...]:
    """Snapshot a legacy MessageChain into portable OutputComponent items."""
    result: list[OutputComponent] = []
    for comp in chain.chain if chain else []:
        if isinstance(comp, Plain):
            result.append(
                ReasoningOutput(text=comp.text)
                if chain and chain.type == "reasoning"
                else PlainOutput(text=comp.text)
            )
        elif isinstance(comp, Image | File | Record | Video):
            raw = (
                (comp.file_ or comp.url)
                if isinstance(comp, File)
                else (comp.file or comp.url or getattr(comp, "path", ""))
            )
            if not raw:
                raise ValueError("Output media has no source")
            source: MediaReference
            if isinstance(raw, str) and raw.startswith("base64://"):
                source = InlineMedia(
                    data=raw.removeprefix("base64://"),
                    mime_type="application/octet-stream",
                )
            elif isinstance(raw, str) and raw.startswith("data:"):
                header, data = raw.split(",", 1)
                if not header.endswith(";base64"):
                    raise ValueError("Inline output media requires base64 data")
                source = InlineMedia(data=data, mime_type=header[5:-7])
            elif isinstance(raw, str) and urlsplit(raw).scheme in ("http", "https"):
                source = URLMedia(url=raw)
            else:
                source = PathMedia(path=str(raw))
            if isinstance(comp, Image):
                result.append(ImageOutput(source=source))
            elif isinstance(comp, File):
                result.append(FileOutput(source=source, name=comp.name or None))
            elif isinstance(comp, Record):
                result.append(AudioOutput(source=source))
            else:
                result.append(VideoOutput(source=source))
        else:
            payload = (
                comp.toDict()
                if hasattr(comp, "toDict")
                else {"type": type(comp).__name__.lower()}
            )
            result.append(
                ExtensionOutput(
                    namespace="astrbot.platform",
                    name=str(payload.get("type", type(comp).__name__.lower())),
                    value=json.loads(json.dumps(payload, default=str)),
                )
            )
    return tuple(result)


class AgentRuntime:
    __init__ = _unsupported_runtime("AgentRuntime")


class AgentService:
    __init__ = _unsupported_runtime("AgentService")


class AgentSession:
    __init__ = _unsupported_runtime("AgentSession")


class AgentTurn:
    __init__ = _unsupported_runtime("AgentTurn")


class AgentRun:
    __init__ = _unsupported_runtime("AgentRun")


class BaseFunctionToolExecutor:
    __init__ = _unsupported_runtime("BaseFunctionToolExecutor")


ToolExecResult = Any


def build_agents_module_dict() -> dict[str, Any]:
    """Export all `astrbot.api.agents` attributes including core message types."""
    from .api import _AgentMessage, _AgentPart, _AstrAgentContext, _ContextWrapper

    class ContextWrapper(_ContextWrapper):
        pass

    class AstrAgentContext(_AstrAgentContext):
        pass

    class AgentContextWrapper(ContextWrapper):
        pass

    return {
        "RuntimeErrorInfo": RuntimeErrorInfo,
        "RuntimeTokenUsage": RuntimeTokenUsage,
        "ContextUsage": ContextUsage,
        "TurnUsage": TurnUsage,
        "ExecutionMetrics": ExecutionMetrics,
        "TextDelta": TextDelta,
        "ReasoningDelta": ReasoningDelta,
        "MessageCompleted": MessageCompleted,
        "OutputReady": OutputReady,
        "chain_from_content": chain_from_content,
        "content_from_chain": content_from_chain,
        "RequestStarted": RequestStarted,
        "RequestFinished": RequestFinished,
        "ToolStarted": ToolStarted,
        "ToolProgress": ToolProgress,
        "ToolFinished": ToolFinished,
        "ToolRejected": ToolRejected,
        "UsageUpdated": UsageUpdated,
        "TurnStarted": TurnStarted,
        "TurnPrepared": TurnPrepared,
        "TurnFinished": TurnFinished,
        "RuntimeEventPayload": RuntimeEventPayload,
        "RunnerEventPayload": RunnerEventPayload,
        "MediaReference": MediaReference,
        "PathMedia": PathMedia,
        "URLMedia": URLMedia,
        "InlineMedia": InlineMedia,
        "PlainOutput": PlainOutput,
        "ReasoningOutput": ReasoningOutput,
        "ImageOutput": ImageOutput,
        "FileOutput": FileOutput,
        "AudioOutput": AudioOutput,
        "VideoOutput": VideoOutput,
        "ExtensionOutput": ExtensionOutput,
        "OutputComponent": OutputComponent,
        "AgentConfig": AgentConfig,
        "StoredAgentConfig": StoredAgentConfig,
        "AgentContextWrapper": AgentContextWrapper,
        "AgentPermissions": AgentPermissions,
        "AgentSessionRef": AgentSessionRef,
        "AgentRole": AgentRole,
        "AgentRun": AgentRun,
        "AgentSessionStatus": AgentSessionStatus,
        "AgentRuntime": AgentRuntime,
        "AgentService": AgentService,
        "AgentSession": AgentSession,
        "AgentTurn": AgentTurn,
        "AssistantMessageSegment": _AgentMessage,
        "AstrAgentContext": AstrAgentContext,
        "AudioURLPart": _AgentPart,
        "BaseFunctionToolExecutor": BaseFunctionToolExecutor,
        "ContentPart": _AgentPart,
        "ContextWrapper": ContextWrapper,
        "Conversation": Conversation,
        "FileInput": FileInput,
        "FunctionTool": FunctionTool,
        "ImageInput": ImageInput,
        "ImageURLPart": _AgentPart,
        "InputComponent": InputComponent,
        "InputReceipt": InputReceipt,
        "Message": _AgentMessage,
        "PlainInput": PlainInput,
        "RuntimeEvent": RuntimeEvent,
        "SessionState": SessionState,
        "SystemMessageSegment": _AgentMessage,
        "TextPart": _AgentPart,
        "ThinkPart": _AgentPart,
        "ToolCall": _AgentPart,
        "ToolCallMessageSegment": _AgentMessage,
        "ToolCallPart": _AgentPart,
        "ToolExecResult": ToolExecResult,
        "ToolSet": ToolSet,
        "TurnResult": TurnResult,
        "TurnStatus": TurnStatus,
        "UserMessageSegment": _AgentMessage,
    }
