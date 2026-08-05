"""Shared, provider-neutral request and media preparation.

This is deliberately a pure-at-the-object-boundary step: callers receive a new
``ProviderRequest`` and their request object and lists remain unchanged.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from astrbot import logger
from astrbot.core.agent.history_sanitizer import sanitize_history_for_storage
from astrbot.core.agent.llm_types import ProviderContentBlock, ProviderRequest
from astrbot.core.agent.message import TextPart
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.media_utils import MediaResolver

if TYPE_CHECKING:
    from astrbot.core.agent.chat_model import ChatModel


_MAX_PREPARED_MEDIA_BYTES = 20 * 1024 * 1024


def clone_provider_request(request: ProviderRequest) -> ProviderRequest:
    """Copy mutable request fields before main-Agent assembly or preparation."""
    return replace(
        request,
        image_urls=list(request.image_urls),
        audio_urls=list(request.audio_urls),
        contexts=deepcopy(request.contexts),
        extra_user_content_parts=[
            part.model_copy(deep=True) for part in request.extra_user_content_parts
        ],
        prepared_content=tuple(request.prepared_content),
    )


def _safe_media_ref(ref: object) -> str | None:
    """Accept local/data references while rejecting untrusted network fetching."""
    if not isinstance(ref, str) or not ref.strip():
        return None
    value = ref.strip()
    try:
        scheme = urlsplit(value).scheme.lower()
    except ValueError:
        return None
    if scheme in {"http", "https"}:
        # MediaResolver intentionally supports HTTP for trusted internal callers,
        # but request preparation receives plugin/user-controlled references.
        # Do not turn it into a general outbound fetch surface.
        logger.warning("Drop remote provider media reference during preparation.")
        return None
    if scheme and scheme not in {"file", "data", "base64"}:
        logger.warning("Drop unsupported provider media reference scheme: %s", scheme)
        return None
    return value


def _provider_supports(provider: ChatModel | None, modality: str) -> bool:
    if provider is None:
        return True
    config = getattr(provider, "provider_config", {}) or {}
    modalities = config.get("modalities") if isinstance(config, dict) else None
    return not isinstance(modalities, list) or modality in modalities


async def _prepare_media(
    refs: list[str],
    *,
    media_type: str,
    provider: ChatModel | None,
    max_bytes: int,
) -> tuple[list[str], list[ProviderContentBlock], bool]:
    """Resolve allowed media to data URLs and report whether anything was dropped."""
    prepared_refs: list[str] = []
    blocks: list[ProviderContentBlock] = []
    dropped = False
    if not _provider_supports(provider, media_type):
        return prepared_refs, blocks, bool(refs)

    for ref in refs:
        safe_ref = _safe_media_ref(ref)
        if safe_ref is None:
            dropped = True
            continue
        try:
            resolved = await MediaResolver(
                safe_ref,
                media_type=media_type,
                default_suffix=".wav" if media_type == "audio" else ".bin",
            ).to_base64_data(
                strict=media_type == "audio",
                target_format="wav" if media_type == "audio" else None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Drop invalid %s provider media: %s",
                media_type,
                safe_error("", exc),
            )
            dropped = True
            continue
        if resolved is None:
            logger.warning("Drop unavailable %s provider media.", media_type)
            dropped = True
            continue
        if len(resolved.base64_data) * 3 // 4 > max_bytes:
            logger.warning("Drop invalid or oversized %s provider media.", media_type)
            dropped = True
            continue
        data_url = resolved.to_data_url()
        prepared_refs.append(data_url)
        blocks.append(
            ProviderContentBlock(
                type=media_type,
                value=data_url,
                mime_type=resolved.mime_type,
            )
        )
    return prepared_refs, blocks, dropped


async def prepare_provider_request(
    request: ProviderRequest,
    *,
    provider: ChatModel | None = None,
    max_media_bytes: int = _MAX_PREPARED_MEDIA_BYTES,
) -> ProviderRequest:
    """Return a sanitized, normalized copy suitable for a provider request.

    History is copied and sanitized, media is locally materialized with MIME and
    size checks, and unsupported or unsafe media is downgraded to a concise text
    marker. It does not invoke plugin hooks or add main-Agent-only policy,
    persona, knowledge-base, or tool capabilities.
    """
    prepared_request = clone_provider_request(request)
    contexts = prepared_request.contexts
    if isinstance(contexts, str):
        # Main-agent callers normally deserialize before this point. A string
        # supplied by SDK callers is not a safe structured history contract.
        contexts_copy: list[dict] = []
    elif isinstance(contexts, list):
        contexts_copy = sanitize_history_for_storage(deepcopy(contexts))
    else:
        contexts_copy = []

    extra_parts = prepared_request.extra_user_content_parts
    image_refs, image_blocks, image_dropped = await _prepare_media(
        prepared_request.image_urls,
        media_type="image",
        provider=provider,
        max_bytes=max_media_bytes,
    )
    audio_refs, audio_blocks, audio_dropped = await _prepare_media(
        prepared_request.audio_urls,
        media_type="audio",
        provider=provider,
        max_bytes=max_media_bytes,
    )
    if image_dropped:
        extra_parts.append(TextPart(text="[image omitted during provider preparation]"))
    if audio_dropped:
        extra_parts.append(TextPart(text="[audio omitted during provider preparation]"))

    blocks: list[ProviderContentBlock] = []
    if prepared_request.prompt and prepared_request.prompt.strip():
        blocks.append(ProviderContentBlock(type="text", value=prepared_request.prompt))
    blocks.extend(
        ProviderContentBlock(type="text", value=part.text)
        for part in extra_parts
        if isinstance(part, TextPart)
    )
    blocks.extend(image_blocks)
    blocks.extend(audio_blocks)

    return replace(
        prepared_request,
        image_urls=image_refs,
        audio_urls=audio_refs,
        contexts=contexts_copy,
        extra_user_content_parts=extra_parts,
        prepared_content=tuple(blocks),
    )
