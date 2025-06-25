import asyncio
import discord
import sys
import re
from discord.abc import Messageable
from discord.channel import DMChannel
from astrbot.api.platform import (
    Platform,
    AstrBotMessage,
    MessageMember,
    PlatformMetadata,
    MessageType,
)
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain, Image, File
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.api.platform import register_platform_adapter
from astrbot import logger
from .client import DiscordBotClient
from .discord_platform_event import DiscordPlatformEvent

from typing import Any, Tuple
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import StarHandlerMetadata, star_handlers_registry

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


# 注册平台适配器
@register_platform_adapter("discord", "Discord 适配器 (基于 Pycord)")
class DiscordPlatformAdapter(Platform):
    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(event_queue)
        self.config = platform_config
        self.settings = platform_settings
        self.client_self_id = None
        self.registered_handlers = []
        # 指令注册相关
        self.enable_command_register = self.config.get("discord_command_register", True)
        self.guild_id = self.config.get("discord_guild_id_for_debug", None)
        self.activity_name = self.config.get("discord_activity_name", None)
        self.shutdown_event = asyncio.Event()
        self._polling_task = None

    @override
    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ):
        """通过会话发送消息"""
        # 创建一个 message_obj 以便在 event 中使用
        message_obj = AstrBotMessage()
        if "_" in session.session_id:
            session.session_id = session.session_id.split("_")[1]
        channel_id_str = session.session_id
        channel = None
        try:
            channel_id = int(channel_id_str)
            channel = self.client.get_channel(channel_id)
        except (ValueError, TypeError):
            logger.warning(f"[Discord] Invalid channel ID format: {channel_id_str}")

        if channel:
            message_obj.type = self._get_message_type(channel)
            message_obj.group_id = self._get_channel_id(channel)
        else:
            logger.warning(
                f"[Discord] Can't get channel info for {channel_id_str}, will guess message type."
            )
            message_obj.type = MessageType.GROUP_MESSAGE
            message_obj.group_id = session.session_id

        message_obj.message_str = message_chain.get_plain_text()
        message_obj.sender = MessageMember(
            user_id=str(self.client_self_id), nickname=self.client.user.display_name
        )
        message_obj.self_id = self.client_self_id
        message_obj.session_id = session.session_id
        message_obj.message = message_chain

        # 创建临时事件对象来发送消息
        temp_event = DiscordPlatformEvent(
            message_str=message_chain.get_plain_text(),
            message_obj=message_obj,
            platform_meta=self.meta(),
            session_id=session.session_id,
            client=self.client,
        )
        await temp_event.send(message_chain)
        await super().send_by_session(session, message_chain)

    @override
    def meta(self) -> PlatformMetadata:
        """返回平台元数据"""
        return PlatformMetadata(
            "discord",
            "Discord 适配器",
            id=self.config.get("id"),
            default_config_tmpl=self.config,
        )

    @override
    async def run(self):
        """主要运行逻辑"""
        # 初始化回调函数
        async def on_received(message_data):
            logger.debug(f"[Discord] 收到消息: {message_data}")
            if self.client_self_id is None:
                self.client_self_id = message_data.get("bot_id")
            abm = await self.convert_message(data=message_data)
            await self.handle_msg(abm)

        # 初始化 Discord 客户端
        token = str(self.config.get("discord_token"))
        if not token:
            logger.error("[Discord] Bot Token 未配置。请在配置文件中正确设置 token。")
            return

        proxy = self.config.get("discord_proxy") or None
        self.client = DiscordBotClient(token, proxy)
        self.client.on_message_received = on_received

        async def callback():
            if self.enable_command_register:
                await self._collect_and_register_commands()
            if self.activity_name:
                await self.client.change_presence(
                    status=discord.Status.online,
                    activity=discord.CustomActivity(name=self.activity_name),
                )

        self.client.on_ready_once_callback = callback

        try:
            self._polling_task = asyncio.create_task(self.client.start_polling())
            await self.shutdown_event.wait()
        except discord.errors.LoginFailure:
            logger.error("[Discord] 登录失败。请检查你的 Bot Token 是否正确。")
        except discord.errors.ConnectionClosed:
            logger.warning("[Discord] 与 Discord 的连接已关闭。")
        except Exception as e:
            logger.error(f"[Discord] 适配器运行时发生意外错误: {e}", exc_info=True)
        # finally: 不再自动调用 self.terminate()，只允许外部统一调度

    def _get_message_type(
        self, channel: Messageable, guild_id: int | None = None
    ) -> MessageType:
        """根据 channel 对象和 guild_id 判断消息类型"""
        if guild_id is not None:
            return MessageType.GROUP_MESSAGE
        if isinstance(channel, DMChannel) or getattr(channel, "guild", None) is None:
            return MessageType.FRIEND_MESSAGE
        return MessageType.GROUP_MESSAGE

    def _get_channel_id(self, channel: Messageable) -> str:
        """根据 channel 对象获取ID"""
        return str(getattr(channel, "id", None))

    def _convert_message_to_abm(self, data: dict) -> AstrBotMessage:
        """将普通消息转换为 AstrBotMessage"""
        message: discord.Message = data["message"]
        is_mentioned = data.get("is_mentioned", False)

        content = message.content

        # 如果机器人被@，移除@部分
        # 剥离 User Mention (<@id>, <@!id>)
        if self.client and self.client.user:
            mention_str = f"<@{self.client.user.id}>"
            mention_str_nickname = f"<@!{self.client.user.id}>"
            if content.startswith(mention_str):
                content = content[len(mention_str):].lstrip()
            elif content.startswith(mention_str_nickname):
                content = content[len(mention_str_nickname):].lstrip()

        # 剥离 Role Mention（bot 拥有的任一角色被提及，<@&role_id>）
        if hasattr(message, "role_mentions") and hasattr(message, "guild") and message.guild:
            bot_member = message.guild.get_member(self.client.user.id) if self.client and self.client.user else None
            if bot_member and hasattr(bot_member, "roles"):
                for role in bot_member.roles:
                    role_mention_str = f"<@&{role.id}>"
                    if content.startswith(role_mention_str):
                        content = content[len(role_mention_str):].lstrip()
                        break  # 只剥离第一个匹配的角色 mention

        abm = AstrBotMessage()
        abm.type = self._get_message_type(message.channel)
        abm.group_id = self._get_channel_id(message.channel)
        abm.message_str = content
        abm.sender = MessageMember(
            user_id=str(message.author.id), nickname=message.author.display_name
        )
        message_chain = []
        if abm.message_str:
            message_chain.append(Plain(text=abm.message_str))
        if message.attachments:
            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith(
                    "image/"
                ):
                    message_chain.append(
                        Image(file=attachment.url, filename=attachment.filename)
                    )
                else:
                    message_chain.append(
                        File(name=attachment.filename, url=attachment.url)
                    )
        abm.message = message_chain
        abm.raw_message = message
        abm.self_id = self.client_self_id
        abm.session_id = str(message.channel.id)
        abm.message_id = str(message.id)
        return abm

    async def convert_message(self, data: dict) -> AstrBotMessage:
        """将平台消息转换成 AstrBotMessage"""
        # 由于 on_interaction 已被禁用，我们只处理普通消息
        return self._convert_message_to_abm(data)

    async def handle_msg(self, message: AstrBotMessage, followup_webhook=None):
        """处理消息"""
        message_event = DiscordPlatformEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
            interaction_followup_webhook=followup_webhook,
        )

        # 检查是否为斜杠指令
        is_slash_command = message_event.interaction_followup_webhook is not None

        # 检查是否被@（User Mention 或 Bot 拥有的 Role Mention）
        is_mention = False
        # User Mention
        if self.client and self.client.user and hasattr(message.raw_message, "mentions"):
            if self.client.user in message.raw_message.mentions:
                is_mention = True
        # Role Mention（Bot 拥有的角色被提及）
        if not is_mention and hasattr(message.raw_message, "role_mentions"):
            bot_member = None
            if hasattr(message.raw_message, "guild") and message.raw_message.guild:
                try:
                    bot_member = message.raw_message.guild.get_member(self.client.user.id)
                except Exception:
                    bot_member = None
            if bot_member and hasattr(bot_member, "roles"):
                bot_roles = set(bot_member.roles)
                mentioned_roles = set(message.raw_message.role_mentions)
                if bot_roles and mentioned_roles and bot_roles.intersection(mentioned_roles):
                    is_mention = True

        # 如果是斜杠指令或被@的消息，设置为唤醒状态
        if is_slash_command or is_mention:
            message_event.is_wake = True
            message_event.is_at_or_wake_command = True

        self.commit_event(message_event)

    @override
    async def terminate(self):
        """终止适配器"""
        logger.info("[Discord] 正在终止适配器... (step 1: cancel polling task)")
        self.shutdown_event.set()
        # 优先 cancel polling_task
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await asyncio.wait_for(self._polling_task, timeout=10)
            except asyncio.CancelledError:
                logger.info("[Discord] polling_task 已取消。")
            except Exception as e:
                logger.warning(f"[Discord] polling_task 取消异常: {e}")
        logger.info("[Discord] 正在清理已注册的斜杠指令... (step 2)")
        # 清理指令
        if self.enable_command_register and self.client:
            try:
                await asyncio.wait_for(
                    self.client.sync_commands(
                        commands=[], guild_ids=[self.guild_id] if self.guild_id else None
                    ),
                    timeout=10
                )
                logger.info("[Discord] 指令清理完成。")
            except Exception as e:
                logger.error(f"[Discord] 清理指令时发生错误: {e}", exc_info=True)
        logger.info("[Discord] 正在关闭 Discord 客户端... (step 3)")
        if self.client and hasattr(self.client, "close"):
            try:
                await asyncio.wait_for(self.client.close(), timeout=10)
            except Exception as e:
                logger.warning(f"[Discord] 客户端关闭异常: {e}")
        logger.info("[Discord] 适配器已终止。")

    def register_handler(self, handler_info):
        """注册处理器信息"""
        self.registered_handlers.append(handler_info)

    async def _collect_and_register_commands(self):
        """收集所有指令并注册到Discord"""
        logger.info("[Discord] 开始收集并注册斜杠指令...")
        registered_commands = []

        for handler_md in star_handlers_registry:
            if not star_map[handler_md.handler_module_path].activated:
                continue
            for event_filter in handler_md.event_filters:
                cmd_info = self._extract_command_info(event_filter, handler_md)
                if not cmd_info:
                    continue

                cmd_name, description, cmd_filter_instance = cmd_info

                # 创建动态回调
                callback = self._create_dynamic_callback(cmd_name)

                # 创建一个通用的参数选项来接收所有文本输入
                options = [
                    discord.Option(
                        name="params",
                        description="指令的所有参数",
                        type=discord.SlashCommandOptionType.string,
                        required=False,
                    )
                ]

                # 创建SlashCommand
                slash_command = discord.SlashCommand(
                    name=cmd_name,
                    description=description,
                    func=callback,
                    options=options,
                    guild_ids=[self.guild_id] if self.guild_id else None,
                )
                self.client.add_application_command(slash_command)
                registered_commands.append(cmd_name)

        if registered_commands:
            logger.info(
                f"[Discord] 准备同步 {len(registered_commands)} 个指令: {', '.join(registered_commands)}"
            )
        else:
            logger.info("[Discord] 没有发现可注册的指令。")

        # 使用 Pycord 的方法同步指令
        # 注意：这可能需要一些时间，并且有频率限制
        await self.client.sync_commands()
        logger.info("[Discord] 指令同步完成。")

    def _create_dynamic_callback(self, cmd_name: str):
        """为每个指令动态创建一个异步回调函数"""

        async def dynamic_callback(ctx: discord.ApplicationContext, params: str = None):
            # 将平台特定的前缀'/'剥离，以适配通用的CommandFilter
            logger.debug(f"[Discord] 回调函数触发: {cmd_name}")
            logger.debug(f"[Discord] 回调函数参数: {ctx}")
            logger.debug(f"[Discord] 回调函数参数: {params}")
            message_str_for_filter = cmd_name
            if params:
                message_str_for_filter += f" {params}"

            logger.debug(
                f"[Discord] 斜杠指令 '{cmd_name}' 被触发。 "
                f"原始参数: '{params}'. "
                f"构建的指令字符串: '{message_str_for_filter}'"
            )

            # 尝试立即响应，防止超时
            followup_webhook = None
            try:
                await ctx.defer()
                followup_webhook = ctx.followup
            except Exception as e:
                logger.warning(f"[Discord] 指令 '{cmd_name}' defer 失败: {e}")

            # 2. 构建 AstrBotMessage
            abm = AstrBotMessage()
            abm.type = self._get_message_type(ctx.channel, ctx.guild_id)
            abm.group_id = self._get_channel_id(ctx.channel)
            abm.message_str = message_str_for_filter
            abm.sender = MessageMember(
                user_id=str(ctx.author.id), nickname=ctx.author.display_name
            )
            abm.message = [Plain(text=message_str_for_filter)]
            abm.raw_message = ctx.interaction
            abm.self_id = self.client_self_id
            abm.session_id = str(ctx.channel_id)
            abm.message_id = str(ctx.interaction.id)

            # 3. 将消息和 webhook 分别交给 handle_msg 处理
            await self.handle_msg(abm, followup_webhook)

        return dynamic_callback

    @staticmethod
    def _extract_command_info(
        event_filter: Any, handler_metadata: StarHandlerMetadata
    ) -> Tuple[str, str, CommandFilter] | None:
        """从事件过滤器中提取指令信息"""
        cmd_name = None
        # is_group = False
        cmd_filter_instance = None

        if isinstance(event_filter, CommandFilter):
            # 暂不支持子指令注册为斜杠指令
            if (
                event_filter.parent_command_names
                and event_filter.parent_command_names != [""]
            ):
                return None
            cmd_name = event_filter.command_name
            cmd_filter_instance = event_filter

        elif isinstance(event_filter, CommandGroupFilter):
            # 暂不支持指令组直接注册为斜杠指令，因为它们没有 handle 方法
            return None

        if not cmd_name:
            return None

        # Discord 斜杠指令名称规范
        if not re.match(r"^[a-z0-9_-]{1,32}$", cmd_name):
            logger.debug(f"[Discord] 跳过不符合规范的指令: {cmd_name}")
            return None

        description = handler_metadata.desc or f"指令: {cmd_name}"
        if len(description) > 100:
            description = f"{description[:97]}..."

        return cmd_name, description, cmd_filter_instance
