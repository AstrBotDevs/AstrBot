import asyncio
import json
import os
import re
import sys
import time
import uuid
from collections import deque
from collections.abc import Sequence
from contextlib import suppress
from typing import TYPE_CHECKING, cast

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import BotCommand, Update
from telegram.constants import ChatType
from telegram.error import Forbidden, InvalidToken, NetworkError
from telegram.ext import (
    ApplicationBuilder,
    BusinessConnectionHandler,
    BusinessMessagesDeletedHandler,
    CallbackQueryHandler,
    ContextTypes,
    ExtBot,
    filters,
)
from telegram.ext import MessageHandler as TelegramMessageHandler

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.platform import (
    AstrBotMessage,
    Group,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.platform.button_interaction import (
    BUTTON_ACTION_EXPIRED_MESSAGE,
    ButtonActionExpiredError,
    decode_button_callback_async,
)
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_temp_path,
)
from astrbot.core.utils.io import download_file
from astrbot.core.utils.media_utils import MediaResolver

from .tg_event import TelegramPlatformEvent

if TYPE_CHECKING:
    from telegram import MessageEntity

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

BUSINESS_SESSION_PREFIX = "biz:"


@register_platform_adapter("telegram", "telegram 适配器")
class TelegramPlatformAdapter(Platform):
    _FORUM_TOPIC_NAME_CACHE_MAX_SIZE = 1000

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings

        base_url = self.config.get(
            "telegram_api_base_url",
            "https://api.telegram.org/bot",
        )
        if not base_url:
            base_url = "https://api.telegram.org/bot"

        file_base_url = self.config.get(
            "telegram_file_base_url",
            "https://api.telegram.org/file/bot",
        )
        if not file_base_url:
            file_base_url = "https://api.telegram.org/file/bot"

        self.base_url = base_url
        self.file_base_url = file_base_url

        self.enable_command_register = self.config.get(
            "telegram_command_register",
            True,
        )
        self.enable_command_refresh = self.config.get(
            "telegram_command_auto_refresh",
            True,
        )
        self.last_command_hash = None

        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_listener(
            lambda ev: logger.error(
                "Scheduled job %s raised: %s",
                ev.job_id,
                ev.exception,
                exc_info=ev.exception,
            ),
            EVENT_JOB_ERROR,
        )
        self._terminating = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._polling_recovery_requested = asyncio.Event()
        self._consecutive_polling_failures = 0
        self._last_polling_failure_at = 0.0
        raw_delay = self.config.get("telegram_polling_restart_delay", 5.0)
        try:
            delay = float(raw_delay)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid 'telegram_polling_restart_delay' value %r in config, "
                "falling back to default 5.0s",
                raw_delay,
            )
            delay = 5.0

        if delay < 0.1:
            logger.warning(
                "Configured 'telegram_polling_restart_delay' (%s) is too small; "
                "enforcing minimum of 0.1s to avoid tight restart loops",
                delay,
            )
            delay = 0.1
        self._polling_restart_delay = delay
        self._polling_recovery_threshold = 3
        self._polling_failure_window = 60.0
        self._application_started = False
        self._forum_topic_names: dict[tuple[str, int | None], str] = {}
        self.business_enabled = bool(self.config.get("telegram_business_enabled", True))
        self._business_connections: dict[str, dict] = {}
        self._business_state_path = os.path.join(
            get_astrbot_data_path(), "telegram_business_connections.json"
        )
        self._seen_update_ids: deque[int] = deque(maxlen=1024)
        self._load_business_connections()
        self._build_application()

        # Media group handling
        # Cache structure: {media_group_id: {"created_at": datetime, "items": [(update, context), ...]}}
        self.media_group_cache: dict[str, dict] = {}
        self.media_group_timeout = self.config.get(
            "telegram_media_group_timeout", 2.5
        )  # seconds - debounce delay between messages
        self.media_group_max_wait = self.config.get(
            "telegram_media_group_max_wait", 10.0
        )  # max seconds - hard cap to prevent indefinite delay

    def _build_application(self) -> None:
        self.application = (
            ApplicationBuilder()
            .token(self.config["telegram_token"])
            .base_url(self.base_url)
            .base_file_url(self.file_base_url)
            .build()
        )
        message_handler = TelegramMessageHandler(
            filters=filters.ALL,
            callback=self.message_handler,
        )
        self.application.add_handler(CallbackQueryHandler(self.callback_query_handler))
        self.application.add_handler(message_handler)
        self.application.add_handler(
            BusinessConnectionHandler(self.business_connection_handler)
        )
        self.application.add_handler(
            BusinessMessagesDeletedHandler(self.deleted_business_messages_handler)
        )
        self.client = self.application.bot
        logger.debug(f"Telegram base url: {self.client.base_url}")

    async def _start_application(self) -> None:
        await self.application.initialize()
        await self.application.start()

        if self.enable_command_register:
            await self.register_commands()

        self._application_started = True

    async def _shutdown_application(
        self,
        *,
        delete_commands: bool,
    ) -> None:
        self._application_started = False

        updater = self.application.updater
        if updater is not None:
            with suppress(Exception):
                await updater.stop()

        if delete_commands and self.enable_command_register:
            with suppress(Exception):
                await self.client.delete_my_commands()

        with suppress(Exception):
            await self.application.stop()

        shutdown = getattr(self.application, "shutdown", None)
        if shutdown is not None:
            with suppress(Exception):
                await shutdown()

    async def _recreate_application(self) -> None:
        if self._terminating:
            self._polling_recovery_requested.clear()
            return

        logger.warning(
            "Telegram polling hit repeated network errors; rebuilding the "
            "Telegram application and HTTP client.",
        )
        await self._shutdown_application(delete_commands=False)
        self._build_application()
        self._consecutive_polling_failures = 0
        self._last_polling_failure_at = 0.0
        self._polling_recovery_requested.clear()

    def _start_command_scheduler(self) -> None:
        if not self.enable_command_refresh or not self.enable_command_register:
            return
        if self.scheduler.running:
            return

        self.scheduler.add_job(
            self.register_commands,
            "interval",
            seconds=self.config.get("telegram_command_register_interval", 300),
            id="telegram_command_register",
            misfire_grace_time=60,
        )
        self.scheduler.start()

    @override
    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        user_name = session.session_id
        business_connection_id = None
        parsed = self._parse_business_session(user_name)
        if parsed is not None:
            user_name, business_connection_id = parsed
            if not self._business_reply_allowed(business_connection_id):
                logger.warning(
                    "Skipping Telegram Business reply for connection %s: "
                    "connection is disabled or not replyable.",
                    business_connection_id,
                )
                return
        await TelegramPlatformEvent.send_with_client(
            self.client,
            message_chain,
            user_name,
            business_connection_id=business_connection_id,
        )
        await super().send_by_session(session, message_chain)

    @override
    def meta(self) -> PlatformMetadata:
        id_ = self.config.get("id") or "telegram"
        return PlatformMetadata(name="telegram", description="telegram 适配器", id=id_)

    @override
    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._start_command_scheduler()

        while not self._terminating:
            try:
                if not self._application_started:
                    await self._start_application()

                self._polling_recovery_requested.clear()
                updater = self.application.updater
                if updater is None:
                    logger.error(
                        "Telegram Updater is not initialized. Cannot start polling."
                    )
                    self._application_started = False
                    await asyncio.sleep(self._polling_restart_delay)
                    continue
                logger.info("Starting Telegram polling...")
                await updater.start_polling(error_callback=self._on_polling_error)
                logger.info("Telegram Platform Adapter is running.")
                while updater.running and not self._terminating:  # noqa: ASYNC110
                    if self._polling_recovery_requested.is_set():
                        await self._recreate_application()
                        break
                    await asyncio.sleep(1)
                else:
                    if not self._terminating:
                        logger.warning(
                            "Telegram polling loop exited unexpectedly, "
                            f"retrying in {self._polling_restart_delay}s."
                        )
                    continue

                if not self._terminating:
                    logger.info("Telegram polling restarted with a fresh client.")
                    continue
            except asyncio.CancelledError:
                raise
            except (Forbidden, InvalidToken) as e:
                logger.error(
                    f"Telegram token is invalid or unauthorized: {e}. Polling stopped."
                )
                break
            except Exception as e:
                logger.exception(
                    "Telegram polling crashed with exception: "
                    f"{type(e).__name__}: {e!s}. "
                    f"Retrying in {self._polling_restart_delay}s.",
                )
                with suppress(Exception):
                    await self._shutdown_application(delete_commands=False)
                self._build_application()

            if not self._terminating:
                await asyncio.sleep(self._polling_restart_delay)

    def _on_polling_error(self, error: Exception) -> None:
        # Non-network errors (e.g. Conflict when two bot instances poll the
        # same token) have a clear cause; log a concise message instead of a
        # full traceback to avoid filling the log.
        if not isinstance(error, NetworkError):
            logger.error(
                f"Telegram polling request failed: {type(error).__name__}: {error!s}"
            )
            return

        logger.error(
            f"Telegram polling request failed: {type(error).__name__}: {error!s}",
            exc_info=error,
        )

        if self._loop is None:
            return

        now = self._loop.time()
        if now - self._last_polling_failure_at > self._polling_failure_window:
            self._consecutive_polling_failures = 0
        self._last_polling_failure_at = now
        self._consecutive_polling_failures += 1

        if self._consecutive_polling_failures < self._polling_recovery_threshold:
            return

        logger.warning(
            "Telegram polling encountered %s network failures within %.1fs; "
            "scheduling client rebuild.",
            self._consecutive_polling_failures,
            self._polling_failure_window,
        )
        if self._loop.is_closed():
            return
        try:
            self._loop.call_soon_threadsafe(self._polling_recovery_requested.set)
        except RuntimeError:
            return

    async def register_commands(self) -> None:
        """收集所有注册的指令并注册到 Telegram"""
        try:
            commands = self.collect_commands()

            if commands:
                current_hash = hash(
                    tuple((cmd.command, cmd.description) for cmd in commands),
                )
                if current_hash == self.last_command_hash:
                    return
                self.last_command_hash = current_hash
                await self.client.delete_my_commands()
                await self.client.set_my_commands(commands)

        except Exception as e:
            logger.error(f"向 Telegram 注册指令时发生错误: {e!s}")

    def collect_commands(self) -> list[BotCommand]:
        """从注册的处理器中收集所有指令"""
        command_dict = {}
        skip_commands = {"start"}

        for handler_md in star_handlers_registry:
            handler_metadata = handler_md
            if (
                handler_metadata.handler_module_path not in star_map
                or not star_map[handler_metadata.handler_module_path].activated
            ):
                continue
            if not handler_metadata.enabled:
                continue
            for event_filter in handler_metadata.event_filters:
                cmd_info_list = self._extract_command_info(
                    event_filter,
                    handler_metadata,
                    skip_commands,
                )
                if cmd_info_list:
                    for cmd_name, description in cmd_info_list:
                        if cmd_name in command_dict:
                            logger.warning(
                                f"命令名 '{cmd_name}' 重复注册，将使用首次注册的定义: "
                                f"'{command_dict[cmd_name]}'"
                            )
                        command_dict.setdefault(cmd_name, description)

        commands_a = sorted(command_dict.keys())
        return [BotCommand(cmd, command_dict[cmd]) for cmd in commands_a]

    @staticmethod
    def _extract_command_info(
        event_filter,
        handler_metadata,
        skip_commands: set,
    ) -> list[tuple[str, str]] | None:
        """从事件过滤器中提取指令信息，包括所有别名"""
        cmd_names = []
        is_group = False
        if isinstance(event_filter, CommandFilter) and event_filter.command_name:
            if (
                event_filter.parent_command_names
                and event_filter.parent_command_names != [""]
            ):
                return None
            # 收集主命令名和所有别名
            cmd_names = [event_filter.command_name]
            if event_filter.alias:
                cmd_names.extend(event_filter.alias)
        elif isinstance(event_filter, CommandGroupFilter):
            if event_filter.parent_group:
                return None
            cmd_names = [event_filter.group_name]
            is_group = True

        result = []
        for cmd_name in cmd_names:
            if not cmd_name or cmd_name in skip_commands:
                continue
            if not re.match(r"^[a-z0-9_]+$", cmd_name) or len(cmd_name) > 32:
                continue

            # Build description.
            description = handler_metadata.desc or (
                f"Command group: {cmd_name}" if is_group else f"Command: {cmd_name}"
            )
            if len(description) > 30:
                description = description[:30] + "..."
            result.append((cmd_name, description))

        return result if result else None

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat:
            logger.warning(
                "Received a start command without an effective chat, skipping /start reply.",
            )
            return
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=self.config["start_message"],
        )

    async def message_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if self._is_duplicate_update(update):
            return

        # Ordinary bot messages keep the existing handling path.
        if update.message:
            logger.debug(f"Telegram message: {update.message}")
            if update.message.media_group_id:
                await self.handle_media_group_message(update, context)
                return
            abm = await self.convert_message(update, context)
            if abm:
                await self.handle_msg(abm)
            return

        # Telegram Business messages arrive via their own Update field.
        if update.business_message:
            if not self.business_enabled:
                logger.debug("Ignoring Telegram Business message: feature disabled.")
                return
            logger.debug(f"Telegram Business message: {update.business_message}")
            if update.business_message.media_group_id:
                await self.handle_media_group_message(update, context)
                return
            abm = await self.convert_business_message(update, context)
            if abm:
                await self.handle_msg(abm)
            return

        # Edits (both regular and business) are not new user messages.
        if update.edited_message or update.edited_business_message:
            logger.debug(
                "Ignoring edited message update (id=%s): edits are not processed "
                "as new messages.",
                update.update_id,
            )
            return

        logger.debug("Ignoring a Telegram update without a supported message.")

    async def callback_query_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Convert a Telegram callback query into a button interaction event.

        Args:
            update: Telegram update containing the callback query.
            context: Telegram callback context.
        """
        query = update.callback_query
        if query is None:
            return

        action_id = None
        data = None
        try:
            if isinstance(query.data, str):
                action_id, data = await decode_button_callback_async(query.data)
        except ButtonActionExpiredError:
            try:
                await query.answer(text=BUTTON_ACTION_EXPIRED_MESSAGE, show_alert=True)
            except Exception as exc:
                logger.warning("Failed to send Telegram button expiry notice: %s", exc)
            return
        except (TypeError, ValueError):
            pass

        try:
            await query.answer()
        except Exception as exc:
            logger.warning("Failed to answer Telegram callback query: %s", exc)

        if action_id is None:
            logger.debug("Ignoring a Telegram callback query not created by AstrBot.")
            return

        source_message = query.message
        chat = source_message.chat if source_message else update.effective_chat
        if chat is None:
            logger.warning("Received a Telegram callback query without a chat.")
            return

        message = AstrBotMessage()
        message.session_id = str(chat.id)
        if chat.type == ChatType.PRIVATE:
            message.type = MessageType.FRIEND_MESSAGE
        else:
            message.type = MessageType.GROUP_MESSAGE
            message.group_id = str(chat.id)
            if (
                source_message is not None
                and getattr(source_message, "is_topic_message", False)
                and getattr(source_message, "message_thread_id", None)
            ):
                message.group_id += f"#{source_message.message_thread_id}"
                message.session_id = message.group_id

        source_message_id = (
            str(source_message.message_id) if source_message is not None else None
        )
        message.message_id = str(query.id)
        message.sender = MessageMember(
            str(query.from_user.id),
            query.from_user.username or "Unknown",
        )
        message.self_id = str(context.bot.username)
        message.raw_message = update
        message.message_str = action_id
        message.message = [
            Comp.ButtonInteraction(
                action_id=action_id,
                data=data,
                interaction_id=str(query.id),
                source_message_id=source_message_id,
                callback_data=query.data,
            )
        ]
        await self.handle_msg(message)

    @staticmethod
    def _parse_text_entities(
        text: str,
        entities: Sequence["MessageEntity"],
        self_id: str,
        *,
        strip_self_mention: bool = False,
    ) -> tuple[str, list[Comp.Plain | Comp.At]]:
        """Build command text and an ordered message chain from Telegram entities.

        Args:
            text: Original message body or media caption.
            entities: Telegram entities with UTF-16 offsets into the text.
            self_id: Bot username used to identify mentions of the bot.
            strip_self_mention: Remove self mentions from command text for text messages.

        Returns:
            Command text and the ordered text and mention components.
        """
        utf16 = text.encode("utf-16-le")
        command_parts: list[str] = []
        plain_parts: list[str] = []
        components: list[Comp.Plain | Comp.At] = []
        cursor = 0
        for entity in sorted(entities, key=lambda item: item.offset):
            end = (entity.offset + entity.length) * 2
            if entity.type == "mention":
                start = entity.offset * 2
                before = utf16[cursor:start].decode("utf-16-le")
                command_parts.append(before)
                plain_parts.append(before)
                if plain := "".join(plain_parts):
                    components.append(Comp.Plain(plain))
                plain_parts.clear()

                mention_text = utf16[start:end].decode("utf-16-le")
                name = mention_text[1:]
                is_self = name.lower() == self_id.lower()
                components.append(Comp.At(qq=self_id if is_self else name, name=name))
                if not (is_self and strip_self_mention):
                    command_parts.append(mention_text)
            elif entity.type == "text_link" and entity.url:
                text_with_url = (
                    utf16[cursor:end].decode("utf-16-le") + f" ({entity.url})"
                )
                command_parts.append(text_with_url)
                plain_parts.append(text_with_url)
            else:
                continue
            cursor = end

        tail = utf16[cursor:].decode("utf-16-le")
        command_parts.append(tail)
        plain_parts.append(tail)
        if plain := "".join(plain_parts):
            components.append(Comp.Plain(plain))
        return "".join(command_parts), components

    async def convert_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        get_reply=True,
        handle_start=True,
    ) -> AstrBotMessage | None:
        """转换 Telegram 的消息对象为 AstrBotMessage 对象。

        @param update: Telegram 的 Update 对象。
        @param context: Telegram 的 Context 对象。
        @param get_reply: 是否获取回复消息。这个参数是为了防止多个回复嵌套。
        """
        if not update.message:
            logger.warning("Received an update without a message.")
            return None

        def _apply_caption() -> None:
            if update.message and update.message.caption:
                message.message_str, components = self._parse_text_entities(
                    update.message.caption,
                    update.message.caption_entities or (),
                    message.self_id,
                )
                message.message.extend(components)

        message = AstrBotMessage()
        message.session_id = str(update.message.chat.id)

        # 获得是群聊还是私聊
        if update.message.chat.type == ChatType.PRIVATE:
            message.type = MessageType.FRIEND_MESSAGE
        else:
            message.type = MessageType.GROUP_MESSAGE
            chat_id = str(update.message.chat.id)
            group_id = chat_id
            is_forum = getattr(update.message.chat, "is_forum", False) is True
            raw_thread_id = (
                update.message.message_thread_id
                if update.message.is_topic_message
                else None
            )
            thread_id = (
                raw_thread_id
                if raw_thread_id and not (is_forum and raw_thread_id == 1)
                else None
            )
            if thread_id is not None:
                # Telegram Topic Group: include thread id to isolate per-topic sessions.
                group_id += "#" + str(thread_id)
                message.session_id = group_id

            chat_title = getattr(update.message.chat, "title", None)
            group_name = chat_title if isinstance(chat_title, str) else None
            topic_name = None
            topic_created = getattr(update.message, "forum_topic_created", None)
            topic_edited = getattr(update.message, "forum_topic_edited", None)
            discovered_topic_name = getattr(topic_created, "name", None)
            if not isinstance(discovered_topic_name, str):
                discovered_topic_name = getattr(topic_edited, "name", None)
            if not isinstance(discovered_topic_name, str):
                reply_message = update.message.reply_to_message
                reply_topic_created = getattr(
                    reply_message, "forum_topic_created", None
                )
                discovered_topic_name = getattr(reply_topic_created, "name", None)

            topic_key = None
            if thread_id is not None:
                topic_key = (chat_id, thread_id)
            elif is_forum:
                topic_key = (chat_id, None)

            if topic_key is not None:
                cached_topic_name = self._forum_topic_names.pop(topic_key, None)
                if (
                    isinstance(discovered_topic_name, str)
                    and discovered_topic_name.strip()
                ):
                    cached_topic_name = discovered_topic_name.strip()
                if cached_topic_name:
                    self._forum_topic_names[topic_key] = cached_topic_name
                    if (
                        len(self._forum_topic_names)
                        > self._FORUM_TOPIC_NAME_CACHE_MAX_SIZE
                    ):
                        oldest_topic_key = next(iter(self._forum_topic_names))
                        del self._forum_topic_names[oldest_topic_key]
                topic_name = cached_topic_name

            if group_name and topic_name:
                group_name = f"{group_name}-{topic_name}"
            message.group = Group(
                group_id=group_id,
                group_name=group_name,
            )
            message._telegram_topic_name = topic_name
        message.message_id = str(update.message.message_id)
        _from_user = update.message.from_user
        if not _from_user:
            logger.warning("[Telegram] Received a message without a from_user.")
            return None
        message.sender = MessageMember(
            str(_from_user.id),
            _from_user.username or _from_user.full_name or "Unknown",
        )
        message.self_id = str(context.bot.username)
        message.raw_message = update
        message.message_str = ""
        message.message = []

        if update.message.reply_to_message and not (
            update.message.is_topic_message
            and update.message.message_thread_id
            == update.message.reply_to_message.message_id
        ):
            # 获取回复消息
            reply_update = Update(
                update_id=1,
                message=update.message.reply_to_message,
            )
            reply_abm = await self.convert_message(reply_update, context, False)

            if reply_abm:
                quote_text = update.message.quote.text if update.message.quote else None
                reply_chain = reply_abm.message
                reply_message_str = reply_abm.message_str
                if quote_text:
                    quote_utf16 = quote_text.encode("utf-16-le")
                    original = update.message.reply_to_message
                    original_utf16 = (original.text or original.caption or "").encode(
                        "utf-16-le"
                    )
                    start = update.message.quote.position * 2
                    end = start + len(quote_utf16)
                    # Telegram omits links from quote entities; use the matched source.
                    if original_utf16[start:end] == quote_utf16:
                        for entity in reversed(
                            original.entities or original.caption_entities or ()
                        ):
                            link_start = entity.offset * 2
                            link_end = (entity.offset + entity.length) * 2
                            if (
                                entity.type == "text_link"
                                and entity.url
                                and link_start < end
                                and link_end > start
                            ):
                                offset = min(link_end, end) - start
                                quote_utf16 = (
                                    quote_utf16[:offset]
                                    + f" ({entity.url})".encode("utf-16-le")
                                    + quote_utf16[offset:]
                                )
                    quote_text = quote_utf16.decode("utf-16-le")
                    reply_chain = [Comp.Plain(quote_text)]
                    reply_message_str = quote_text

                message.message.append(
                    Comp.Reply(
                        id=reply_abm.message_id,
                        chain=reply_chain,
                        sender_id=reply_abm.sender.user_id,
                        sender_nickname=reply_abm.sender.nickname,
                        time=reply_abm.timestamp,
                        message_str=reply_message_str,
                        text=reply_message_str,
                        qq=reply_abm.sender.user_id,
                    ),
                )

        if update.message.text:
            plain_text, components = self._parse_text_entities(
                update.message.text,
                update.message.entities or (),
                message.self_id,
                strip_self_mention=True,
            )

            if (
                message.type == MessageType.GROUP_MESSAGE
                and update.message
                and update.message.reply_to_message
                and update.message.reply_to_message.from_user
                and update.message.reply_to_message.from_user.id == context.bot.id
            ):
                prefix = f"/@{context.bot.username} "
                plain_text = prefix + plain_text
                if components and isinstance(components[0], Comp.Plain):
                    components[0].text = prefix + components[0].text
                else:
                    components.insert(0, Comp.Plain(prefix))

            # 群聊场景命令特殊处理
            if plain_text.startswith("/"):
                command_parts = plain_text.split(" ", 1)
                if "@" in command_parts[0]:
                    command, bot_name = command_parts[0].split("@")
                    if bot_name == self.client.username:
                        plain_text = command + (
                            f" {command_parts[1]}" if len(command_parts) > 1 else ""
                        )
                        for component in components:
                            if isinstance(component, Comp.Plain):
                                if component.text.startswith(command_parts[0]):
                                    component.text = (
                                        command
                                        + component.text[len(command_parts[0]) :]
                                    )
                                break

            message.message.extend(components)
            message.message_str = plain_text

            if handle_start and message.message_str.strip() == "/start":
                await self.start(update, context)
                return None

        elif update.message.voice:
            file = await update.message.voice.get_file()

            file_basename = os.path.basename(cast(str, file.file_path))
            temp_dir = get_astrbot_temp_path()
            temp_path = os.path.join(temp_dir, file_basename)
            await download_file(cast(str, file.file_path), path=temp_path)
            path_wav = await MediaResolver(
                temp_path,
                media_type="audio",
                default_suffix=".wav",
            ).to_path(target_format="wav")

            record = Comp.Record(file=path_wav, url=path_wav)
            record.path = path_wav
            message.message = [record]

        elif update.message.audio:
            # Audio files use their own Bot API field and do not fall back to document.
            file = await update.message.audio.get_file()

            file_basename = os.path.basename(cast(str, file.file_path))
            temp_dir = get_astrbot_temp_path()
            temp_path = os.path.join(temp_dir, file_basename)
            await download_file(cast(str, file.file_path), path=temp_path)
            path_wav = await MediaResolver(
                temp_path,
                media_type="audio",
                default_suffix=".wav",
            ).to_path(target_format="wav")

            record = Comp.Record(file=path_wav, url=path_wav)
            record.path = path_wav
            message.message.append(record)
            _apply_caption()

        elif update.message.photo:
            photo = update.message.photo[-1]  # get the largest photo
            file = await photo.get_file()
            message.message.append(Comp.Image(file=file.file_path, url=file.file_path))
            _apply_caption()

        elif update.message.sticker:
            # 将sticker当作图片处理
            sticker = update.message.sticker
            if sticker.is_animated or sticker.is_video:
                # .tgs/.webm stickers are not bitmaps; use the static thumbnail.
                file = await sticker.thumbnail.get_file() if sticker.thumbnail else None
            else:
                file = await sticker.get_file()
            if file:
                message.message.append(
                    Comp.Image(file=file.file_path, url=file.file_path)
                )
            if sticker.emoji:
                sticker_text = f"Sticker: {sticker.emoji}"
                message.message_str = sticker_text
                message.message.append(Comp.Plain(sticker_text))

        elif update.message.document:
            file = await update.message.document.get_file()
            file_name = update.message.document.file_name or uuid.uuid4().hex
            file_path = file.file_path
            if file_path is None:
                logger.warning(
                    f"Telegram document file_path is None, cannot save the file {file_name}.",
                )
            else:
                message.message.append(
                    Comp.File(file=file_path, name=file_name, url=file_path)
                )
                _apply_caption()

        elif update.message.video:
            file = await update.message.video.get_file()
            file_name = update.message.video.file_name or uuid.uuid4().hex
            file_path = file.file_path
            if file_path is None:
                logger.warning(
                    f"Telegram video file_path is None, cannot save the file {file_name}.",
                )
            else:
                message.message.append(Comp.Video(file=file_path, path=file.file_path))
                _apply_caption()

        elif update.message.video_note:
            # Video notes carry no file_name and cannot have a caption.
            file = await update.message.video_note.get_file()
            file_path = file.file_path
            if file_path is None:
                logger.warning(
                    "Telegram video note file_path is None, cannot save the file.",
                )
            else:
                message.message.append(Comp.Video(file=file_path, path=file_path))

        return message

    async def convert_business_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        get_reply=True,
    ) -> AstrBotMessage | None:
        """Convert a Telegram Business message into an AstrBotMessage.

        Business messages reuse the regular conversion logic through a synthetic
        Update whose ``message`` points to ``update.business_message``. The
        result is then tagged with the business connection and given a
        business-specific session id so replies are sent on behalf of the
        business account and conversations stay isolated.

        Args:
            update: Telegram update carrying ``business_message``.
            context: Telegram callback context.
            get_reply: Whether to convert the replied-to message chain.

        Returns:
            Converted AstrBotMessage, or ``None`` when it should be ignored.
        """
        source = update.business_message
        if source is None:
            return None
        business_connection_id = getattr(source, "business_connection_id", None)
        if not business_connection_id:
            logger.warning(
                "Telegram Business message without business_connection_id; ignoring."
            )
            return None
        if not self._business_reply_allowed(business_connection_id):
            logger.warning(
                "Skipping Telegram Business message for connection %s: "
                "connection is disabled or not replyable.",
                business_connection_id,
            )
            return None

        synthetic_update = Update(update_id=update.update_id, message=source)
        abm = await self.convert_message(
            synthetic_update,
            context,
            get_reply=get_reply,
            handle_start=False,
        )
        if abm is None:
            return None

        abm.business_connection_id = business_connection_id
        abm.session_id = (
            f"{BUSINESS_SESSION_PREFIX}{source.chat.id}:{business_connection_id}"
        )
        abm.type = MessageType.FRIEND_MESSAGE
        return abm

    async def business_connection_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Record Telegram Business connection lifecycle updates."""
        if self._is_duplicate_update(update):
            return
        connection = update.business_connection
        if connection is None:
            return
        self._record_business_connection(connection)
        rights = getattr(connection, "rights", None)
        can_reply = getattr(rights, "can_reply", None) if rights is not None else None
        logger.info(
            "Telegram Business connection %s updated: enabled=%s can_reply=%s user=%s",
            connection.id,
            connection.is_enabled,
            can_reply,
            connection.user.id,
        )

    async def deleted_business_messages_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Log deleted Telegram Business messages.

        AstrBot's event pipeline has no message-deletion event, so deletion is
        only recorded in the log for auditing purposes.
        """
        if self._is_duplicate_update(update):
            return
        deleted = update.deleted_business_messages
        if deleted is None:
            return
        logger.info(
            "Telegram Business messages deleted: connection=%s chat=%s ids=%s",
            deleted.business_connection_id,
            deleted.chat.id,
            list(deleted.message_ids),
        )

    def _record_business_connection(self, connection) -> None:
        """Persist the latest state of a Telegram Business connection."""
        rights = getattr(connection, "rights", None)
        can_reply = getattr(rights, "can_reply", None) if rights is not None else None
        self._business_connections[connection.id] = {
            "id": connection.id,
            "user_id": connection.user.id,
            "username": getattr(connection.user, "username", None),
            "user_chat_id": connection.user_chat_id,
            "is_enabled": bool(connection.is_enabled),
            "can_reply": can_reply,
            "updated_at": int(time.time()),
        }
        self._persist_business_connections()

    def _business_reply_allowed(self, business_connection_id: str) -> bool:
        """Return whether replies may be sent for a business connection.

        Unknown connections are allowed so Telegram can enforce the final
        authorization; known connections are gated on their recorded state.
        """
        info = self._business_connections.get(business_connection_id)
        if info is None:
            return True
        if not info.get("is_enabled", True):
            return False
        return info.get("can_reply") is not False

    def _load_business_connections(self) -> None:
        """Load persisted business connection state, ignoring missing/corrupt files."""
        try:
            with open(self._business_state_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._business_connections = data
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(
                "Failed to load Telegram Business connection state from %s: %s",
                self._business_state_path,
                e,
            )

    def _persist_business_connections(self) -> None:
        """Persist business connection state atomically (best effort)."""
        try:
            os.makedirs(os.path.dirname(self._business_state_path), exist_ok=True)
            tmp_path = f"{self._business_state_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._business_connections, f, ensure_ascii=False)
            os.replace(tmp_path, self._business_state_path)
        except Exception as e:
            logger.warning(
                "Failed to persist Telegram Business connection state to %s: %s",
                self._business_state_path,
                e,
            )

    def _is_duplicate_update(self, update: Update) -> bool:
        """Return True when the update id was already processed."""
        update_id = getattr(update, "update_id", None)
        if update_id is None:
            return False
        if update_id in self._seen_update_ids:
            logger.debug("Ignoring duplicate Telegram update id=%s", update_id)
            return True
        self._seen_update_ids.append(update_id)
        return False

    @staticmethod
    def _parse_business_session(session_id: str) -> tuple[str, str] | None:
        """Decode a business session id into ``(chat_id, business_connection_id)``."""
        if not isinstance(session_id, str) or not session_id.startswith(
            BUSINESS_SESSION_PREFIX
        ):
            return None
        chat_id, sep, business_connection_id = session_id[
            len(BUSINESS_SESSION_PREFIX) :
        ].partition(":")
        if not sep or not business_connection_id:
            return None
        return chat_id, business_connection_id

    async def handle_media_group_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle messages that are part of a media group (album).

        Caches incoming messages and schedules delayed processing to collect all
        media items before sending to the pipeline. Uses debounce mechanism with
        a hard cap (max_wait) to prevent indefinite delay.
        """
        from datetime import datetime, timedelta

        source = update.message or update.business_message
        if not source:
            return

        media_group_id = source.media_group_id
        if not media_group_id:
            return

        # Initialize cache for this media group if needed
        if media_group_id not in self.media_group_cache:
            self.media_group_cache[media_group_id] = {
                "created_at": datetime.now(),
                "items": [],
            }
            logger.debug(f"Create media group cache: {media_group_id}")

        # Add this message to the cache
        entry = self.media_group_cache[media_group_id]
        entry["items"].append((update, context))
        logger.debug(
            f"Add message to media group {media_group_id}, "
            f"currently has {len(entry['items'])} items.",
        )

        # Calculate delay: if already waited too long, process immediately;
        # otherwise use normal debounce timeout
        elapsed = (datetime.now() - entry["created_at"]).total_seconds()
        if elapsed >= self.media_group_max_wait:
            delay = 0
            logger.debug(
                f"Media group {media_group_id} has reached max wait time "
                f"({elapsed:.1f}s >= {self.media_group_max_wait}s), processing immediately.",
            )
        else:
            delay = self.media_group_timeout
            logger.debug(
                f"Scheduled media group {media_group_id} to be processed in {delay} seconds "
                f"(already waited {elapsed:.1f}s)"
            )

        # Schedule/reschedule processing (replace_existing=True handles debounce)
        job_id = f"media_group_{media_group_id}"
        self.scheduler.add_job(
            self.process_media_group,
            "date",
            run_date=datetime.now() + timedelta(seconds=delay),
            args=[media_group_id],
            id=job_id,
            replace_existing=True,
        )

    async def process_media_group(self, media_group_id: str) -> None:
        """Process a complete media group by merging all collected messages.

        Args:
            media_group_id: The unique identifier for this media group
        """
        if media_group_id not in self.media_group_cache:
            logger.warning(f"Media group {media_group_id} not found in cache")
            return

        entry = self.media_group_cache.pop(media_group_id)
        updates_and_contexts = entry["items"]
        if not updates_and_contexts:
            logger.warning(f"Media group {media_group_id} is empty")
            return

        logger.info(
            f"Processing media group {media_group_id}, total {len(updates_and_contexts)} items"
        )

        try:
            # Use the first update to create the base message (with reply, caption, etc.)
            first_update, first_context = updates_and_contexts[0]
            if first_update.business_message:
                abm = await self.convert_business_message(first_update, first_context)
            else:
                abm = await self.convert_message(first_update, first_context)

            if not abm:
                logger.warning(
                    f"Failed to convert the first message of media group {media_group_id}"
                )
                return

            # Add additional media from remaining updates by reusing convert_message
            for update, context in updates_and_contexts[1:]:
                if update.business_message:
                    # Convert the message but skip reply chains (get_reply=False)
                    extra = await self.convert_business_message(
                        update, context, get_reply=False
                    )
                else:
                    extra = await self.convert_message(update, context, get_reply=False)
                if not extra:
                    continue

                # Merge only the message components (keep base session/meta from first)
                abm.message.extend(extra.message)
                logger.debug(
                    f"Added {len(extra.message)} components to media group {media_group_id}"
                )

            # Process the merged message
            await self.handle_msg(abm)
        except Exception:
            logger.error(
                f"Failed to process media group {media_group_id}", exc_info=True
            )

    def create_event(self, message: AstrBotMessage) -> TelegramPlatformEvent:
        """Creates a Telegram message event.

        Args:
            message: AstrBot message object to wrap.

        Returns:
            Created Telegram message event.
        """
        return TelegramPlatformEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
        )

    async def handle_msg(self, message: AstrBotMessage) -> None:
        self.commit_event(self.create_event(message))

    def get_client(self) -> ExtBot:
        return self.client

    async def terminate(self) -> None:
        try:
            self._terminating = True
            if self.scheduler.running:
                self.scheduler.shutdown()
            self._polling_recovery_requested.set()
            await self._shutdown_application(delete_commands=True)

            logger.info("Telegram adapter has been closed.")
        except Exception as e:
            logger.error(f"Error occurred while closing Telegram adapter: {e}")
