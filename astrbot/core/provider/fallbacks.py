from __future__ import annotations

from astrbot.core import logger


def _get_provider_source_types(config: dict) -> dict[str, str]:
    provider_source_types: dict[str, str] = {}
    for provider_source in config.get("provider_sources", []):
        if not isinstance(provider_source, dict):
            continue
        provider_source_id = provider_source.get("id")
        if not isinstance(provider_source_id, str) or not provider_source_id:
            continue
        provider_source_types[provider_source_id] = (
            provider_source.get("provider_type") or "chat_completion"
        )
    return provider_source_types


def get_enabled_chat_provider_ids(config: dict) -> set[str]:
    """Return provider IDs that can be used as chat fallback providers."""
    provider_ids: set[str] = set()
    provider_source_types = _get_provider_source_types(config)
    for provider in config.get("provider", []):
        if not isinstance(provider, dict):
            continue
        provider_id = provider.get("id")
        if not isinstance(provider_id, str) or not provider_id:
            continue
        if provider.get("enable") is False:
            continue
        provider_type = provider.get("provider_type")
        provider_source_id = provider.get("provider_source_id")
        if not provider_type:
            if provider_source_id:
                if not isinstance(provider_source_id, str):
                    continue
                provider_type = provider_source_types.get(provider_source_id)
            else:
                provider_type = "chat_completion"
        if provider_type != "chat_completion":
            continue
        provider_ids.add(provider_id)
    return provider_ids


def prune_fallback_chat_models(config: dict) -> list[str]:
    """Drop stale or disabled provider IDs from provider_settings.fallback_chat_models."""
    provider_settings = config.get("provider_settings")
    if not isinstance(provider_settings, dict):
        return []

    fallback_ids = provider_settings.get("fallback_chat_models")
    if not isinstance(fallback_ids, list):
        return []

    valid_provider_ids = get_enabled_chat_provider_ids(config)
    seen: set[str] = set()
    pruned_fallback_ids: list[str] = []
    removed_fallback_ids: list[str] = []

    for fallback_id in fallback_ids:
        if not isinstance(fallback_id, str) or not fallback_id:
            removed_fallback_ids.append(str(fallback_id))
            continue
        if fallback_id in seen:
            removed_fallback_ids.append(fallback_id)
            continue
        seen.add(fallback_id)
        if fallback_id not in valid_provider_ids:
            removed_fallback_ids.append(fallback_id)
            continue
        pruned_fallback_ids.append(fallback_id)

    if pruned_fallback_ids != fallback_ids:
        provider_settings["fallback_chat_models"] = pruned_fallback_ids
        logger.info(
            "Removed stale fallback chat providers from config: %s",
            removed_fallback_ids,
        )

    return removed_fallback_ids
