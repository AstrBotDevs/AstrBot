from collections.abc import Mapping
from typing import Literal, TypedDict

from astrbot import logger
from astrbot.core.utils.http_ssl import build_tls_connector


class LLMModalities(TypedDict):
    input: list[Literal["text", "image", "audio", "video"]]
    output: list[Literal["text", "image", "audio", "video"]]


class LLMLimit(TypedDict):
    context: int
    output: int


class LLMMetadata(TypedDict):
    id: str
    reasoning: bool
    tool_call: bool
    knowledge: str
    release_date: str
    modalities: LLMModalities
    open_weights: bool
    limit: LLMLimit


class LLMMetadataCatalog:
    """Runtime-owned metadata fetched from the public model catalog."""

    def __init__(self) -> None:
        self._models: dict[str, LLMMetadata] = {}

    def get(self, model_id: str) -> LLMMetadata | None:
        """Return metadata for one model when it is known."""
        return self._models.get(model_id)

    def replace(self, models: Mapping[str, LLMMetadata]) -> None:
        """Atomically replace the currently available metadata snapshot."""
        self._models = dict(models)

    async def refresh(self) -> None:
        """Fetch and publish the latest model metadata without sharing global state."""
        url = "https://models.dev/api.json"
        try:
            from astrbot.core.utils.proxy_route import (
                create_aiohttp_session,
                current_aiohttp_proxy,
            )

            async with create_aiohttp_session(
                connector=build_tls_connector()
            ) as session:
                async with session.get(url, proxy=current_aiohttp_proxy()) as response:
                    data = await response.json()
            models: dict[str, LLMMetadata] = {}
            for info in data.values():
                for model in info.get("models", {}).values():
                    model_id = model.get("id")
                    if not model_id:
                        continue
                    models[model_id] = LLMMetadata(
                        id=model_id,
                        reasoning=model.get("reasoning", False),
                        tool_call=model.get("tool_call", False),
                        knowledge=model.get("knowledge", "none"),
                        release_date=model.get("release_date", ""),
                        modalities=model.get("modalities", {"input": [], "output": []}),
                        open_weights=model.get("open_weights", False),
                        limit=model.get("limit", {"context": 0, "output": 0}),
                    )
            self.replace(models)
            logger.info("Successfully fetched metadata for %s LLMs.", len(models))
        except Exception as exc:
            logger.error("Failed to fetch LLM metadata: %s", exc)
