import base64
from collections.abc import Callable
from typing import Any

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain

from .deerflow_stream_utils import extract_text


def is_likely_base64_image(value: str) -> bool:
    if " " in value:
        return False

    compact = value.replace("\n", "").replace("\r", "")
    if not compact or len(compact) < 32 or len(compact) % 4 != 0:
        return False

    base64_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
    if any(ch not in base64_chars for ch in compact):
        return False
    try:
        base64.b64decode(compact, validate=True)
    except Exception:
        return False
    return True


def build_user_content(prompt: str, image_urls: list[str]) -> Any:
    if not image_urls:
        return prompt

    content: list[dict[str, Any]] = []
    skipped_invalid_images = 0
    if prompt:
        content.append({"type": "text", "text": prompt})

    for image_url in image_urls:
        url = image_url
        if not isinstance(url, str):
            continue
        url = url.strip()
        if not url:
            continue
        if url.startswith(("http://", "https://", "data:")):
            content.append({"type": "image_url", "image_url": {"url": url}})
            continue
        if not is_likely_base64_image(url):
            skipped_invalid_images += 1
            continue
        compact_base64 = url.replace("\n", "").replace("\r", "")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{compact_base64}"},
            },
        )

    if skipped_invalid_images:
        logger.debug(
            "Skipped %d DeerFlow image inputs that were neither URL/data URI nor valid base64.",
            skipped_invalid_images,
        )
    return content


def image_component_from_url(url: Any) -> Comp.Image | None:
    if not isinstance(url, str):
        return None

    normalized = url.strip()
    if not normalized:
        return None

    if normalized.startswith(("http://", "https://")):
        try:
            return Comp.Image.fromURL(normalized)
        except Exception:
            return None

    if not normalized.startswith("data:"):
        return None

    header, sep, payload = normalized.partition(",")
    if not sep:
        return None
    if ";base64" not in header.lower():
        return None

    compact_payload = payload.replace("\n", "").replace("\r", "").strip()
    if not compact_payload:
        return None
    try:
        base64.b64decode(compact_payload, validate=True)
    except Exception:
        return None
    return Comp.Image.fromBase64(compact_payload)


def append_components_from_content(
    content: Any,
    components: list[Comp.BaseMessageComponent],
    image_resolver: Callable[[Any], Comp.Image | None],
) -> None:
    if isinstance(content, str):
        if content:
            components.append(Comp.Plain(content))
        return

    if isinstance(content, list):
        for item in content:
            append_components_from_content(item, components, image_resolver)
        return

    if not isinstance(content, dict):
        return

    item_type = str(content.get("type", "")).lower()
    if item_type == "text" and isinstance(content.get("text"), str):
        text = content["text"]
        if text:
            components.append(Comp.Plain(text))
        return

    if item_type == "image_url":
        image_payload = content.get("image_url")
        image_url: Any = image_payload
        if isinstance(image_payload, dict):
            image_url = image_payload.get("url")
        image_comp = image_resolver(image_url)
        if image_comp is not None:
            components.append(image_comp)
        return

    if "content" in content:
        append_components_from_content(
            content.get("content"), components, image_resolver
        )
        return

    kwargs = content.get("kwargs")
    if isinstance(kwargs, dict) and "content" in kwargs:
        append_components_from_content(
            kwargs.get("content"), components, image_resolver
        )


def build_chain_from_ai_content(
    content: Any,
    image_resolver: Callable[[Any], Comp.Image | None],
) -> MessageChain:
    components: list[Comp.BaseMessageComponent] = []
    append_components_from_content(content, components, image_resolver)
    if components:
        return MessageChain(chain=components)

    fallback_text = extract_text(content)
    if fallback_text:
        return MessageChain(chain=[Comp.Plain(fallback_text)])
    return MessageChain()
