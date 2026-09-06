import asyncio
from collections.abc import AsyncGenerator
from io import BytesIO
from pathlib import Path
from typing import TypedDict

import discord

from astrbot import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import (
    BaseMessageComponent,
    ComponentType,
    File,
    Image,
    Plain,
    Record,
    Reply,
)
from astrbot.api.platform import (
    AstrBotMessage,
    At,
    Group,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.platform.sources.discord.client import DiscordBotClient
from astrbot.core.platform.sources.discord.components import DiscordEmbed, DiscordView
from astrbot.core.utils.media_utils import (
    MEDIA_MIME_EXTENSIONS,
    MediaResolver,
    describe_media_ref,
)


class DiscordViewComponent(BaseMessageComponent):
    type: ComponentType = ComponentType.DiscordRawView

    def __init__(self, view: discord.ui.View) -> None:
        self.view = view


class DiscordSendPayload(TypedDict, total=False):
    """Shared send fields accepted by both channels and followup webhooks."""

    content: str
    files: list[discord.File]
    view: discord.ui.View
    embeds: list[discord.Embed]


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

    async def send_typing(self) -> None:
        """Discord typing state is managed by the channel context when needed."""

    async def stop_typing(self) -> None:
        """Discord does not expose an explicit stop-typing operation."""

    async def send(self, message: MessageChain) -> None:
        """发送消息到Discord平台"""
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
            return
        kwargs: DiscordSendPayload = {}
        if content:
            kwargs["content"] = content
        if files:
            kwargs["files"] = files
        if view:
            kwargs["view"] = view
        if embeds:
            kwargs["embeds"] = embeds
        if not kwargs:
            logger.debug("[Discord] 尝试发送空消息,已忽略｡")
            return
        try:
            if self.interaction_followup_webhook:
                await self.interaction_followup_webhook.send(**kwargs)
            else:
                channel = await self._get_channel()
                if not channel:
                    return
                if not isinstance(channel, discord.abc.Messageable):
                    logger.error(f"[Discord] 频道 {channel.id} 不是可发送消息的类型")
                    return
                if reference_message_id:
                    reference = discord.MessageReference(
                        message_id=int(reference_message_id), channel_id=channel.id
                    )
                    await channel.send(reference=reference, **kwargs)
                else:
                    await channel.send(**kwargs)
        except Exception as e:
            logger.error(f"[Discord] 发送消息时发生未知错误: {e}", exc_info=True)
        await super().send(message)

    async def send_streaming(
        self,
        generator: AsyncGenerator[MessageChain, None],
        use_fallback: bool = False,
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
            logger.error(f"[Discord] 无法获取频道 {self.session_id}")
            return None

    async def get_group(
        self, group_id: str | None = None, **kwargs: object
    ) -> Group | None:
        """Get Discord channel and guild metadata without fetching all members.

        AstrBot treats a Discord channel or thread as the group. Guild metadata is
        attached for context, while members are exposed only when the local cache is
        known to be complete.

        Args:
            group_id: Discord channel or thread ID. Defaults to the current group.
            **kwargs: Reserved for compatibility with the platform event interface.

        Returns:
            Enriched group metadata, or ``None`` when no group ID is available.
        """
        if group_id is None and self.message_obj.type != MessageType.GROUP_MESSAGE:
            return None

        requested_group_id = str(group_id or self.get_group_id())
        if not requested_group_id:
            return None

        current_group = self.message_obj.group
        group = Group(
            group_id=requested_group_id,
            group_name=(
                current_group.group_name
                if current_group and current_group.group_id == requested_group_id
                else None
            ),
        )
        try:
            channel_id = int(requested_group_id)
        except ValueError:
            logger.warning(f"[Discord] Invalid group channel ID: {requested_group_id}")
            return group

        channel = self.client.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.client.fetch_channel(channel_id)
            except Exception as exc:
                logger.warning(
                    f"[Discord] Failed to get group channel {requested_group_id}: {exc}"
                )
                return group

        channel_name = getattr(channel, "name", None)
        if isinstance(channel_name, str):
            group.group_name = channel_name

        guild = getattr(channel, "guild", None)
        guild_name = getattr(guild, "name", None)
        if not isinstance(guild_name, str):
            guild_id = getattr(channel, "guild_id", None) or getattr(guild, "id", None)
            try:
                resolved_guild_id = int(guild_id) if guild_id is not None else None
            except (TypeError, ValueError):
                resolved_guild_id = None
            if resolved_guild_id is not None:
                get_guild = getattr(self.client, "get_guild", None)
                cached_guild = (
                    get_guild(resolved_guild_id) if callable(get_guild) else None
                )
                if cached_guild is not None:
                    guild = cached_guild
                else:
                    fetch_guild = getattr(self.client, "fetch_guild", None)
                    if callable(fetch_guild):
                        try:
                            guild = await fetch_guild(resolved_guild_id)
                        except Exception as exc:
                            logger.warning(
                                f"[Discord] Failed to get guild {resolved_guild_id}: {exc}"
                            )
                guild_name = getattr(guild, "name", None)

        if guild is None:
            return group

        if isinstance(guild_name, str) and isinstance(channel_name, str):
            group.group_name = f"{guild_name}-{channel_name}"
        elif isinstance(guild_name, str):
            group.group_name = guild_name

        icon = getattr(guild, "icon", None)
        icon_url = getattr(icon, "url", None) if icon else None
        if icon_url:
            group.group_avatar = str(icon_url)

        owner_id = getattr(guild, "owner_id", None)
        if owner_id is not None:
            group.group_owner = str(owner_id)

        member_count = getattr(guild, "member_count", None)
        if isinstance(member_count, int):
            group.member_count = member_count

        cached_members = getattr(guild, "members", None)
        members_intent = bool(
            getattr(getattr(self.client, "intents", None), "members", False)
        )
        cache_complete = bool(
            members_intent
            and cached_members is not None
            and (
                getattr(guild, "chunked", False)
                or (
                    group.member_count is not None
                    and len(cached_members) >= group.member_count
                )
            )
        )
        if not cache_complete or cached_members is None:
            return group

        group.group_admins = []
        visible_members: list[MessageMember] = []
        group.members = None if isinstance(channel, discord.Thread) else visible_members
        for member in cached_members:
            member_id = getattr(member, "id", None)
            if member_id is None:
                continue
            guild_permissions = getattr(member, "guild_permissions", None)
            if (
                getattr(guild_permissions, "administrator", False)
                and str(member_id) != group.group_owner
            ):
                group.group_admins.append(str(member_id))
            if not isinstance(channel, discord.abc.GuildChannel):
                continue
            try:
                if not channel.permissions_for(member).view_channel:
                    continue
            except Exception:
                continue
            visible_members.append(
                MessageMember(
                    user_id=str(member_id),
                    nickname=getattr(member, "display_name", None),
                )
            )

        return group

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
        for i in message.chain:
            if isinstance(i, Plain):
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
                    ).to_base64_data(strict=True, target_format="wav")
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
                                f"[Discord] 获取文件失败,路径不存在: {file_path_str}",
                            )
                    else:
                        logger.warning(f"[Discord] 获取文件失败: {i.name}")
                except Exception as e:
                    logger.warning(f"[Discord] 处理文件失败: {i.name}, 错误: {e}")
            elif isinstance(i, DiscordEmbed):
                embeds.append(i.to_discord_embed())
            elif isinstance(i, DiscordView):
                view = i.to_discord_view()
            elif isinstance(i, DiscordViewComponent):
                if isinstance(i.view, discord.ui.View):
                    view = i.view
            else:
                logger.debug(f"[Discord] 忽略了不支持的消息组件: {i.type}")
        content = "".join(content_parts)
        if len(content) > 2000:
            logger.warning("[Discord] 消息内容超过2000字符,将被截断｡")
            content = content[:2000]
        return (content, files, view, embeds, reference_message_id)

    async def react(self, emoji: str) -> None:
        """对原消息添加反应"""
        try:
            if hasattr(self.message_obj, "raw_message") and hasattr(
                self.message_obj.raw_message,
                "add_reaction",
            ):
                await self.message_obj.raw_message.add_reaction(emoji)
        except Exception as e:
            logger.error(f"[Discord] 添加反应失败: {e}")

    def is_slash_command(self) -> bool:
        """判断是否为斜杠命令"""
        return (
            hasattr(self.message_obj, "raw_message")
            and hasattr(self.message_obj.raw_message, "type")
            and (
                self.message_obj.raw_message.type
                == discord.InteractionType.application_command
            )
        )

    def is_button_interaction(self) -> bool:
        """判断是否为按钮交互"""
        return (
            hasattr(self.message_obj, "raw_message")
            and hasattr(self.message_obj.raw_message, "type")
            and (self.message_obj.raw_message.type == discord.InteractionType.component)
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
            self.message_obj.raw_message,
            "mentions",
        ):
            return any(
                mention.id == int(self.message_obj.self_id)
                for mention in self.message_obj.raw_message.mentions
            )
        return False

    def get_mention_clean_content(self) -> str:
        """获取去除@后的清洁内容"""
        if hasattr(self.message_obj, "raw_message") and hasattr(
            self.message_obj.raw_message,
            "clean_content",
        ):
            return self.message_obj.raw_message.clean_content
        return self.message_str
