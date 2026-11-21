from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from .assets import AssetRef
from .conversations import Message
from .errors import CapabilityDenied, InvalidRequest
from .events import UMO, MessageEvent
from .protocol_registry import register_protocol_dataclass

if TYPE_CHECKING:
    from .context import PluginContext

_GENERATE_CAPABILITY = "llm.generate"


class ProviderKind(StrEnum):
    CHAT = "chat"
    EMBEDDING = "embedding"
    SPEECH_TO_TEXT = "speech_to_text"
    TEXT_TO_SPEECH = "text_to_speech"


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class ProviderInfo:
    """Public metadata of one LLM provider instance."""

    id: str
    kind: ProviderKind
    model: str | None
    provider_type: str


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class ChatResponse:
    """One-shot chat completion result."""

    content: str
    reasoning_content: str | None = None


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class ChatChunk:
    """One streamed chat completion chunk, as emitted by the adapter."""

    delta: str
    reasoning_delta: str | None = None


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class EmbeddingResponse:
    """Embedding vectors for the requested inputs, in order."""

    embeddings: tuple[tuple[float, ...], ...]


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class Transcript:
    """Speech-to-text transcription result."""

    text: str


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class AgentRequest:
    """Request for one agent loop run.

    ``input`` is the Responses-style unified input: a plain string (single
    user message), one Message, or a tuple mixing both. Multimodal content
    travels inside Message.content parts.
    ``agent`` is reserved for custom agent runners: None selects the built-in
    tool-loop agent. ``steps`` on AgentResponse is likewise reserved.

    ``tools`` follows the legacy tool_loop_agent semantics: None offers no
    tools, while a name tuple offers exactly those tools. ``event`` carries
    the triggering event and defaults to the ambient one.
    """

    input: str | Message | tuple[Message, ...] = ""
    system_prompt: str | None = None
    provider_id: str | None = None
    umo: UMO | None = None
    max_steps: int = 30
    agent: str | None = None
    tools: tuple[str, ...] | None = None
    event: MessageEvent | None = None


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class AgentStep:
    """One recorded step of an agent run (reserved)."""

    tool: str
    arguments: Mapping[str, Any]
    result: str | None = None


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class AgentResponse:
    """Final result of one agent loop run."""

    text: str
    reasoning_content: str | None = None
    steps: tuple[AgentStep, ...] = ()


class LLMService:
    """Call AstrBot chat providers through typed SDK DTOs."""

    def __init__(self, ctx: PluginContext) -> None:
        """Initialize the service.

        Args:
            ctx: Owning plugin context used for Host invocation.
        """
        self._ctx = ctx

    async def current_provider(
        self,
        kind: ProviderKind,
        *,
        umo: UMO | None = None,
    ) -> ProviderInfo | None:
        """Return the provider currently selected for the given kind."""
        result = await self._ctx._invoke_capability(
            _GENERATE_CAPABILITY,
            "current_provider",
            {
                "kind": kind.value,
                "umo": umo if umo is not None else self._ctx._ambient_umo(),
            },
        )
        return result.get("provider")

    async def list_providers(self, kind: ProviderKind) -> list[ProviderInfo]:
        """Return provider metadata for the given kind."""
        result = await self._ctx._invoke_capability(
            _GENERATE_CAPABILITY,
            "list_providers",
            {"kind": kind.value},
        )
        return list(result.get("providers", []))

    async def generate(
        self,
        input: str | Message | tuple[Message, ...],
        *,
        messages: tuple[Message, ...] = (),
        umo: UMO | None = None,
        provider_id: str | None = None,
        system_prompt: str | None = None,
    ) -> ChatResponse:
        """Run one chat completion.

        ``input`` is the new user input: a plain string, one Message, or
        a tuple mixing both. ``messages`` carries the prior
        history, with the input appended after it.

        Args:
            input: User input for this turn.
            messages: Prior conversation history.
            umo: Optional session for provider selection.
            provider_id: Optional explicit provider instance.
            system_prompt: Optional system prompt override.

        Returns:
            The completion response.
        """
        history = list(messages)
        if isinstance(input, str):
            if input:
                history.append(Message(role="user", content=input))
        else:
            history.extend(
                message for item in _normalize_input(input) for message in item
            )
        payload = {
            "messages": history,
            "system_prompt": system_prompt,
            "provider_id": provider_id,
            "umo": umo if umo is not None else self._ctx._ambient_umo(),
        }
        result = await self._ctx._invoke_capability(
            _GENERATE_CAPABILITY,
            "generate",
            payload,
        )
        return result["response"]

    async def embed(
        self,
        input: str | tuple[str, ...],
        *,
        provider_id: str | None = None,
        umo: UMO | None = None,
    ) -> EmbeddingResponse:
        """Embed one or more texts with an embedding provider.

        Args:
            input: Single text or a tuple of texts.
            provider_id: Optional explicit provider instance.
            umo: Optional session for provider selection.

        Returns:
            Embedding vectors in input order.
        """
        result = await self._ctx._invoke_capability(
            "llm.embed",
            "embed",
            {
                "input": input,
                "provider_id": provider_id,
                "umo": umo if umo is not None else self._ctx._ambient_umo(),
            },
        )
        return result["response"]

    async def transcribe(
        self,
        audio: AssetRef | str,
        *,
        provider_id: str | None = None,
        umo: UMO | None = None,
    ) -> Transcript:
        """Transcribe audio into text with an STT provider.

        Args:
            audio: Asset reference, or a public URL.
            provider_id: Optional explicit provider instance.
            umo: Optional session for provider selection.

        Returns:
            The transcription.
        """
        result = await self._ctx._invoke_capability(
            "speech.transcribe",
            "transcribe",
            {
                "audio": audio,
                "provider_id": provider_id,
                "umo": umo if umo is not None else self._ctx._ambient_umo(),
            },
        )
        return result["transcript"]

    async def synthesize(
        self,
        text: str,
        *,
        provider_id: str | None = None,
        umo: UMO | None = None,
    ) -> AssetRef:
        """Synthesize speech from text with a TTS provider.

        Args:
            text: Text to synthesize.
            provider_id: Optional explicit provider instance.
            umo: Optional session for provider selection.

        Returns:
            Reference to the audio asset held by the Host.
        """
        result = await self._ctx._invoke_capability(
            "speech.synthesize",
            "synthesize",
            {
                "text": text,
                "provider_id": provider_id,
                "umo": umo if umo is not None else self._ctx._ambient_umo(),
            },
        )
        return result["asset"]

    async def run_agent(self, request: AgentRequest) -> AgentResponse:
        """Run the built-in tool-loop agent with this plugin's own tools.

        Requires both the llm.agent and llm.generate capabilities. Tool calls
        made by the agent execute in this plugin and remain subject to its
        capability grants.
        """
        if not self._ctx.capabilities.has("llm.generate"):
            raise CapabilityDenied("run_agent requires the llm.generate capability")
        if request.agent is not None:
            raise InvalidRequest("custom agent runners are not available yet")
        payload = {
            "messages": [
                message for item in _normalize_input(request.input) for message in item
            ]
            if not isinstance(request.input, str)
            else None,
            "prompt": request.input if isinstance(request.input, str) else None,
            "system_prompt": request.system_prompt,
            "provider_id": request.provider_id,
            "umo": (
                request.umo if request.umo is not None else self._ctx._ambient_umo()
            ),
            "max_steps": request.max_steps,
            "tools": list(request.tools) if request.tools is not None else None,
            "event": (
                request.event
                if request.event is not None
                else self._ctx._ambient_event()
            ),
        }
        result = await self._ctx._invoke_capability(
            "llm.agent",
            "run",
            payload,
        )
        return result["response"]

    def stream(
        self,
        input: str | Message | tuple[Message, ...],
        *,
        messages: tuple[Message, ...] = (),
        umo: UMO | None = None,
        provider_id: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """Stream one chat completion chunk by chunk.

        Same input shape as generate. Backpressure is flow-controlled: the
        Host only produces the next chunk after the caller advances this
        iterator.
        """
        history = list(messages)
        if isinstance(input, str):
            if input:
                history.append(Message(role="user", content=input))
        else:
            history.extend(
                message for item in _normalize_input(input) for message in item
            )
        payload = {
            "messages": history,
            "system_prompt": system_prompt,
            "provider_id": provider_id,
            "umo": umo if umo is not None else self._ctx._ambient_umo(),
        }
        return self._ctx._invoke_capability_stream(
            _GENERATE_CAPABILITY,
            "generate_stream",
            payload,
        )


def _normalize_input(
    input: str | Message | tuple[Message, ...],
) -> list[tuple[Message, ...]]:
    """Normalize an input value into message tuples.

    Strings become single user text messages; Message items pass through.

    Raises:
        InvalidRequest: An input item is not a string or Message.
    """
    if isinstance(input, str):
        return []
    items = input if isinstance(input, tuple) else (input,)
    normalized: list[tuple[Message, ...]] = []
    for item in items:
        if isinstance(item, str):
            normalized.append((Message(role="user", content=item),))
        elif isinstance(item, Message):
            normalized.append((item,))
        else:
            raise InvalidRequest(
                f"input items must be str or Message, got {type(item)!r}"
            )
    return normalized
