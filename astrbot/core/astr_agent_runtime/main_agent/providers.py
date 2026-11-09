"""Model selection and per-run model settings."""

from __future__ import annotations

import base64

from astrbot.core import logger
from astrbot.core.llm_error_messages import (
    set_llm_error_message as set_llm_error_message,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider import Provider
from astrbot.core.provider.capabilities import supports_modality as supports_modality
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context

from .config import MainAgentBuildConfig

BLOCKED = {"dGZid2h2d3IuY2xvdWQuc2VhbG9zLmlv", "a291cmljaGF0"}

decoded_blocked = [base64.b64decode(b).decode("utf-8") for b in BLOCKED]


async def select_chat_provider(
    event: AstrMessageEvent, plugin_context: Context
) -> Provider | None:
    """Select the chat provider for an event.

    Args:
        event: Message event that may contain an explicit provider selection.
        plugin_context: Plugin context used to resolve configured providers.

    Returns:
        Selected chat provider, or None if selection fails.
    """
    sel_provider = event.get_extra("selected_provider")
    if sel_provider and isinstance(sel_provider, str):
        provider = plugin_context.get_provider_by_id(sel_provider)
        if provider is None:
            logger.error("Selected provider %s was not found.", sel_provider)
            set_llm_error_message(
                event,
                "providerNotFound",
                provider=sel_provider,
            )
            return None
        if not isinstance(provider, Provider):
            logger.error(
                "Selected provider has invalid type %s; skipping the request.",
                type(provider),
            )
            set_llm_error_message(
                event,
                "invalidProviderType",
                provider_type=type(provider).__name__,
            )
            return None
        return provider
    try:
        locale = event.get_extra("locale")
        locale_kwargs = {"locale": locale} if isinstance(locale, str) else {}
        return await plugin_context.get_using_provider_async(
            umo=event.unified_msg_origin, **locale_kwargs
        )
    except ValueError as exc:
        logger.error("Error occurred while selecting provider: %s", exc)
        set_llm_error_message(event, "requestFailed", detail=str(exc))
        return None


async def resolve_compression_provider(
    config: MainAgentBuildConfig,
    plugin_context: Context,
    event: AstrMessageEvent | None = None,
) -> Provider | None:
    """Resolve the provider used for context compression.

    Args:
        config: Main agent build configuration.
        plugin_context: Plugin context used to resolve providers.
        event: Optional event used for session-specific fallback selection.

    Returns:
        Compression provider, or None if compression is disabled or unavailable.
    """
    if config.context_limit_reached_strategy != "llm_compress":
        return None
    if config.llm_compress_provider_id:
        provider = plugin_context.get_provider_by_id(config.llm_compress_provider_id)
        if provider and isinstance(provider, Provider):
            return provider
        logger.warning(
            "Configured compression provider %s is unavailable.",
            config.llm_compress_provider_id,
        )
    # fallback: use current chat provider for this session
    if event:
        try:
            return await plugin_context.get_using_provider_async(
                umo=event.unified_msg_origin
            )
        except ValueError:
            pass
    return None


def resolve_fallback_providers(
    provider: Provider, plugin_context: Context, fallback_ids: list[str]
) -> list[Provider]:
    """Resolve ordered fallback models, excluding unavailable and duplicate entries.

    Args:
        provider: Primary model, which must not appear again in the fallbacks.
        plugin_context: Provider registry.
        fallback_ids: Configured provider IDs in retry order.

    Returns:
        Available chat providers in their configured order.
    """
    if not isinstance(fallback_ids, list):
        logger.warning(
            "Agent Runner fallback_provider_ids is not a list, skip fallback providers."
        )
        return []

    provider_id = str(provider.provider_config.get("id", ""))
    seen_provider_ids: set[str] = {provider_id} if provider_id else set()
    fallbacks: list[Provider] = []

    for fallback_id in fallback_ids:
        if not isinstance(fallback_id, str) or not fallback_id:
            continue
        if fallback_id in seen_provider_ids:
            continue
        fallback_provider = plugin_context.get_provider_by_id(fallback_id)
        if fallback_provider is None:
            logger.warning("Fallback chat provider `%s` not found, skip.", fallback_id)
            continue
        if not isinstance(fallback_provider, Provider):
            logger.warning(
                "Fallback chat provider `%s` is invalid type: %s, skip.",
                fallback_id,
                type(fallback_provider),
            )
            continue
        fallbacks.append(fallback_provider)
        seen_provider_ids.add(fallback_id)
    return fallbacks


def select_image_provider(
    provider: Provider,
    req: ProviderRequest,
    fallback_providers: list[Provider],
) -> Provider:
    """Select a vision-capable fallback when prepared images remain in the request.

    Args:
        provider: Initial chat provider.
        req: Request after image captioning.
        fallback_providers: Available fallbacks in configured order.

    Returns:
        The initial provider or the first fallback supporting images.
    """
    if not req.image_urls or supports_modality(provider, "image"):
        return provider

    provider_id = provider.provider_config.get("id", "<unknown>")
    for fallback_provider in fallback_providers:
        if not supports_modality(fallback_provider, "image"):
            continue
        fallback_id = fallback_provider.provider_config.get("id", "<unknown>")
        logger.warning(
            "Chat provider %s does not support image input, switching this request to fallback provider %s.",
            provider_id,
            fallback_id,
        )
        return fallback_provider

    logger.warning(
        "Chat provider %s does not support image input and no image-capable fallback provider is available.",
        provider_id,
    )
    return provider
