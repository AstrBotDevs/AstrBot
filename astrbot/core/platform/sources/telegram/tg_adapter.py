import asyncio
import os
import re
import sys
import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import BotCommand, Update
from telegram.constants import ChatType
from telegram.ext import ApplicationBuilder, ContextTypes, ExtBot, filters
from telegram.ext import MessageHandler as TelegramMessageHandler

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_image_by_url
from astrbot.core.utils.media_utils import convert_audio_to_wav

from .tg_event import TelegramPlatformEvent

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


@register_platform_adapter("telegram", "telegram 适配器")
class TelegramPlatformAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings
        self.client_self_id = uuid.uuid4().hex[:8]

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

        self.enable_command_register = self.config.get(
            "telegram_command_register",
            True,
        )
        self.enable_command_refresh = self.config.get(
            "telegram_command_auto_refresh",
            True,
        )
        self.last_command_hash = None

        self.application = (
            ApplicationBuilder()
            .token(self.config["telegram_token"])
            .base_url(base_url)
            .base_file_url(file_base_url)
            .build()
        )
        message_handler = TelegramMessageHandler(
            filters=filters.ALL,  # receive all messages
            callback=self.message_handler,
        )
        self.application.add_handler(message_handler)
        self.client = self.application.bot
        logger.debug(f"Telegram base url: {self.client.base_url}")

        self.scheduler = AsyncIOScheduler()

        # Media group handling
        # Cache structure: {media_group_id: {"created_at": datetime, "items": [(update, context), ...]}}
        self.media_group_cache: dict[str, dict] = {}
        self.media_group_timeout = self.config.get(
            "telegram_media_group_timeout", 2.5
        )  # seconds - debounce delay between messages
        self.media_group_max_wait = self.config.get(
            "telegram_media_group_max_wait", 10.0
        )  # max seconds - hard cap to prevent indefinite delay

    @override
    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        from_username = session.session_id
        await TelegramPlatformEvent.send_with_client(
            self.client,
            message_chain,
            from_username,
        )
        await super().send_by_session(session, message_chain)

    @override
    def meta(self) -> PlatformMetadata:
        id_ = self.config.get("id") or "telegram"
        return PlatformMetadata(name="telegram", description="telegram 适配器", id=id_)

    @override
    async def run(self) -> None:
        await self.application.initialize()
        await self.application.start()

        if self.enable_command_register:
            await self.register_commands()

        if self.enable_command_refresh and self.enable_command_register:
            self.scheduler.add_job(
                self.register_commands,
                "interval",
                seconds=self.config.get("telegram_command_register_interval", 300),
                id="telegram_command_register",
                misfire_grace_time=60,
            )
            self.scheduler.start()

        if not self.application.updater:
            logger.error("Telegram Updater is not initialized. Cannot start polling.")
            return

        queue = self.application.updater.start_polling()
        logger.info("Telegram Platform Adapter is running.")
        await queue

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
            if not star_map[handler_metadata.handler_module_path].activated:
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
        logger.debug(f"Telegram message: {update.message}")

        # Handle media group messages
        if update.message and update.message.media_group_id:
            await self.handle_media_group_message(update, context)
            return

        # Handle regular messages
        abm = await self.convert_message(update, context)
        if abm:
            await self.handle_msg(abm)

    async def convert_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        get_reply=True,
    ) -> AstrBotMessage | None:
        """转换 Telegram 的消息对象为 AstrBotMessage 对象。

        @param update: Telegram 的 Update 对象。
        @param context: Telegram 的 Context 对象。
        @param get_reply: 是否获取回复消息。这个参数是为了防止多个回复嵌套。
        """
        if not update.message:
            logger.warning("Received an update without a message.")
            return None

        message = AstrBotMessage()
        message.session_id = str(update.message.chat.id)

        # 获得是群聊还是私聊
        if update.message.chat.type == ChatType.PRIVATE:
            message.type = MessageType.FRIEND_MESSAGE
        else:
            message.type = MessageType.GROUP_MESSAGE
            message.group_id = str(update.message.chat.id)
            if update.message.message_thread_id:
                # Topic Group
                message.group_id += "#" + str(update.message.message_thread_id)
                message.session_id = message.group_id
        message.message_id = str(update.message.message_id)
        _from_user = update.message.from_user
        if not _from_user:
            logger.warning("[Telegram] Received a message without a from_user.")
            return None
        message.sender = MessageMember(
            str(_from_user.id),
            _from_user.username or "Unknown",
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
                message.message.append(
                    Comp.Reply(
                        id=reply_abm.message_id,
                        chain=reply_abm.message,
                        sender_id=reply_abm.sender.user_id,
                        sender_nickname=reply_abm.sender.nickname,
                        time=reply_abm.timestamp,
                        message_str=reply_abm.message_str,
                        text=reply_abm.message_str,
                        qq=reply_abm.sender.user_id,
                    ),
                )

        if update.message.text:
            # 处理文本消息
            plain_text = update.message.text
            if (
                message.type == MessageType.GROUP_MESSAGE
                and update.message
                and update.message.reply_to_message
                and update.message.reply_to_message.from_user
                and update.message.reply_to_message.from_user.id == context.bot.id
            ):
                plain_text2 = f"/@{context.bot.username} " + plain_text
                plain_text = plain_text2

            # 群聊场景命令特殊处理
            if plain_text.startswith("/"):
                command_parts = plain_text.split(" ", 1)
                if "@" in command_parts[0]:
                    command, bot_name = command_parts[0].split("@")
                    if bot_name == self.client.username:
                        plain_text = command + (
                            f" {command_parts[1]}" if len(command_parts) > 1 else ""
                        )

            if update.message.entities:
                for entity in update.message.entities:
                    if entity.type == "mention":
                        name = plain_text[
                            entity.offset + 1 : entity.offset + entity.length
                        ]
                        message.message.append(Comp.At(qq=name, name=name))
                        # 如果mention是当前bot则移除；否则保留
                        if name.lower() == context.bot.username.lower():
                            plain_text = (
                                plain_text[: entity.offset]
                                + plain_text[entity.offset + entity.length :]
                            )

            if plain_text:
                message.message.append(Comp.Plain(plain_text))
            message.message_str = plain_text

            if message.message_str.strip() == "/start":
                await self.start(update, context)
                return None

        elif update.message.voice:
            file = await update.message.voice.get_file()

            file_basename = os.path.basename(file.file_path)
            temp_dir = get_astrbot_temp_path()
            temp_path = os.path.join(temp_dir, file_basename)
            temp_path = await download_image_by_url(file.file_path, path=temp_path)
            path_wav = os.path.join(
                temp_dir,
                f"{file_basename}.wav",
            )
            path_wav = await convert_audio_to_wav(temp_path, path_wav)

            message.message = [
                Comp.Record(file=path_wav, url=path_wav),
            ]

        elif update.message.photo:
            photo = update.message.photo[-1]  # get the largest photo
            file = await photo.get_file()
            message.message.append(Comp.Image(file=file.file_path, url=file.file_path))
            if update.message.caption:
                message.message_str = update.message.caption
                message.message.append(Comp.Plain(message.message_str))
            if update.message.caption_entities:
                for entity in update.message.caption_entities:
                    if entity.type == "mention":
                        name = message.message_str[
                            entity.offset + 1 : entity.offset + entity.length
                        ]
                        message.message.append(Comp.At(qq=name, name=name))

        elif update.message.sticker:
            # 将sticker当作图片处理
            file = await update.message.sticker.get_file()
            message.message.append(Comp.Image(file=file.file_path, url=file.file_path))
            if update.message.sticker.emoji:
                sticker_text = f"Sticker: {update.message.sticker.emoji}"
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

        return message

    async def handle_media_group_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle messages that are part of a media group (album).

        Caches incoming messages and schedules delayed processing to collect all
        media items before sending to the pipeline. Uses debounce mechanism with
        a hard cap (max_wait) to prevent indefinite delay.
        """
        from datetime import datetime, timedelta

        if not update.message:
            return

        media_group_id = update.message.media_group_id
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

        # Use the first update to create the base message (with reply, caption, etc.)
        first_update, first_context = updates_and_contexts[0]
        abm = await self.convert_message(first_update, first_context)

        if not abm:
            logger.warning(
                f"Failed to convert the first message of media group {media_group_id}"
            )
            return

        # Add additional media from remaining updates by reusing convert_message
        for update, context in updates_and_contexts[1:]:
            # Convert the message but skip reply chains (get_reply=False)
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

    async def handle_msg(self, message: AstrBotMessage) -> None:
        message_event = TelegramPlatformEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
        )
        self.commit_event(message_event)

    def get_client(self) -> ExtBot:
        return self.client

    async def terminate(self) -> None:
        try:
            if self.scheduler.running:
                self.scheduler.shutdown()

            await self.application.stop()

            if self.enable_command_register:
                await self.client.delete_my_commands()

            # 保险起见先判断是否存在updater对象
            if self.application.updater is not None:
                await self.application.updater.stop()

            logger.info("Telegram adapter has been closed.")
        except Exception as e:
            logger.error(f"Error occurred while closing Telegram adapter: {e}")
