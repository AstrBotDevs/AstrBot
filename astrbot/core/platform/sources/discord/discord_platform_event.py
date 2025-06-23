import asyncio
import discord
import base64
from io import BytesIO
from pathlib import Path
from typing import Optional
import sys

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata, At
from astrbot.api.message_components import (
    Plain,
    Image,
    File,
    BaseMessageComponent,
    Reply,
)
from astrbot import logger
from .client import DiscordBotClient
from .components import DiscordEmbed, DiscordView

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


# 自定义Discord视图组件（兼容旧版本）
class DiscordViewComponent(BaseMessageComponent):
    type: str = "discord_view"

    def __init__(self, view: discord.ui.View):
        self.view = view


class DiscordPlatformEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        client: DiscordBotClient,
        interaction_followup_webhook: Optional[discord.Webhook] = None,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client
        self.interaction_followup_webhook = interaction_followup_webhook

    @override
    async def send(self, message: MessageChain):
        """发送消息到Discord平台"""

        # 解析消息链为 Discord 所需的对象
        try:
            content, files, view, embeds, reference_message_id = await self._parse_to_discord(message)
        except Exception as e:
            logger.error(f"[Discord] 解析消息链时失败: {e}", exc_info=True)
            return

        kwargs = {}
        if content:
            kwargs["content"] = content
        if files:
            kwargs["files"] = files
        if view:
            kwargs["view"] = view
        if embeds:
            kwargs["embeds"] = embeds
        if reference_message_id and not self.interaction_followup_webhook:
            kwargs["reference"] = self.client.get_message(int(reference_message_id))
        if not kwargs:
            logger.debug("[Discord] 尝试发送空消息，已忽略。")
            return

        # 根据上下文执行发送/回复操作
        try:
            # -- 斜杠指令/交互上下文 --
            if self.interaction_followup_webhook:
                await self.interaction_followup_webhook.send(**kwargs)

            # -- 常规消息上下文 --
            else:
                channel = await self._get_channel()
                if not channel:
                    return
                else:
                    await channel.send(**kwargs)

        except Exception as e:
            logger.error(f"[Discord] 发送消息时发生未知错误: {e}", exc_info=True)

        await super().send(message)

    async def _get_channel(self) -> Optional[discord.abc.Messageable]:
        """获取当前事件对应的频道对象"""
        try:
            channel_id = int(self.session_id)
            return self.client.get_channel(
                channel_id
            ) or await self.client.fetch_channel(channel_id)
        except (ValueError, discord.errors.NotFound, discord.errors.Forbidden):
            logger.error(f"[Discord] 无法获取频道 {self.session_id}")
            return None

    async def _parse_to_discord(
        self,
        message: MessageChain,
    ) -> tuple[str, list[discord.File], Optional[discord.ui.View], list[discord.Embed]]:
        """将 MessageChain 解析为 Discord 发送所需的内容"""
        content = ""
        files = []
        view = None
        embeds = []
        reference_message_id = None
        for i in message.chain:  # 遍历消息链
            if isinstance(i, Plain):  # 如果是文字类型的
                content += i.text
            elif isinstance(i, Reply):
                reference_message_id = i.id
            elif isinstance(i, At):
                content += f"<@{i.qq}>"
            elif isinstance(i, Image):
                logger.debug(f"[Discord] 开始处理 Image 组件: {i}")
                try:
                    filename = getattr(i, "filename", None)
                    file_content = getattr(i, "file", None)

                    if not file_content:
                        logger.warning(f"[Discord] Image 组件没有 file 属性: {i}")
                        continue

                    discord_file = None

                    # 1. URL
                    if file_content.startswith("http"):
                        logger.debug(f"[Discord] 处理 URL 图片: {file_content}")
                        embed = discord.Embed().set_image(url=file_content)
                        embeds.append(embed)
                        continue

                    # 2. File URI
                    elif file_content.startswith("file:///"):
                        logger.debug(f"[Discord] 处理 File URI: {file_content}")
                        path = Path(file_content[8:])
                        if await asyncio.to_thread(path.exists):
                            file_bytes = await asyncio.to_thread(path.read_bytes)
                            discord_file = discord.File(
                                BytesIO(file_bytes), filename=filename or path.name
                            )
                        else:
                            logger.warning(f"[Discord] 图片文件不存在: {path}")

                    # 3. Base64 URI
                    elif file_content.startswith("base64://"):
                        logger.debug("[Discord] 处理 Base64 URI")
                        b64_data = file_content.split("base64://", 1)[1]
                        missing_padding = len(b64_data) % 4
                        if missing_padding:
                            b64_data += "=" * (4 - missing_padding)
                        img_bytes = base64.b64decode(b64_data)
                        discord_file = discord.File(
                            BytesIO(img_bytes), filename=filename or "image.png"
                        )

                    # 4. 裸 Base64 或本地路径
                    else:
                        try:
                            logger.debug("[Discord] 尝试作为裸 Base64 处理")
                            b64_data = file_content
                            missing_padding = len(b64_data) % 4
                            if missing_padding:
                                b64_data += "=" * (4 - missing_padding)
                            img_bytes = base64.b64decode(b64_data)
                            discord_file = discord.File(
                                BytesIO(img_bytes), filename=filename or "image.png"
                            )
                        except (ValueError, TypeError, base64.binascii.Error):
                            logger.debug(
                                f"[Discord] 裸 Base64 解码失败，作为本地路径处理: {file_content}"
                            )
                            path = Path(file_content)
                            if await asyncio.to_thread(path.exists):
                                file_bytes = await asyncio.to_thread(path.read_bytes)
                                discord_file = discord.File(
                                    BytesIO(file_bytes), filename=filename or path.name
                                )
                            else:
                                logger.warning(f"[Discord] 图片文件不存在: {path}")

                    if discord_file:
                        files.append(discord_file)

                except Exception:
                    # 使用 getattr 来安全地访问 i.file，以防 i 本身就是问题
                    file_info = getattr(i, "file", "未知")
                    logger.error(
                        f"[Discord] 处理图片时发生未知严重错误: {file_info}",
                        exc_info=True,
                    )
            elif isinstance(i, File):
                try:
                    file_path_str = await i.get_file()
                    if file_path_str:
                        path = Path(file_path_str)
                        if await asyncio.to_thread(path.exists):
                            file_bytes = await asyncio.to_thread(path.read_bytes)
                            files.append(
                                discord.File(BytesIO(file_bytes),
                                             filename=i.name)
                            )
                        else:
                            logger.warning(
                                f"[Discord] 获取文件失败，路径不存在: {file_path_str}"
                            )
                    else:
                        logger.warning(f"[Discord] 获取文件失败: {i.name}")
                except Exception as e:
                    logger.warning(f"[Discord] 处理文件失败: {i.name}, 错误: {e}")
            elif isinstance(i, DiscordEmbed):
                # Discord Embed消息
                embeds.append(i.to_discord_embed())
            elif isinstance(i, DiscordView):
                # Discord视图组件（按钮、选择菜单等）
                view = i.to_discord_view()
            elif isinstance(i, DiscordViewComponent):
                # 如果消息链中包含Discord视图组件（兼容旧版本）
                if isinstance(i.view, discord.ui.View):
                    view = i.view
            else:
                logger.debug(f"[Discord] 忽略了不支持的消息组件: {i.type}")

        if len(content) > 2000:
            logger.warning("[Discord] 消息内容超过2000字符，将被截断。")
            content = content[:2000]
        return content, files, view, embeds, reference_message_id

    async def react(self, emoji: str):
        """对原消息添加反应"""
        try:
            if hasattr(self.message_obj, "raw_message") and hasattr(
                self.message_obj.raw_message, "add_reaction"
            ):
                await self.message_obj.raw_message.add_reaction(emoji)
        except Exception as e:
            logger.error(f"[Discord] 添加反应失败: {e}")

    def is_slash_command(self) -> bool:
        """判断是否为斜杠命令"""
        return (
            hasattr(self.message_obj, "raw_message")
            and hasattr(self.message_obj.raw_message, "type")
            and self.message_obj.raw_message.type
            == discord.InteractionType.application_command
        )

    def is_button_interaction(self) -> bool:
        """判断是否为按钮交互"""
        return (
            hasattr(self.message_obj, "raw_message")
            and hasattr(self.message_obj.raw_message, "type")
            and self.message_obj.raw_message.type == discord.InteractionType.component
        )

    def get_interaction_custom_id(self) -> str:
        """获取交互组件的custom_id"""
        if self.is_button_interaction():
            try:
                return self.message_obj.raw_message.data.get("custom_id", "")
            except Exception:
                pass
        return ""

    def is_mentioned(self) -> bool:
        """判断机器人是否被@"""
        if hasattr(self.message_obj, "raw_message") and hasattr(
            self.message_obj.raw_message, "mentions"
        ):
            return any(
                mention.id == int(self.message_obj.self_id)
                for mention in self.message_obj.raw_message.mentions
            )
        return False

    def get_mention_clean_content(self) -> str:
        """获取去除@后的清洁内容"""
        if hasattr(self.message_obj, "raw_message") and hasattr(
            self.message_obj.raw_message, "clean_content"
        ):
            return self.message_obj.raw_message.clean_content
        return self.message_str
