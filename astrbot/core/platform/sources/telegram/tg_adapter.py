import asyncio
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

from .tg_event import TelegramPlatformEvent

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


@register_platform_adapter("telegram", "telegram 适配器")
class TelegramPlatformAdapter(Platform):
    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(event_queue)
        self.config = platform_config
        self.settings = platform_settings
        self.client_self_id = uuid.uuid4().hex[:8]

        base_url = self.config.get(
            "telegram_api_base_url", "https://api.telegram.org/bot"
        )
        if not base_url:
            base_url = "https://api.telegram.org/bot"

        file_base_url = self.config.get(
            "telegram_file_base_url", "https://api.telegram.org/file/bot"
        )
        if not file_base_url:
            file_base_url = "https://api.telegram.org/file/bot"

        self.base_url = base_url

        self.enable_command_register = self.config.get(
            "telegram_command_register", True
        )
        self.enable_command_refresh = self.config.get(
            "telegram_command_auto_refresh", True
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

    @override
    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ):
        from_username = session.session_id
        await TelegramPlatformEvent.send_with_client(
            self.client, message_chain, from_username
        )
        await super().send_by_session(session, message_chain)

    @override
    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="telegram", description="telegram 适配器", id=self.config.get("id")
        )

    @override
    async def run(self):
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

        queue = self.application.updater.start_polling()
        logger.info("Telegram Platform Adapter is running.")
        await queue

    async def register_commands(self):
        """收集所有注册的指令并注册到 Telegram"""
        try:
            commands = self.collect_commands()

            if commands:
                current_hash = hash(
                    tuple((cmd.command, cmd.description) for cmd in commands)
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

        for handler_md in star_handlers_registry._handlers:
            handler_metadata = handler_md[1]
            if not star_map[handler_metadata.handler_module_path].activated:
                continue
            for event_filter in handler_metadata.event_filters:
                cmd_info = self._extract_command_info(
                    event_filter, handler_metadata, skip_commands
                )
                if cmd_info:
                    cmd_name, description = cmd_info
                    command_dict.setdefault(cmd_name, description)

        commands_a = sorted(command_dict.keys())
        return [BotCommand(cmd, command_dict[cmd]) for cmd in commands_a]

    @staticmethod
    def _extract_command_info(
        event_filter, handler_metadata, skip_commands: set
    ) -> tuple[str, str] | None:
        """从事件过滤器中提取指令信息"""
        cmd_name = None
        is_group = False
        if isinstance(event_filter, CommandFilter) and event_filter.command_name:
            if (
                event_filter.parent_command_names
                and event_filter.parent_command_names != [""]
            ):
                return None
            cmd_name = event_filter.command_name
        elif isinstance(event_filter, CommandGroupFilter):
            if event_filter.parent_group:
                return None
            cmd_name = event_filter.group_name
            is_group = True

        if not cmd_name or cmd_name in skip_commands:
            return None

        if not re.match(r"^[a-z0-9_]+$", cmd_name) or len(cmd_name) > 32:
            logger.debug(f"跳过无法注册的命令: {cmd_name}")
            return None

        # Build description.
        description = handler_metadata.desc or (
            f"指令组: {cmd_name} (包含多个子指令)" if is_group else f"指令: {cmd_name}"
        )
        if len(description) > 30:
            description = description[:30] + "..."
        return cmd_name, description

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=self.config["start_message"]
        )

    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.debug(f"Telegram message: {update.message}")
        abm = await self.convert_message(update, context)
        if abm:
            await self.handle_msg(abm)

    async def convert_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, get_reply=True
    ) -> AstrBotMessage:
        """转换 Telegram 的消息对象为 AstrBotMessage 对象。

        @param update: Telegram 的 Update 对象。
        @param context: Telegram 的 Context 对象。
        @param get_reply: 是否获取回复消息。这个参数是为了防止多个回复嵌套。
        """
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
        message.sender = MessageMember(
            str(update.message.from_user.id), update.message.from_user.username
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
                )
            )

        if update.message.text:
            # 处理文本消息
            plain_text = update.message.text

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
                        plain_text = (
                            plain_text[: entity.offset]
                            + plain_text[entity.offset + entity.length :]
                        )

            if plain_text:
                message.message.append(Comp.Plain(plain_text))
            message.message_str = plain_text

            if message.message_str.strip() == "/start":
                await self.start(update, context)
                return

        elif update.message.voice:
            file = await update.message.voice.get_file()
            message.message = [
                Comp.Record(file=file.file_path, url=file.file_path),
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
            message.message = [
                Comp.File(file=file.file_path, name=update.message.document.file_name),
            ]

        elif update.message.video:
            file = await update.message.video.get_file()
            message.message = [
                Comp.Video(file=file.file_path, path=file.file_path),
            ]

        return message

    async def handle_msg(self, message: AstrBotMessage):
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

    async def terminate(self):
        try:
            if self.scheduler.running:
                self.scheduler.shutdown()

            await self.application.stop()

            if self.enable_command_register:
                await self.client.delete_my_commands()

            # 保险起见先判断是否存在updater对象
            if self.application.updater is not None:
                await self.application.updater.stop()

            logger.info("Telegram 适配器已被优雅地关闭")
        except Exception as e:
            logger.error(f"Telegram 适配器关闭时出错: {e}")
