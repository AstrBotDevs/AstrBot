from collections.abc import Mapping
from typing import Literal, TypedDict

import aiohttp

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


LLM_METADATA_URLS = (
    "https://models.dev/api.json",
    "https://models.opencode.ai/api.json",
)


def _parse_llm_metadata(data: object) -> dict[str, LLMMetadata]:
    """Validate and normalize one metadata catalog response."""
    if not isinstance(data, Mapping):
        raise ValueError("LLM metadata response must be a JSON object")

    models: dict[str, LLMMetadata] = {}
    for info in data.values():
        if not isinstance(info, Mapping):
            raise ValueError("LLM metadata provider must be an object")
        provider_models = info.get("models", {})
        if not isinstance(provider_models, Mapping):
            raise ValueError("LLM metadata models must be an object")
        for model in provider_models.values():
            if not isinstance(model, Mapping):
                raise ValueError("LLM metadata model must be an object")
            model_id = model.get("id")
            if not isinstance(model_id, str) or not model_id:
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
    return models


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
        from astrbot.core.utils.proxy_route import (
            create_aiohttp_session,
            current_aiohttp_proxy,
        )

        last_error: Exception | None = None
        try:
            async with create_aiohttp_session(
                connector=build_tls_connector()
            ) as session:
                for url in LLM_METADATA_URLS:
                    try:
                        async with session.get(
                            url,
                            proxy=current_aiohttp_proxy(),
                        ) as response:
                            response.raise_for_status()
                            data = await response.json()
                            models = _parse_llm_metadata(data)

                            self.replace(models)
                            logger.info(
                                "Successfully fetched metadata for %s LLMs from %s.",
                                len(models),
                                url,
                            )
                            return
                    except (TimeoutError, aiohttp.ClientError, ValueError) as exc:
                        last_error = exc
                        logger.warning(
                            "Endpoint %s failed: %s, trying next...",
                            url,
                            exc,
                        )
                        continue
        except Exception as exc:
            last_error = exc

        logger.error("All metadata endpoints failed: %s", last_error)
