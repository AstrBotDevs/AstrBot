import asyncio
import os
import re
import sys
import uuid
from contextlib import suppress
from typing import Any, cast

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeChatAdministrators,
    BotCommandScopeChatMember,
    BotCommandScopeDefault,
    Update,
)
from telegram.constants import ChatType
from telegram.error import Forbidden, InvalidToken, NetworkError
from telegram.ext import ApplicationBuilder, ContextTypes, ExtBot, filters
from telegram.ext import CallbackQueryHandler as TelegramCallbackQueryHandler
from telegram.ext import ChatMemberHandler as TelegramChatMemberHandler
from telegram.ext import ChosenInlineResultHandler as TelegramChosenInlineResultHandler
from telegram.ext import InlineQueryHandler as TelegramInlineQueryHandler
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
from astrbot.core.utils.io import download_file
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
        self.command_registered_plugins = self._normalize_command_plugin_allowlist(
            self.config.get("telegram_command_registered_plugins"),
        )
        self.command_scopes = self._normalize_command_scope_configs(
            self.config.get("telegram_command_scopes"),
        )
        self.last_command_hashes: dict[tuple[str, str | None], int] = {}
        self.update_mode = self._normalize_update_mode(
            self.config.get("telegram_update_mode"),
        )

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

    @staticmethod
    def _normalize_update_mode(value: Any) -> str:
        mode = str(value or "polling").strip().lower()
        if mode not in {"polling", "webhook"}:
            raise ValueError(
                "telegram_update_mode must be either 'polling' or 'webhook'.",
            )
        return mode

    def _build_application(self) -> None:
        builder = (
            ApplicationBuilder()
            .token(self.config["telegram_token"])
            .base_url(self.base_url)
            .base_file_url(self.file_base_url)
        )
        telegram_proxy = self.config.get("telegram_proxy")
        if telegram_proxy:
            builder = builder.proxy(telegram_proxy)
            builder = builder.get_updates_proxy(telegram_proxy)

        self.application = builder.build()
        message_handler = TelegramMessageHandler(
            filters=filters.ALL,
            callback=self.message_handler,
        )
        self.application.add_handler(message_handler)
        self.application.add_handler(
            TelegramCallbackQueryHandler(callback=self.callback_query_handler),
        )
        self.application.add_handler(
            TelegramInlineQueryHandler(callback=self.inline_query_handler),
        )
        self.application.add_handler(
            TelegramChosenInlineResultHandler(
                callback=self.chosen_inline_result_handler,
            ),
        )
        self.application.add_handler(
            TelegramChatMemberHandler(
                callback=self.chat_member_handler,
                chat_member_types=TelegramChatMemberHandler.CHAT_MEMBER,
            ),
        )
        self.application.add_handler(
            TelegramChatMemberHandler(
                callback=self.my_chat_member_handler,
                chat_member_types=TelegramChatMemberHandler.MY_CHAT_MEMBER,
            ),
        )
        self.client = self.application.bot
        logger.debug(f"Telegram base url: {self.client.base_url}")

    @staticmethod
    def _allowed_updates() -> list[str]:
        return [
            "message",
            "callback_query",
            "inline_query",
            "chosen_inline_result",
            "chat_member",
            "my_chat_member",
        ]

    @staticmethod
    def _normalize_webhook_path(path: Any) -> str:
        normalized = str(path or "astrbot-telegram-webhook").strip()
        return normalized.lstrip("/")

    @staticmethod
    def _telegram_user_name(user: Any) -> str:
        return (
            getattr(user, "username", None)
            or getattr(user, "full_name", None)
            or getattr(user, "first_name", None)
            or "Unknown"
        )

    @staticmethod
    def _message_file_name(obj: Any, fallback_ext: str = "") -> str:
        return getattr(obj, "file_name", None) or f"{uuid.uuid4().hex}{fallback_ext}"

    @staticmethod
    def _set_chat_context(
        message: AstrBotMessage,
        chat: Any,
        *,
        fallback_user_id: str,
        source_message: Any | None = None,
    ) -> None:
        chat_id = str(getattr(chat, "id", fallback_user_id) or fallback_user_id)
        chat_type = getattr(chat, "type", ChatType.PRIVATE)
        if chat_type == ChatType.PRIVATE:
            message.type = MessageType.FRIEND_MESSAGE
            message.session_id = chat_id
            return

        message.type = MessageType.GROUP_MESSAGE
        message.group_id = chat_id
        message.session_id = chat_id
        if source_message is not None:
            message_thread_id = getattr(source_message, "message_thread_id", None)
            is_topic_message = getattr(source_message, "is_topic_message", False)
            if is_topic_message and message_thread_id:
                message.group_id += "#" + str(message_thread_id)
                message.session_id = message.group_id

    def _new_message_from_user(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        from_user: Any,
        *,
        message_text: str,
        message_id: str,
        chat: Any | None = None,
        source_message: Any | None = None,
    ) -> AstrBotMessage:
        message = AstrBotMessage()
        message.sender = MessageMember(
            str(getattr(from_user, "id", "")),
            self._telegram_user_name(from_user),
        )
        message.self_id = str(context.bot.username)
        message.raw_message = update
        message.message_str = message_text
        message.message = [Comp.Plain(message_text)] if message_text else []
        message.message_id = message_id
        self._set_chat_context(
            message,
            chat,
            fallback_user_id=str(getattr(from_user, "id", "")),
            source_message=source_message,
        )
        return message

    @staticmethod
    def _mark_telegram_event(
        message: AstrBotMessage,
        event_type: str,
        payload: Any,
        *,
        skip_llm: bool = True,
    ) -> AstrBotMessage:
        message.telegram_event_type = event_type
        message.telegram_payload = payload
        message.telegram_skip_llm = skip_llm
        return message

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
                await self.delete_registered_commands()

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

    def _webhook_start_kwargs(self) -> dict[str, Any]:
        webhook_url = str(self.config.get("telegram_webhook_url") or "").strip()
        if not webhook_url:
            raise ValueError(
                "telegram_webhook_url is required when telegram_update_mode is 'webhook'.",
            )

        kwargs: dict[str, Any] = {
            "listen": self.config.get("telegram_webhook_listen", "0.0.0.0"),
            "port": int(self.config.get("telegram_webhook_port", 8443)),
            "url_path": self._normalize_webhook_path(
                self.config.get("telegram_webhook_url_path"),
            ),
            "webhook_url": webhook_url,
            "allowed_updates": self._allowed_updates(),
            "drop_pending_updates": self.config.get(
                "telegram_webhook_drop_pending_updates",
                False,
            ),
        }
        secret_token = str(
            self.config.get("telegram_webhook_secret_token") or "",
        ).strip()
        if secret_token:
            kwargs["secret_token"] = secret_token
        cert_path = str(self.config.get("telegram_webhook_cert_path") or "").strip()
        key_path = str(self.config.get("telegram_webhook_key_path") or "").strip()
        if cert_path:
            kwargs["cert"] = cert_path
        if key_path:
            kwargs["key"] = key_path
        return kwargs

    async def _run_webhook(self) -> None:
        if not self._application_started:
            await self._start_application()

        updater = self.application.updater
        if updater is None:
            raise RuntimeError("Telegram Updater is not initialized.")

        webhook_kwargs = self._webhook_start_kwargs()
        logger.info(
            "Starting Telegram webhook on %s:%s/%s ...",
            webhook_kwargs["listen"],
            webhook_kwargs["port"],
            webhook_kwargs["url_path"],
        )
        await updater.start_webhook(**webhook_kwargs)
        logger.info("Telegram Platform Adapter webhook is running.")
        while updater.running and not self._terminating:  # noqa: ASYNC110
            await asyncio.sleep(1)

    async def _run_polling(self) -> bool:
        if not self._application_started:
            await self._start_application()

        self._polling_recovery_requested.clear()
        updater = self.application.updater
        if updater is None:
            logger.error("Telegram Updater is not initialized. Cannot start polling.")
            self._application_started = False
            await asyncio.sleep(self._polling_restart_delay)
            return False
        logger.info("Starting Telegram polling...")
        await updater.start_polling(
            allowed_updates=self._allowed_updates(),
            error_callback=self._on_polling_error,
        )
        logger.info("Telegram Platform Adapter is running.")
        while updater.running and not self._terminating:  # noqa: ASYNC110
            if self._polling_recovery_requested.is_set():
                await self._recreate_application()
                return True
            await asyncio.sleep(1)
        return False

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
        self._loop = asyncio.get_running_loop()
        self._start_command_scheduler()

        while not self._terminating:
            try:
                if self.update_mode == "webhook":
                    await self._run_webhook()
                    if not self._terminating:
                        logger.warning(
                            "Telegram webhook loop exited unexpectedly, "
                            f"retrying in {self._polling_restart_delay}s.",
                        )
                    continue

                polling_restarted = await self._run_polling()
                if polling_restarted:
                    logger.info("Telegram polling restarted with a fresh client.")
                    continue

                if not self._terminating:
                    logger.warning(
                        "Telegram polling loop exited unexpectedly, "
                        f"retrying in {self._polling_restart_delay}s.",
                    )
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
                    "Telegram adapter crashed with exception: "
                    f"{type(e).__name__}: {e!s}. "
                    f"Retrying in {self._polling_restart_delay}s.",
                )
                with suppress(Exception):
                    await self._shutdown_application(delete_commands=False)
                self._build_application()

            if not self._terminating:
                await asyncio.sleep(self._polling_restart_delay)

    def _on_polling_error(self, error: Exception) -> None:
        logger.error(
            f"Telegram polling request failed: {type(error).__name__}: {error!s}",
            exc_info=error,
        )
        if not isinstance(error, NetworkError):
            return

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
            if not commands:
                if self.command_registered_plugins == set():
                    await self.delete_registered_commands()
                    self.last_command_hashes.clear()
                return
            if len(commands) > 100:
                raise ValueError(
                    "Telegram supports at most 100 bot commands per scope. "
                    "Use telegram_command_registered_plugins to narrow registered plugins.",
                )

            current_hash = hash(
                tuple((cmd.command, cmd.description) for cmd in commands),
            )
            for scope_config in self.command_scopes:
                scope = self._build_bot_command_scope(scope_config)
                language_code = self._command_language_code(scope_config)
                scope_key = self._command_scope_key(scope_config)
                scoped_hash = hash((scope_key, language_code, current_hash))
                if scoped_hash == self.last_command_hashes.get(
                    (scope_key, language_code),
                ):
                    continue
                await self.client.delete_my_commands(
                    scope=scope,
                    language_code=language_code,
                )
                await self.client.set_my_commands(
                    commands,
                    scope=scope,
                    language_code=language_code,
                )
                self.last_command_hashes[(scope_key, language_code)] = scoped_hash

        except Exception as e:
            logger.error(f"向 Telegram 注册指令时发生错误: {e!s}")

    async def delete_registered_commands(self) -> None:
        for scope_config in self.command_scopes:
            await self.client.delete_my_commands(
                scope=self._build_bot_command_scope(scope_config),
                language_code=self._command_language_code(scope_config),
            )

    @staticmethod
    def _normalize_command_plugin_allowlist(value: Any) -> set[str] | None:
        if value in (None, ""):
            return None
        if isinstance(value, str):
            raw_items = [item.strip() for item in value.split(",")]
        elif isinstance(value, list):
            raw_items = [str(item).strip() for item in value]
        else:
            raise ValueError(
                "telegram_command_registered_plugins must be a list or CSV string.",
            )
        allowlist = {item for item in raw_items if item}
        if "*" in allowlist:
            return None
        return allowlist

    @staticmethod
    def _normalize_command_scope_configs(value: Any) -> list[dict[str, Any]]:
        if value in (None, "", []):
            return [{"type": "default"}]
        if not isinstance(value, list):
            raise ValueError("telegram_command_scopes must be a list of scope configs.")

        configs: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, str):
                configs.append({"type": item})
            elif isinstance(item, dict):
                normalized = dict(item)
                template_key = str(normalized.pop("__template_key", "") or "").strip()
                legacy_template_key = str(normalized.pop("template", "") or "").strip()
                template_key = template_key or legacy_template_key
                if not normalized.get("type") and template_key:
                    normalized["type"] = template_key
                configs.append(normalized)
            else:
                raise ValueError(
                    "telegram_command_scopes items must be strings or dicts.",
                )
        return configs or [{"type": "default"}]

    @staticmethod
    def _command_scope_key(scope_config: dict[str, Any]) -> str:
        parts = [
            str(scope_config.get("type") or "default"),
            str(scope_config.get("chat_id") or ""),
            str(scope_config.get("user_id") or ""),
        ]
        return ":".join(parts)

    @staticmethod
    def _command_language_code(scope_config: dict[str, Any]) -> str | None:
        language_code = str(scope_config.get("language_code") or "").strip()
        return language_code or None

    @staticmethod
    def _build_bot_command_scope(scope_config: dict[str, Any]):
        scope_type = str(scope_config.get("type") or "default")
        match scope_type:
            case "default":
                return BotCommandScopeDefault()
            case "all_private_chats":
                return BotCommandScopeAllPrivateChats()
            case "all_group_chats":
                return BotCommandScopeAllGroupChats()
            case "all_chat_administrators":
                return BotCommandScopeAllChatAdministrators()
            case "chat":
                chat_id = scope_config.get("chat_id")
                if chat_id in (None, ""):
                    raise ValueError("telegram command scope 'chat' requires chat_id.")
                return BotCommandScopeChat(chat_id=chat_id)
            case "chat_administrators":
                chat_id = scope_config.get("chat_id")
                if chat_id in (None, ""):
                    raise ValueError(
                        "telegram command scope 'chat_administrators' requires chat_id.",
                    )
                return BotCommandScopeChatAdministrators(chat_id=chat_id)
            case "chat_member":
                chat_id = scope_config.get("chat_id")
                user_id = scope_config.get("user_id")
                if chat_id in (None, "") or user_id in (None, ""):
                    raise ValueError(
                        "telegram command scope 'chat_member' requires chat_id and user_id.",
                    )
                return BotCommandScopeChatMember(chat_id=chat_id, user_id=user_id)
            case _:
                raise ValueError(
                    f"Unsupported Telegram command scope type: {scope_type}",
                )

    def _plugin_matches_command_allowlist(self, module_path: str) -> bool:
        if self.command_registered_plugins is None:
            return True

        plugin = star_map.get(module_path)
        candidates = {
            module_path,
            module_path.split(".")[-1],
        }
        if plugin:
            candidates.update(
                str(value)
                for value in (
                    plugin.name,
                    plugin.display_name,
                    plugin.root_dir_name,
                    plugin.module_path,
                )
                if value
            )
        return bool(candidates & self.command_registered_plugins)

    def collect_commands(self) -> list[BotCommand]:
        """从注册的处理器中收集所有指令"""
        command_dict = {}
        skip_commands = {"start"}

        for handler_md in star_handlers_registry:
            handler_metadata = handler_md
            if handler_metadata.handler_module_path not in star_map:
                continue
            if not star_map[handler_metadata.handler_module_path].activated:
                continue
            if not self._plugin_matches_command_allowlist(
                handler_metadata.handler_module_path,
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
        logger.debug(f"Telegram message: {update.message}")

        # Handle media group messages
        if update.message and update.message.media_group_id:
            await self.handle_media_group_message(update, context)
            return

        # Handle regular messages
        abm = await self.convert_message(update, context)
        if abm:
            await self.handle_msg(abm)

    async def callback_query_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        logger.debug(f"Telegram callback query: {update.callback_query}")
        abm = await self.convert_callback_query(update, context)
        if abm:
            await self.handle_msg(abm)

    async def inline_query_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        logger.debug(f"Telegram inline query: {update.inline_query}")
        abm = await self.convert_inline_query(update, context)
        if abm:
            await self.handle_msg(abm)

    async def chosen_inline_result_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        logger.debug(f"Telegram chosen inline result: {update.chosen_inline_result}")
        abm = await self.convert_chosen_inline_result(update, context)
        if abm:
            await self.handle_msg(abm)

    async def chat_member_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        logger.debug(f"Telegram chat member update: {update.chat_member}")
        abm = await self.convert_chat_member_update(
            update,
            context,
            "chat_member",
        )
        if abm:
            await self.handle_msg(abm)

    async def my_chat_member_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        logger.debug(f"Telegram my chat member update: {update.my_chat_member}")
        abm = await self.convert_chat_member_update(
            update,
            context,
            "my_chat_member",
        )
        if abm:
            await self.handle_msg(abm)

    async def convert_callback_query(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> AstrBotMessage | None:
        """Convert a Telegram callback query into an AstrBot message event."""
        callback_query = update.callback_query
        if not callback_query:
            logger.warning("Received an update without a callback query.")
            return None

        from_user = getattr(callback_query, "from_user", None)
        if not from_user:
            logger.warning("[Telegram] Received a callback query without from_user.")
            return None

        source_message = getattr(callback_query, "message", None)
        source_chat = getattr(source_message, "chat", None)
        data = getattr(callback_query, "data", None)
        game_short_name = getattr(callback_query, "game_short_name", None)
        message_text = str(data or game_short_name or "")

        message = self._new_message_from_user(
            update,
            context,
            from_user,
            message_text=message_text,
            message_id=str(
                getattr(callback_query, "id", None)
                or getattr(source_message, "message_id", "")
                or "",
            ),
            chat=source_chat,
            source_message=source_message,
        )
        return self._mark_telegram_event(message, "callback_query", callback_query)

    async def convert_inline_query(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> AstrBotMessage | None:
        inline_query = update.inline_query
        if not inline_query:
            logger.warning("Received an update without an inline query.")
            return None

        from_user = getattr(inline_query, "from_user", None)
        if not from_user:
            logger.warning("[Telegram] Received an inline query without from_user.")
            return None

        query_text = str(getattr(inline_query, "query", "") or "")
        message = self._new_message_from_user(
            update,
            context,
            from_user,
            message_text=query_text,
            message_id=str(getattr(inline_query, "id", "") or ""),
            chat=None,
        )
        return self._mark_telegram_event(message, "inline_query", inline_query)

    async def convert_chosen_inline_result(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> AstrBotMessage | None:
        chosen_result = update.chosen_inline_result
        if not chosen_result:
            logger.warning("Received an update without a chosen inline result.")
            return None

        from_user = getattr(chosen_result, "from_user", None)
        if not from_user:
            logger.warning(
                "[Telegram] Received a chosen inline result without from_user.",
            )
            return None

        query = str(getattr(chosen_result, "query", "") or "")
        result_id = str(getattr(chosen_result, "result_id", "") or "")
        message_text = query or result_id
        message = self._new_message_from_user(
            update,
            context,
            from_user,
            message_text=message_text,
            message_id=result_id or str(getattr(update, "update_id", "") or ""),
            chat=None,
        )
        return self._mark_telegram_event(
            message,
            "chosen_inline_result",
            chosen_result,
        )

    async def convert_chat_member_update(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        event_type: str,
    ) -> AstrBotMessage | None:
        chat_member_update = (
            update.chat_member if event_type == "chat_member" else update.my_chat_member
        )
        if not chat_member_update:
            logger.warning("Received an update without a chat member payload.")
            return None

        from_user = getattr(chat_member_update, "from_user", None)
        chat = getattr(chat_member_update, "chat", None)
        if not from_user:
            logger.warning(
                "[Telegram] Received a chat member update without from_user."
            )
            return None

        old_member = getattr(chat_member_update, "old_chat_member", None)
        new_member = getattr(chat_member_update, "new_chat_member", None)
        old_status = getattr(old_member, "status", "")
        new_status = getattr(new_member, "status", "")
        message_text = f"{event_type}: {old_status}->{new_status}"
        message = self._new_message_from_user(
            update,
            context,
            from_user,
            message_text=message_text,
            message_id=str(getattr(update, "update_id", "") or ""),
            chat=chat,
        )
        return self._mark_telegram_event(message, event_type, chat_member_update)

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

        telegram_message = update.message

        def _apply_caption() -> None:
            if not telegram_message:
                return
            if telegram_message.caption:
                message.message_str = telegram_message.caption
                message.message.append(Comp.Plain(message.message_str))
            if telegram_message.caption and telegram_message.caption_entities:
                for entity in telegram_message.caption_entities:
                    if entity.type == "mention":
                        name = telegram_message.caption[
                            entity.offset + 1 : entity.offset + entity.length
                        ]
                        message.message.append(Comp.At(qq=name, name=name))

        message = AstrBotMessage()
        message.session_id = str(telegram_message.chat.id)

        # 获得是群聊还是私聊
        if telegram_message.chat.type == ChatType.PRIVATE:
            message.type = MessageType.FRIEND_MESSAGE
        else:
            message.type = MessageType.GROUP_MESSAGE
            message.group_id = str(telegram_message.chat.id)
            if telegram_message.is_topic_message and telegram_message.message_thread_id:
                # Telegram Topic Group: include thread id to isolate per-topic sessions.
                message.group_id += "#" + str(telegram_message.message_thread_id)
                message.session_id = message.group_id
        message.message_id = str(telegram_message.message_id)
        new_chat_members = getattr(telegram_message, "new_chat_members", None)
        left_chat_member = getattr(telegram_message, "left_chat_member", None)
        _from_user = telegram_message.from_user or (
            new_chat_members[0] if new_chat_members else left_chat_member
        )
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

        if new_chat_members:
            member_names = ", ".join(
                self._telegram_user_name(member) for member in new_chat_members
            )
            message.message_str = f"member_joined: {member_names}"
            message.message = [Comp.Plain(message.message_str)]
            return self._mark_telegram_event(
                message,
                "member_joined",
                new_chat_members,
            )

        if left_chat_member:
            member_name = self._telegram_user_name(left_chat_member)
            message.message_str = f"member_left: {member_name}"
            message.message = [Comp.Plain(message.message_str)]
            return self._mark_telegram_event(
                message,
                "member_left",
                left_chat_member,
            )

        if telegram_message.reply_to_message and not (
            telegram_message.is_topic_message
            and telegram_message.message_thread_id
            == telegram_message.reply_to_message.message_id
        ):
            # 获取回复消息
            reply_update = Update(
                update_id=1,
                message=telegram_message.reply_to_message,
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

        if telegram_message.text:
            # 处理文本消息
            plain_text = telegram_message.text
            if (
                message.type == MessageType.GROUP_MESSAGE
                and telegram_message
                and telegram_message.reply_to_message
                and telegram_message.reply_to_message.from_user
                and telegram_message.reply_to_message.from_user.id == context.bot.id
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

            if telegram_message.entities:
                for entity in telegram_message.entities:
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

        elif telegram_message.voice:
            file = await telegram_message.voice.get_file()

            file_basename = os.path.basename(cast(str, file.file_path))
            temp_dir = get_astrbot_temp_path()
            temp_path = os.path.join(temp_dir, file_basename)
            await download_file(cast(str, file.file_path), path=temp_path)
            path_wav = os.path.join(
                temp_dir,
                f"{file_basename}.wav",
            )
            path_wav = await convert_audio_to_wav(temp_path, path_wav)

            record = Comp.Record(file=path_wav, url=path_wav)
            record.path = path_wav
            message.message = [record]

        elif telegram_message.photo:
            photo = telegram_message.photo[-1]  # get the largest photo
            file = await photo.get_file()
            message.message.append(Comp.Image(file=file.file_path, url=file.file_path))
            _apply_caption()

        elif telegram_message.sticker:
            # 将sticker当作图片处理
            file = await telegram_message.sticker.get_file()
            message.message.append(Comp.Image(file=file.file_path, url=file.file_path))
            if telegram_message.sticker.emoji:
                sticker_text = f"Sticker: {telegram_message.sticker.emoji}"
                message.message_str = sticker_text
                message.message.append(Comp.Plain(sticker_text))

        elif telegram_message.document:
            file = await telegram_message.document.get_file()
            file_name = telegram_message.document.file_name or uuid.uuid4().hex
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

        elif telegram_message.video:
            file = await telegram_message.video.get_file()
            file_name = telegram_message.video.file_name or uuid.uuid4().hex
            file_path = file.file_path
            if file_path is None:
                logger.warning(
                    f"Telegram video file_path is None, cannot save the file {file_name}.",
                )
            else:
                message.message.append(Comp.Video(file=file_path, path=file.file_path))
                _apply_caption()

        elif telegram_message.audio:
            file = await telegram_message.audio.get_file()
            file_name = self._message_file_name(telegram_message.audio, ".mp3")
            file_path = file.file_path
            if file_path is None:
                logger.warning(
                    f"Telegram audio file_path is None, cannot save the file {file_name}.",
                )
            else:
                message.message.append(
                    Comp.File(file=file_path, name=file_name, url=file_path),
                )
                _apply_caption()

        elif telegram_message.animation:
            file = await telegram_message.animation.get_file()
            file_path = file.file_path
            if file_path is None:
                logger.warning("Telegram animation file_path is None, cannot save it.")
            else:
                message.message.append(Comp.Image(file=file_path, url=file_path))
                _apply_caption()

        elif telegram_message.video_note:
            file = await telegram_message.video_note.get_file()
            file_path = file.file_path
            if file_path is None:
                logger.warning("Telegram video_note file_path is None, cannot save it.")
            else:
                message.message.append(Comp.Video(file=file_path, path=file_path))

        elif telegram_message.location:
            location = telegram_message.location
            message.message_str = f"Location: {location.latitude}, {location.longitude}"
            message.message.append(
                Comp.Location(
                    lat=location.latitude,
                    lon=location.longitude,
                    title="",
                    content=message.message_str,
                ),
            )

        elif telegram_message.venue:
            venue = telegram_message.venue
            message.message_str = f"Venue: {venue.title} {venue.address}"
            message.message.append(
                Comp.Location(
                    lat=venue.location.latitude,
                    lon=venue.location.longitude,
                    title=venue.title,
                    content=venue.address,
                ),
            )

        elif telegram_message.contact:
            contact = telegram_message.contact
            user_id = getattr(contact, "user_id", None)
            message.message_str = (
                f"Contact: {getattr(contact, 'first_name', '')} "
                f"{getattr(contact, 'last_name', '')}".strip()
                or getattr(contact, "phone_number", "")
            )
            if user_id is not None:
                message.message.append(Comp.Contact(id=int(user_id)))
            message.message.append(Comp.Plain(message.message_str))

        elif telegram_message.poll:
            poll = telegram_message.poll
            message.message_str = f"Poll: {getattr(poll, 'question', '')}"
            message.message.append(Comp.Plain(message.message_str))
            return self._mark_telegram_event(
                message,
                "poll",
                poll,
                skip_llm=False,
            )

        elif telegram_message.dice:
            dice = telegram_message.dice
            message.message_str = (
                f"Dice: {getattr(dice, 'emoji', '')}={getattr(dice, 'value', '')}"
            )
            message.message.append(Comp.Plain(message.message_str))
            return self._mark_telegram_event(
                message,
                "dice",
                dice,
                skip_llm=False,
            )

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

        try:
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
        except Exception:
            logger.error(
                f"Failed to process media group {media_group_id}", exc_info=True
            )

    async def handle_msg(self, message: AstrBotMessage) -> None:
        message_event = TelegramPlatformEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
        )
        event_type = getattr(message, "telegram_event_type", None)
        if event_type:
            message_event.set_extra("telegram_event_type", event_type)
            message_event.set_extra(
                "telegram_payload",
                getattr(message, "telegram_payload", None),
            )
        if getattr(message, "telegram_skip_llm", False):
            message_event.should_call_llm(True)
        self.commit_event(message_event)

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
