"""Model discovery shared by Xinference adapters."""

from xinference_client.client.restful.async_restful_client import AsyncClient

from astrbot import logger


async def find_running_model(
    client: AsyncClient, model_name: str, previous_uid: str | None = None
) -> str | None:
    """Find the first matching model, preserving an existing UID on no match."""
    running_models = await client.list_models()
    for uid, model_spec in running_models.items():
        if model_spec.get("model_name") == model_name:
            logger.info(f"Model '{model_name}' is already running with UID: {uid}")
            return uid
    return previous_uid
