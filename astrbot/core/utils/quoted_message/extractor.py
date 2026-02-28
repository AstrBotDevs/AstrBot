from __future__ import annotations
from astrbot.core.lang import t

from dataclasses import dataclass

from astrbot import logger
from astrbot.core.message.components import Reply
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings

from .chain_parser import OneBotPayloadParser, ReplyChainParser
from .image_resolver import ImageResolver
from .onebot_client import OneBotClient
from .settings import SETTINGS, QuotedMessageParserSettings


async def _collect_text_and_images_from_forward_ids(
    onebot_client: OneBotClient,
    payload_parser: OneBotPayloadParser,
    forward_ids: list[str],
    *,
    max_fetch: int,
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

        parsed = payload_parser.parse_get_forward_payload(forward_payload)
        if parsed["text"]:
            texts.append(parsed["text"])
        if parsed["image_refs"]:
            image_refs.extend(parsed["image_refs"])
        for nested_id in parsed["forward_ids"]:
            if nested_id not in seen:
                pending.append(nested_id)

    if pending:
        logger.warning(
            t("msg-80530653", max_fetch=max_fetch),
        )

    return texts, normalize_and_dedupe_strings(image_refs)


@dataclass(slots=True)
class QuotedMessageContent:
    embedded_text: str | None
    embedded_image_refs: list[str]
    reply_id: str
    direct_text: str | None
    direct_image_refs: list[str]
    forward_texts: list[str]
    forward_image_refs: list[str]


class QuotedMessageExtractor:
    def __init__(
        self,
        event: AstrMessageEvent,
        settings: QuotedMessageParserSettings = SETTINGS,
    ):
        self._event = event
        self._settings = settings
        self._reply_parser = ReplyChainParser(settings=settings)
        self._payload_parser = OneBotPayloadParser(settings=settings)
        self._client = OneBotClient(event, settings=settings)
        self._image_resolver = ImageResolver(event, self._client)

    async def _fetch_quoted_content(
        self,
        reply_component: Reply | None = None,
        *,
        fetch_remote: bool,
    ) -> QuotedMessageContent | None:
        reply = reply_component or self._reply_parser.find_first_reply_component(
            self._event
        )
        if not reply:
            return None

        embedded_text = self._reply_parser.extract_text_from_reply_component(reply)
        embedded_image_refs = list(
            self._reply_parser.extract_image_refs_from_reply_component(reply)
        )

        reply_id = getattr(reply, "id", None)
        reply_id_str = str(reply_id).strip() if reply_id is not None else ""
        if not fetch_remote or not reply_id_str:
            return QuotedMessageContent(
                embedded_text=embedded_text,
                embedded_image_refs=embedded_image_refs,
                reply_id=reply_id_str,
                direct_text=None,
                direct_image_refs=[],
                forward_texts=[],
                forward_image_refs=[],
            )

        msg_payload = await self._client.get_msg(reply_id_str)
        if not msg_payload:
            return QuotedMessageContent(
                embedded_text=embedded_text,
                embedded_image_refs=embedded_image_refs,
                reply_id=reply_id_str,
                direct_text=None,
                direct_image_refs=[],
                forward_texts=[],
                forward_image_refs=[],
            )

        parsed = self._payload_parser.parse_get_msg_payload(msg_payload)
        forward_texts, forward_images = await _collect_text_and_images_from_forward_ids(
            self._client,
            self._payload_parser,
            parsed["forward_ids"],
            max_fetch=self._settings.max_forward_fetch,
        )
        return QuotedMessageContent(
            embedded_text=embedded_text,
            embedded_image_refs=embedded_image_refs,
            reply_id=reply_id_str,
            direct_text=parsed["text"],
            direct_image_refs=list(parsed["image_refs"]),
            forward_texts=forward_texts,
            forward_image_refs=forward_images,
        )

    async def text(self, reply_component: Reply | None = None) -> str | None:
        embedded_content = await self._fetch_quoted_content(
            reply_component,
            fetch_remote=False,
        )
        if not embedded_content:
            return None

        if (
            embedded_content.embedded_text
            and not self._reply_parser.is_forward_placeholder_only_text(
                embedded_content.embedded_text
            )
        ):
            return embedded_content.embedded_text

        if not embedded_content.reply_id:
            return embedded_content.embedded_text

        fetched_content = await self._fetch_quoted_content(
            reply_component,
            fetch_remote=True,
        )
        if not fetched_content:
            return embedded_content.embedded_text

        text_parts: list[str] = []
        if fetched_content.direct_text:
            text_parts.append(fetched_content.direct_text)
        text_parts.extend(fetched_content.forward_texts)

        return "\n".join(text_parts).strip() or embedded_content.embedded_text

    async def images(self, reply_component: Reply | None = None) -> list[str]:
        content = await self._fetch_quoted_content(reply_component, fetch_remote=True)
        if not content:
            return []

        image_refs: list[str] = []
        image_refs.extend(content.embedded_image_refs)
        image_refs.extend(content.direct_image_refs)
        image_refs.extend(content.forward_image_refs)

        return await self._image_resolver.resolve_for_llm(image_refs)


async def extract_quoted_message_text(
    event: AstrMessageEvent,
    reply_component: Reply | None = None,
    settings: QuotedMessageParserSettings | None = None,
) -> str | None:
    return await QuotedMessageExtractor(event, settings=settings or SETTINGS).text(
        reply_component
    )


async def extract_quoted_message_images(
    event: AstrMessageEvent,
    reply_component: Reply | None = None,
    settings: QuotedMessageParserSettings | None = None,
) -> list[str]:
    return await QuotedMessageExtractor(event, settings=settings or SETTINGS).images(
        reply_component
    )
