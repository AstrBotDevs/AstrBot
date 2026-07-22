import asyncio
import inspect
import re
import sys
import types
import typing
from typing import Any, cast

import discord
from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import File, Image, Plain, Record
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
from astrbot.core.star.star_handler import StarHandlerMetadata, star_handlers_registry
from astrbot.core.utils.media_utils import MediaResolver
from discord.abc import GuildChannel, Messageable, PrivateChannel
from discord.channel import DMChannel

from .client import DiscordBotClient
from .discord_platform_event import DiscordPlatformEvent

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

# Discord CHAT_INPUT 命令名：小写 + 字母/数字(含 Unicode，中文可用)/_/- ，1-32
# 官方近似: ^[-_\p{L}\p{N}\p{sc=Deva}\p{sc=Thai}]{1,32}$
_DISCORD_CMD_NAME_RE = re.compile(r"^[-_\w]{1,32}$")
_DISCORD_MAX_OPTIONS = 25
_DISCORD_DESC_MAX = 100


@register_platform_adapter(
    "discord", "Discord 适配器 (基于 Pycord)", support_streaming_message=False
)
class DiscordPlatformAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings
        self.bot_self_id: str | None = None
        self.registered_handlers: list = []
        self.enable_command_register = bool(
            self.config.get("discord_command_register", True)
        )
        self.guild_id = self._normalize_guild_id(
            self.config.get("discord_guild_id_for_debug", None)
        )
        self.activity_name = self.config.get("discord_activity_name", None)
        self.shutdown_event = asyncio.Event()
        self._polling_task: asyncio.Task | None = None
        # 避免 run() 前访问 client 触发 AttributeError
        self.client: DiscordBotClient | None = None

    @staticmethod
    def _normalize_guild_id(raw: Any) -> int | None:
        if raw is None or raw == "":
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            logger.warning(f"[Discord] Invalid discord_guild_id_for_debug: {raw!r}")
            return None

    def _client_ready(self) -> bool:
        return self.client is not None and self.client.user is not None

    def _ensure_bot_self_id(self) -> None:
        if self.bot_self_id is None and self.client is not None and self.client.user:
            self.bot_self_id = str(self.client.user.id)

    @staticmethod
    def _resolve_channel_id_from_session(session_id: str) -> str:
        """从 session_id 解析 channel id，不修改调用方对象。

        兼容:
        - 纯数字 channel id
        - ``platform_channelId`` / ``discord_123`` 等形式（取最后一段）
        """
        if not session_id:
            return session_id
        if "_" in session_id:
            return session_id.rsplit("_", 1)[-1]
        return session_id

    async def _resolve_channel(self, channel_id: int):
        """先读缓存，未命中再 fetch，避免冷启动 get_channel 恒为 None。"""
        if self.client is None:
            return None
        channel = self.client.get_channel(channel_id)
        if channel is not None:
            return channel
        try:
            return await self.client.fetch_channel(channel_id)
        except Exception as e:
            logger.warning(
                f"[Discord] fetch_channel({channel_id}) failed: {e}"
            )
            return None

    @override
    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        """通过会话发送消息"""
        if not self._client_ready():
            logger.error(
                "[Discord] Client is not ready (self.client.user is None); "
                "message send skipped"
            )
            return

        assert self.client is not None and self.client.user is not None
        self._ensure_bot_self_id()

        session_id = self._resolve_channel_id_from_session(session.session_id)
        channel = None
        try:
            channel_id = int(session_id)
            channel = await self._resolve_channel(channel_id)
        except (ValueError, TypeError):
            logger.warning(f"[Discord] Invalid channel ID format: {session_id}")

        message_obj = AstrBotMessage()
        if channel is not None:
            message_obj.type = self._get_message_type(channel)
            message_obj.group_id = self._get_channel_id(channel)
        else:
            logger.warning(
                f"[Discord] Can't get channel info for {session_id}, "
                "will guess message type.",
            )
            message_obj.type = MessageType.GROUP_MESSAGE
            message_obj.group_id = session_id

        message_obj.message_str = message_chain.get_plain_text()
        message_obj.sender = MessageMember(
            user_id=str(self.bot_self_id or ""),
            nickname=self.client.user.display_name,
        )
        message_obj.self_id = cast(str, self.bot_self_id)
        message_obj.session_id = session_id
        message_obj.message = message_chain.chain

        try:
            temp_event = self.create_event(message_obj)
            await temp_event.send(message_chain)
        except Exception as e:
            logger.error(
                f"[Discord] send_by_session failed for channel {session_id}: {e}",
                exc_info=True,
            )
            raise
        await super().send_by_session(session, message_chain)

    @override
    def meta(self) -> PlatformMetadata:
        """返回平台元数据"""
        return PlatformMetadata(
            "discord",
            "Discord Adapter",
            id=cast(str, self.config.get("id")),
            default_config_tmpl=self.config,
            support_streaming_message=False,
        )

    @override
    async def run(self) -> None:
        """主要运行逻辑"""

        async def on_received(message_data) -> None:
            try:
                logger.debug(f"[Discord] Message received: {message_data}")
                if self.bot_self_id is None and isinstance(message_data, dict):
                    bot_id = message_data.get("bot_id")
                    if bot_id is not None:
                        self.bot_self_id = str(bot_id)
                self._ensure_bot_self_id()
                abm = await self.convert_message(data=message_data)
                await self.handle_msg(abm)
            except Exception as e:
                logger.error(
                    f"[Discord] Error while handling received message: {e}",
                    exc_info=True,
                )

        raw_token = self.config.get("discord_token")
        token = str(raw_token).strip() if raw_token else ""
        if not token:
            logger.error(
                "[Discord] Bot token is not configured. "
                "Please set a valid token in the config file."
            )
            return

        proxy = self.config.get("discord_proxy") or None
        if isinstance(proxy, str):
            proxy = proxy.strip() or None
        allow_bot_messages = bool(self.config.get("discord_allow_bot_messages"))
        client = DiscordBotClient(token, proxy, allow_bot_messages)
        self.client = client
        client.on_message_received = on_received

        async def on_ready_once() -> None:
            try:
                self._ensure_bot_self_id()
                if self.enable_command_register:
                    await self._collect_and_register_commands()
                if self.activity_name and self.client is not None:
                    await self.client.change_presence(
                        status=discord.Status.online,
                        activity=discord.CustomActivity(name=str(self.activity_name)),
                    )
            except Exception as e:
                logger.error(
                    f"[Discord] on_ready_once_callback err: {e}",
                    exc_info=True,
                )

        client.on_ready_once_callback = on_ready_once

        def _on_polling_done(task: asyncio.Task) -> None:
            if task.cancelled():
                return
            exc = task.exception()
            if exc is not None:
                logger.error(
                    f"[Discord] Polling task crashed: {exc}",
                    exc_info=exc,
                )

        try:
            self._polling_task = asyncio.create_task(client.start_polling())
            self._polling_task.add_done_callback(_on_polling_done)
            await self.shutdown_event.wait()
        except discord.errors.LoginFailure:
            logger.error(
                "[Discord] Login failed. Please check whether the bot token is correct."
            )
        except discord.errors.ConnectionClosed:
            logger.warning("[Discord] Connection with Discord has been closed.")
        except Exception as e:
            logger.error(
                f"[Discord] Unexpected error while adapter is running: {e}",
                exc_info=True,
            )

    def _get_message_type(
        self,
        channel: Messageable | GuildChannel | PrivateChannel,
        guild_id: int | None = None,
    ) -> MessageType:
        """根据 channel 对象和 guild_id 判断消息类型"""
        if guild_id is not None:
            return MessageType.GROUP_MESSAGE
        if isinstance(channel, DMChannel) or getattr(channel, "guild", None) is None:
            return MessageType.FRIEND_MESSAGE
        return MessageType.GROUP_MESSAGE

    def _get_channel_id(
        self, channel: Messageable | GuildChannel | PrivateChannel
    ) -> str:
        """根据 channel 对象获取 ID；无 id 时返回空串，避免 'None' 污染会话"""
        channel_id = getattr(channel, "id", None)
        return str(channel_id) if channel_id is not None else ""

    def _strip_bot_leading_mentions(self, content: str, message) -> str:
        """只剥离开头属于本 bot 的 user/role mention，避免误删其它 @。

        支持开头连续的 bot user mention + bot role mention。
        """
        if not content:
            return content

        bot_user = self.client.user if self.client else None
        bot_id = bot_user.id if bot_user else None
        if bot_id is None:
            return content

        changed = True
        while changed:
            changed = False
            for mention_str in (f"<@{bot_id}>", f"<@!{bot_id}>"):
                if content.startswith(mention_str):
                    content = content[len(mention_str) :].lstrip()
                    changed = True
                    break
            if changed:
                continue

            guild = getattr(message, "guild", None)
            if not guild:
                break
            try:
                bot_member = guild.get_member(bot_id)
            except Exception:
                bot_member = None
            if not bot_member or not getattr(bot_member, "roles", None):
                break
            for role in bot_member.roles:
                role_mention_str = f"<@&{role.id}>"
                if content.startswith(role_mention_str):
                    content = content[len(role_mention_str) :].lstrip()
                    changed = True
                    break

        return content

    def _convert_message_to_abm(self, data: dict) -> AstrBotMessage:
        """将普通消息转换为 AstrBotMessage"""
        message = data["message"]
        content = message.content or ""

        content = self._strip_bot_leading_mentions(content, message)

        abm = AstrBotMessage()
        abm.type = self._get_message_type(message.channel)
        abm.group_id = self._get_channel_id(message.channel)
        abm.message_str = content

        author = message.author
        abm.sender = MessageMember(
            user_id=str(getattr(author, "id", "") or ""),
            nickname=getattr(author, "display_name", None)
            or getattr(author, "name", None)
            or "",
        )

        message_chain: list = []
        if abm.message_str:
            message_chain.append(Plain(text=abm.message_str))

        attachments = getattr(message, "attachments", None) or []
        for attachment in attachments:
            ct = (getattr(attachment, "content_type", None) or "").lower()
            url = getattr(attachment, "url", None) or ""
            filename = getattr(attachment, "filename", None) or "file"
            if not url:
                continue
            if ct.startswith("image/"):
                message_chain.append(Image(file=url, filename=filename))
            elif ct.startswith("audio/"):
                message_chain.append(Record(file=url, url=url))
            else:
                message_chain.append(File(name=filename, url=url))

        abm.message = message_chain
        abm.raw_message = message
        abm.self_id = cast(str, self.bot_self_id)
        channel_id = getattr(message.channel, "id", None)
        abm.session_id = str(channel_id) if channel_id is not None else ""
        abm.message_id = str(getattr(message, "id", "") or "")
        return abm

    async def convert_message(self, data: dict) -> AstrBotMessage:
        """将平台消息转换成 AstrBotMessage，并对音频做本地解析"""
        abm = self._convert_message_to_abm(data)
        for component in abm.message:
            if not isinstance(component, Record):
                continue
            audio_ref = component.url or component.file
            if not audio_ref:
                continue
            try:
                path_wav = await MediaResolver(
                    audio_ref,
                    media_type="audio",
                    default_suffix=".wav",
                ).to_path(target_format="wav")
                component.file = path_wav
                component.url = path_wav
                if hasattr(component, "path"):
                    component.path = path_wav
            except Exception as e:
                logger.warning(
                    f"[Discord] Failed to resolve audio attachment: {e}",
                    exc_info=True,
                )
        return abm

    def create_event(
        self, message: AstrBotMessage, followup_webhook=None
    ) -> DiscordPlatformEvent:
        """创建 Discord 消息事件"""
        return DiscordPlatformEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
            interaction_followup_webhook=followup_webhook,
        )

    async def handle_msg(self, message: AstrBotMessage, followup_webhook=None) -> None:
        """处理消息"""
        if not self._client_ready():
            logger.error(
                "[Discord] Client is not ready (self.client.user is None); "
                "message handling skipped"
            )
            return

        assert self.client is not None and self.client.user is not None
        self._ensure_bot_self_id()

        # 补写 self_id，避免上游仍是 None
        if not message.self_id and self.bot_self_id:
            message.self_id = self.bot_self_id

        message_event = self.create_event(message, followup_webhook)

        # 斜杠指令优先
        if message_event.interaction_followup_webhook is not None:
            message_event.is_wake = True
            message_event.is_at_or_wake_command = True
            self.commit_event(message_event)
            return

        raw_message = message.raw_message
        if not isinstance(raw_message, discord.Message):
            logger.warning(
                f"[Discord] Non-Message type received and ignored: {type(raw_message)}"
            )
            return

        is_mention = False
        try:
            if self.client.user in (raw_message.mentions or []):
                is_mention = True
        except Exception:
            is_mention = False

        if not is_mention and raw_message.role_mentions and raw_message.guild:
            bot_member = None
            try:
                bot_member = raw_message.guild.get_member(self.client.user.id)
            except Exception:
                bot_member = None
            if bot_member and getattr(bot_member, "roles", None):
                bot_roles = set(bot_member.roles)
                mentioned_roles = set(raw_message.role_mentions)
                if bot_roles.intersection(mentioned_roles):
                    is_mention = True

        if is_mention:
            message_event.is_wake = True
            message_event.is_at_or_wake_command = True

        self.commit_event(message_event)

    @override
    async def terminate(self) -> None:
        logger.info("[Discord] Shutting down adapter...")
        self.shutdown_event.set()

        logger.info("[Discord] Cleaning up commands...")
        if self.enable_command_register and self.client is not None:
            try:
                guild_ids = [self.guild_id] if self.guild_id else None
                await asyncio.wait_for(
                    self.client.sync_commands(commands=[], guild_ids=guild_ids),
                    timeout=10,
                )
                logger.info("[Discord] Commands cleaned up successfully.")
            except Exception as e:
                logger.warning(
                    f"[Discord] Error occurred while cleaning up commands: {e}"
                )

        if self._polling_task is not None:
            self._polling_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self._polling_task), timeout=10)
            except asyncio.CancelledError:
                logger.info("[Discord] Polling task cancelled successfully.")
            except asyncio.TimeoutError:
                logger.warning("[Discord] Polling task cancel timed out.")
            except Exception as e:
                logger.warning(
                    f"[Discord] Error occurred while cancelling polling task: {e}"
                )
            self._polling_task = None

        logger.info("[Discord] Closing client connection...")
        if self.client is not None and hasattr(self.client, "close"):
            try:
                await asyncio.wait_for(self.client.close(), timeout=10)
            except Exception as e:
                logger.warning(f"[Discord] Error occurred while closing client: {e}")
        logger.info("[Discord] Adapter shutdown complete.")

    def register_handler(self, handler_info) -> None:
        """注册处理器信息"""
        self.registered_handlers.append(handler_info)

    async def _collect_and_register_commands(self) -> None:
        """收集所有指令并注册到 Discord"""
        if self.client is None:
            logger.warning("[Discord] Client is None; skip command registration.")
            return

        logger.info("[Discord] Collecting and registering slash commands...")
        registered_commands: list[str] = []
        seen_names: set[str] = set()

        for handler_md in star_handlers_registry:
            plugin = star_map.get(handler_md.handler_module_path)
            if not plugin or not plugin.activated:
                continue
            if not handler_md.enabled:
                continue

            for event_filter in handler_md.event_filters:
                cmd_info = self._extract_command_info(event_filter, handler_md)
                if not cmd_info:
                    continue

                cmd_name, description, _cmd_filter = cmd_info
                if cmd_name in seen_names:
                    logger.warning(
                        f"[Discord] Duplicate slash command '{cmd_name}' skipped."
                    )
                    continue

                options = self._build_slash_options(handler_md.handler)
                if len(options) > _DISCORD_MAX_OPTIONS:
                    logger.warning(
                        f"[Discord] Command '{cmd_name}' has {len(options)} options; "
                        f"truncating to {_DISCORD_MAX_OPTIONS} (Discord limit)."
                    )
                    options = options[:_DISCORD_MAX_OPTIONS]

                # 无签名参数时保留通用 params，兼容原版自由文本参数
                if not options:
                    options = [
                        discord.Option(
                            name="params",
                            description="指令的所有参数",
                            type=discord.SlashCommandOptionType.string,
                            required=False,
                        ),
                    ]

                # Discord 要求 required options 排在 optional 之前
                options = sorted(options, key=lambda o: (not bool(o.required), o.name))
                param_names = [o.name for o in options]
                callback = self._create_dynamic_callback(cmd_name, param_names)

                try:
                    slash_command = discord.SlashCommand(
                        name=cmd_name,
                        description=description,
                        func=callback,
                        options=options,
                        guild_ids=[self.guild_id] if self.guild_id else None,
                    )
                    self.client.add_application_command(slash_command)
                except Exception as e:
                    logger.warning(
                        f"[Discord] Failed to add command '{cmd_name}': {e}",
                        exc_info=True,
                    )
                    continue

                seen_names.add(cmd_name)
                registered_commands.append(cmd_name)

        if registered_commands:
            logger.info(
                f"[Discord] Ready to sync {len(registered_commands)} commands: "
                f"{', '.join(registered_commands)}",
            )
        else:
            logger.info("[Discord] No commands found for registration.")

        try:
            # guild 调试模式下只同步到该 guild，避免全局配额与延迟
            if self.guild_id:
                await self.client.sync_commands(guild_ids=[self.guild_id])
            else:
                await self.client.sync_commands()
            logger.info("[Discord] Command synchronization completed.")
        except discord.HTTPException as e:
            if self._is_daily_command_quota_error(e):
                logger.warning(
                    "[Discord] Daily application command create quota reached "
                    "(30034); command sync skipped. Existing commands should "
                    "continue to work until the quota resets.",
                )
                return
            logger.warning(f"[Discord] Sync commands failed: {e}")
        except Exception as e:
            logger.warning(f"[Discord] Sync commands failed: {e}", exc_info=True)

    @staticmethod
    def _is_daily_command_quota_error(error: discord.HTTPException) -> bool:
        return getattr(error, "code", None) == 30034

    @staticmethod
    def _unwrap_optional(annotation: Any) -> Any:
        origin = typing.get_origin(annotation)
        union_types: set[Any] = {typing.Union}
        if hasattr(types, "UnionType"):
            union_types.add(types.UnionType)
        if origin in union_types:
            args = typing.get_args(annotation)
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return non_none[0]
        return annotation

    @staticmethod
    def _is_valid_discord_option_name(name: str) -> bool:
        return bool(name and _DISCORD_CMD_NAME_RE.match(name) and name == name.lower())

    @classmethod
    def _build_slash_options(cls, handler) -> list:
        """从 handler 函数签名提取参数，映射到 Discord Option。

        - 跳过 self/event、*args/**kwargs
        - 校验 option 名
        - required 优先（调用方再统一 sort）
        """
        options: list = []
        seen: set[str] = set()
        try:
            try:
                type_hints = typing.get_type_hints(handler)
            except Exception:
                type_hints = {}

            sig = inspect.signature(handler)
            for name, param in sig.parameters.items():
                if name in ("self", "event", "cls"):
                    continue
                if param.kind in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ):
                    continue
                if not cls._is_valid_discord_option_name(name):
                    logger.warning(
                        f"[Discord] Skip invalid option name '{name}' "
                        f"for handler {handler!r}"
                    )
                    continue
                if name in seen:
                    continue
                seen.add(name)

                annotation = type_hints.get(name, param.annotation)
                if annotation is inspect.Parameter.empty:
                    annotation = str
                annotation = cls._unwrap_optional(annotation)

                opt_type = discord.SlashCommandOptionType.string
                if annotation is int:
                    opt_type = discord.SlashCommandOptionType.integer
                elif annotation is float:
                    opt_type = discord.SlashCommandOptionType.number
                elif annotation is bool:
                    opt_type = discord.SlashCommandOptionType.boolean

                required = param.default is inspect.Parameter.empty
                options.append(
                    discord.Option(
                        name=name,
                        description=f"请输入 {name}"[:_DISCORD_DESC_MAX],
                        type=opt_type,
                        required=required,
                    )
                )
        except Exception as e:
            logger.warning(
                f"[Discord] Failed to build slash options for {handler!r}: {e}",
                exc_info=True,
            )
        return options

    @staticmethod
    def _format_slash_param_value(value: Any) -> str:
        """将 slash 参数序列化为命令字符串片段。

        - bool/数字直接转文本
        - 含空格或引号时用双引号包裹，避免简单 split 错位
        """
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        text = str(value)
        if not text:
            return '""'
        if re.search(r"\s", text) or any(c in text for c in "\"'"):
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return text

    def _create_dynamic_callback(self, cmd_name: str, param_names: list | None = None):
        """为每个指令动态创建异步回调。

        使用显式命名参数签名，兼容 pycord 按参数名注入 option 值；
        同时接受 *args/**kwargs 作兜底。
        """
        param_names = list(param_names or [])

        async def _handle(
            ctx: discord.ApplicationContext,
            bound: dict[str, Any],
        ) -> None:
            followup_webhook = None
            try:
                # 已响应过则不要再 defer
                if not ctx.interaction.response.is_done():
                    await asyncio.wait_for(ctx.defer(), timeout=2.5)
                followup_webhook = ctx.followup
            except asyncio.TimeoutError:
                logger.warning(
                    f"[Discord] Defer command '{cmd_name}' timeout. "
                    "Network might be too slow."
                )
                try:
                    if not ctx.interaction.response.is_done():
                        await ctx.respond("处理超时，请稍后重试。", ephemeral=True)
                except Exception:
                    pass
                return
            except Exception as e:
                logger.warning(
                    f"[Discord] Failed to defer command '{cmd_name}': {e}"
                )
                try:
                    if not ctx.interaction.response.is_done():
                        await ctx.respond("指令响应失败，请稍后重试。", ephemeral=True)
                except Exception:
                    pass
                return

            try:
                self._ensure_bot_self_id()
                logger.debug(f"[Discord] Callback triggered: {cmd_name}, bound={bound}")

                parts: list[str] = []
                if param_names:
                    for name in param_names:
                        if name not in bound or bound[name] is None:
                            continue
                        parts.append(self._format_slash_param_value(bound[name]))
                else:
                    for v in bound.values():
                        if v is not None:
                            parts.append(self._format_slash_param_value(v))
                params_str = " ".join(parts)

                message_str_for_filter = cmd_name
                if params_str:
                    message_str_for_filter += f" {params_str}"

                logger.debug(
                    f"[Discord] Slash command '{cmd_name}' triggered. "
                    f"Raw params: '{params_str}'. "
                    f"Built command string: '{message_str_for_filter}'",
                )

                channel = ctx.channel
                abm = AstrBotMessage()
                if channel is not None:
                    abm.type = self._get_message_type(channel, ctx.guild_id)
                    abm.group_id = self._get_channel_id(channel)
                else:
                    abm.type = (
                        MessageType.GROUP_MESSAGE
                        if ctx.guild_id is not None
                        else MessageType.FRIEND_MESSAGE
                    )
                    abm.group_id = (
                        str(ctx.channel_id) if ctx.channel_id is not None else ""
                    )

                author = ctx.author
                abm.message_str = message_str_for_filter
                abm.sender = MessageMember(
                    user_id=str(getattr(author, "id", "") or ""),
                    nickname=getattr(author, "display_name", None)
                    or getattr(author, "name", None)
                    or "",
                )
                abm.message = [Plain(text=message_str_for_filter)]
                abm.raw_message = ctx.interaction
                abm.self_id = cast(str, self.bot_self_id)
                abm.session_id = (
                    str(ctx.channel_id) if ctx.channel_id is not None else ""
                )
                abm.message_id = str(ctx.interaction.id)

                await self.handle_msg(abm, followup_webhook)
            except Exception as e:
                logger.error(
                    f"[Discord] Slash command '{cmd_name}' handler error: {e}",
                    exc_info=True,
                )
                try:
                    if followup_webhook is not None:
                        await followup_webhook.send(
                            "指令执行出错，请稍后重试。",
                            ephemeral=True,
                        )
                except Exception:
                    pass

        # 为 pycord 构造带显式 option 参数的回调（比纯 **kwargs 更稳）
        if param_names:
            # 生成: async def dynamic_callback(ctx, a=None, b=None, *args, **kwargs)
            args_sig = ", ".join(f"{n}=None" for n in param_names)
            # 注意：参数名已通过 Discord 名校验，可安全用于代码生成
            func_src = (
                f"async def dynamic_callback(ctx, {args_sig}, *args, **kwargs):\n"
                f"    bound = {{}}\n"
            )
            for n in param_names:
                func_src += f"    bound[{n!r}] = {n} if {n} is not None else kwargs.get({n!r})\n"
            func_src += (
                "    # 位置参兜底\n"
                "    if args:\n"
                f"        _names = {param_names!r}\n"
                "        for _i, _v in enumerate(args):\n"
                "            if _i < len(_names) and bound.get(_names[_i]) is None:\n"
                "                bound[_names[_i]] = _v\n"
                "    for _k, _v in kwargs.items():\n"
                "        if bound.get(_k) is None:\n"
                "            bound[_k] = _v\n"
                "    await _handle(ctx, bound)\n"
            )
            local_ns: dict[str, Any] = {"_handle": _handle}
            try:
                exec(func_src, local_ns)  # noqa: S102 — 参数名已白名单校验
                return local_ns["dynamic_callback"]
            except Exception as e:
                logger.warning(
                    f"[Discord] Failed to build typed callback for '{cmd_name}': {e}; "
                    "falling back to **kwargs callback.",
                    exc_info=True,
                )

        async def dynamic_callback(
            ctx: discord.ApplicationContext, *args, **kwargs
        ) -> None:
            bound: dict[str, Any] = dict(kwargs)
            if args and param_names:
                for idx, value in enumerate(args):
                    if idx < len(param_names) and bound.get(param_names[idx]) is None:
                        bound[param_names[idx]] = value
            await _handle(ctx, bound)

        return dynamic_callback

    @staticmethod
    def _extract_command_info(
        event_filter: Any,
        handler_metadata: StarHandlerMetadata,
    ) -> tuple[str, str, CommandFilter | None] | None:
        """从事件过滤器中提取指令信息"""
        cmd_name = None
        cmd_filter_instance = None

        if isinstance(event_filter, CommandFilter):
            # 暂不支持子指令注册为斜杠指令
            parent_names = getattr(event_filter, "parent_command_names", None)
            if parent_names and parent_names != [""]:
                return None
            cmd_name = getattr(event_filter, "command_name", None)
            cmd_filter_instance = event_filter
        elif isinstance(event_filter, CommandGroupFilter):
            # 暂不支持指令组直接注册为斜杠指令
            return None

        if not cmd_name or not isinstance(cmd_name, str):
            return None

        cmd_name = cmd_name.strip()
        if not cmd_name:
            return None

        # Discord 允许 Unicode（含中文），须全小写、1-32
        if cmd_name != cmd_name.lower() or not _DISCORD_CMD_NAME_RE.match(cmd_name):
            logger.warning(
                f"[Discord] 跳过无法注册的斜杠命令名: '{cmd_name}'。"
                "须为 1-32 位小写字符（可用中文/字母/数字/_/-），"
                "大写或非法字符请改名或通过 alias 触发。"
            )
            return None

        handler = handler_metadata.handler
        description = ""
        doc = getattr(handler, "__doc__", None)
        if doc:
            description = str(doc).strip().split("\n")[0].strip()
        if not description:
            description = (getattr(handler_metadata, "desc", None) or "").strip()
        if not description:
            description = f"Command: {cmd_name}"
        if len(description) > _DISCORD_DESC_MAX:
            description = f"{description[: _DISCORD_DESC_MAX - 3]}..."
        if not description.strip():
            description = f"Command: {cmd_name}"

        return cmd_name, description, cmd_filter_instance
