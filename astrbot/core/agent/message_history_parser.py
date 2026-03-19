from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from astrbot.core.agent.message import Message


class MessageHistoryParser:
    def parse(self, history: Iterable[Any]) -> list[Message]:
        parsed: list[Message] = []
        for item in history:
            if not isinstance(item, dict):
                continue

            try:
                parsed.append(Message.model_validate(item))
                continue
            except Exception:
                pass

            fallback = self.sanitize_message_dict(item)
            if not fallback:
                continue
            try:
                parsed.append(Message.model_validate(fallback))
            except Exception:
                continue

        return parsed

    def sanitize_message_dict(self, item: dict[str, Any]) -> dict[str, Any] | None:
        role = str(item.get("role", "")).strip().lower()
        if role not in {"system", "user", "assistant", "tool"}:
            return None

        result: dict[str, Any] = {"role": role}

        if role == "assistant" and isinstance(item.get("tool_calls"), list):
            result["tool_calls"] = item["tool_calls"]

        if role == "tool" and item.get("tool_call_id"):
            result["tool_call_id"] = str(item.get("tool_call_id"))

        content = item.get("content")
        if content is None and role == "assistant" and result.get("tool_calls"):
            result["content"] = None
            return result

        result["content"] = self.sanitize_content(content, role)

        if result["content"] is None and not (
            role == "assistant" and result.get("tool_calls")
        ):
            return None

        return result

    def sanitize_content(self, content: Any, role: str) -> str | list[dict] | None:
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            return self.sanitize_list_content(content)

        if content is None:
            if role == "assistant":
                return None
            return ""

        dumped = self.safe_json(content)
        return dumped if dumped is not None else str(content)

    def sanitize_list_content(self, content: list[Any]) -> str | list[dict]:
        parts: list[dict[str, Any]] = []
        fallback_texts: list[str] = []

        for part in content:
            if isinstance(part, str):
                if part.strip():
                    fallback_texts.append(part)
                continue
            if not isinstance(part, dict):
                txt = self.safe_json(part)
                if txt:
                    fallback_texts.append(txt)
                continue
            self.sanitize_content_part(part, parts, fallback_texts)

        if fallback_texts:
            parts.insert(0, {"type": "text", "text": "\n".join(fallback_texts)})

        if parts:
            return parts
        return ""

    def sanitize_content_part(
        self,
        part: dict[str, Any],
        parts: list[dict[str, Any]],
        fallback_texts: list[str],
    ) -> None:
        part_type = str(part.get("type", "")).strip()
        if part_type == "text":
            text_val = part.get("text")
            if text_val is not None:
                parts.append({"type": "text", "text": str(text_val)})
            return

        if part_type == "image_url":
            image_obj = part.get("image_url")
            if isinstance(image_obj, dict) and image_obj.get("url"):
                image_part: dict[str, Any] = {
                    "type": "image_url",
                    "image_url": {"url": str(image_obj.get("url"))},
                }
                if image_obj.get("id"):
                    image_part["image_url"]["id"] = str(image_obj.get("id"))
                parts.append(image_part)
            return

        if part_type == "audio_url":
            audio_obj = part.get("audio_url")
            if isinstance(audio_obj, dict) and audio_obj.get("url"):
                audio_part: dict[str, Any] = {
                    "type": "audio_url",
                    "audio_url": {"url": str(audio_obj.get("url"))},
                }
                if audio_obj.get("id"):
                    audio_part["audio_url"]["id"] = str(audio_obj.get("id"))
                parts.append(audio_part)
            return

        if part_type == "think":
            think = part.get("think")
            if think:
                fallback_texts.append(str(think))
            return

        raw_text = part.get("text") or part.get("content")
        if raw_text:
            fallback_texts.append(str(raw_text))
        else:
            dumped = self.safe_json(part)
            if dumped:
                fallback_texts.append(dumped)

    @staticmethod
    def safe_json(value: Any) -> str | None:
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            return None
