import asyncio
import discord
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

    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ):
        """通过会话发送消息"""
        # 创建临时事件对象来发送消息
        temp_event = DiscordPlatformEvent(
            message_str="",
            message_obj=None,
            platform_meta=self.meta(),
            session_id=session.session_id,
            client=self.client,
        )
        await temp_event.send(message_chain)
        await super().send_by_session(session, message_chain)

    def meta(self) -> PlatformMetadata:
        """返回平台元数据"""
        return PlatformMetadata(
            "discord",
            "Discord 适配器",
            id=self.config.get("id"),
            default_config_tmpl=self.config,
        )

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

        try:
            await self.client.start_polling()
        except discord.errors.LoginFailure:
            logger.error("[Discord] 登录失败。请检查你的 Bot Token 是否正确。")
        except discord.errors.ConnectionClosed:
            logger.warning("[Discord] 与 Discord 的连接已关闭。")
        except Exception as e:
            logger.error(f"[Discord] 适配器运行时发生意外错误: {e}", exc_info=True)

    def _determine_message_type(
        self, channel, guild_id=None
    ) -> tuple[MessageType, str]:
        """判断消息类型和群组ID"""
        if guild_id is None and (
            isinstance(channel, discord.DMChannel)
            or getattr(channel, "guild", None) is None
        ):
            return MessageType.FRIEND_MESSAGE, ""

        gid = guild_id or getattr(channel, "guild", None).id
        return MessageType.GROUP_MESSAGE, str(gid)

    def _convert_interaction_to_abm(self, data: dict) -> AstrBotMessage:
        """将交互事件转换为 AstrBotMessage"""
        interaction: discord.Interaction = data["interaction"]
        abm = AstrBotMessage()

        abm.type, abm.group_id = self._determine_message_type(
            interaction.channel, interaction.guild_id
        )

        # 对于交互事件，message_str 通常没有意义，且可能导致被闲聊等通用插件错误响应。
        # 将其清空，以确保只有专门的指令处理器会响应。
        abm.message_str = ""
        abm.sender = MessageMember(
            user_id=str(interaction.user.id), nickname=interaction.user.display_name
        )
        abm.message = [Plain(text=data["content"])]
        abm.raw_message = interaction
        abm.self_id = self.client_self_id
        abm.session_id = (
            str(interaction.channel_id)
            if interaction.channel_id
            else str(interaction.user.id)
        )
        abm.message_id = str(interaction.id)
        return abm

    def _convert_message_to_abm(self, data: dict) -> AstrBotMessage:
        """将普通消息转换为 AstrBotMessage"""
        message: discord.Message = data["message"]
        is_mentioned = data.get("is_mentioned", False)

        content = message.content

        # 如果机器人被@，移除@部分
        if (
            is_mentioned
            and self.client
            and self.client.user
            and self.client.user in message.mentions
        ):
            # 构建机器人的@字符串，格式为 <@USER_ID> 或 <@!USER_ID>
            mention_str = f"<@{self.client.user.id}>"
            mention_str_nickname = (
                f"<@!{self.client.user.id}>"  # 有些客户端会使用带!的格式
            )

            if content.startswith(mention_str):
                content = content[len(mention_str) :].lstrip()
            elif content.startswith(mention_str_nickname):
                content = content[len(mention_str_nickname) :].lstrip()

        abm = AstrBotMessage()

        abm.type, abm.group_id = self._determine_message_type(message.channel)

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
        if data.get("type") in ["interaction", "slash_command"]:
            return self._convert_interaction_to_abm(data)
        else:
            return self._convert_message_to_abm(data)

    async def handle_msg(self, message: AstrBotMessage):
        """处理消息"""
        message_event = DiscordPlatformEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
        )

        # 如果是被@的消息，设置为唤醒状态
        if (
            self.client
            and self.client.user
            and hasattr(message.raw_message, "mentions")
            and self.client.user in message.raw_message.mentions
        ):
            message_event.is_wake = True
            message_event.is_at_or_wake_command = True

        self.commit_event(message_event)

    async def terminate(self):
        """终止适配器"""
        logger.info("[Discord] 正在终止适配器...")
        if self.client and hasattr(self.client, "close"):
            await self.client.close()
        logger.info("[Discord] 适配器已终止。")

    def register_handler(self, handler_info):
        """注册处理器信息"""
        self.registered_handlers.append(handler_info)
