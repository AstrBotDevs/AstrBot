import asyncio
import os
import re
from collections.abc import Callable
from contextlib import ExitStack
from typing import Any, cast
from urllib.parse import urlsplit

import telegramify_markdown
from telegram import (
    InputFile,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    ReactionTypeCustomEmoji,
    ReactionTypeEmoji,
)
from telegram.constants import ChatAction, MessageLimit
from telegram.error import BadRequest
from telegram.ext import ExtBot

from astrbot import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import (
    At,
    BaseMessageComponent,
    File,
    Image,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.api.platform import AstrBotMessage, MessageType, PlatformMetadata
from astrbot.core.utils.metrics import Metric

from .components import (
    TelegramForceReply,
    TelegramInlineKeyboard,
    TelegramInlineQueryResult,
    TelegramInlineQueryResultsButton,
    TelegramMediaGroup,
    TelegramMediaGroupItem,
    TelegramMessageOptions,
    TelegramRemoveKeyboard,
    TelegramReplyKeyboard,
)

TelegramReplyMarkup = (
    TelegramInlineKeyboard
    | TelegramReplyKeyboard
    | TelegramRemoveKeyboard
    | TelegramForceReply
)
TelegramAlbumInputMedia = (
    InputMediaPhoto | InputMediaVideo | InputMediaDocument | InputMediaAudio
)
TelegramMediaComponent = Image | Video | File

MEDIA_GROUP_LIMIT = 10
MEDIA_GROUP_MIN_ITEMS = 2


def _is_gif(path: str) -> bool:
    if path.lower().endswith(".gif"):
        return True
    try:
        with open(path, "rb") as f:
            return f.read(6) in (b"GIF87a", b"GIF89a")
    except OSError:
        return False


def _is_http_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def _is_gif_url(value: str) -> bool:
    return urlsplit(value).path.lower().endswith(".gif")


def _is_webpage_curl_failed_error(error: Exception) -> bool:
    return "webpage_curl_failed" in str(error).lower()


class TelegramPlatformEvent(AstrMessageEvent):
    # Telegram 的最大消息长度限制
    MAX_MESSAGE_LENGTH = 4096

    SPLIT_PATTERNS = {
        "paragraph": re.compile(r"\n\n"),
        "line": re.compile(r"\n"),
        "sentence": re.compile(r"[.!?。！？]"),
        "word": re.compile(r"\s"),
    }

    # sendMessageDraft 的 draft_id 类级递增计数器
    _TELEGRAM_DRAFT_ID_MAX = 2_147_483_647
    _next_draft_id: int = 0

    @classmethod
    def _allocate_draft_id(cls) -> int:
        """分配一个递增的 draft_id，溢出时归 1。"""
        cls._next_draft_id = (
            1
            if cls._next_draft_id >= cls._TELEGRAM_DRAFT_ID_MAX
            else cls._next_draft_id + 1
        )
        return cls._next_draft_id

    # 消息类型到 chat action 的映射，用于优先级判断
    ACTION_BY_TYPE: dict[type, str] = {
        Record: ChatAction.UPLOAD_VOICE,
        Video: ChatAction.UPLOAD_VIDEO,
        File: ChatAction.UPLOAD_DOCUMENT,
        Image: ChatAction.UPLOAD_PHOTO,
        Plain: ChatAction.TYPING,
    }

    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        client: ExtBot,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client

    @staticmethod
    def _extract_send_options(
        message: MessageChain,
    ) -> tuple[
        list[BaseMessageComponent],
        TelegramMessageOptions,
        TelegramReplyMarkup | None,
    ]:
        chain: list[BaseMessageComponent] = []
        options = TelegramMessageOptions()
        reply_markup = None

        for item in message.chain:
            if isinstance(item, TelegramMessageOptions):
                options = item
            elif isinstance(
                item,
                (
                    TelegramInlineKeyboard,
                    TelegramReplyKeyboard,
                    TelegramRemoveKeyboard,
                    TelegramForceReply,
                ),
            ):
                reply_markup = item
            else:
                chain.append(item)

        return chain, options, reply_markup

    @staticmethod
    def _normalize_parse_mode(parse_mode: str | None) -> str | None:
        if parse_mode is None:
            return None
        normalized = parse_mode.strip()
        if not normalized or normalized.lower() in {"plain", "plaintext", "none"}:
            return None
        if normalized not in {"MarkdownV2", "Markdown", "HTML"}:
            raise ValueError(
                "Telegram parse_mode must be one of MarkdownV2, Markdown, HTML, or plaintext.",
            )
        return normalized

    @staticmethod
    def _is_plaintext_parse_mode(parse_mode: str | None) -> bool:
        if parse_mode is None:
            return False
        return parse_mode.strip().lower() in {"plain", "plaintext", "none"}

    @classmethod
    def _build_text_payload(
        cls,
        payload: dict[str, Any],
        options: TelegramMessageOptions,
        reply_markup: TelegramReplyMarkup | None,
    ) -> dict[str, Any]:
        send_payload = dict(payload)
        link_preview_options = options.to_link_preview_options()
        if link_preview_options is not None:
            send_payload["link_preview_options"] = link_preview_options
        if reply_markup is not None:
            send_payload["reply_markup"] = reply_markup.to_telegram_markup()
        return send_payload

    @staticmethod
    def _split_telegram_chat_reference(chat_id: str) -> tuple[str, int | None]:
        if "#" not in chat_id:
            return chat_id, None
        raw_chat_id, raw_thread_id = chat_id.split("#", 1)
        if not raw_thread_id:
            return raw_chat_id, None
        return raw_chat_id, int(raw_thread_id)

    def _current_chat_reference(self) -> tuple[str, int | None]:
        if self.get_message_type() == MessageType.GROUP_MESSAGE:
            chat_id = self.message_obj.group_id
        else:
            chat_id = self.get_sender_id()
        if not chat_id:
            raise RuntimeError("Telegram event has no target chat_id.")
        return self._split_telegram_chat_reference(chat_id)

    def _current_message_id(self) -> int:
        message_id = getattr(self.message_obj, "message_id", None)
        if message_id in (None, ""):
            raise RuntimeError("Telegram event has no message_id.")
        return int(message_id)

    @staticmethod
    def _convert_reply_markup(reply_markup: Any) -> Any:
        if hasattr(reply_markup, "to_telegram_markup"):
            return reply_markup.to_telegram_markup()
        return reply_markup

    @staticmethod
    def _convert_inline_query_result(result: Any) -> Any:
        if isinstance(result, TelegramInlineQueryResult):
            return result.to_telegram_result()
        if hasattr(result, "to_telegram_result"):
            return result.to_telegram_result()
        return result

    @staticmethod
    def _is_markdown_parse_error(error: BadRequest) -> bool:
        message = getattr(error, "message", str(error)).lower()
        return any(
            fragment in message
            for fragment in (
                "can't parse entities",
                "can't parse entity",
                "parse entities",
                "entity",
                "markdown",
            )
        )

    @classmethod
    def _split_message(cls, text: str) -> list[str]:
        if len(text) <= cls.MAX_MESSAGE_LENGTH:
            return [text]

        chunks = []
        while text:
            if len(text) <= cls.MAX_MESSAGE_LENGTH:
                chunks.append(text)
                break

            split_point = cls.MAX_MESSAGE_LENGTH
            segment = text[: cls.MAX_MESSAGE_LENGTH]

            for _, pattern in cls.SPLIT_PATTERNS.items():
                if matches := list(pattern.finditer(segment)):
                    last_match = matches[-1]
                    split_point = last_match.end()
                    break

            chunks.append(text[:split_point])
            text = text[split_point:].lstrip()

        return chunks

    @classmethod
    async def _send_text_chunks(
        cls,
        client: ExtBot,
        text: str,
        payload: dict[str, Any],
        *,
        use_markdown: bool | None = None,
        options: TelegramMessageOptions | None = None,
    ) -> None:
        """按 Telegram 限制切分文本后逐段发送。"""
        options = options or TelegramMessageOptions()
        parse_mode = cls._normalize_parse_mode(options.parse_mode)
        for chunk in cls._split_message(text):
            if parse_mode is not None:
                await client.send_message(
                    text=chunk,
                    parse_mode=parse_mode,
                    **cast(Any, payload),
                )
                continue

            if use_markdown is False or cls._is_plaintext_parse_mode(
                options.parse_mode,
            ):
                await client.send_message(text=chunk, **cast(Any, payload))
                continue

            try:
                markdown_text = telegramify_markdown.markdownify(chunk)
            except Exception as e:
                logger.warning(
                    f"Failed to convert message to Markdown，using normal text: {e!s}"
                )
                await client.send_message(text=chunk, **cast(Any, payload))
                continue

            try:
                await client.send_message(
                    text=markdown_text,
                    parse_mode="MarkdownV2",
                    **cast(Any, payload),
                )
            except BadRequest as e:
                if not cls._is_markdown_parse_error(e):
                    raise
                logger.warning(
                    f"Failed to convert message to Markdown，using normal text: {e!s}"
                )
                await client.send_message(text=chunk, **cast(Any, payload))

    @classmethod
    async def _send_chat_action(
        cls,
        client: ExtBot,
        chat_id: str,
        action: ChatAction | str,
        message_thread_id: str | None = None,
    ) -> None:
        """发送聊天状态动作"""
        try:
            payload: dict[str, Any] = {"chat_id": chat_id, "action": action}
            if message_thread_id:
                payload["message_thread_id"] = message_thread_id
            await client.send_chat_action(**payload)
        except Exception as e:
            logger.warning(f"[Telegram] 发送 chat action 失败: {e}")

    @classmethod
    def _get_chat_action_for_chain(cls, chain: list[Any]) -> ChatAction | str:
        """根据消息链中的组件类型确定合适的 chat action（按优先级）"""
        for seg_type, action in cls.ACTION_BY_TYPE.items():
            if any(isinstance(seg, seg_type) for seg in chain):
                return action
        return ChatAction.TYPING

    @classmethod
    async def _send_media_with_action(
        cls,
        client: ExtBot,
        upload_action: ChatAction | str,
        send_coro,
        *,
        user_name: str,
        message_thread_id: str | None = None,
        **payload: Any,
    ) -> None:
        """发送媒体时显示 upload action，发送完成后恢复 typing"""
        effective_thread_id = message_thread_id or cast(
            str | None, payload.get("message_thread_id")
        )
        await cls._send_chat_action(
            client, user_name, upload_action, effective_thread_id
        )
        send_payload = dict(payload)
        if effective_thread_id and "message_thread_id" not in send_payload:
            send_payload["message_thread_id"] = effective_thread_id
        await send_coro(**send_payload)
        await cls._send_chat_action(
            client, user_name, ChatAction.TYPING, effective_thread_id
        )

    @classmethod
    async def _send_voice_with_fallback(
        cls,
        client: ExtBot,
        path: str,
        payload: dict[str, Any],
        *,
        caption: str | None = None,
        user_name: str = "",
        message_thread_id: str | None = None,
        use_media_action: bool = False,
    ) -> None:
        """Send a voice message, falling back to a document if the user's
        privacy settings forbid voice messages (``BadRequest`` with
        ``Voice_messages_forbidden``).

        When *use_media_action* is ``True`` the helper wraps the send calls
        with ``_send_media_with_action`` (used by the streaming path).
        """
        try:
            if use_media_action:
                media_payload = dict(payload)
                if message_thread_id and "message_thread_id" not in media_payload:
                    media_payload["message_thread_id"] = message_thread_id
                await cls._send_media_with_action(
                    client,
                    ChatAction.UPLOAD_VOICE,
                    client.send_voice,
                    user_name=user_name,
                    voice=path,
                    **cast(Any, media_payload),
                )
            else:
                await client.send_voice(voice=path, **cast(Any, payload))
        except BadRequest as e:
            # python-telegram-bot raises BadRequest for Voice_messages_forbidden;
            # distinguish the voice-privacy case via the API error message.
            if "Voice_messages_forbidden" not in e.message:
                raise
            logger.warning(
                "User privacy settings prevent receiving voice messages, falling back to sending an audio file. "
                "To enable voice messages, go to Telegram Settings → Privacy and Security → Voice Messages → set to 'Everyone'."
            )
            if use_media_action:
                media_payload = dict(payload)
                if message_thread_id and "message_thread_id" not in media_payload:
                    media_payload["message_thread_id"] = message_thread_id
                await cls._send_media_with_action(
                    client,
                    ChatAction.UPLOAD_DOCUMENT,
                    client.send_document,
                    user_name=user_name,
                    document=path,
                    caption=caption,
                    **cast(Any, media_payload),
                )
            else:
                await client.send_document(
                    document=path,
                    caption=caption,
                    **cast(Any, payload),
                )

    @classmethod
    def _prepare_caption_payload(
        cls,
        caption: str | None,
        *,
        use_markdown: bool | None = None,
        options: TelegramMessageOptions | None = None,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        """构造 Telegram caption 参数，遵守 Bot API 的 caption 长度限制。"""
        if caption is None:
            return {}
        if len(caption) > int(MessageLimit.CAPTION_LENGTH):
            raise ValueError(
                "Telegram media caption must be 1024 characters or fewer.",
            )

        effective_options = options or TelegramMessageOptions(parse_mode=parse_mode)
        if parse_mode is not None:
            effective_options = TelegramMessageOptions(parse_mode=parse_mode)
        normalized_parse_mode = cls._normalize_parse_mode(effective_options.parse_mode)
        if normalized_parse_mode is not None:
            return {"caption": caption, "parse_mode": normalized_parse_mode}
        if use_markdown is False or cls._is_plaintext_parse_mode(
            effective_options.parse_mode,
        ):
            return {"caption": caption}
        try:
            markdown_caption = telegramify_markdown.markdownify(caption)
        except Exception as e:
            logger.warning(
                f"Failed to convert media caption to Markdown，using normal text: {e!s}"
            )
            return {"caption": caption}
        return {"caption": markdown_caption, "parse_mode": "MarkdownV2"}

    @staticmethod
    def _media_family(item: BaseMessageComponent) -> str | None:
        if isinstance(item, Image | Video):
            return "visual"
        if isinstance(item, File):
            return "document"
        return None

    @staticmethod
    def _component_reference(item: TelegramMediaComponent) -> str:
        if isinstance(item, Image):
            return str(item.url or item.file or "")
        if isinstance(item, Video):
            return str(item.file or "")
        return str(item.url or item.file_ or item.file or "")

    @staticmethod
    async def _component_path(item: TelegramMediaComponent) -> str:
        if isinstance(item, Image | Video):
            return await item.convert_to_file_path()
        return await item.get_file()

    @staticmethod
    async def _explicit_item_path(item: TelegramMediaGroupItem) -> str:
        media = item.media
        if isinstance(media, Image | Video):
            return await media.convert_to_file_path()
        if isinstance(media, File):
            return await media.get_file()
        if isinstance(media, str):
            if media.startswith("file://"):
                path = media[7:]
                if (
                    os.name == "nt"
                    and len(path) > 2
                    and path[0] == "/"
                    and path[2] == ":"
                ):
                    path = path[1:]
                return os.path.abspath(path)
            return os.path.abspath(media)
        raise ValueError("Telegram media group item media must be a component or path.")

    @staticmethod
    def _explicit_item_reference(item: TelegramMediaGroupItem) -> str:
        media = item.media
        if isinstance(media, Image | Video):
            return str(media.url or media.file or "")
        if isinstance(media, File):
            return str(media.url or media.file_ or media.file or "")
        if isinstance(media, str):
            return media
        return ""

    @staticmethod
    def _input_file_from_path(
        path: str,
        opened_files: ExitStack,
        *,
        filename: str | None = None,
    ) -> InputFile:
        # Bot API media group 的本地文件必须走 multipart；让文件句柄活到 await 完成。
        file_handle = opened_files.enter_context(open(path, "rb"))
        return InputFile(
            file_handle,
            filename=filename or os.path.basename(path),
            attach=True,
        )

    @classmethod
    async def _thumbnail_input(
        cls,
        thumbnail: Any,
        opened_files: ExitStack,
        *,
        force_upload: bool = False,
    ) -> Any:
        if thumbnail is None:
            return None
        if isinstance(thumbnail, Image):
            reference = str(thumbnail.url or thumbnail.file or "")
            if _is_http_url(reference) and not force_upload:
                return reference
            return cls._input_file_from_path(
                await thumbnail.convert_to_file_path(),
                opened_files,
            )
        if isinstance(thumbnail, str):
            if _is_http_url(thumbnail) and not force_upload:
                return thumbnail
            path = thumbnail[7:] if thumbnail.startswith("file://") else thumbnail
            return cls._input_file_from_path(os.path.abspath(path), opened_files)
        return thumbnail

    @classmethod
    async def _build_album_item(
        cls,
        item: TelegramMediaComponent,
        opened_files: ExitStack,
        *,
        force_upload: bool = False,
        caption_payload: dict[str, Any] | None = None,
    ) -> TelegramAlbumInputMedia | None:
        caption_payload = caption_payload or {}
        reference = cls._component_reference(item)
        if isinstance(item, Image):
            if _is_http_url(reference) and not force_upload:
                if _is_gif_url(reference):
                    return None
                return InputMediaPhoto(media=reference, **caption_payload)
            path = await item.convert_to_file_path()
            if _is_gif(path):
                return None
            return InputMediaPhoto(
                media=cls._input_file_from_path(path, opened_files),
                **caption_payload,
            )

        if isinstance(item, Video):
            if _is_http_url(reference) and not force_upload:
                return InputMediaVideo(media=reference, **caption_payload)
            path = await item.convert_to_file_path()
            return InputMediaVideo(
                media=cls._input_file_from_path(path, opened_files),
                **caption_payload,
            )

        if isinstance(item, File):
            if _is_http_url(reference) and not force_upload:
                return InputMediaDocument(
                    media=reference,
                    filename=item.name or None,
                    **caption_payload,
                )
            path = await item.get_file()
            return InputMediaDocument(
                media=cls._input_file_from_path(
                    path,
                    opened_files,
                    filename=item.name or None,
                ),
                filename=item.name or None,
                **caption_payload,
            )
        return None

    @classmethod
    async def _build_explicit_album_item(
        cls,
        item: TelegramMediaGroupItem,
        opened_files: ExitStack,
        *,
        force_upload: bool = False,
        caption_payload: dict[str, Any] | None = None,
    ) -> TelegramAlbumInputMedia:
        caption_payload = caption_payload or {}
        reference = cls._explicit_item_reference(item)
        if _is_http_url(reference) and not force_upload:
            media: Any = reference
        else:
            media = cls._input_file_from_path(
                await cls._explicit_item_path(item),
                opened_files,
                filename=item.filename,
            )

        if item.media_type == "photo":
            return InputMediaPhoto(
                media=media,
                has_spoiler=item.has_spoiler,
                show_caption_above_media=item.show_caption_above_media,
                **caption_payload,
            )

        thumbnail = await cls._thumbnail_input(
            item.thumbnail,
            opened_files,
            force_upload=force_upload,
        )
        if item.media_type == "video":
            return InputMediaVideo(
                media=media,
                thumbnail=thumbnail,
                has_spoiler=item.has_spoiler,
                show_caption_above_media=item.show_caption_above_media,
                supports_streaming=item.supports_streaming,
                **caption_payload,
            )
        if item.media_type == "document":
            return InputMediaDocument(
                media=media,
                filename=item.filename,
                thumbnail=thumbnail,
                disable_content_type_detection=item.disable_content_type_detection,
                **caption_payload,
            )
        if item.media_type == "audio":
            return InputMediaAudio(
                media=media,
                filename=item.filename,
                thumbnail=thumbnail,
                duration=item.duration,
                performer=item.performer,
                title=item.title,
                **caption_payload,
            )
        raise ValueError(
            f"Unsupported Telegram media group item type: {item.media_type}"
        )

    @classmethod
    async def _build_album_media(
        cls,
        items: list[TelegramMediaComponent],
        opened_files: ExitStack,
        *,
        force_upload: bool = False,
        caption_payload: dict[str, Any] | None = None,
    ) -> list[TelegramAlbumInputMedia]:
        media: list[TelegramAlbumInputMedia] = []
        for index, item in enumerate(items):
            built = await cls._build_album_item(
                item,
                opened_files,
                force_upload=force_upload,
                caption_payload=caption_payload if index == 0 else None,
            )
            if built is None:
                break
            media.append(built)
        return media

    @classmethod
    async def _build_explicit_album_media(
        cls,
        items: list[TelegramMediaGroupItem],
        opened_files: ExitStack,
        *,
        force_upload: bool = False,
        caption_payload: dict[str, Any] | None = None,
    ) -> list[TelegramAlbumInputMedia]:
        return [
            await cls._build_explicit_album_item(
                item,
                opened_files,
                force_upload=force_upload,
                caption_payload=caption_payload if index == 0 else None,
            )
            for index, item in enumerate(items)
        ]

    @classmethod
    def _items_have_remote_url(cls, items: list[Any]) -> bool:
        for item in items:
            if isinstance(item, TelegramMediaGroupItem):
                reference = cls._explicit_item_reference(item)
            else:
                reference = cls._component_reference(cast(TelegramMediaComponent, item))
            if _is_http_url(reference):
                return True
        return False

    @classmethod
    async def _send_media_group_with_fallback(
        cls,
        client: ExtBot,
        items: list[TelegramMediaComponent],
        payload: dict[str, Any],
        *,
        caption_payload: dict[str, Any] | None = None,
    ) -> None:
        with ExitStack() as opened_files:
            media = await cls._build_album_media(
                items,
                opened_files,
                caption_payload=caption_payload,
            )
            try:
                await client.send_media_group(media=media, **cast(Any, payload))
            except BadRequest as e:
                if not (
                    _is_webpage_curl_failed_error(e)
                    and cls._items_have_remote_url(items)
                ):
                    raise
                logger.warning(
                    "Telegram failed to fetch a remote media group item; "
                    "retrying by uploading local copies: %s",
                    e,
                )
                with ExitStack() as upload_files:
                    upload_media = await cls._build_album_media(
                        items,
                        upload_files,
                        force_upload=True,
                        caption_payload=caption_payload,
                    )
                    if len(upload_media) != len(media):
                        raise
                    await client.send_media_group(
                        media=upload_media,
                        **cast(Any, payload),
                    )

    @classmethod
    async def _send_explicit_media_group(
        cls,
        client: ExtBot,
        group: TelegramMediaGroup,
        payload: dict[str, Any],
        *,
        use_markdown: bool | None = None,
    ) -> None:
        cls._validate_media_group_families(group.items)
        batches = [
            group.items[index : index + MEDIA_GROUP_LIMIT]
            for index in range(0, len(group.items), MEDIA_GROUP_LIMIT)
        ]
        for batch_index, batch in enumerate(batches):
            caption_payload = (
                cls._prepare_caption_payload(
                    group.caption,
                    use_markdown=use_markdown,
                    parse_mode=group.parse_mode,
                )
                if batch_index == 0
                else {}
            )
            if len(batch) == 1:
                await cls._send_explicit_single_media(
                    client,
                    batch[0],
                    payload,
                    caption_payload=caption_payload,
                )
                continue
            with ExitStack() as opened_files:
                media = await cls._build_explicit_album_media(
                    batch,
                    opened_files,
                    caption_payload=caption_payload,
                )
                try:
                    await client.send_media_group(media=media, **cast(Any, payload))
                except BadRequest as e:
                    if not (
                        _is_webpage_curl_failed_error(e)
                        and cls._items_have_remote_url(batch)
                    ):
                        raise
                    logger.warning(
                        "Telegram failed to fetch a remote explicit media group item; "
                        "retrying by uploading local copies: %s",
                        e,
                    )
                    with ExitStack() as upload_files:
                        upload_media = await cls._build_explicit_album_media(
                            batch,
                            upload_files,
                            force_upload=True,
                            caption_payload=caption_payload,
                        )
                        await client.send_media_group(
                            media=upload_media,
                            **cast(Any, payload),
                        )

    @staticmethod
    def _validate_media_group_families(items: list[TelegramMediaGroupItem]) -> None:
        media_types = {item.media_type for item in items}
        if "audio" in media_types and media_types != {"audio"}:
            raise ValueError(
                "Telegram audio media groups can only contain audio items."
            )
        if "document" in media_types and media_types != {"document"}:
            raise ValueError(
                "Telegram document media groups can only contain document items.",
            )

    @classmethod
    async def _send_explicit_single_media(
        cls,
        client: ExtBot,
        item: TelegramMediaGroupItem,
        payload: dict[str, Any],
        *,
        caption_payload: dict[str, Any] | None = None,
    ) -> None:
        caption_payload = caption_payload or {}
        reference = cls._explicit_item_reference(item)
        if _is_http_url(reference):
            media = reference
        else:
            with ExitStack() as opened_files:
                path = await cls._explicit_item_path(item)
                media = cls._input_file_from_path(
                    path, opened_files, filename=item.filename
                )
                await cls._send_single_media_by_type(
                    client,
                    item.media_type,
                    media,
                    payload,
                    filename=item.filename,
                    **caption_payload,
                )
                return
        await cls._send_single_media_by_type(
            client,
            item.media_type,
            media,
            payload,
            filename=item.filename,
            **caption_payload,
        )

    @staticmethod
    async def _send_single_media_by_type(
        client: ExtBot,
        media_type: str,
        media: Any,
        payload: dict[str, Any],
        *,
        filename: str | None = None,
        **caption_payload: Any,
    ) -> None:
        if media_type == "photo":
            await client.send_photo(
                photo=media, **caption_payload, **cast(Any, payload)
            )
        elif media_type == "video":
            await client.send_video(
                video=media, **caption_payload, **cast(Any, payload)
            )
        elif media_type == "document":
            await client.send_document(
                document=media,
                filename=filename,
                **caption_payload,
                **cast(Any, payload),
            )
        elif media_type == "audio":
            await client.send_audio(
                audio=media,
                filename=filename,
                **caption_payload,
                **cast(Any, payload),
            )
        else:
            raise ValueError(f"Unsupported Telegram media type: {media_type}")

    @classmethod
    def _collect_media_segment(
        cls,
        chain: list[BaseMessageComponent],
        start_idx: int,
    ) -> tuple[str, list[str], list[TelegramMediaComponent], int]:
        family: str | None = None
        captions: list[str] = []
        media: list[TelegramMediaComponent] = []
        idx = start_idx
        while idx < len(chain):
            item = chain[idx]
            if isinstance(item, Plain):
                captions.append(item.text)
                idx += 1
                continue
            item_family = cls._media_family(item)
            if item_family is None:
                break
            if family is None:
                family = item_family
            if item_family != family:
                break
            media.append(cast(TelegramMediaComponent, item))
            idx += 1
        return family or "", captions, media, idx

    @classmethod
    def _next_media_index(
        cls,
        chain: list[BaseMessageComponent],
        start_idx: int,
    ) -> int | None:
        idx = start_idx
        while idx < len(chain):
            item = chain[idx]
            if isinstance(item, Plain):
                idx += 1
                continue
            if cls._media_family(item) is not None:
                return idx
            return None
        return None

    @classmethod
    async def _send_single_component_media(
        cls,
        client: ExtBot,
        item: TelegramMediaComponent,
        payload: dict[str, Any],
        *,
        caption_payload: dict[str, Any] | None = None,
    ) -> None:
        caption_payload = caption_payload or {}
        if isinstance(item, Image):
            path = await item.convert_to_file_path()
            if _is_gif(path):
                await client.send_animation(
                    animation=path,
                    **caption_payload,
                    **cast(Any, payload),
                )
            else:
                await client.send_photo(
                    photo=path,
                    **caption_payload,
                    **cast(Any, payload),
                )
        elif isinstance(item, Video):
            path = await item.convert_to_file_path()
            await client.send_video(
                video=path,
                **caption_payload,
                **cast(Any, payload),
            )
        elif isinstance(item, File):
            path = await item.get_file()
            name = item.name or os.path.basename(path)
            await client.send_document(
                document=path,
                filename=name,
                **caption_payload,
                **cast(Any, payload),
            )

    @classmethod
    async def _is_album_photo_component(cls, item: Image) -> bool:
        reference = cls._component_reference(item)
        if _is_http_url(reference):
            return not _is_gif_url(reference)
        return not _is_gif(await item.convert_to_file_path())

    @classmethod
    async def _send_albumable_component_media(
        cls,
        client: ExtBot,
        items: list[TelegramMediaComponent],
        payload: dict[str, Any],
        *,
        caption: str | None,
        use_markdown: bool | None,
        options: TelegramMessageOptions,
    ) -> None:
        batches = [
            items[index : index + MEDIA_GROUP_LIMIT]
            for index in range(0, len(items), MEDIA_GROUP_LIMIT)
        ]
        for batch_index, batch in enumerate(batches):
            caption_payload = (
                cls._prepare_caption_payload(
                    caption,
                    use_markdown=use_markdown,
                    options=options,
                )
                if batch_index == 0
                else {}
            )
            if len(batch) == 1:
                await cls._send_single_component_media(
                    client,
                    batch[0],
                    payload,
                    caption_payload=caption_payload,
                )
                continue
            await cls._send_media_group_with_fallback(
                client,
                batch,
                payload,
                caption_payload=caption_payload,
            )

    @classmethod
    async def _send_component_media_segment(
        cls,
        client: ExtBot,
        items: list[TelegramMediaComponent],
        payload: dict[str, Any],
        *,
        caption: str | None,
        use_markdown: bool | None,
        options: TelegramMessageOptions,
    ) -> None:
        caption_consumed = False
        current_batch: list[TelegramMediaComponent] = []

        async def flush_batch() -> None:
            nonlocal caption_consumed, current_batch
            if not current_batch:
                return
            batch_caption = caption if not caption_consumed else None
            if batch_caption is not None:
                caption_consumed = True
            await cls._send_albumable_component_media(
                client,
                current_batch,
                payload,
                caption=batch_caption,
                use_markdown=use_markdown,
                options=options,
            )
            current_batch = []

        for item in items:
            if isinstance(item, Image) and not await cls._is_album_photo_component(
                item
            ):
                await flush_batch()
                single_caption = caption if not caption_consumed else None
                if single_caption is not None:
                    caption_consumed = True
                await cls._send_single_component_media(
                    client,
                    item,
                    payload,
                    caption_payload=cls._prepare_caption_payload(
                        single_caption,
                        use_markdown=use_markdown,
                        options=options,
                    ),
                )
                continue
            current_batch.append(item)

        await flush_batch()

    async def _ensure_typing(
        self,
        user_name: str,
        message_thread_id: str | None = None,
    ) -> None:
        """确保显示 typing 状态"""
        await self._send_chat_action(
            self.client, user_name, ChatAction.TYPING, message_thread_id
        )

    async def send_typing(self) -> None:
        message_thread_id = None
        if self.get_message_type() == MessageType.GROUP_MESSAGE:
            user_name = self.message_obj.group_id
        else:
            user_name = self.get_sender_id()

        if "#" in user_name:
            user_name, message_thread_id = user_name.split("#")

        await self._ensure_typing(user_name, message_thread_id)

    @classmethod
    async def send_with_client(
        cls,
        client: ExtBot,
        message: MessageChain,
        user_name: str,
    ) -> None:
        chain, options, reply_markup = cls._extract_send_options(message)

        has_reply = False
        reply_message_id = None
        at_user_id = None
        for i in chain:
            if isinstance(i, Reply):
                has_reply = True
                reply_message_id = i.id
            if isinstance(i, At):
                at_user_id = i.name

        at_flag = False
        message_thread_id = None
        if "#" in user_name:
            # it's a supergroup chat with message_thread_id
            user_name, message_thread_id = user_name.split("#")

        # 根据消息链确定合适的 chat action 并发送
        action = cls._get_chat_action_for_chain(chain)
        await cls._send_chat_action(client, user_name, action, message_thread_id)

        extra_payload = cls._build_text_payload({}, options, reply_markup)
        idx = 0
        while idx < len(chain):
            i = chain[idx]
            payload = {
                "chat_id": user_name,
            }
            if has_reply:
                payload["reply_to_message_id"] = str(reply_message_id)
            if message_thread_id:
                payload["message_thread_id"] = message_thread_id
            media_payload = payload | {
                key: value
                for key, value in extra_payload.items()
                if key != "link_preview_options"
            }

            if isinstance(i, TelegramMediaGroup):
                if "reply_markup" in media_payload and len(i.items) > 1:
                    raise ValueError(
                        "Telegram media groups do not support reply_markup. "
                        "Send buttons in a separate message.",
                    )
                album_payload = {
                    key: value
                    for key, value in media_payload.items()
                    if key != "reply_markup"
                }
                await cls._send_explicit_media_group(
                    client,
                    i,
                    album_payload,
                    use_markdown=message.use_markdown_,
                )
            elif isinstance(i, Plain):
                if at_user_id and not at_flag:
                    i.text = f"@{at_user_id} {i.text}"
                    at_flag = True
                next_media_idx = cls._next_media_index(chain, idx + 1)
                if next_media_idx is None:
                    await cls._send_text_chunks(
                        client,
                        i.text,
                        payload | extra_payload,
                        use_markdown=message.use_markdown_,
                        options=options,
                    )
                else:
                    _, captions, media, next_idx = cls._collect_media_segment(
                        chain,
                        idx,
                    )
                    if media:
                        if "reply_markup" in media_payload and len(media) > 1:
                            raise ValueError(
                                "Telegram media groups do not support reply_markup. "
                                "Send buttons in a separate message.",
                            )
                        album_payload = {
                            key: value
                            for key, value in media_payload.items()
                            if key != "reply_markup"
                        }
                        await cls._send_component_media_segment(
                            client,
                            media,
                            album_payload if len(media) > 1 else media_payload,
                            caption="".join(captions) or None,
                            use_markdown=message.use_markdown_,
                            options=options,
                        )
                        idx = next_idx
                        continue
            elif isinstance(i, Image | Video | File):
                _, captions, media, next_idx = cls._collect_media_segment(chain, idx)
                if media:
                    if "reply_markup" in media_payload and len(media) > 1:
                        raise ValueError(
                            "Telegram media groups do not support reply_markup. "
                            "Send buttons in a separate message.",
                        )
                    album_payload = {
                        key: value
                        for key, value in media_payload.items()
                        if key != "reply_markup"
                    }
                    await cls._send_component_media_segment(
                        client,
                        media,
                        album_payload if len(media) > 1 else media_payload,
                        caption="".join(captions) or None,
                        use_markdown=message.use_markdown_,
                        options=options,
                    )
                    idx = next_idx
                    continue
            elif isinstance(i, Record):
                path = await i.convert_to_file_path()
                await cls._send_voice_with_fallback(
                    client,
                    path,
                    media_payload,
                    caption=i.text or None,
                    use_media_action=False,
                )
            elif isinstance(i, Video):
                path = await i.convert_to_file_path()
                await client.send_video(
                    video=path,
                    caption=getattr(i, "text", None) or None,
                    **cast(Any, media_payload),
                )
            idx += 1

    async def send(self, message: MessageChain) -> None:
        if self.get_message_type() == MessageType.GROUP_MESSAGE:
            await self.send_with_client(self.client, message, self.message_obj.group_id)
        else:
            await self.send_with_client(self.client, message, self.get_sender_id())
        await super().send(message)

    def get_telegram_client(self) -> ExtBot:
        """Return the Telegram Bot client for advanced Bot API calls."""
        return self.client

    def get_telegram_update(self):
        """Return the raw Telegram Update object."""
        return getattr(self.message_obj, "raw_message", None)

    def get_telegram_event_type(self) -> str:
        """Return the Telegram structured event type stored on this event."""
        return str(self.get_extra("telegram_event_type", "") or "")

    def get_telegram_payload(self) -> Any:
        """Return the Telegram object that triggered this structured event."""
        return self.get_extra("telegram_payload")

    def _get_callback_query(self):
        raw_message = getattr(self.message_obj, "raw_message", None)
        return getattr(raw_message, "callback_query", None)

    def is_button_interaction(self) -> bool:
        """Return whether this event comes from a Telegram callback query."""
        return self._get_callback_query() is not None

    def get_interaction_custom_id(self) -> str:
        """Return Telegram callback_data for inline button interactions."""
        callback_query = self._get_callback_query()
        if callback_query is None:
            return ""
        return str(getattr(callback_query, "data", "") or "")

    def get_interaction_data(self) -> str:
        """Alias for callback_data to match other platform interaction helpers."""
        return self.get_interaction_custom_id()

    def get_interaction_user_id(self) -> str:
        callback_query = self._get_callback_query()
        if callback_query is None:
            return ""
        from_user = getattr(callback_query, "from_user", None)
        if not from_user:
            return ""
        return str(getattr(from_user, "id", "") or "")

    async def answer_interaction(
        self,
        text: str | None = None,
        *,
        show_alert: bool | None = None,
        url: str | None = None,
        cache_time: int | None = None,
    ) -> None:
        callback_query = self._get_callback_query()
        if callback_query is None:
            raise RuntimeError("This Telegram event is not a button interaction.")
        await callback_query.answer(
            text=text,
            show_alert=show_alert,
            url=url,
            cache_time=cache_time,
        )

    async def ack_interaction(self) -> None:
        await self.answer_interaction()

    def get_inline_query(self):
        update = self.get_telegram_update()
        return getattr(update, "inline_query", None)

    def is_inline_query(self) -> bool:
        return self.get_inline_query() is not None

    def get_inline_query_text(self) -> str:
        inline_query = self.get_inline_query()
        if inline_query is None:
            return ""
        return str(getattr(inline_query, "query", "") or "")

    def get_chosen_inline_result(self):
        update = self.get_telegram_update()
        return getattr(update, "chosen_inline_result", None)

    def is_chosen_inline_result(self) -> bool:
        return self.get_chosen_inline_result() is not None

    def get_chat_member_update(self):
        update = self.get_telegram_update()
        event_type = self.get_telegram_event_type()
        if event_type == "my_chat_member":
            return getattr(update, "my_chat_member", None)
        if event_type == "chat_member":
            return getattr(update, "chat_member", None)
        return getattr(update, "chat_member", None) or getattr(
            update,
            "my_chat_member",
            None,
        )

    def is_chat_member_event(self) -> bool:
        return self.get_chat_member_update() is not None

    async def answer_inline_query(
        self,
        results: list[Any],
        *,
        inline_query_id: str | None = None,
        cache_time: int | None = None,
        is_personal: bool | None = None,
        next_offset: str | None = None,
        button: TelegramInlineQueryResultsButton | Any | None = None,
        current_offset: str | None = None,
        **kwargs: Any,
    ) -> None:
        inline_query = self.get_inline_query()
        target_inline_query_id = inline_query_id or (
            str(getattr(inline_query, "id", "") or "") if inline_query else ""
        )
        if not target_inline_query_id:
            raise RuntimeError("This Telegram event has no inline_query_id.")

        telegram_button = (
            button.to_telegram_button()
            if isinstance(button, TelegramInlineQueryResultsButton)
            else button
        )
        telegram_results = [
            self._convert_inline_query_result(result) for result in results
        ]
        await self.client.answer_inline_query(
            inline_query_id=target_inline_query_id,
            results=telegram_results,
            cache_time=cache_time,
            is_personal=is_personal,
            next_offset=next_offset,
            button=telegram_button,
            current_offset=current_offset,
            **kwargs,
        )

    async def edit_text(
        self,
        text: str,
        *,
        reply_markup: TelegramInlineKeyboard | Any | None = None,
        parse_mode: str | None = None,
        link_preview_options: Any = None,
        **kwargs: Any,
    ) -> Any:
        chat_id, _ = self._current_chat_reference()
        return await self.client.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=self._current_message_id(),
            reply_markup=self._convert_reply_markup(reply_markup),
            parse_mode=parse_mode,
            link_preview_options=link_preview_options,
            **kwargs,
        )

    async def edit_reply_markup(
        self,
        reply_markup: TelegramInlineKeyboard | Any | None = None,
        **kwargs: Any,
    ) -> Any:
        chat_id, _ = self._current_chat_reference()
        return await self.client.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=self._current_message_id(),
            reply_markup=self._convert_reply_markup(reply_markup),
            **kwargs,
        )

    async def delete_message(self, **kwargs: Any) -> Any:
        chat_id, _ = self._current_chat_reference()
        return await self.client.delete_message(
            chat_id=chat_id,
            message_id=self._current_message_id(),
            **kwargs,
        )

    async def copy_message(
        self,
        chat_id: str,
        *,
        from_chat_id: str | None = None,
        message_id: int | None = None,
        message_thread_id: int | None = None,
        reply_markup: TelegramReplyMarkup | Any | None = None,
        **kwargs: Any,
    ) -> Any:
        source_chat_id, _ = self._current_chat_reference()
        target_chat_id, target_thread_id = self._split_telegram_chat_reference(
            str(chat_id),
        )
        return await self.client.copy_message(
            chat_id=target_chat_id,
            from_chat_id=from_chat_id or source_chat_id,
            message_id=message_id or self._current_message_id(),
            message_thread_id=message_thread_id
            if message_thread_id is not None
            else target_thread_id,
            reply_markup=self._convert_reply_markup(reply_markup),
            **kwargs,
        )

    async def forward_message(
        self,
        chat_id: str,
        *,
        from_chat_id: str | None = None,
        message_id: int | None = None,
        message_thread_id: int | None = None,
        **kwargs: Any,
    ) -> Any:
        source_chat_id, _ = self._current_chat_reference()
        target_chat_id, target_thread_id = self._split_telegram_chat_reference(
            str(chat_id),
        )
        return await self.client.forward_message(
            chat_id=target_chat_id,
            from_chat_id=from_chat_id or source_chat_id,
            message_id=message_id or self._current_message_id(),
            message_thread_id=message_thread_id
            if message_thread_id is not None
            else target_thread_id,
            **kwargs,
        )

    async def react(self, emoji: str | None, big: bool = False) -> None:
        """给原消息添加 Telegram 反应：
        - 普通 emoji：传入 '👍'、'😂' 等
        - 自定义表情：传入其 custom_emoji_id（纯数字字符串）
        - 取消本机器人的反应：传入 None 或空字符串
        """
        try:
            # 解析 chat_id（去掉超级群的 "#<thread_id>" 片段）
            if self.get_message_type() == MessageType.GROUP_MESSAGE:
                chat_id = (self.message_obj.group_id or "").split("#")[0]
            else:
                chat_id = self.get_sender_id()

            message_id = int(self.message_obj.message_id)

            # 组装 reaction 参数（必须是 ReactionType 的列表）
            if not emoji:  # 清空本 bot 的反应
                reaction_param = []  # 空列表表示移除本 bot 的反应
            elif emoji.isdigit():  # 自定义表情：传 custom_emoji_id
                reaction_param = [ReactionTypeCustomEmoji(emoji)]
            else:  # 普通 emoji
                reaction_param = [ReactionTypeEmoji(emoji)]

            await self.client.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=reaction_param,  # 注意是列表
                is_big=big,  # 可选：大动画
            )
        except Exception as e:
            logger.error(f"[Telegram] 添加反应失败: {e}")

    async def _send_message_draft(
        self,
        chat_id: str,
        draft_id: int,
        text: str,
        message_thread_id: str | None = None,
        parse_mode: str | None = None,
    ) -> None:
        """通过 Bot.send_message_draft 发送草稿消息（流式推送部分消息）。

        该 API 仅支持私聊。

        Args:
            chat_id: 目标私聊的 chat_id
            draft_id: 草稿唯一标识，非零整数；相同 draft_id 的变更会以动画展示
            text: 消息文本，1-4096 字符
            message_thread_id: 可选，目标消息线程 ID
            parse_mode: 可选，消息文本的解析模式
        """
        if not text or not text.strip():
            return

        kwargs: dict[str, Any] = {}
        if message_thread_id:
            kwargs["message_thread_id"] = int(message_thread_id)
        if parse_mode:
            kwargs["parse_mode"] = parse_mode

        try:
            logger.debug(
                f"[Telegram] sendMessageDraft: chat_id={chat_id}, draft_id={draft_id}, text_len={len(text)}"
            )
            await self.client.send_message_draft(
                chat_id=int(chat_id),
                draft_id=draft_id,
                text=text,
                **kwargs,
            )
        except Exception as e:
            logger.warning(f"[Telegram] sendMessageDraft 失败: {e!s}")

    async def _process_chain_items(
        self,
        chain: MessageChain,
        payload: dict[str, Any],
        user_name: str,
        message_thread_id: str | None,
        on_text: Callable[[str], None],
    ) -> None:
        """处理 MessageChain 中的各类组件，文本通过 on_text 回调追加，媒体直接发送。"""
        for i in chain.chain:
            if isinstance(i, Plain):
                on_text(i.text)
            elif isinstance(i, Image):
                image_path = await i.convert_to_file_path()
                if _is_gif(image_path):
                    action = ChatAction.UPLOAD_VIDEO
                    send_coro = self.client.send_animation
                    media_kwarg = {"animation": image_path}
                else:
                    action = ChatAction.UPLOAD_PHOTO
                    send_coro = self.client.send_photo
                    media_kwarg = {"photo": image_path}
                await self._send_media_with_action(
                    self.client,
                    action,
                    send_coro,
                    user_name=user_name,
                    **media_kwarg,
                    **cast(Any, payload),
                )
            elif isinstance(i, File):
                path = await i.get_file()
                name = i.name or os.path.basename(path)
                await self._send_media_with_action(
                    self.client,
                    ChatAction.UPLOAD_DOCUMENT,
                    self.client.send_document,
                    user_name=user_name,
                    document=path,
                    filename=name,
                    **cast(Any, payload),
                )
            elif isinstance(i, Record):
                path = await i.convert_to_file_path()
                await self._send_voice_with_fallback(
                    self.client,
                    path,
                    payload,
                    caption=i.text or None,
                    user_name=user_name,
                    message_thread_id=message_thread_id,
                    use_media_action=True,
                )
            elif isinstance(i, Video):
                path = await i.convert_to_file_path()
                await self._send_media_with_action(
                    self.client,
                    ChatAction.UPLOAD_VIDEO,
                    self.client.send_video,
                    user_name=user_name,
                    video=path,
                    **cast(Any, payload),
                )
            else:
                logger.warning(f"不支持的消息类型: {type(i)}")

    async def _send_final_segment(self, delta: str, payload: dict[str, Any]) -> None:
        """将累积文本作为 MarkdownV2 真实消息发送，失败时回退到纯文本。"""
        await self._send_text_chunks(self.client, delta, payload)

    async def send_streaming(self, generator, use_fallback: bool = False):
        message_thread_id = None

        if self.get_message_type() == MessageType.GROUP_MESSAGE:
            user_name = self.message_obj.group_id
        else:
            user_name = self.get_sender_id()

        if "#" in user_name:
            # it's a supergroup chat with message_thread_id
            user_name, message_thread_id = user_name.split("#")
        payload = {
            "chat_id": user_name,
        }
        if message_thread_id:
            payload["message_thread_id"] = message_thread_id

        # sendMessageDraft 仅支持私聊（显式检查 FRIEND_MESSAGE）
        is_private = self.get_message_type() == MessageType.FRIEND_MESSAGE

        if is_private:
            logger.info("[Telegram] 流式输出: 使用 sendMessageDraft (私聊)")
            await self._send_streaming_draft(
                user_name, message_thread_id, payload, generator
            )
        else:
            logger.info("[Telegram] 流式输出: 使用 edit_message_text fallback (群聊)")
            await self._send_streaming_edit(
                user_name, message_thread_id, payload, generator
            )

        # 内联父类 send_streaming 的副作用（避免传入已消费的 generator）
        asyncio.create_task(
            Metric.upload(msg_event_tick=1, adapter_name=self.platform_meta.name),
        )
        self._has_send_oper = True

    async def _send_streaming_draft(
        self,
        user_name: str,
        message_thread_id: str | None,
        payload: dict[str, Any],
        generator,
    ) -> None:
        """使用 sendMessageDraft API 进行流式推送（私聊专用）。

        流式过程中使用 sendMessageDraft 推送草稿动画，
        流式结束后发送一条真实消息保留最终内容（draft 是临时的，会消失）。
        使用信号驱动的发送循环：每次有新 token 到达时唤醒发送，
        发送频率由网络 RTT 自然限制（最多一个请求 in-flight）。
        """
        draft_id = self._allocate_draft_id()
        delta = ""
        last_sent_text = ""
        done = False  # 信号：生成器已结束
        text_changed = asyncio.Event()  # 有新 token 到达时触发

        async def _draft_sender_loop() -> None:
            """信号驱动的草稿发送循环，有新内容就发，RTT 自然限流。"""
            nonlocal last_sent_text
            while not done:
                await text_changed.wait()
                text_changed.clear()
                # 发送最新的缓冲区内容（MarkdownV2 渲染，与真实消息一致）
                if delta and delta != last_sent_text:
                    draft_text = delta[: self.MAX_MESSAGE_LENGTH]
                    if draft_text != last_sent_text:
                        try:
                            md = telegramify_markdown.markdownify(
                                draft_text,
                            )
                            await self._send_message_draft(
                                user_name,
                                draft_id,
                                md,
                                message_thread_id,
                                parse_mode="MarkdownV2",
                            )
                            last_sent_text = draft_text
                        except Exception:
                            # markdownify 对未闭合语法可能失败，回退纯文本
                            try:
                                await self._send_message_draft(
                                    user_name,
                                    draft_id,
                                    draft_text,
                                    message_thread_id,
                                )
                                last_sent_text = draft_text
                            except Exception as e2:
                                logger.debug(
                                    f"[Telegram] sendMessageDraft failed (ignored): {e2!s}"
                                )

        sender_task = asyncio.create_task(_draft_sender_loop())

        def _append_text(t: str) -> None:
            nonlocal delta
            delta += t
            text_changed.set()  # 唤醒发送循环

        try:
            async for chain in generator:
                if not isinstance(chain, MessageChain):
                    continue

                if chain.type == "break":
                    # 分割符：发送真实消息保留内容，重置缓冲区
                    if delta:
                        # 用 emoji 清空 draft 显示，避免 draft 和真实消息同时可见
                        await self._send_message_draft(
                            user_name,
                            draft_id,
                            "\u23f3",
                            message_thread_id,
                        )
                        await self._send_final_segment(delta, payload)
                    delta = ""
                    last_sent_text = ""
                    draft_id = self._allocate_draft_id()
                    continue

                await self._process_chain_items(
                    chain, payload, user_name, message_thread_id, _append_text
                )
        finally:
            done = True
            text_changed.set()  # 唤醒循环使其退出
            await sender_task

        # 流式结束：用 emoji 清空 draft，然后发真实消息持久化
        if delta:
            await self._send_message_draft(
                user_name,
                draft_id,
                "\u23f3",
                message_thread_id,
            )
            await self._send_final_segment(delta, payload)

    async def _send_streaming_edit(
        self,
        user_name: str,
        message_thread_id: str | None,
        payload: dict[str, Any],
        generator,
    ) -> None:
        """使用 send_message + edit_message_text 进行流式推送（群聊 fallback）。"""
        delta = ""
        current_content = ""
        message_id = None
        last_edit_time = 0  # 上次编辑消息的时间
        throttle_interval = 0.6  # 编辑消息的间隔时间 (秒)
        last_chat_action_time = 0  # 上次发送 chat action 的时间
        chat_action_interval = 0.5  # chat action 的节流间隔 (秒)

        # 发送初始 typing 状态
        await self._ensure_typing(user_name, message_thread_id)
        last_chat_action_time = asyncio.get_running_loop().time()

        def _append_text(t: str) -> None:
            nonlocal delta
            delta += t

        async for chain in generator:
            if not isinstance(chain, MessageChain):
                continue

            if chain.type == "break":
                # 分割符
                if message_id:
                    try:
                        await self.client.edit_message_text(
                            text=delta,
                            chat_id=payload["chat_id"],
                            message_id=message_id,
                        )
                    except Exception as e:
                        logger.warning(f"编辑消息失败(streaming-break): {e!s}")
                message_id = None
                delta = ""
                continue

            await self._process_chain_items(
                chain, payload, user_name, message_thread_id, _append_text
            )

            # 编辑或发送消息
            if message_id and len(delta) <= self.MAX_MESSAGE_LENGTH:
                current_time = asyncio.get_running_loop().time()
                time_since_last_edit = current_time - last_edit_time

                if time_since_last_edit >= throttle_interval:
                    current_time = asyncio.get_running_loop().time()
                    if current_time - last_chat_action_time >= chat_action_interval:
                        await self._ensure_typing(user_name, message_thread_id)
                        last_chat_action_time = current_time
                    try:
                        await self.client.edit_message_text(
                            text=delta,
                            chat_id=payload["chat_id"],
                            message_id=message_id,
                        )
                        current_content = delta
                    except Exception as e:
                        logger.warning(f"编辑消息失败(streaming): {e!s}")
                    last_edit_time = asyncio.get_running_loop().time()
            else:
                current_time = asyncio.get_running_loop().time()
                if current_time - last_chat_action_time >= chat_action_interval:
                    await self._ensure_typing(user_name, message_thread_id)
                    last_chat_action_time = current_time
                try:
                    msg = await self.client.send_message(
                        text=delta, **cast(Any, payload)
                    )
                    current_content = delta
                except Exception as e:
                    logger.warning(f"发送消息失败(streaming): {e!s}")
                message_id = msg.message_id
                last_edit_time = asyncio.get_running_loop().time()

        try:
            if delta and current_content != delta:
                try:
                    markdown_text = telegramify_markdown.markdownify(
                        delta,
                    )
                    await self.client.edit_message_text(
                        text=markdown_text,
                        chat_id=payload["chat_id"],
                        message_id=message_id,
                        parse_mode="MarkdownV2",
                    )
                except Exception as e:
                    logger.warning(f"Markdown转换失败，使用普通文本: {e!s}")
                    await self.client.edit_message_text(
                        text=delta,
                        chat_id=payload["chat_id"],
                        message_id=message_id,
                    )
        except Exception as e:
            logger.warning(f"编辑消息失败(streaming): {e!s}")
