from __future__ import annotations

from typing import Any

from astrbot import logger
from astrbot.core.db import BaseDatabase
from astrbot.core.provider.entities import LLMResponse, ProviderRequest, TokenUsage


def _provider_id(provider: Any) -> str:
    provider_config = getattr(provider, "provider_config", {}) or {}
    return provider_config.get("id", "") or provider.meta().id


def _response_status(response: LLMResponse | None) -> str:
    if response is None or response.role == "err":
        return "error"
    return "completed"


def _runner_status(response: LLMResponse | None, aborted: bool) -> str:
    if aborted:
        return "aborted"
    if response is not None and response.role == "err":
        return "error"
    return "completed"


async def record_agent_runner_stats(
    db: BaseDatabase,
    *,
    umo: str,
    request: ProviderRequest | None,
    agent_runner: Any,
    final_response: LLMResponse | None,
    agent_type: str = "internal",
) -> None:
    """Persist aggregate agent runner stats without affecting its response."""
    if agent_runner is None:
        return

    provider = getattr(agent_runner, "provider", None)
    stats = getattr(agent_runner, "stats", None)
    if provider is None or stats is None:
        return

    try:
        conversation_id = (
            request.conversation.cid
            if request is not None and request.conversation is not None
            else None
        )
        await db.insert_provider_stat(
            umo=umo,
            conversation_id=conversation_id,
            provider_id=_provider_id(provider),
            provider_model=provider.get_model(),
            status=_runner_status(
                final_response,
                agent_runner.was_aborted(),
            ),
            stats=stats.to_dict(),
            agent_type=agent_type,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Persist provider stats failed: %s", exc, exc_info=True)


async def record_llm_response_stats(
    db: BaseDatabase,
    *,
    umo: str,
    provider: Any,
    response: LLMResponse | None,
    start_time: float,
    end_time: float,
    conversation_id: str | None = None,
    agent_type: str = "internal",
) -> None:
    """Persist stats for one direct provider request."""
    try:
        usage = response.usage if response and response.usage else TokenUsage()
        await db.insert_provider_stat(
            umo=umo,
            conversation_id=conversation_id,
            provider_id=_provider_id(provider),
            provider_model=provider.get_model(),
            status=_response_status(response),
            stats={
                "token_usage": usage.__dict__.copy(),
                "start_time": start_time,
                "end_time": end_time,
                "time_to_first_token": 0.0,
            },
            agent_type=agent_type,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Persist provider stats failed: %s", exc, exc_info=True)
