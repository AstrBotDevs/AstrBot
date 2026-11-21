from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import InvalidRequest, NotFound
from astrbot_sdk.llm import (
    ChatChunk,
    ChatResponse,
    ProviderInfo,
    ProviderKind,
)

from ..convert import to_core_context_message, to_umo_string

if TYPE_CHECKING:
    from astrbot.core.star.context import Context

_KIND_TO_PROVIDER_TYPE = {
    ProviderKind.CHAT: "CHAT_COMPLETION",
    ProviderKind.EMBEDDING: "EMBEDDING",
    ProviderKind.SPEECH_TO_TEXT: "SPEECH_TO_TEXT",
    ProviderKind.TEXT_TO_SPEECH: "TEXT_TO_SPEECH",
}


async def _resolve_provider(
    manager: Any,
    payload: dict[str, Any],
    *,
    default_kind: ProviderKind,
) -> Any:
    """Resolve a provider by explicit ID or the session's default."""
    provider_id = payload.get("provider_id")
    if provider_id:
        provider = await manager.get_provider_by_id(str(provider_id))
        if provider is None:
            raise NotFound(f"provider not found: {provider_id}")
        return provider
    kind = _parse_kind(payload, default=default_kind)
    umo = payload.get("umo")
    from astrbot.core.provider.entities import ProviderType as CoreProviderType

    return await manager.get_using_provider_async(
        provider_type=CoreProviderType[_KIND_TO_PROVIDER_TYPE[kind]],
        umo=to_umo_string(umo) if umo is not None else None,
    )


class LLMGenerateService:
    """Serve the llm.generate capability through the AstrBot provider manager."""

    capability_id = "llm.generate"

    def __init__(self, context: Context, store: Any = None) -> None:
        """Initialize the service.

        Args:
            context: AstrBot star context with the provider manager.
            store: Optional asset store for content part resolution.
        """
        self._context = context
        self._store = store

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve provider queries and chat completions."""
        if operation == "current_provider":
            provider = await _resolve_provider(
                self._context.provider_manager,
                payload,
                default_kind=ProviderKind.CHAT,
            )
            return {
                "provider": (
                    _to_provider_info(provider) if provider is not None else None
                ),
            }
        if operation == "list_providers":
            kind = _parse_kind(payload)
            manager = self._context.provider_manager
            insts = {
                ProviderKind.CHAT: manager.provider_insts,
                ProviderKind.EMBEDDING: manager.embedding_provider_insts,
                ProviderKind.SPEECH_TO_TEXT: manager.stt_provider_insts,
                ProviderKind.TEXT_TO_SPEECH: manager.tts_provider_insts,
            }[kind]
            return {
                "providers": [_to_provider_info(provider) for provider in insts],
            }
        if operation == "generate":
            provider = await self._resolve_chat_provider(payload)
            response = await provider.text_chat(
                **_text_chat_kwargs(
                    payload,
                    resolve_asset=self._store.resolve if self._store else None,
                ),
            )
            return {
                "response": ChatResponse(
                    content=response.completion_text,
                    reasoning_content=response.reasoning_content or None,
                ),
            }
        if operation == "generate_stream":
            return self._stream(payload)
        raise NotFound(f"unknown llm operation: {operation}")

    async def _stream(self, payload: dict[str, Any]) -> AsyncIterator[ChatChunk]:
        """Yield chat chunks from the provider's streaming completion."""
        provider = await self._resolve_chat_provider(payload)
        stream = provider.text_chat_stream(
            **_text_chat_kwargs(
                payload,
                resolve_asset=self._store.resolve if self._store else None,
            ),
        )
        if inspect.isawaitable(stream):
            stream = await stream
        async for response in stream:
            yield ChatChunk(
                delta=response.completion_text,
                reasoning_delta=response.reasoning_content or None,
            )

    async def _resolve_chat_provider(self, payload: dict[str, Any]) -> Any:
        """Resolve the chat provider for generate operations."""
        provider = await _resolve_provider(
            self._context.provider_manager,
            payload,
            default_kind=ProviderKind.CHAT,
        )
        if provider is None:
            raise NotFound("no chat provider available")
        return provider


def _parse_kind(
    payload: dict[str, Any],
    *,
    default: ProviderKind | None = None,
) -> ProviderKind:
    """Parse the provider kind field."""
    raw = payload.get("kind")
    if raw is None:
        if default is not None:
            return default
        raise InvalidRequest("kind is required")
    try:
        return ProviderKind(str(raw))
    except ValueError as exc:
        raise InvalidRequest(f"unknown provider kind: {raw}") from exc


def _to_provider_info(provider: Any) -> ProviderInfo:
    """Convert a core provider into the public DTO."""
    meta = provider.meta()
    kind = next(
        (
            kind
            for kind, name in _KIND_TO_PROVIDER_TYPE.items()
            if name == meta.provider_type.name
        ),
        ProviderKind.CHAT,
    )
    return ProviderInfo(
        id=str(meta.id),
        kind=kind,
        model=meta.model,
        provider_type=str(meta.type),
    )


def _text_chat_kwargs(
    payload: dict[str, Any],
    *,
    resolve_asset: Any = None,
) -> dict[str, Any]:
    """Build provider.text_chat kwargs from the operation payload."""
    kwargs: dict[str, Any] = {}
    prompt = payload.get("prompt")
    if prompt is not None:
        kwargs["prompt"] = str(prompt)
    messages = payload.get("messages")
    if messages:
        kwargs["contexts"] = [
            to_core_context_message(message, resolve_asset=resolve_asset)
            for message in messages
        ]
    system_prompt = payload.get("system_prompt")
    if system_prompt is not None:
        kwargs["system_prompt"] = str(system_prompt)
    return kwargs
