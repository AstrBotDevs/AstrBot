from __future__ import annotations

from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import InvalidRequest, NotFound
from astrbot_sdk.llm import EmbeddingResponse, ProviderKind

from .llm import _resolve_provider

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


class LLMEmbedService:
    """Serve the llm.embed capability through embedding providers."""

    capability_id = "llm.embed"

    def __init__(self, context: Context) -> None:
        """Initialize the service.

        Args:
            context: AstrBot star context with the provider manager.
        """
        self._context = context

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve the embed operation."""
        if operation != "embed":
            raise NotFound(f"unknown embed operation: {operation}")
        raw_input = payload.get("input")
        if isinstance(raw_input, str):
            texts = [raw_input]
        elif isinstance(raw_input, (list | tuple)) and all(
            isinstance(item, str) for item in raw_input
        ):
            texts = list(raw_input)
        else:
            raise InvalidRequest("input must be a string or a list of strings")
        if not texts:
            raise InvalidRequest("input cannot be empty")

        provider = await _resolve_provider(
            self._context.provider_manager,
            payload,
            default_kind=ProviderKind.EMBEDDING,
        )
        if provider is None:
            raise NotFound("no embedding provider available")
        vectors = await provider.get_embeddings(texts)
        return {
            "response": EmbeddingResponse(
                embeddings=tuple(tuple(vector) for vector in vectors),
            ),
        }
