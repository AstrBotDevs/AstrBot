import asyncio
from typing import Literal, TypedDict

import aiohttp

from astrbot.core import logger
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


LLM_METADATAS: dict[str, LLMMetadata] = {}
LLM_METADATA_URLS = (
    "https://models.dev/api.json",
    "https://models.opencode.ai/api.json",
)


async def update_llm_metadata() -> None:
    global LLM_METADATAS
    last_error: Exception | None = None
    async with aiohttp.ClientSession(
        trust_env=True, connector=build_tls_connector()
    ) as session:
        for url in LLM_METADATA_URLS:
            try:
                async with session.get(url) as response:
                    response.raise_for_status()
                    data = await response.json()
                    if not isinstance(data, dict):
                        raise ValueError("LLM metadata response must be a JSON object")
            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
                ValueError,
            ) as e:
                last_error = e
                logger.warning(f"Endpoint {url} failed: {e}, trying next...")
                continue

            models = {}
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
            # Replace the global cache in-place so references remain valid
            LLM_METADATAS.clear()
            LLM_METADATAS.update(models)
            logger.info(
                f"Successfully fetched metadata for {len(models)} LLMs from {url}."
            )
            return

    logger.error(f"All metadata endpoints failed: {last_error}")
