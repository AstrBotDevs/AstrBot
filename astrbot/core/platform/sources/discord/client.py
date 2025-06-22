import discord
from astrbot import logger
import sys

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


# Discord Bot客户端
class DiscordBotClient(discord.Bot):
    """Discord客户端封装"""

    def __init__(self, token: str, proxy: str = None):
        self.token = token
        self.proxy = proxy

        # 设置Intent权限，遵循权限最小化原则
        intents = discord.Intents.default()
        intents.message_content = True  # 订阅消息内容事件 (Privileged)
        intents.members = True  # 订阅成员事件 (Privileged)

        # 初始化Bot
        super().__init__(intents=intents, proxy=proxy)

        # 回调函数
        self.on_message_received = None
        self.on_ready_once_callback = None
        self._ready_once_fired = False

    @override
    async def on_ready(self):
        """当机器人成功连接并准备就绪时触发"""
        logger.info(f"[Discord] 已作为 {self.user} (ID: {self.user.id}) 登录")
        logger.info("[Discord] 客户端已准备就绪。")

        if self.on_ready_once_callback and not self._ready_once_fired:
            self._ready_once_fired = True
            try:
                await self.on_ready_once_callback()
            except Exception as e:
                logger.error(
                    f"[Discord] on_ready_once_callback 执行失败: {e}", exc_info=True)

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

    @override
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


    def _extract_interaction_content(self, interaction: discord.Interaction) -> str:
        """从交互中提取内容"""
        interaction_type = interaction.type
        interaction_data = getattr(interaction, "data", {})

        if not interaction_data:
            return ""

        if interaction_type == discord.InteractionType.application_command:
            command_name = interaction_data.get("name", "")
            if options := interaction_data.get("options", []):
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

    @override
    async def close(self):
        """关闭客户端"""
        if not self.is_closed():
            await super().close()
