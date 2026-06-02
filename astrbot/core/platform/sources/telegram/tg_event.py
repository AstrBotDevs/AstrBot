import asyncio
import os
import re
from collections.abc import Callable
from typing import Any, cast

import telegramify_markdown
from telegram import ReactionTypeCustomEmoji, ReactionTypeEmoji
from telegram.constants import ChatAction
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


def _is_gif(path: str) -> bool:
    if path.lower().endswith(".gif"):
        return True
    try:
        with open(path, "rb") as f:
            return f.read(6) in (b"GIF87a", b"GIF89a")
    except OSError:
        return False


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
        image_path = None
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
        for i in chain:
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

            if isinstance(i, Plain):
                if at_user_id and not at_flag:
                    i.text = f"@{at_user_id} {i.text}"
                    at_flag = True
                await cls._send_text_chunks(
                    client,
                    i.text,
                    payload | extra_payload,
                    use_markdown=message.use_markdown_,
                    options=options,
                )
            elif isinstance(i, Image):
                image_path = await i.convert_to_file_path()
                if _is_gif(image_path):
                    send_coro = client.send_animation
                    media_kwarg = {"animation": image_path}
                else:
                    send_coro = client.send_photo
                    media_kwarg = {"photo": image_path}
                await send_coro(**media_kwarg, **cast(Any, media_payload))
            elif isinstance(i, File):
                path = await i.get_file()
                name = i.name or os.path.basename(path)
                await client.send_document(
                    document=path, filename=name, **cast(Any, media_payload)
                )
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
