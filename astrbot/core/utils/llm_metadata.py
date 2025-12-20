from typing import Literal, TypedDict

import aiohttp

from astrbot.core import logger


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


async def update_llm_metadata():
    url = "https://models.dev/api.json"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                global LLM_METADATAS
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
                            modalities=model.get(
                                "modalities", {"input": [], "output": []}
                            ),
                            open_weights=model.get("open_weights", False),
                            limit=model.get("limit", {"context": 0, "output": 0}),
                        )
                # Replace the global cache in-place so references remain valid
                LLM_METADATAS.clear()
                LLM_METADATAS.update(models)
                logger.info(f"Successfully fetched metadata for {len(models)} LLMs.")
    except Exception as e:
        logger.error(f"Failed to fetch LLM metadata: {e}")
        return
