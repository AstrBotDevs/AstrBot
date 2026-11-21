"""Legacy provider facade: old ProviderRequest/LLMResponse shapes and Provider.

The isolated Runner cannot hold real provider instances; this module exposes
the old provider API as a thin proxy over the plugin's ``ctx.llm`` service.
"""

from __future__ import annotations

import enum
from collections.abc import AsyncIterator
from typing import Any

from ...conversations import AudioPart, ImagePart, Message, TextPart
from ...llm import ProviderKind
from .components import MessageChain, Plain
from .errors import IsolationUnsupportedError


class Personality(dict):
    """Legacy personality record (a plain dict in practice)."""


class ProviderType(enum.Enum):
    """Legacy provider type enum mirroring the core values."""

    CHAT_COMPLETION = "chat_completion"
    SPEECH_TO_TEXT = "speech_to_text"
    TEXT_TO_SPEECH = "text_to_speech"
    EMBEDDING = "embedding"
    RERANK = "rerank"


_LEGACY_TYPE_BY_KIND = {
    ProviderKind.CHAT: ProviderType.CHAT_COMPLETION,
    ProviderKind.SPEECH_TO_TEXT: ProviderType.SPEECH_TO_TEXT,
    ProviderKind.TEXT_TO_SPEECH: ProviderType.TEXT_TO_SPEECH,
    ProviderKind.EMBEDDING: ProviderType.EMBEDDING,
}


class ProviderMetaData:
    """Legacy provider metadata (id, model, type, provider_type)."""

    def __init__(
        self,
        id: str,
        model: str | None = None,
        type: str = "",
        provider_type: ProviderType | None = None,
    ) -> None:
        self.id = id
        self.model = model
        self.type = type
        self.provider_type = provider_type


class ProviderRequest:
    """Legacy mutable LLM request object used by hooks and direct calls."""

    def __init__(
        self,
        prompt: str | None = None,
        session_id: str | None = "",
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
        contexts: list | None = None,
        system_prompt: str = "",
        func_tool: Any = None,
        conversation: Any = None,
        model: str | None = None,
        extra_user_content_parts: list | None = None,
        tool_calls_result: Any = None,
        **_: Any,
    ) -> None:
        self.prompt = prompt
        self.session_id = session_id
        self.image_urls = image_urls if image_urls is not None else []
        self.audio_urls = audio_urls if audio_urls is not None else []
        self.contexts = contexts if contexts is not None else []
        self.system_prompt = system_prompt
        self.func_tool = func_tool
        self.conversation = conversation
        self.model = model
        self.extra_user_content_parts = (
            extra_user_content_parts if extra_user_content_parts is not None else []
        )
        self.tool_calls_result = tool_calls_result

    def __repr__(self) -> str:
        return (
            f"ProviderRequest(prompt={self.prompt}, session_id={self.session_id}, "
            f"image_count={len(self.image_urls)}, "
            f"audio_count={len(self.audio_urls)}, "
            f"system_prompt={self.system_prompt})"
        )


class LLMResponse:
    """Legacy LLM response with the old field shape."""

    def __init__(
        self,
        role: str,
        completion_text: str | None = None,
        result_chain: MessageChain | None = None,
        tools_call_args: list[dict[str, Any]] | None = None,
        tools_call_name: list[str] | None = None,
        tools_call_ids: list[str] | None = None,
        reasoning_content: str | None = None,
        raw_completion: Any = None,
        is_chunk: bool = False,
        id: str | None = None,
        usage: Any = None,
        **_: Any,
    ) -> None:
        self.role = role
        self.result_chain = result_chain
        self.tools_call_args = tools_call_args if tools_call_args is not None else []
        self.tools_call_name = tools_call_name if tools_call_name is not None else []
        self.tools_call_ids = tools_call_ids if tools_call_ids is not None else []
        self.reasoning_content = reasoning_content
        self.raw_completion = raw_completion
        self.is_chunk = is_chunk
        self.id = id
        self.usage = usage
        self._completion_text = ""
        # Route through the setter to mirror the old result_chain semantics.
        self.completion_text = completion_text or ""

    @property
    def completion_text(self) -> str:
        if self.result_chain:
            return self.result_chain.get_plain_text()
        return self._completion_text

    @completion_text.setter
    def completion_text(self, value: str) -> None:
        if self.result_chain:
            self.result_chain.chain = [
                comp for comp in self.result_chain.chain if not isinstance(comp, Plain)
            ]
            self.result_chain.chain.insert(0, Plain(value))
        else:
            self._completion_text = value


def _content_to_parts(content: Any) -> list:
    """Convert one OpenAI-style content value into SDK message parts."""
    if isinstance(content, str):
        return [TextPart(content)]
    parts: list = []
    for item in content or []:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "text":
            parts.append(TextPart(str(item.get("text", ""))))
        elif item_type == "image_url":
            url = item.get("image_url") or {}
            if isinstance(url, dict):
                url = url.get("url", "")
            parts.append(ImagePart(str(url)))
        elif item_type in ("audio_url", "input_audio"):
            url = item.get("audio_url") or item.get("input_audio") or ""
            if isinstance(url, dict):
                url = url.get("url", "") or url.get("data", "")
            parts.append(AudioPart(str(url)))
    return parts


def contexts_to_messages(contexts: list | None) -> list[Message]:
    """Convert legacy OpenAI-format contexts into SDK Message DTOs."""
    messages: list[Message] = []
    for entry in contexts or []:
        if isinstance(entry, Message):
            messages.append(entry)
            continue
        if not isinstance(entry, dict):
            continue
        role = str(entry.get("role", "user"))
        content = entry.get("content", "")
        if isinstance(content, str):
            messages.append(Message(role=role, content=content))
        else:
            messages.append(
                Message(role=role, content=tuple(_content_to_parts(content)))
            )
    return messages


def build_input_message(
    prompt: str | None,
    image_urls: list[str] | None,
    audio_urls: list[str] | None,
) -> Message | None:
    """Build the final user message from legacy prompt/media arguments."""
    parts: list = []
    if prompt:
        parts.append(TextPart(prompt))
    parts.extend(ImagePart(str(url)) for url in image_urls or [])
    parts.extend(AudioPart(str(url)) for url in audio_urls or [])
    if not parts:
        return None
    if len(parts) == 1 and isinstance(parts[0], TextPart):
        return Message(role="user", content=parts[0].text)
    return Message(role="user", content=tuple(parts))


class Provider:
    """Facade over ``ctx.llm`` with the legacy Provider API.

    The provider binding is resolved lazily on first use so the legacy
    synchronous getters (``get_using_provider``) keep their shape inside the
    asynchronous isolated Runner.
    """

    def __init__(
        self,
        ctx: Any,
        provider_id: str | None = None,
        umo: Any = None,
        info: Any = None,
    ) -> None:
        self._ctx = ctx
        self._provider_id = provider_id
        self._umo = umo
        self._info: Any = info

    async def _resolve(self) -> tuple[str | None, Any]:
        """Resolve the effective provider id and metadata once."""
        if self._provider_id is not None:
            if self._info is None:
                providers = await self._ctx.llm.list_providers(ProviderKind.CHAT)
                self._info = next(
                    (p for p in providers if p.id == self._provider_id),
                    None,
                )
            return self._provider_id, self._info
        info = await self._ctx.llm.current_provider(ProviderKind.CHAT, umo=self._umo)
        if info is None:
            return None, None
        self._info = info
        return info.id, info

    async def text_chat(
        self,
        prompt: str | None = None,
        session_id: str | None = "",
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
        contexts: list | None = None,
        system_prompt: str = "",
        func_tool: Any = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Run one chat completion with the legacy argument shape."""
        if func_tool is not None:
            raise IsolationUnsupportedError(
                "Provider.text_chat(func_tool=...) is unavailable in isolated "
                "legacy mode; use Context.tool_loop_agent() instead"
            )
        provider_id, _ = await self._resolve()
        messages = contexts_to_messages(contexts)
        input_message = build_input_message(prompt, image_urls, audio_urls)
        if input_message is not None:
            messages.append(input_message)
        response = await self._ctx.llm.generate(
            tuple(messages),
            provider_id=provider_id,
            system_prompt=system_prompt or None,
            umo=self._umo,
        )
        return LLMResponse(
            role="assistant",
            completion_text=response.content,
            reasoning_content=response.reasoning_content,
        )

    async def text_chat_stream(
        self,
        prompt: str | None = None,
        session_id: str | None = "",
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
        contexts: list | None = None,
        system_prompt: str = "",
        func_tool: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMResponse]:
        """Stream one chat completion with the legacy argument shape."""
        if func_tool is not None:
            raise IsolationUnsupportedError(
                "Provider.text_chat_stream(func_tool=...) is unavailable in "
                "isolated legacy mode; use Context.tool_loop_agent() instead"
            )
        provider_id, _ = await self._resolve()
        messages = contexts_to_messages(contexts)
        input_message = build_input_message(prompt, image_urls, audio_urls)
        if input_message is not None:
            messages.append(input_message)
        stream = self._ctx.llm.stream(
            tuple(messages),
            provider_id=provider_id,
            system_prompt=system_prompt or None,
            umo=self._umo,
        )
        async for chunk in stream:
            yield LLMResponse(
                role="assistant",
                completion_text=chunk.delta,
                reasoning_content=chunk.reasoning_delta,
                is_chunk=True,
            )

    async def get_model_name(self) -> str | None:
        """Return the resolved provider's model name."""
        _, info = await self._resolve()
        return getattr(info, "model", None)

    def meta(self) -> ProviderMetaData | None:
        """Return the provider's metadata from the seeded/resolved info.

        In-process this method is synchronous; the facade serves it from
        the handshake snapshot or the last RPC resolution.
        """
        info = self._info
        if info is None:
            if self._provider_id is None:
                return None
            return ProviderMetaData(id=self._provider_id)
        legacy_type = _LEGACY_TYPE_BY_KIND.get(getattr(info, "kind", None))
        return ProviderMetaData(
            id=getattr(info, "id", None) or self._provider_id or "",
            model=getattr(info, "model", None),
            type=getattr(info, "provider_type", ""),
            provider_type=legacy_type,
        )

    def get_provider_id(self) -> str | None:
        """Return the explicitly bound provider id, if any."""
        return self._provider_id


class TTSProvider:
    """Legacy TTS facade backed by ctx.llm.synthesize."""

    def __init__(
        self,
        ctx: Any,
        provider_id: str | None = None,
        umo: Any = None,
    ) -> None:
        self._ctx = ctx
        self._provider_id = provider_id
        self._umo = umo

    def get_provider_id(self) -> str | None:
        """Return the explicitly bound provider id, if any."""
        return self._provider_id

    async def get_audio(self, text: str) -> Any:
        """Synthesize speech; returns an AssetRef media components accept."""
        return await self._ctx.llm.synthesize(
            text,
            provider_id=self._provider_id,
            umo=self._umo,
        )


class STTProvider:
    """Legacy STT facade backed by ctx.llm.transcribe."""

    def __init__(
        self,
        ctx: Any,
        provider_id: str | None = None,
        umo: Any = None,
    ) -> None:
        self._ctx = ctx
        self._provider_id = provider_id
        self._umo = umo

    def get_provider_id(self) -> str | None:
        """Return the explicitly bound provider id, if any."""
        return self._provider_id

    async def get_text(self, audio_url: Any) -> str:
        """Transcribe audio into text."""
        transcript = await self._ctx.llm.transcribe(
            audio_url,
            provider_id=self._provider_id,
            umo=self._umo,
        )
        return transcript.text


class EmbeddingProvider:
    """Legacy embedding facade backed by ctx.llm.embed."""

    def __init__(
        self,
        ctx: Any,
        provider_id: str | None = None,
        umo: Any = None,
    ) -> None:
        self._ctx = ctx
        self._provider_id = provider_id
        self._umo = umo

    def get_provider_id(self) -> str | None:
        """Return the explicitly bound provider id, if any."""
        return self._provider_id

    async def get_embedding(self, text: str) -> list[float]:
        """Embed one text."""
        response = await self._ctx.llm.embed(
            text,
            provider_id=self._provider_id,
            umo=self._umo,
        )
        return list(response.embeddings[0])

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        """Embed a batch of texts."""
        response = await self._ctx.llm.embed(
            tuple(text),
            provider_id=self._provider_id,
            umo=self._umo,
        )
        return [list(vector) for vector in response.embeddings]

    async def get_dim(self) -> int:
        """Return the embedding dimension (measured with a probe text)."""
        return len(await self.get_embedding("dim"))
