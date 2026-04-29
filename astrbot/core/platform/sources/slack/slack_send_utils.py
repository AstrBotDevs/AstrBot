from collections.abc import Awaitable, Callable
from typing import Any, cast

from slack_sdk.web.async_client import AsyncWebClient

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import BaseMessageComponent, File, Image, Plain

from .session_codec import SLACK_SAFE_TEXT_FALLBACK, build_slack_text_fallbacks

ParseSlackBlocksFn = Callable[
    [MessageChain, AsyncWebClient, dict[str, str] | None],
    Awaitable[tuple[list[dict[str, Any]], str]],
]
BuildTextFallbackFn = Callable[[MessageChain, dict[str, str] | None], str]


async def from_segment_to_slack_block(
    segment: BaseMessageComponent,
    web_client: AsyncWebClient,
    fallbacks: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Convert a message segment into a Slack block."""
    # Use caller-provided, pre-normalized fallbacks when available to avoid
    # repeated normalization per segment.
    resolved_fallbacks = (
        build_slack_text_fallbacks(None) if fallbacks is None else fallbacks
    )
    if isinstance(segment, Plain):
        return {"type": "section", "text": {"type": "mrkdwn", "text": segment.text}}
    if isinstance(segment, Image):
        url = segment.url or segment.file
        if url and url.startswith("http"):
            return {
                "type": "image",
                "image_url": url,
                "alt_text": "图片",
            }
        path = await segment.convert_to_file_path()
        response = await web_client.files_upload_v2(
            file=path,
            filename="image.jpg",
        )
        if not response["ok"]:
            logger.error(f"Slack file upload failed: {response['error']}")
            return {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": resolved_fallbacks["image_upload_failed"],
                },
            }
        image_url = cast(list, response["files"])[0]["url_private"]
        logger.debug(f"Slack file upload response: {response}")
        return {
            "type": "image",
            "slack_file": {
                "url": image_url,
            },
            "alt_text": "图片",
        }
    if isinstance(segment, File):
        url = segment.url or segment.file
        response = await web_client.files_upload_v2(
            file=url,
            filename=segment.name or "file",
        )
        if not response["ok"]:
            logger.error(f"Slack file upload failed: {response['error']}")
            return {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": resolved_fallbacks["file_upload_failed"],
                },
            }
        file_url = cast(list, response["files"])[0]["permalink"]
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"file: <{file_url}|{segment.name or 'file'}>",
            },
        }

    return None


async def parse_slack_blocks(
    message_chain: MessageChain,
    web_client: AsyncWebClient,
    fallbacks: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Parse a message chain into Slack blocks and fallback text."""
    resolved_fallbacks = (
        build_slack_text_fallbacks(None) if fallbacks is None else fallbacks
    )
    blocks: list[dict[str, Any]] = []
    text_content = ""
    fallback_parts = []

    for segment in message_chain.chain:
        if isinstance(segment, Plain):
            text_content += segment.text
            fallback_parts.append(segment.text)
            continue

        if text_content.strip():
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": text_content},
                },
            )
            text_content = ""

        block = await from_segment_to_slack_block(
            segment,
            web_client,
            fallbacks=resolved_fallbacks,
        )
        if not block:
            continue

        blocks.append(block)
        if isinstance(segment, Image):
            fallback_parts.append(resolved_fallbacks["image"])
        elif isinstance(segment, File):
            fallback_parts.append(
                resolved_fallbacks["file_template"].format(
                    name=segment.name or "file",
                ),
            )
        else:
            fallback_parts.append(resolved_fallbacks["generic"])

    if text_content.strip():
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": text_content}},
        )

    fallback_text = "".join(fallback_parts).strip() or resolved_fallbacks["safe_text"]
    return blocks, fallback_text


def build_text_fallback_from_chain(
    message_chain: MessageChain,
    fallbacks: dict[str, str] | None = None,
) -> str:
    """Build safe text fallback when block payload is rejected."""
    resolved_fallbacks = (
        build_slack_text_fallbacks(None) if fallbacks is None else fallbacks
    )
    parts = []
    for segment in message_chain.chain:
        if isinstance(segment, Plain):
            parts.append(segment.text)
        elif isinstance(segment, File):
            parts.append(
                resolved_fallbacks["file_template"].format(
                    name=segment.name or "file",
                ),
            )
        elif isinstance(segment, Image):
            parts.append(resolved_fallbacks["image"])
        else:
            parts.append(resolved_fallbacks["generic"])
    return "".join(parts).strip() or resolved_fallbacks["safe_text"]


async def send_with_blocks_and_fallback(
    *,
    web_client: AsyncWebClient,
    channel: str,
    thread_ts: str | None,
    message_chain: MessageChain,
    fallbacks: dict[str, str] | None = None,
    parse_blocks: ParseSlackBlocksFn = parse_slack_blocks,
    build_text_fallback: BuildTextFallbackFn = build_text_fallback_from_chain,
    session_id: str = "",
) -> None:
    """Send Slack message with blocks first, then fallback to text-only on failure."""
    resolved_fallbacks = (
        build_slack_text_fallbacks(None) if fallbacks is None else fallbacks
    )
    if not channel:
        logger.warning(
            "Skip Slack send because channel_id is empty. session_id=%s thread_ts=%s",
            session_id,
            thread_ts or "",
        )
        return
    blocks, text = await parse_blocks(
        message_chain,
        web_client,
        resolved_fallbacks,
    )
    safe_text = text or resolved_fallbacks.get("safe_text", SLACK_SAFE_TEXT_FALLBACK)

    message_payload: dict[str, Any] = {
        "channel": channel,
        "text": safe_text,
        "blocks": blocks or None,
    }
    if thread_ts:
        message_payload["thread_ts"] = thread_ts

    try:
        await web_client.chat_postMessage(**message_payload)
        return
    except Exception:
        logger.exception(
            "Slack send failed, retrying with text-only payload. "
            "session_id=%s channel_id=%s thread_ts=%s",
            session_id,
            channel,
            thread_ts or "",
        )

    fallback_text = build_text_fallback(message_chain, resolved_fallbacks)
    fallback_text = (fallback_text or "").strip() or resolved_fallbacks.get(
        "safe_text", SLACK_SAFE_TEXT_FALLBACK
    )
    fallback_payload: dict[str, Any] = {
        "channel": channel,
        "text": fallback_text,
    }
    if thread_ts:
        fallback_payload["thread_ts"] = thread_ts

    try:
        await web_client.chat_postMessage(**fallback_payload)
    except Exception:
        logger.exception(
            "Slack send text-only fallback failed. "
            "session_id=%s channel_id=%s thread_ts=%s",
            session_id,
            channel,
            thread_ts or "",
        )
