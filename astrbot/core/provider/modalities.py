from __future__ import annotations

import copy
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from astrbot import logger
from astrbot.core.agent.message import Message


@dataclass(slots=True)
class ContextSanitizeStats:
    fixed_image_blocks: int = 0
    fixed_audio_blocks: int = 0
    fixed_tool_messages: int = 0
    removed_tool_calls: int = 0
    removed_empty_assistant_messages: int = 0
    fixed_invalid_media_blocks: int = 0

    @property
    def changed(self) -> bool:
        return bool(
            self.fixed_image_blocks
            or self.fixed_audio_blocks
            or self.fixed_tool_messages
            or self.removed_tool_calls
            or self.removed_empty_assistant_messages
            or self.fixed_invalid_media_blocks
        )


def _message_to_dict(message: dict[str, Any] | Message) -> dict[str, Any] | None:
    if isinstance(message, Message):
        return dict(message.model_dump())
    if isinstance(message, dict):
        return dict(copy.deepcopy(message))
    return None


def sanitize_contexts_by_modalities(
    contexts: Sequence[dict[str, Any] | Message],
    modalities: list[str] | None,
) -> tuple[list[dict[str, Any]], ContextSanitizeStats]:
    if not contexts:
        return [], ContextSanitizeStats()
    supports_image = (
        not modalities or not isinstance(modalities, list) or "image" in modalities
    )
    supports_audio = (
        not modalities or not isinstance(modalities, list) or "audio" in modalities
    )
    supports_tool_use = (
        not modalities or not isinstance(modalities, list) or "tool_use" in modalities
    )

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

        content = msg.get("content")
        if isinstance(content, list):
            filtered_parts: list[Any] = []
            changed_parts = False
            for part in content:
                if not isinstance(part, dict):
                    filtered_parts.append(part)
                    continue
                part_type = str(part.get("type", "")).lower()
                if part_type in {"image_url", "image"}:
                    image_value = part.get("image_url") or part.get("image")
                    image_url = (
                        image_value.get("url")
                        if isinstance(image_value, dict)
                        else image_value
                    )
                    valid_image = isinstance(image_url, str) and bool(image_url.strip())
                    if valid_image and image_url.startswith("data:"):
                        _, separator, encoded = image_url.partition(",")
                        valid_image = bool(separator and encoded.strip())
                    if not valid_image:
                        stats.fixed_invalid_media_blocks += 1
                        changed_parts = True
                        filtered_parts.append(
                            {"type": "text", "text": "[Image unavailable]"}
                        )
                        continue
                    if not supports_image:
                        stats.fixed_image_blocks += 1
                        changed_parts = True
                        filtered_parts.append({"type": "text", "text": "[Image]"})
                        continue
                if part_type in {"audio_url", "input_audio", "audio"}:
                    audio_value = (
                        part.get("audio_url")
                        or part.get("input_audio")
                        or part.get("audio")
                    )
                    audio_url = (
                        audio_value.get("url")
                        if isinstance(audio_value, dict)
                        else audio_value
                    )
                    valid_audio = isinstance(audio_url, str) and bool(audio_url.strip())
                    if valid_audio and audio_url.startswith("data:"):
                        _, separator, encoded = audio_url.partition(",")
                        valid_audio = bool(separator and encoded.strip())
                    if not valid_audio:
                        stats.fixed_invalid_media_blocks += 1
                        changed_parts = True
                        filtered_parts.append(
                            {"type": "text", "text": "[Audio unavailable]"}
                        )
                        continue
                    if not supports_audio:
                        stats.fixed_audio_blocks += 1
                        changed_parts = True
                        filtered_parts.append({"type": "text", "text": "[Audio]"})
                        continue
                filtered_parts.append(part)
            if changed_parts:
                msg["content"] = filtered_parts

        if role == "assistant":
            content = msg.get("content")
            has_tool_calls = bool(msg.get("tool_calls"))
            if not has_tool_calls:
                meaningful_content = bool(content)
                if isinstance(content, str):
                    meaningful_content = bool(content.strip())
                elif isinstance(content, list):
                    meaningful_content = any(
                        (
                            not isinstance(part, dict)
                            or (
                                part.get("type") == "text"
                                and str(part.get("text") or "").strip()
                            )
                            or part.get("type")
                            in {"image_url", "image", "audio_url", "input_audio"}
                        )
                        for part in content
                    )
                if not meaningful_content:
                    stats.removed_empty_assistant_messages += 1
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
        "fixed_tool_messages=%s, removed_tool_calls=%s, "
        "removed_empty_assistant_messages=%s, fixed_invalid_media_blocks=%s",
        stats.fixed_image_blocks,
        stats.fixed_audio_blocks,
        stats.fixed_tool_messages,
        stats.removed_tool_calls,
        stats.removed_empty_assistant_messages,
        stats.fixed_invalid_media_blocks,
    )
