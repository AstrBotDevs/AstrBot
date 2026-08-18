import asyncio
from collections.abc import AsyncGenerator
from io import BytesIO
from pathlib import Path
from typing import cast

import discord
from discord.types.interactions import ComponentInteractionData

from astrbot import logger
from astrbot.core.message.components import (
    At,
    BaseMessageComponent,
    ComponentType,
    File,
    Image,
    Plain,
    Record,
    Reply,
)
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import AstrBotMessage, PlatformMetadata
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.media_utils import (
    MEDIA_MIME_EXTENSIONS,
    MediaResolver,
    describe_media_ref,
)

from .client import DiscordBotClient
from .components import DiscordEmbed, DiscordView


# 自定义Discord视图组件（兼容旧版本）
class DiscordViewComponent(BaseMessageComponent):
    type: ComponentType = ComponentType.Unknown

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
        self._client = client
        self.interaction_followup_webhook = interaction_followup_webhook

    async def send(self, message: MessageChain):
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
            logger.error(f"[Discord] 解析消息链时失败: {e}", exc_info=True)
            return self._failure_send_result(
                str(e),
                message_count=len(message.chain),
            )

        from astrbot.core.platform.message_limits import (
            DISCORD_TEXT_LIMIT,
            split_platform_text,
        )

        chunks = split_platform_text(content, DISCORD_TEXT_LIMIT)
        text_parts = list(chunks.parts) or ([""] if (files or view or embeds) else [])
        if not text_parts:
            logger.debug("[Discord] 尝试发送空消息，已忽略。")
            return self._failure_send_result(
                "empty Discord outbound payload",
                message_count=len(message.chain),
            )

        sent = 0
        try:
            for index, part in enumerate(text_parts):
                kwargs = {}
                if part:
                    kwargs["content"] = part
                if index == 0:
                    if files:
                        kwargs["files"] = files
                    if view:
                        kwargs["view"] = view
                    if embeds:
                        kwargs["embeds"] = embeds
                    if reference_message_id and not self.interaction_followup_webhook:
                        kwargs["reference"] = self._client.get_message(
                            int(reference_message_id)
                        )
                if not kwargs:
                    continue
                if self.interaction_followup_webhook:
                    await self.interaction_followup_webhook.send(**kwargs)
                else:
                    channel = await self._get_channel()
                    if not channel:
                        return self._failure_send_result(
                            f"channel unavailable for target {self.route_identity.target_id}",
                            message_count=sent,
                        )
                    if not isinstance(channel, discord.abc.Messageable):
                        logger.error(
                            f"[Discord] 频道 {channel.id} 不是可发送消息的类型"
                        )
                        return self._failure_send_result(
                            f"channel {channel.id} is not messageable",
                            message_count=sent,
                        )
                    await channel.send(**kwargs)
                sent += 1
        except Exception as e:
            logger.error(f"[Discord] 发送消息时发生未知错误: {e}", exc_info=True)
            return self._failure_send_result(
                str(e),
                message_count=sent,
            )

        if chunks.truncated:
            logger.warning("[Discord] Reached the maximum number of hard-limit chunks.")
        return await super().send(message)

    async def send_streaming(
        self, generator: AsyncGenerator[MessageChain], use_fallback: bool = False
    ):
        return await self._send_buffered_streaming_response(
            generator,
            use_fallback,
            record_empty=True,
        )

    async def _get_channel(
        self,
    ) -> discord.Thread | discord.abc.GuildChannel | discord.abc.PrivateChannel | None:
        """获取当前事件对应的频道对象"""
        try:
            channel_id = int(self.route_identity.target_id)
            return self._client.get_channel(
                channel_id,
            ) or await self._client.fetch_channel(channel_id)
        except ValueError, discord.errors.NotFound, discord.errors.Forbidden:
            logger.error(f"[Discord] 无法获取频道 {self.route_identity.target_id}")
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
                logger.debug(f"[Discord] 开始处理 Image 组件: {i}")
                try:
                    filename = getattr(i, "filename", None)
                    file_content = getattr(i, "file", None)

                    if not file_content:
                        logger.warning(f"[Discord] Image 组件没有 file 属性: {i}")
                        continue

                    if file_content.startswith("http"):
                        logger.debug(
                            "[Discord] 处理 URL 图片: %s",
                            describe_media_ref(file_content),
                        )
                        embed = discord.Embed().set_image(url=file_content)
                        embeds.append(embed)
                        continue

                    image_data = await MediaResolver(
                        file_content,
                        media_type="image",
                    ).to_base64_data(strict=True)
                    if not image_data:
                        logger.warning(
                            "[Discord] 图片解析失败: %s",
                            describe_media_ref(file_content),
                        )
                        continue

                    suffix = MEDIA_MIME_EXTENSIONS.get(image_data.mime_type, ".png")
                    files.append(
                        discord.File(
                            BytesIO(image_data.to_bytes()),
                            filename=filename or f"image{suffix}",
                        )
                    )

                except Exception:
                    # 使用 getattr 来安全地访问 i.file，以防 i 本身就是问题
                    file_info = getattr(i, "file", "未知")
                    logger.error(
                        "[Discord] 处理图片时发生未知严重错误: %s",
                        describe_media_ref(file_info),
                        exc_info=True,
                    )
            elif isinstance(i, Record):
                logger.debug(f"[Discord] 开始处理 Record 组件: {i}")
                try:
                    audio_ref = getattr(i, "file", None) or getattr(i, "url", None)
                    if not audio_ref:
                        logger.warning(f"[Discord] Record 组件没有 file/url 属性: {i}")
                        continue

                    audio_data = await MediaResolver(
                        audio_ref,
                        media_type="audio",
                        default_suffix=".wav",
                    ).to_base64_data(
                        strict=True,
                        target_format="wav",
                    )
                    if not audio_data:
                        logger.warning(
                            "[Discord] 语音解析失败: %s",
                            describe_media_ref(audio_ref),
                        )
                        continue

                    files.append(
                        discord.File(
                            BytesIO(audio_data.to_bytes()),
                            filename="audio.wav",
                        )
                    )
                except Exception:
                    audio_ref = getattr(i, "file", "未知")
                    logger.error(
                        "[Discord] 处理语音时发生未知严重错误: %s",
                        describe_media_ref(audio_ref),
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
                                f"[Discord] 获取文件失败，路径不存在: {file_path_str}",
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

        content = "".join(content_parts)
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
            logger.error(f"[Discord] 添加反应失败: {e}")

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
