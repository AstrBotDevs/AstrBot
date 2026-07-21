from __future__ import annotations

import copy
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from astrbot import logger
from astrbot.core.agent.message import Message


@dataclass(slots=True)
class ContextSanitizeStats:
    fixed_image_blocks: int = 0
    fixed_audio_blocks: int = 0
    fixed_tool_messages: int = 0
    removed_tool_calls: int = 0

    @property
    def changed(self) -> bool:
        return bool(
            self.fixed_image_blocks
            or self.fixed_audio_blocks
            or self.fixed_tool_messages
            or self.removed_tool_calls
        )


def _message_to_dict(message: dict[str, Any] | Message) -> dict[str, Any] | None:
    if isinstance(message, Message):
        return dict(message.model_dump())
    if isinstance(message, dict):
        return dict(copy.deepcopy(message))
    return None


# Image MIME types that some OpenAI-compatible gateways reject even when the
# model claims image support. Animated GIFs in particular are accepted by raw
# Gemini (which wants image/heif/video/mp4 for animations) but rejected by
# several Gemini-flavored OpenAI proxies with "mime type is not supported".
# Keeping this list narrow avoids over-stripping providers that do accept GIF
# (e.g. Anthropic Claude). See issue #9295.
_UNSUPPORTED_IMAGE_MIMES = frozenset({"image/gif"})

# Lazily-built extension → MIME mapping used only for http(s) URL fallback.
_IMAGE_EXT_TO_MIME: dict[str, str] = {
    ".gif": "image/gif",
}


def _extract_image_mime(part: dict[str, Any]) -> str | None:
    """Best-effort extraction of an image MIME type from a multimodal part.

    Handles the OpenAI-style ``{"image_url": {"url": ...}}`` and the Anthropic /
    Gemini-style ``{"source": {"media_type": ...}}`` / ``{"mimeType": ...}``
    layouts, as well as a bare ``{"url": ...}`` or ``{"image_url": "<url>"}``.

    Returns:
        The normalized MIME type (e.g. ``image/gif``) if it can be determined,
        otherwise ``None``.
    """
    image_url = part.get("image_url")
    if isinstance(image_url, dict):
        url = image_url.get("url")
    else:
        url = image_url
    if not isinstance(url, str):
        url = part.get("url") if isinstance(part.get("url"), str) else None

    if isinstance(url, str):
        url = url.strip()
        # data URLs look like "data:image/gif;base64,...."
        if url.lower().startswith("data:"):
            head = url[5:].split(",", 1)[0]
            # head is e.g. "image/gif;base64"
            mime = head.split(";", 1)[0].strip().lower()
            if mime:
                return mime
        else:
            # Fall back to the URL path extension for http(s) URLs. urlsplit
            # robustly separates the path from query/fragment even when those
            # delimiters appear percent-encoded inside the path itself.
            path = urlsplit(url).path.lower()
            for ext, mime in _IMAGE_EXT_TO_MIME.items():
                if path.endswith(ext):
                    return mime

    source = part.get("source")
    if isinstance(source, dict):
        media_type = source.get("media_type")
        if isinstance(media_type, str):
            # Normalize by stripping parameters (e.g. "image/gif; charset=binary"
            # -> "image/gif") so it matches _UNSUPPORTED_IMAGE_MIMES.
            return media_type.split(";", 1)[0].strip().lower()

    mime_type = part.get("mimeType") or part.get("mime_type")
    if isinstance(mime_type, str):
        # Strip parameters (e.g. "image/gif;codec=xyz" -> "image/gif") to align
        # with the data-URL and source.media_type handling above.
        return mime_type.split(";", 1)[0].strip().lower()

    return None


def _is_unsupported_image_mime(mime: str | None) -> bool:
    """Return True when the MIME is known to be rejected by some providers."""
    return bool(mime) and mime in _UNSUPPORTED_IMAGE_MIMES


def sanitize_contexts_by_modalities(
    contexts: Sequence[dict[str, Any] | Message],
    modalities: list[str] | None,
) -> tuple[list[dict[str, Any]], ContextSanitizeStats]:
    if not contexts:
        return [], ContextSanitizeStats()
    if not modalities or not isinstance(modalities, list):
        copied_contexts = []
        for msg in contexts:
            copied_msg = _message_to_dict(msg)
            if copied_msg:
                copied_contexts.append(copied_msg)
        return copied_contexts, ContextSanitizeStats()

    supports_image = "image" in modalities
    supports_audio = "audio" in modalities
    supports_tool_use = "tool_use" in modalities
    # Even when the provider declares all modalities, we may still need to walk
    # the contexts to drop specific image MIME types (e.g. image/gif) that some
    # OpenAI-compatible gateways reject. See issue #9295.
    needs_mime_pass = supports_image and bool(_UNSUPPORTED_IMAGE_MIMES)
    if supports_image and supports_audio and supports_tool_use and not needs_mime_pass:
        copied_contexts = []
        for msg in contexts:
            copied_msg = _message_to_dict(msg)
            if copied_msg:
                copied_contexts.append(copied_msg)
        return copied_contexts, ContextSanitizeStats()

    sanitized_contexts: list[dict[str, Any]] = []
    stats = ContextSanitizeStats()

    for raw_msg in contexts:
        msg = _message_to_dict(raw_msg)
        if not msg:
            continue
        role = msg.get("role")
        if not role:
            continue

        if not supports_tool_use:
            if role == "tool":
                stats.fixed_tool_messages += 1
                fixed_msg: dict[str, Any] = {
                    "role": "user",
                    "content": _tool_result_placeholder(msg.get("content")),
                }
                msg = fixed_msg
            if role == "assistant" and "tool_calls" in msg:
                stats.removed_tool_calls += 1
                msg.pop("tool_calls", None)
                msg.pop("tool_call_id", None)

        if not supports_image or not supports_audio or needs_mime_pass:
            content = msg.get("content")
            if isinstance(content, list):
                filtered_parts: list[Any] = []
                removed_any_multimodal = False
                for part in content:
                    if isinstance(part, dict):
                        part_type = str(part.get("type", "")).lower()
                        if part_type in {"image_url", "image"} and (
                            not supports_image
                            or _is_unsupported_image_mime(_extract_image_mime(part))
                        ):
                            # Either the model has no image modality at all, or it
                            # declares image support but the specific MIME (e.g.
                            # image/gif) is rejected by some OpenAI-compatible
                            # gateways (notably certain Gemini endpoints that only
                            # accept JPEG/PNG/WebP). Replacing the block with a
                            # placeholder prevents the unsupported bytes from being
                            # persisted into the session history and poisoning all
                            # subsequent requests. See issue #9295.
                            removed_any_multimodal = True
                            stats.fixed_image_blocks += 1
                            filtered_parts.append({"type": "text", "text": "[Image]"})
                            continue
                        if not supports_audio and part_type in {
                            "audio_url",
                            "input_audio",
                        }:
                            removed_any_multimodal = True
                            stats.fixed_audio_blocks += 1
                            filtered_parts.append({"type": "text", "text": "[Audio]"})
                            continue
                    filtered_parts.append(part)
                if removed_any_multimodal:
                    msg["content"] = filtered_parts

        if role == "assistant":
            content = msg.get("content")
            has_tool_calls = bool(msg.get("tool_calls"))
            if not has_tool_calls:
                if not content:
                    continue
                if isinstance(content, str) and not content.strip():
                    continue

        sanitized_contexts.append(msg)

    return sanitized_contexts, stats


def _tool_result_placeholder(content: Any) -> str:
    if isinstance(content, str):
        content_text = content.strip()
    elif isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                part_type = str(part.get("type", "")).lower()
                if part_type == "text":
                    text_parts.append(str(part.get("text", "")))
                elif part_type in {"image_url", "image"}:
                    text_parts.append("[Image]")
                elif part_type in {"audio_url", "input_audio"}:
                    text_parts.append("[Audio]")
        content_text = "\n".join(part for part in text_parts if part).strip()
    else:
        content_text = ""
    if not content_text:
        return "[Tool result]"
    return f"[Tool result]\n{content_text}"


def log_context_sanitize_stats(stats: ContextSanitizeStats) -> None:
    if not stats.changed:
        return
    logger.debug(
        "context modality fix applied: "
        "fixed_image_blocks=%s, fixed_audio_blocks=%s, "
        "fixed_tool_messages=%s, removed_tool_calls=%s",
        stats.fixed_image_blocks,
        stats.fixed_audio_blocks,
        stats.fixed_tool_messages,
        stats.removed_tool_calls,
    )
