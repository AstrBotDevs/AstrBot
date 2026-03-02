from astrbot.core.lang import t
import asyncio
import base64
import binascii
from collections.abc import AsyncGenerator
from io import BytesIO
from pathlib import Path
from typing import cast

import discord
from discord.types.interactions import ComponentInteractionData

from astrbot import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import (
    BaseMessageComponent,
    File,
    Image,
    Plain,
    Reply,
)
from astrbot.api.platform import AstrBotMessage, At, PlatformMetadata

from .client import DiscordBotClient
from .components import DiscordEmbed, DiscordView


# 自定义Discord视图组件（兼容旧版本）
class DiscordViewComponent(BaseMessageComponent):
    type: str = "discord_view"

    def __init__(self, view: discord.ui.View) -> None:
        self.view = view


class DiscordPlatformEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        client: DiscordBotClient,
        interaction_followup_webhook: discord.Webhook | None = None,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client
        self.interaction_followup_webhook = interaction_followup_webhook

    async def send(self, message: MessageChain) -> None:
        """发送消息到Discord平台"""
        # 解析消息链为 Discord 所需的对象
        try:
            (
                content,
                files,
                view,
                embeds,
                reference_message_id,
            ) = await self._parse_to_discord(message)
        except Exception as e:
            logger.error(t("msg-0056366b", e=e), exc_info=True)
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
            logger.debug(t("msg-fa0a9e40"))
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
                if not isinstance(channel, discord.abc.Messageable):
                    logger.error(t("msg-5ccebf9a", res=channel.id))
                    return
                await channel.send(**kwargs)

        except Exception as e:
            logger.error(t("msg-1550c1eb", e=e), exc_info=True)

        await super().send(message)

    async def send_streaming(
        self, generator: AsyncGenerator[MessageChain, None], use_fallback: bool = False
    ):
        buffer = None
        async for chain in generator:
            if not buffer:
                buffer = chain
            else:
                buffer.chain.extend(chain.chain)
        if not buffer:
            return None
        buffer.squash_plain()
        await self.send(buffer)
        return await super().send_streaming(generator, use_fallback)

    async def _get_channel(
        self,
    ) -> discord.Thread | discord.abc.GuildChannel | discord.abc.PrivateChannel | None:
        """获取当前事件对应的频道对象"""
        try:
            channel_id = int(self.session_id)
            return self.client.get_channel(
                channel_id,
            ) or await self.client.fetch_channel(channel_id)
        except (ValueError, discord.errors.NotFound, discord.errors.Forbidden):
            logger.error(t("msg-7857133d", res=self.session_id))
            return None

    async def _parse_to_discord(
        self,
        message: MessageChain,
    ) -> tuple[
        str,
        list[discord.File],
        discord.ui.View | None,
        list[discord.Embed],
        str | int | None,
    ]:
        """将 MessageChain 解析为 Discord 发送所需的内容"""
        content_parts = []
        files = []
        view = None
        embeds = []
        reference_message_id = None
        for i in message.chain:  # 遍历消息链
            if isinstance(i, Plain):  # 如果是文字类型的
                content_parts.append(i.text)
            elif isinstance(i, Reply):
                reference_message_id = i.id
            elif isinstance(i, At):
                content_parts.append(f"<@{i.qq}>")
            elif isinstance(i, Image):
                logger.debug(t("msg-050aa8d6", i=i))
                try:
                    filename = getattr(i, "filename", None)
                    file_content = getattr(i, "file", None)

                    if not file_content:
                        logger.warning(t("msg-57c802ef", i=i))
                        continue

                    discord_file = None

                    # 1. URL
                    if file_content.startswith("http"):
                        logger.debug(t("msg-f2bea7ac", file_content=file_content))
                        embed = discord.Embed().set_image(url=file_content)
                        embeds.append(embed)
                        continue

                    # 2. File URI
                    if file_content.startswith("file:///"):
                        logger.debug(t("msg-c3eae1f1", file_content=file_content))
                        path = Path(file_content[8:])
                        if await asyncio.to_thread(path.exists):
                            file_bytes = await asyncio.to_thread(path.read_bytes)
                            discord_file = discord.File(
                                BytesIO(file_bytes),
                                filename=filename or path.name,
                            )
                        else:
                            logger.warning(t("msg-6201da92", path=path))

                    # 3. Base64 URI
                    elif file_content.startswith("base64://"):
                        logger.debug(t("msg-2a6f0cd4"))
                        b64_data = file_content.split("base64://", 1)[1]
                        missing_padding = len(b64_data) % 4
                        if missing_padding:
                            b64_data += "=" * (4 - missing_padding)
                        img_bytes = base64.b64decode(b64_data)
                        discord_file = discord.File(
                            BytesIO(img_bytes),
                            filename=filename or "image.png",
                        )

                    # 4. 裸 Base64 或本地路径
                    else:
                        try:
                            logger.debug(t("msg-b589c643"))
                            b64_data = file_content
                            missing_padding = len(b64_data) % 4
                            if missing_padding:
                                b64_data += "=" * (4 - missing_padding)
                            img_bytes = base64.b64decode(b64_data)
                            discord_file = discord.File(
                                BytesIO(img_bytes),
                                filename=filename or "image.png",
                            )
                        except (ValueError, TypeError, binascii.Error):
                            logger.debug(
                                t("msg-41dd4b8f", file_content=file_content),
                            )
                            path = Path(file_content)
                            if await asyncio.to_thread(path.exists):
                                file_bytes = await asyncio.to_thread(path.read_bytes)
                                discord_file = discord.File(
                                    BytesIO(file_bytes),
                                    filename=filename or path.name,
                                )
                            else:
                                logger.warning(t("msg-6201da92", path=path))

                    if discord_file:
                        files.append(discord_file)

                except Exception:
                    # 使用 getattr 来安全地访问 i.file，以防 i 本身就是问题
                    file_info = getattr(i, "file", "未知")
                    logger.error(
                        t("msg-f59778a1", file_info=file_info),
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
                                discord.File(BytesIO(file_bytes), filename=i.name),
                            )
                        else:
                            logger.warning(
                                t("msg-85665612", file_path_str=file_path_str),
                            )
                    else:
                        logger.warning(t("msg-e55956fb", res=i.name))
                except Exception as e:
                    logger.warning(t("msg-56cc0d48", res=i.name, e=e))
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
                logger.debug(t("msg-c0705d4e", res=i.type))

        content = "".join(content_parts)
        if len(content) > 2000:
            logger.warning(t("msg-0417d127"))
            content = content[:2000]
        return content, files, view, embeds, reference_message_id

    async def react(self, emoji: str) -> None:
        """对原消息添加反应"""
        try:
            if hasattr(self.message_obj, "raw_message") and hasattr(
                self.message_obj.raw_message,
                "add_reaction",
            ):
                await cast(discord.Message, self.message_obj.raw_message).add_reaction(
                    emoji
                )
        except Exception as e:
            logger.error(t("msg-6277510f", e=e))

    def is_slash_command(self) -> bool:
        """判断是否为斜杠命令"""
        return (
            hasattr(self.message_obj, "raw_message")
            and hasattr(self.message_obj.raw_message, "type")
            and cast(discord.Interaction, self.message_obj.raw_message).type
            == discord.InteractionType.application_command
        )

    def is_button_interaction(self) -> bool:
        """判断是否为按钮交互"""
        return (
            hasattr(self.message_obj, "raw_message")
            and hasattr(self.message_obj.raw_message, "type")
            and cast(discord.Interaction, self.message_obj.raw_message).type
            == discord.InteractionType.component
        )

    def get_interaction_custom_id(self) -> str:
        """获取交互组件的custom_id"""
        if self.is_button_interaction():
            try:
                return cast(
                    ComponentInteractionData,
                    cast(discord.Interaction, self.message_obj.raw_message).data,
                ).get("custom_id", "")
            except Exception:
                pass
        return ""

    def is_mentioned(self) -> bool:
        """判断机器人是否被@"""
        if hasattr(self.message_obj, "raw_message") and hasattr(
            self.message_obj.raw_message,
            "mentions",
        ):
            return any(
                mention.id == int(self.message_obj.self_id)
                for mention in cast(
                    discord.Message, self.message_obj.raw_message
                ).mentions
            )
        return False

    def get_mention_clean_content(self) -> str:
        """获取去除@后的清洁内容"""
        if hasattr(self.message_obj, "raw_message") and hasattr(
            self.message_obj.raw_message,
            "clean_content",
        ):
            return cast(discord.Message, self.message_obj.raw_message).clean_content
        return self.message_str
