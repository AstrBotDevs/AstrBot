from __future__ import annotations

from astrbot import logger
from astrbot.core.message.components import Reply
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings

from .chain_parser import OneBotPayloadParser, ReplyChainParser
from .image_resolver import ImageResolver
from .onebot_client import OneBotClient
from .settings import SETTINGS


async def _collect_text_and_images_from_forward_ids(
    onebot_client: OneBotClient,
    forward_ids: list[str],
    *,
    max_fetch: int = SETTINGS.max_forward_fetch,
) -> tuple[list[str], list[str]]:
    texts: list[str] = []
    image_refs: list[str] = []
    pending: list[str] = []
    seen: set[str] = set()

    for fid in forward_ids:
        if not isinstance(fid, str):
            continue
        cleaned = fid.strip()
        if cleaned:
            pending.append(cleaned)

    fetch_count = 0
    while pending and fetch_count < max_fetch:
        current_id = pending.pop(0)
        if current_id in seen:
            continue
        seen.add(current_id)
        fetch_count += 1

        forward_payload = await onebot_client.get_forward_msg(current_id)
        if not forward_payload:
            continue

        parsed = OneBotPayloadParser.parse_get_forward_payload(forward_payload)
        if parsed["text"]:
            texts.append(parsed["text"])
        if parsed["image_refs"]:
            image_refs.extend(parsed["image_refs"])
        for nested_id in parsed["forward_ids"]:
            if nested_id not in seen:
                pending.append(nested_id)

    if pending:
        logger.warning(
            "quoted_message_parser: stop fetching nested forward messages after %d hops",
            max_fetch,
        )

    return texts, normalize_and_dedupe_strings(image_refs)


class QuotedMessageExtractor:
    def __init__(self, event: AstrMessageEvent):
        self._event = event
        self._client = OneBotClient(event)
        self._image_resolver = ImageResolver(event, self._client)

    async def text(self, reply_component: Reply | None = None) -> str | None:
        reply = reply_component or ReplyChainParser.find_first_reply_component(
            self._event
        )
        if not reply:
            return None

        embedded_text = ReplyChainParser.extract_text_from_reply_component(reply)
        if embedded_text and not ReplyChainParser.is_forward_placeholder_only_text(
            embedded_text
        ):
            return embedded_text

        reply_id = getattr(reply, "id", None)
        if reply_id is None:
            return embedded_text
        reply_id_str = str(reply_id).strip()
        if not reply_id_str:
            return embedded_text

        msg_payload = await self._client.get_msg(reply_id_str)
        if not msg_payload:
            return embedded_text

        parsed = OneBotPayloadParser.parse_get_msg_payload(msg_payload)
        text_parts: list[str] = []
        direct_text = parsed["text"]
        if direct_text:
            text_parts.append(direct_text)

        (
            forward_texts,
            _forward_images,
        ) = await _collect_text_and_images_from_forward_ids(
            self._client,
            parsed["forward_ids"],
        )
        text_parts.extend(forward_texts)

        return "\n".join(text_parts).strip() or embedded_text

    async def images(self, reply_component: Reply | None = None) -> list[str]:
        reply = reply_component or ReplyChainParser.find_first_reply_component(
            self._event
        )
        if not reply:
            return []

        image_refs = list(
            ReplyChainParser.extract_image_refs_from_reply_component(reply)
        )

        reply_id = getattr(reply, "id", None)
        if reply_id is None:
            return await self._image_resolver.resolve_for_llm(image_refs)
        reply_id_str = str(reply_id).strip()
        if not reply_id_str:
            return await self._image_resolver.resolve_for_llm(image_refs)

        msg_payload = await self._client.get_msg(reply_id_str)
        if not msg_payload:
            return await self._image_resolver.resolve_for_llm(image_refs)

        parsed = OneBotPayloadParser.parse_get_msg_payload(msg_payload)
        image_refs.extend(parsed["image_refs"])

        (
            _forward_texts,
            forward_images,
        ) = await _collect_text_and_images_from_forward_ids(
            self._client,
            parsed["forward_ids"],
        )
        image_refs.extend(forward_images)

        return await self._image_resolver.resolve_for_llm(image_refs)


async def extract_quoted_message_text(
    event: AstrMessageEvent,
    reply_component: Reply | None = None,
) -> str | None:
    return await QuotedMessageExtractor(event).text(reply_component)


async def extract_quoted_message_images(
    event: AstrMessageEvent,
    reply_component: Reply | None = None,
) -> list[str]:
    return await QuotedMessageExtractor(event).images(reply_component)
