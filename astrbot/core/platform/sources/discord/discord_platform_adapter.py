import asyncio
import discord
from typing import List

from astrbot.api.platform import (
    Platform,
    AstrBotMessage,
    MessageMember,
    PlatformMetadata,
    MessageType,
)
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain, Image, File, BaseMessageComponent
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.api.platform import register_platform_adapter
from astrbot import logger

try:
    from .discord_platform_event import DiscordPlatformEvent
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    from discord_platform_event import DiscordPlatformEvent


# Discord专用组件
class DiscordEmbed(BaseMessageComponent):
    """Discord Embed消息组件"""

    type: str = "discord_embed"

    def __init__(
        self,
        title: str = None,
        description: str = None,
        color: int = None,
        url: str = None,
        thumbnail: str = None,
        image: str = None,
        footer: str = None,
        fields: List[dict] = None,
    ):
        self.title = title
        self.description = description
        self.color = color
        self.url = url
        self.thumbnail = thumbnail
        self.image = image
        self.footer = footer
        self.fields = fields or []

    def to_discord_embed(self) -> discord.Embed:
        """转换为Discord Embed对象"""
        embed = discord.Embed()

        if self.title:
            embed.title = self.title
        if self.description:
            embed.description = self.description
        if self.color:
            embed.color = self.color
        if self.url:
            embed.url = self.url
        if self.thumbnail:
            embed.set_thumbnail(url=self.thumbnail)
        if self.image:
            embed.set_image(url=self.image)
        if self.footer:
            embed.set_footer(text=self.footer)

        for field in self.fields:
            embed.add_field(
                name=field.get("name", ""),
                value=field.get("value", ""),
                inline=field.get("inline", False),
            )

        return embed


class DiscordButton(BaseMessageComponent):
    """Discord按钮组件"""

    type: str = "discord_button"

    def __init__(
        self,
        label: str,
        custom_id: str = None,
        style: str = "primary",
        emoji: str = None,
        url: str = None,
        disabled: bool = False,
    ):
        self.label = label
        self.custom_id = custom_id
        self.style = style
        self.emoji = emoji
        self.url = url
        self.disabled = disabled


class DiscordView(BaseMessageComponent):
    """Discord视图组件，包含按钮和选择菜单"""

    type: str = "discord_view"

    def __init__(
        self, components: List[BaseMessageComponent] = None, timeout: float = None
    ):
        self.components = components or []
        self.timeout = timeout

    def to_discord_view(self) -> discord.ui.View:
        """转换为Discord View对象"""
        view = discord.ui.View(timeout=self.timeout)

        for component in self.components:
            if isinstance(component, DiscordButton):
                button_style = getattr(
                    discord.ButtonStyle, component.style, discord.ButtonStyle.primary
                )

                if component.url:
                    # URL按钮
                    button = discord.ui.Button(
                        label=component.label,
                        style=discord.ButtonStyle.link,
                        url=component.url,
                        emoji=component.emoji,
                        disabled=component.disabled,
                    )
                else:
                    # 普通按钮
                    button = discord.ui.Button(
                        label=component.label,
                        style=button_style,
                        custom_id=component.custom_id,
                        emoji=component.emoji,
                        disabled=component.disabled,
                    )

                view.add_item(button)

        return view


# Discord Bot客户端
class DiscordBotClient(discord.Bot):
    """Discord客户端封装"""

    def __init__(self, token: str, proxy: str = None):
        self.token = token
        self.proxy = proxy

        # 设置Intent权限，为了最大兼容性使用all()
        intents = discord.Intents.all()

        # 初始化Bot
        super().__init__(intents=intents, proxy=proxy)

        # 回调函数
        self.on_message_received = None

    async def on_ready(self):
        """当机器人成功连接并准备就绪时触发"""
        logger.info(f"[Discord] 已作为 {self.user} (ID: {self.user.id}) 登录")
        logger.info("[Discord] 客户端已准备就绪。")

    def _create_message_data(self, message: discord.Message) -> dict:
        """从 discord.Message 创建数据字典"""
        is_mentioned = self.user in message.mentions
        return {
            "message": message,
            "bot_id": str(self.user.id),
            "content": message.content,
            "username": message.author.display_name,
            "userid": str(message.author.id),
            "message_id": str(message.id),
            "channel_id": str(message.channel.id),
            "guild_id": str(message.guild.id) if message.guild else None,
            "type": "message",
            "is_mentioned": is_mentioned,
            "clean_content": message.clean_content,
        }

    def _create_interaction_data(self, interaction: discord.Interaction) -> dict:
        """从 discord.Interaction 创建数据字典"""
        return {
            "interaction": interaction,
            "bot_id": str(self.user.id),
            "content": self._extract_interaction_content(interaction),
            "username": interaction.user.display_name,
            "userid": str(interaction.user.id),
            "message_id": str(interaction.id),
            "channel_id": str(interaction.channel_id)
            if interaction.channel_id
            else None,
            "guild_id": str(interaction.guild_id) if interaction.guild_id else None,
            "type": "interaction",
        }

    async def on_message(self, message: discord.Message):
        """当接收到消息时触发"""
        if message.author.bot:
            return

        logger.debug(
            f"[Discord] 收到原始消息 from {message.author.name}: {message.content}"
        )

        if self.on_message_received:
            message_data = self._create_message_data(message)
            await self.on_message_received(message_data)

    async def on_interaction(self, interaction: discord.Interaction):
        """当接收到交互（按钮点击等）时触发"""
        logger.debug(
            f"[Discord] 收到交互 from {interaction.user.name}: {interaction.data}"
        )

        if self.on_message_received:
            interaction_data = self._create_interaction_data(interaction)
            await self.on_message_received(interaction_data)

    def _extract_interaction_content(self, interaction: discord.Interaction) -> str:
        """从交互中提取内容"""
        interaction_type = interaction.type
        interaction_data = getattr(interaction, "data", {})

        if not interaction_data:
            return ""

        if interaction_type == discord.InteractionType.application_command:
            command_name = interaction_data.get("name", "")
            options = interaction_data.get("options", [])
            if options:
                params = " ".join(
                    [f"{opt['name']}:{opt.get('value', '')}" for opt in options]
                )
                return f"/{command_name} {params}"
            return f"/{command_name}"

        elif interaction_type == discord.InteractionType.component:
            custom_id = interaction_data.get("custom_id", "")
            component_type = interaction_data.get("component_type", "")
            return f"component:{custom_id}:{component_type}"

        return str(interaction_data)

    async def start_polling(self):
        """开始轮询消息，这是个阻塞方法"""
        await self.start(self.token)

    async def close(self):
        """关闭客户端"""
        if not self.is_closed():
            await super().close()


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
            "Discord 适配器 (基于 Pycord)",
            id=self.config.get("id"),
            default_config_tmpl=self.config,
        )

    async def run(self):
        """主要运行逻辑"""

        # 初始化回调函数
        async def on_received(message_data):
            logger.debug(f"[Discord] 收到消息: {message_data}")
            abm = await self.convert_message(data=message_data)
            await self.handle_msg(abm)

        # 初始化 Discord 客户端
        token = str(self.config.get("discord_token"))
        if not token or "在此处" in token:
            logger.error("[Discord] Bot Token 未配置。请在配置文件中正确设置 token。")
            return

        proxy = self.config.get("discord_proxy") or None
        self.client = DiscordBotClient(token, proxy)
        self.client.on_message_received = on_received

        # 注册已登记的命令处理器
        self._register_handlers()

        try:
            await self.client.start_polling()
        except discord.errors.LoginFailure:
            logger.error("[Discord] 登录失败。请检查你的 Bot Token 是否正确。")
        except discord.errors.ConnectionClosed:
            logger.warning("[Discord] 与 Discord 的连接已关闭。")
        except Exception as e:
            logger.error(f"[Discord] 适配器运行时发生意外错误: {e}", exc_info=True)

    def _register_handlers(self):
        """注册命令处理器"""
        # 这里可以扫描插件中使用装饰器的方法并注册
        # 由于AstrBot的插件系统，这部分需要在插件加载时处理
        pass

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
        interaction = data["interaction"]
        abm = AstrBotMessage()

        abm.type, abm.group_id = self._determine_message_type(
            interaction.channel, interaction.guild_id
        )

        abm.message_str = data["content"]
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
        message = data["message"]
        is_mentioned = data.get("is_mentioned", False)
        clean_content = data.get("clean_content", message.content)
        abm = AstrBotMessage()

        abm.type, abm.group_id = self._determine_message_type(message.channel)

        abm.message_str = clean_content if is_mentioned else message.content
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
            hasattr(message.raw_message, "mentions")
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
