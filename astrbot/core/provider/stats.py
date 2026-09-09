from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from astrbot import logger
from astrbot.core.db import BaseDatabase
from astrbot.core.provider.entities import LLMResponse, ProviderRequest, TokenUsage


@dataclass(slots=True)
class ProviderStatSegment:
    provider: Any
    usage: TokenUsage
    start_time: float
    end_time: float
    status: str = "error"


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
    if response is None or response.role == "err":
        return "error"
    return "completed"


def _token_usage_dict(usage: TokenUsage) -> dict[str, int]:
    return {
        "input_other": usage.input_other,
        "input_cached": usage.input_cached,
        "output": usage.output,
    }


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
        segments: list[ProviderStatSegment] = list(
            getattr(agent_runner, "provider_stat_segments", ())
        )
        segmented_usage = TokenUsage()
        for segment in segments:
            segmented_usage += segment.usage
            await db.insert_provider_stat(
                umo=umo,
                conversation_id=conversation_id,
                provider_id=_provider_id(segment.provider),
                provider_model=segment.provider.get_model(),
                status=segment.status,
                stats={
                    "token_usage": _token_usage_dict(segment.usage),
                    "start_time": segment.start_time,
                    "end_time": segment.end_time,
                    "time_to_first_token": 0.0,
                },
                agent_type=agent_type,
            )

        aggregate_stats = stats.to_dict()
        aggregate_usage = stats.token_usage - segmented_usage
        aggregate_stats["token_usage"] = {
            "input_other": max(0, aggregate_usage.input_other),
            "input_cached": max(0, aggregate_usage.input_cached),
            "output": max(0, aggregate_usage.output),
        }
        if segments:
            original_start = aggregate_stats["start_time"]
            aggregate_start = max(
                original_start,
                max(segment.end_time for segment in segments),
            )
            aggregate_stats["start_time"] = aggregate_start
            aggregate_stats["time_to_first_token"] = max(
                0.0,
                aggregate_stats["time_to_first_token"]
                - (aggregate_start - original_start),
            )
        if (
            aggregate_stats["end_time"] <= 0
            or aggregate_stats["end_time"] < aggregate_stats["start_time"]
        ):
            aggregate_stats["end_time"] = max(
                time.time(),
                aggregate_stats["start_time"],
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
            stats=aggregate_stats,
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
    usage: TokenUsage | None = None,
) -> None:
    """Persist stats for one direct provider request."""
    try:
        effective_usage = usage
        if effective_usage is None and response is not None:
            effective_usage = response.usage
        if effective_usage is None:
            effective_usage = TokenUsage()
        await db.insert_provider_stat(
            umo=umo,
            conversation_id=conversation_id,
            provider_id=_provider_id(provider),
            provider_model=provider.get_model(),
            status=_response_status(response),
            stats={
                "token_usage": _token_usage_dict(effective_usage),
                "start_time": start_time,
                "end_time": end_time,
                "time_to_first_token": 0.0,
            },
            agent_type=agent_type,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Persist provider stats failed: %s", exc, exc_info=True)
