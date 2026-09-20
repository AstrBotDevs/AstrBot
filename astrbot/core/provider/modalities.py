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
    if supports_image and supports_audio and supports_tool_use:
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

        if not supports_image or not supports_audio:
            content = msg.get("content")
            if isinstance(content, list):
                filtered_parts: list[Any] = []
                removed_any_multimodal = False
                for part in content:
                    if isinstance(part, dict):
                        part_type = str(part.get("type", "")).lower()
                        if not supports_image and part_type in {"image_url", "image"}:
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
