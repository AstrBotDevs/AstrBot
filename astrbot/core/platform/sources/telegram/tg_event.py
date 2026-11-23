import asyncio
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from functools import partial
from typing import ClassVar, NotRequired, Protocol, TypedDict, runtime_checkable

import telegramify_markdown
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReactionTypeCustomEmoji,
    ReactionTypeEmoji,
)
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import ExtBot

from astrbot import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import (
    ActionRow,
    At,
    Button,
    File,
    Image,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.api.platform import AstrBotMessage, Group, MessageType, PlatformMetadata
from astrbot.core.message.components import BaseMessageComponent
from astrbot.core.platform.button_interaction import encode_button_callback
from astrbot.core.utils.metrics import Metric


class DeliveryPayload(TypedDict):
    """Routing fields accepted by each Telegram delivery method used here."""

    chat_id: str | int
    message_thread_id: NotRequired[int]
    reply_to_message_id: NotRequired[int]
    reply_markup: NotRequired[InlineKeyboardMarkup]


class ChatActionPayload(TypedDict):
    chat_id: str
    action: str
    message_thread_id: NotRequired[int]


class DraftOptions(TypedDict, total=False):
    message_thread_id: int
    parse_mode: str


class EditPayload(TypedDict):
    chat_id: str | int
    message_id: int
    parse_mode: NotRequired[str]


@runtime_checkable
class ClosableStream(Protocol):
    """The optional asynchronous cleanup contract of a message source."""

    def aclose(self) -> Awaitable[None]: ...


def _is_gif(path: str) -> bool:
    if path.lower().endswith(".gif"):
        return True
    try:
        with open(path, "rb") as f:
            return f.read(6) in (b"GIF87a", b"GIF89a")
    except OSError:
        return False


class TelegramPlatformEvent(AstrMessageEvent):
    MAX_MESSAGE_LENGTH = 4096
    SPLIT_PATTERNS: ClassVar[dict[str, re.Pattern[str]]] = {
        "paragraph": re.compile("\\n\\n"),
        "line": re.compile("\\n"),
        "sentence": re.compile("[.!?｡!?]"),
        "word": re.compile("\\s"),
    }
    _TELEGRAM_DRAFT_ID_MAX = 2147483647
    _next_draft_id: int = 0

    @classmethod
    def _allocate_draft_id(cls) -> int:
        """分配一个递增的 draft_id,溢出时归 1｡"""
        cls._next_draft_id = (
            1
            if cls._next_draft_id >= cls._TELEGRAM_DRAFT_ID_MAX
            else cls._next_draft_id + 1
        )
        return cls._next_draft_id

    ACTION_BY_TYPE: ClassVar[dict[type, str]] = {
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

    @staticmethod
    def _normalize_delivery_payload(payload: DeliveryPayload) -> DeliveryPayload:
        """Copy routing fields into the integer form required by the Telegram SDK."""
        normalized = payload.copy()
        if (thread_id := payload.get("message_thread_id")) is not None:
            normalized["message_thread_id"] = int(thread_id)
        if (reply_id := payload.get("reply_to_message_id")) is not None:
            normalized["reply_to_message_id"] = int(reply_id)
        return normalized

    @classmethod
    async def _send_text_chunks(
        cls,
        client: ExtBot,
        text: str,
        payload: DeliveryPayload,
    ) -> None:
        """按 Telegram 限制切分文本后逐段发送。"""
        payload = cls._normalize_delivery_payload(payload)
        chunks = cls._split_message(text)
        for index, chunk in enumerate(chunks):
            chunk_payload = payload.copy()
            if index < len(chunks) - 1:
                chunk_payload.pop("reply_markup", None)
            try:
                markdown_text = telegramify_markdown.markdownify(chunk)
            except Exception as error:
                logger.warning("Telegram Markdown conversion failed: %s", error)
                await client.send_message(text=chunk, **chunk_payload)
                continue
            try:
                await client.send_message(
                    text=markdown_text,
                    parse_mode="MarkdownV2",
                    **chunk_payload,
                )
            except BadRequest as e:
                logger.warning(
                    f"Telegram rejected Markdown; retrying as plain text: {e!s}"
                )
                await client.send_message(text=chunk, **chunk_payload)

    @classmethod
    def _build_inline_keyboard(
        cls,
        rows: list[ActionRow],
    ) -> InlineKeyboardMarkup | None:
        """Render common button rows as a Telegram inline keyboard.

        Args:
            rows: Common action rows to render.

        Returns:
            Telegram markup, or ``None`` when no valid buttons remain.
        """
        keyboard: list[list[InlineKeyboardButton]] = []
        for row in rows:
            telegram_row: list[InlineKeyboardButton] = []
            for button in row.buttons:
                if isinstance(button.action, Button.UrlAction):
                    telegram_row.append(
                        InlineKeyboardButton(button.label, url=button.action.url)
                    )
                    continue

                if not isinstance(button.action, Button.CallbackAction):
                    continue
                callback_data = encode_button_callback(
                    button.id, button.action.data, expires_at=row.action_expires_at
                )
                if len(callback_data.encode("utf-8")) > 64:
                    logger.warning(
                        "Skipping Telegram button %r because its callback token "
                        "exceeds 64 bytes.",
                        button.id,
                    )
                    continue
                telegram_row.append(
                    InlineKeyboardButton(
                        button.label,
                        callback_data=callback_data,
                    )
                )
            if telegram_row:
                keyboard.append(telegram_row)

        return InlineKeyboardMarkup(keyboard) if keyboard else None

    @classmethod
    async def _send_chat_action(
        cls,
        client: ExtBot,
        chat_id: str,
        action: ChatAction | str,
        message_thread_id: str | int | None = None,
    ) -> None:
        """发送聊天状态动作"""
        try:
            payload: ChatActionPayload = {"chat_id": chat_id, "action": action}
            if message_thread_id:
                payload["message_thread_id"] = int(message_thread_id)
            await client.send_chat_action(**payload)
        except Exception as e:
            logger.warning(f"[Telegram] 发送 chat action 失败: {e}")

    @classmethod
    def _get_chat_action_for_chain(
        cls, chain: Sequence[BaseMessageComponent]
    ) -> ChatAction | str:
        """根据消息链中的组件类型确定合适的 chat action(按优先级)"""
        for seg_type, action in cls.ACTION_BY_TYPE.items():
            if any(isinstance(seg, seg_type) for seg in chain):
                return action
        return ChatAction.TYPING

    @classmethod
    async def _send_media_with_action(
        cls,
        client: ExtBot,
        upload_action: ChatAction | str,
        send_coro: Callable[[], Awaitable[Message]],
        *,
        user_name: str,
        message_thread_id: str | int | None = None,
    ) -> None:
        """发送媒体时显示 upload action,发送完成后恢复 typing"""
        await cls._send_chat_action(
            client,
            user_name,
            upload_action,
            message_thread_id,
        )
        await send_coro()
        await cls._send_chat_action(
            client,
            user_name,
            ChatAction.TYPING,
            message_thread_id,
        )

    @classmethod
    async def _send_voice_with_fallback(
        cls,
        client: ExtBot,
        path: str,
        payload: DeliveryPayload,
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
        media_payload = cls._normalize_delivery_payload(payload)
        if message_thread_id and "message_thread_id" not in media_payload:
            media_payload["message_thread_id"] = int(message_thread_id)
        try:
            if use_media_action:
                await cls._send_media_with_action(
                    client,
                    ChatAction.UPLOAD_VOICE,
                    partial(client.send_voice, voice=path, **media_payload),
                    user_name=user_name,
                    message_thread_id=media_payload.get("message_thread_id"),
                )
            else:
                await client.send_voice(voice=path, **media_payload)
        except BadRequest as e:
            if "Voice_messages_forbidden" not in str(e):
                raise
            logger.warning(
                "User privacy settings prevent receiving voice messages, falling back to sending an audio file. To enable voice messages, go to Telegram Settings ￫ Privacy and Security ￫ Voice Messages ￫ set to 'Everyone'.",
            )
            if use_media_action:
                await cls._send_media_with_action(
                    client,
                    ChatAction.UPLOAD_DOCUMENT,
                    partial(
                        client.send_document,
                        document=path,
                        caption=caption,
                        **media_payload,
                    ),
                    user_name=user_name,
                    message_thread_id=media_payload.get("message_thread_id"),
                )
            else:
                await client.send_document(
                    document=path, caption=caption, **media_payload
                )

    async def _ensure_typing(
        self,
        user_name: str,
        message_thread_id: str | None = None,
    ) -> None:
        """确保显示 typing 状态"""
        await self._send_chat_action(
            self.client,
            user_name,
            ChatAction.TYPING,
            message_thread_id,
        )

    def _message_target(self) -> tuple[str, str | None]:
        message_thread_id = None
        if self.get_message_type() == MessageType.GROUP_MESSAGE:
            user_name = self.message_obj.group_id
        else:
            user_name = self.get_sender_id()
        if "#" in user_name:
            user_name, message_thread_id = user_name.split("#")
        return user_name, message_thread_id

    async def send_typing(self) -> None:
        user_name, message_thread_id = self._message_target()
        await self._ensure_typing(user_name, message_thread_id)

    @classmethod
    async def send_with_client(
        cls,
        client: ExtBot,
        message: MessageChain,
        user_name: str,
    ) -> None:
        image_path = None

        action_rows = [i for i in message.chain if isinstance(i, ActionRow)]
        reply_markup = cls._build_inline_keyboard(action_rows)
        renderable_indexes = [
            index
            for index, component in enumerate(message.chain)
            if isinstance(component, (Plain, Image, File, Record, Video))
        ]
        last_renderable_index = renderable_indexes[-1] if renderable_indexes else None

        has_reply = False
        reply_message_id = None
        at_user_id = None
        for i in message.chain:
            if isinstance(i, Reply):
                has_reply = True
                reply_message_id = i.id
            if isinstance(i, At):
                at_user_id = i.name
        at_flag = False
        message_thread_id = None
        if "#" in user_name:
            user_name, message_thread_id = user_name.split("#")
        action = cls._get_chat_action_for_chain(message.chain)
        await cls._send_chat_action(client, user_name, action, message_thread_id)

        for index, i in enumerate(message.chain):
            payload: DeliveryPayload = {
                "chat_id": user_name,
            }
            if has_reply and reply_message_id is not None:
                payload["reply_to_message_id"] = int(reply_message_id)
            if message_thread_id:
                payload["message_thread_id"] = int(message_thread_id)
            if reply_markup is not None and index == last_renderable_index:
                payload["reply_markup"] = reply_markup

            if isinstance(i, Plain):
                if at_user_id and (not at_flag):
                    i.text = f"@{at_user_id} {i.text}"
                    at_flag = True
                await cls._send_text_chunks(client, i.text, payload)
            elif isinstance(i, Image):
                image_path = await i.convert_to_file_path()
                if _is_gif(image_path):
                    await client.send_animation(animation=image_path, **payload)
                else:
                    await client.send_photo(photo=image_path, **payload)
            elif isinstance(i, File):
                path = await i.get_file()
                name = i.name or os.path.basename(path)
                await client.send_document(document=path, filename=name, **payload)
            elif isinstance(i, Record):
                path = await i.convert_to_file_path()
                await cls._send_voice_with_fallback(
                    client,
                    path,
                    payload,
                    caption=i.text or None,
                    use_media_action=False,
                )
            elif isinstance(i, Video):
                path = await i.convert_to_file_path()
                await client.send_video(
                    video=path,
                    caption=getattr(i, "text", None) or None,
                    **payload,
                )

        if action_rows and last_renderable_index is None:
            fallback_text = next(
                (row.fallback_text for row in action_rows if row.fallback_text),
                "Choose an option:",
            )
            payload = {"chat_id": user_name}
            if reply_markup is not None:
                payload["reply_markup"] = reply_markup
            if has_reply and reply_message_id is not None:
                payload["reply_to_message_id"] = int(reply_message_id)
            if message_thread_id:
                payload["message_thread_id"] = int(message_thread_id)
            await cls._send_text_chunks(client, fallback_text, payload)

    async def send(self, message: MessageChain) -> None:
        if self.get_message_type() == MessageType.GROUP_MESSAGE:
            await self.send_with_client(self.client, message, self.message_obj.group_id)
        else:
            await self.send_with_client(self.client, message, self.get_sender_id())
        await super().send(message)

    async def get_group(
        self, group_id: str | None = None, **kwargs: object
    ) -> Group | None:
        """Get Telegram group metadata available to the bot.

        Telegram topics use ``<chat_id>#<thread_id>`` inside AstrBot. The Bot API
        calls target the parent chat while the returned group keeps the topic-aware ID.

        Args:
            group_id: AstrBot group ID to query. Defaults to the current group.
            **kwargs: Reserved for compatibility with the platform event interface.

        Returns:
            Enriched group metadata, or ``None`` when no group ID is available.
        """
        requested_group_id = str(group_id or self.get_group_id())
        if not requested_group_id:
            return None

        current_group = self.message_obj.group
        group = self._group_lookup_snapshot(requested_group_id)
        topic_name = (
            getattr(self.message_obj, "_telegram_topic_name", None)
            if current_group and current_group.group_id == requested_group_id
            else None
        )
        chat_id = requested_group_id.split("#", 1)[0]
        api_chat_id: str | int = (
            int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
        )

        try:
            chat = await self.client.get_chat(chat_id=api_chat_id)
            title = getattr(chat, "title", None)
            if isinstance(title, str):
                group.group_name = (
                    f"{title}-{topic_name}"
                    if isinstance(topic_name, str) and topic_name
                    else title
                )

            photo = getattr(chat, "photo", None)
            file_id = getattr(photo, "big_file_id", None) if photo else None
            if file_id:
                try:
                    photo_file = await self.client.get_file(file_id=file_id)
                    file_path = getattr(photo_file, "file_path", None)
                    if file_path:
                        group.group_avatar = str(file_path)
                except Exception as exc:
                    logger.warning(
                        f"[Telegram] Failed to get group photo for {chat_id}: {exc}"
                    )
        except Exception as exc:
            logger.warning(
                f"[Telegram] Failed to get group information for {chat_id}: {exc}"
            )

        try:
            group.member_count = await self.client.get_chat_member_count(
                chat_id=api_chat_id
            )
        except Exception as exc:
            logger.warning(
                f"[Telegram] Failed to get group member count for {chat_id}: {exc}"
            )

        try:
            administrators = await self.client.get_chat_administrators(
                chat_id=api_chat_id
            )
            group.group_admins = []
            for administrator in administrators:
                status = getattr(administrator, "status", None)
                user = getattr(administrator, "user", None)
                user_id = getattr(user, "id", None)
                if user_id is None:
                    continue
                if status == "creator":
                    group.group_owner = str(user_id)
                elif status == "administrator":
                    group.group_admins.append(str(user_id))
        except Exception as exc:
            logger.warning(
                f"[Telegram] Failed to get group administrators for {chat_id}: {exc}"
            )

        return group

    async def react(self, emoji: str | None, big: bool = False) -> None:
        """给原消息添加 Telegram 反应:
        - 普通 emoji:传入 '👍'､'😂' 等
        - 自定义表情:传入其 custom_emoji_id(纯数字字符串)
        - 取消本机器人的反应:传入 None 或空字符串
        """
        try:
            if self.get_message_type() == MessageType.GROUP_MESSAGE:
                chat_id = (self.message_obj.group_id or "").split("#")[0]
            else:
                chat_id = self.get_sender_id()
            message_id = int(self.message_obj.message_id)
            if not emoji:
                reaction_param = []
            elif emoji.isdigit():
                reaction_param = [ReactionTypeCustomEmoji(emoji)]
            else:
                reaction_param = [ReactionTypeEmoji(emoji)]
            await self.client.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=reaction_param,
                is_big=big,
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
        """通过 Bot.send_message_draft 发送草稿消息(流式推送部分消息)｡

        该 API 仅支持私聊｡

        Args:
            chat_id: 目标私聊的 chat_id
            draft_id: 草稿唯一标识,非零整数;相同 draft_id 的变更会以动画展示
            text: 消息文本,1-4096 字符
            message_thread_id: 可选,目标消息线程 ID
            parse_mode: 可选,消息文本的解析模式

        """
        if not text or not text.strip():
            return

        kwargs: DraftOptions = {}
        if message_thread_id:
            kwargs["message_thread_id"] = int(message_thread_id)
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
        try:
            logger.debug(
                f"[Telegram] sendMessageDraft: chat_id={chat_id}, draft_id={draft_id}, text_len={len(text)}",
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
        payload: DeliveryPayload,
        user_name: str,
        message_thread_id: str | None,
        on_text: Callable[[str], None],
    ) -> None:
        """处理 MessageChain 中的各类组件,文本通过 on_text 回调追加,媒体直接发送｡"""
        for i in chain.chain:
            if isinstance(i, Plain):
                on_text(i.text)
            elif isinstance(i, Image):
                image_path = await i.convert_to_file_path()
                if _is_gif(image_path):
                    action = ChatAction.UPLOAD_VIDEO
                    send_coro = partial(
                        self.client.send_animation, animation=image_path, **payload
                    )
                else:
                    action = ChatAction.UPLOAD_PHOTO
                    send_coro = partial(
                        self.client.send_photo, photo=image_path, **payload
                    )
                await self._send_media_with_action(
                    self.client,
                    action,
                    send_coro,
                    user_name=user_name,
                    message_thread_id=payload.get("message_thread_id"),
                )
            elif isinstance(i, File):
                path = await i.get_file()
                name = i.name or os.path.basename(path)
                await self._send_media_with_action(
                    self.client,
                    ChatAction.UPLOAD_DOCUMENT,
                    partial(
                        self.client.send_document,
                        document=path,
                        filename=name,
                        **payload,
                    ),
                    user_name=user_name,
                    message_thread_id=payload.get("message_thread_id"),
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
                    partial(self.client.send_video, video=path, **payload),
                    user_name=user_name,
                    message_thread_id=payload.get("message_thread_id"),
                )
            else:
                logger.warning(f"不支持的消息类型: {type(i)}")

    async def _send_final_segment(self, delta: str, payload: DeliveryPayload) -> None:
        """将累积文本作为 MarkdownV2 真实消息发送,失败时回退到纯文本｡"""
        await self._send_text_chunks(self.client, delta, payload)

    async def send_streaming(
        self, generator: AsyncIterator[MessageChain], use_fallback: bool = False
    ) -> None:
        user_name, message_thread_id = self._message_target()
        payload: DeliveryPayload = {"chat_id": user_name}
        if message_thread_id:
            payload["message_thread_id"] = int(message_thread_id)
        stream_error: BaseException | None = None
        try:
            is_private = self.get_message_type() == MessageType.FRIEND_MESSAGE
            if is_private:
                logger.info("[Telegram] 流式输出: 使用 sendMessageDraft (私聊)")
                await self._send_streaming_draft(
                    user_name,
                    message_thread_id,
                    payload,
                    generator,
                )
            else:
                logger.info(
                    "[Telegram] 流式输出: 使用 edit_message_text fallback (群聊)"
                )
                await self._send_streaming_edit(
                    user_name,
                    message_thread_id,
                    payload,
                    generator,
                )
        except BaseException as error:
            stream_error = error
            raise
        finally:
            if isinstance(generator, ClosableStream) and callable(generator.aclose):
                try:
                    await generator.aclose()
                except BaseException as cleanup_error:
                    if stream_error is None:
                        raise
                    # Keep the original delivery or cancellation exception intact.
                    logger.warning(
                        "Telegram stream cleanup failed after a delivery error: %s",
                        cleanup_error,
                    )
        asyncio.create_task(
            Metric.upload(msg_event_tick=1, adapter_name=self.platform_meta.name),
        )
        self._has_send_oper = True

    async def _send_streaming_draft(
        self,
        user_name: str,
        message_thread_id: str | None,
        payload: DeliveryPayload,
        generator: AsyncIterator[MessageChain],
    ) -> None:
        """使用 sendMessageDraft API 进行流式推送(私聊专用)｡

        流式过程中使用 sendMessageDraft 推送草稿动画,
        流式结束后发送一条真实消息保留最终内容(draft 是临时的,会消失)｡
        使用信号驱动的发送循环:每次有新 token 到达时唤醒发送,
        发送频率由网络 RTT 自然限制(最多一个请求 in-flight)｡
        """
        draft_id = self._allocate_draft_id()
        delta = ""
        last_sent_text = ""
        done = False
        text_changed = asyncio.Event()

        async def _draft_sender_loop() -> None:
            """信号驱动的草稿发送循环,有新内容就发,RTT 自然限流｡"""
            nonlocal last_sent_text
            while not done:
                await text_changed.wait()
                text_changed.clear()
                if delta and delta != last_sent_text:
                    draft_text = delta[: self.MAX_MESSAGE_LENGTH]
                    if draft_text != last_sent_text:
                        try:
                            md = telegramify_markdown.markdownify(draft_text)
                            await self._send_message_draft(
                                user_name,
                                draft_id,
                                md,
                                message_thread_id,
                                parse_mode="MarkdownV2",
                            )
                            last_sent_text = draft_text
                        except Exception:
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
                                    f"[Telegram] sendMessageDraft failed (ignored): {e2!s}",
                                )

        sender_task = asyncio.create_task(_draft_sender_loop())

        def _append_text(t: str) -> None:
            nonlocal delta
            delta += t
            text_changed.set()

        try:
            async for chain in generator:
                if not isinstance(chain, MessageChain):
                    continue
                if chain.type == "break":
                    if delta.strip():
                        await self._send_message_draft(
                            user_name,
                            draft_id,
                            "⏳",
                            message_thread_id,
                        )
                        await self._send_final_segment(delta, payload)
                    delta = ""
                    last_sent_text = ""
                    draft_id = self._allocate_draft_id()
                    continue
                await self._process_chain_items(
                    chain,
                    payload,
                    user_name,
                    message_thread_id,
                    _append_text,
                )
        finally:
            done = True
            text_changed.set()
            await sender_task
        if delta.strip():
            await self._send_message_draft(user_name, draft_id, "⏳", message_thread_id)
            await self._send_final_segment(delta, payload)

    async def _send_streaming_edit(
        self,
        user_name: str,
        message_thread_id: str | None,
        payload: DeliveryPayload,
        generator: AsyncIterator[MessageChain],
    ) -> None:
        """使用 send_message + edit_message_text 进行流式推送(群聊 fallback)｡"""
        payload = self._normalize_delivery_payload(payload)
        delta = ""
        current_content = ""
        message_id = None
        last_edit_time: float = 0
        throttle_interval = 0.6
        last_chat_action_time: float = 0
        chat_action_interval = 0.5
        await self._ensure_typing(user_name, message_thread_id)
        last_chat_action_time = asyncio.get_running_loop().time()

        def _append_text(t: str) -> None:
            nonlocal delta
            delta += t

        async for chain in generator:
            if not isinstance(chain, MessageChain):
                continue
            if chain.type == "break":
                if message_id and delta != current_content:
                    try:
                        await self.client.edit_message_text(
                            text=delta,
                            chat_id=payload["chat_id"],
                            message_id=message_id,
                        )
                    except BadRequest as e:
                        logger.warning(f"编辑消息失败(streaming-break): {e!s}")
                message_id = None
                delta = ""
                current_content = ""
                continue
            await self._process_chain_items(
                chain,
                payload,
                user_name,
                message_thread_id,
                _append_text,
            )
            if not delta.strip() or delta == current_content:
                continue
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
                    except BadRequest as e:
                        logger.warning(f"编辑消息失败(streaming): {e!s}")
                    last_edit_time = asyncio.get_running_loop().time()
            else:
                current_time = asyncio.get_running_loop().time()
                if current_time - last_chat_action_time >= chat_action_interval:
                    await self._ensure_typing(user_name, message_thread_id)
                    last_chat_action_time = current_time
                try:
                    msg = await self.client.send_message(text=delta, **payload)
                    current_content = delta
                    message_id = msg.message_id
                except Exception as e:
                    logger.warning("Telegram initial stream send failed: %s", e)
                    raise
                last_edit_time = asyncio.get_running_loop().time()
        try:
            if message_id and current_content != delta:
                edit_payload: EditPayload = {
                    "chat_id": payload["chat_id"],
                    "message_id": message_id,
                }
                try:
                    markdown_text = telegramify_markdown.markdownify(delta)
                except Exception as error:
                    logger.warning("Telegram Markdown conversion failed: %s", error)
                    markdown_text = delta
                else:
                    edit_payload["parse_mode"] = "MarkdownV2"
                try:
                    await self.client.edit_message_text(
                        text=markdown_text, **edit_payload
                    )
                except BadRequest as error:
                    if "parse_mode" not in edit_payload:
                        raise
                    logger.warning(
                        "Telegram rejected Markdown; retrying as plain text: %s", error
                    )
                    edit_payload.pop("parse_mode")
                    await self.client.edit_message_text(text=delta, **edit_payload)
        except BadRequest as e:
            logger.warning(f"编辑消息失败(streaming): {e!s}")
