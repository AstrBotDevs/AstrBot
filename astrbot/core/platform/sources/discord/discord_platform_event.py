import asyncio
import re
from collections.abc import AsyncGenerator
from io import BytesIO
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlparse

import discord
from discord.types.interactions import ComponentInteractionData

from astrbot import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import (
    ActionRow,
    BaseMessageComponent,
    File,
    Image,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.api.platform import (
    AstrBotMessage,
    At,
    Group,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.utils.media_utils import (
    MEDIA_MIME_EXTENSIONS,
    MediaResolver,
    describe_media_ref,
)

from .client import DiscordBotClient
from .components import DiscordEmbed, DiscordView, action_rows_to_discord_view

_DISCORD_MARKUP = re.compile(
    r"\\.|(?<!`)(?P<ticks>`{1,3})(?!`)(?P<code>.*?)(?<!`)(?P=ticks)(?!`)"
    r"|(?P<spoiler>\|\|)|<(?:@[!&]?|#|a?:[A-Za-z0-9_]{1,32}:)[0-9]{1,20}>"
    r"|@everyone|@here",
    re.DOTALL,
)


# 自定义Discord视图组件（兼容旧版本）
class DiscordViewComponent(BaseMessageComponent):
    type: str = "discord_view"

    def __init__(self, view: discord.ui.View) -> None:
        self.view = view


class DiscordPlatformEvent(AstrMessageEvent):
    MAX_MESSAGE_LENGTH = 2000

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

    @classmethod
    def _split_content(cls, content: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
        """Split text without separating Discord markup from its content.

        Args:
            content: Rendered content of the outgoing message chain.
            limit: Available characters, excluding any enclosing spoiler markers.

        Returns:
            Message-sized chunks in delivery order.
        """
        if len(content) <= limit:
            return [content]

        tokens = list(_DISCORD_MARKUP.finditer(content))
        # Code spans are opaque tokens, so literal pipes in code cannot close a spoiler.
        delimiters = (token.start() for token in tokens if token["spoiler"])
        spoiler_ends = dict(zip(delimiters, delimiters))
        parts: list[tuple[str, bool]] = []
        start = 0
        for token in tokens:
            if token.start() < start:
                continue
            if token.start() > start:
                parts.append((content[start : token.start()], False))
            start = token.end()
            if token.start() in spoiler_ends:
                end = spoiler_ends[token.start()]
                for piece in cls._split_content(content[start:end], limit - 4):
                    parts.append(("||" + piece + "||", True))
                start = end + 2
            elif token["ticks"] and len(token[0]) > limit:
                for piece in cls._split_code(token["code"], token["ticks"], limit):
                    parts.append((piece, True))
            else:
                parts.append((token[0], True))
        parts.append((content[start:], False))

        chunks = [""]
        for text, atomic in parts:
            room = limit - len(chunks[-1])
            if atomic and len(text) > room:
                chunks.append(text)
            else:
                chunks[-1] += text[:room]
                chunks.extend(
                    text[i : i + limit] for i in range(room, len(text), limit)
                )
        return chunks

    @staticmethod
    def _split_code(body: str, ticks: str, limit: int) -> list[str]:
        """Render independently delimited pieces of an oversized code span.

        Args:
            body: Text between the original backticks, including any language tag.
            ticks: Opening and closing backtick delimiter.
            limit: Maximum size including repeated delimiters and language tag.

        Returns:
            Code messages with balanced delimiters.
        """
        block = ticks == "```"
        opening = ticks
        if block:
            language = re.match(r"[\w.+#-]{0,64}\r?\n", body)
            opening += language[0] if language else "\n"
            if language:
                body = body[language.end() :]

        capacity = limit - len(opening) - len(ticks)
        chunks = []
        start = 0
        while start < len(body):
            stop = min(start + capacity, len(body))
            if block:
                # Prefer a complete line; a long line needs room for the fence newline.
                newline = body.rfind("\n", start, stop)
                if stop < len(body) and newline >= start:
                    stop = newline + 1
                elif stop - start == capacity and body[stop - 1] != "\n":
                    stop -= 1
            elif body[start] == "`" or body[stop - 1] == "`":
                # Leave room to separate literal backticks from the inline delimiter.
                stop = min(stop, start + capacity - 2)
            piece = body[start:stop]
            if block and not piece.endswith("\n"):
                piece += "\n"
            elif not block and (piece.startswith("`") or piece.endswith("`")):
                piece = " " + piece + " "
            chunks.append(opening + piece + ticks)
            start = stop
        return chunks

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
            logger.error(f"[Discord] 解析消息链时失败: {e}", exc_info=True)
            return

        extra_kwargs = {}
        if files:
            extra_kwargs["files"] = files
        if view:
            extra_kwargs["view"] = view
        if embeds:
            extra_kwargs["embeds"] = embeds
        if reference_message_id and not self.interaction_followup_webhook:
            extra_kwargs["reference"] = self.client.get_message(
                int(reference_message_id)
            )
        chunks = [chunk for chunk in self._split_content(content) if chunk.strip()]
        if not chunks and not (files or view or embeds):
            logger.debug("[Discord] 尝试发送空消息，已忽略。")
            return

        # 根据上下文执行发送/回复操作
        try:
            # -- 斜杠指令/交互上下文 --
            if self.interaction_followup_webhook:
                sender = self.interaction_followup_webhook.send

            # -- 常规消息上下文 --
            else:
                channel = await self._get_channel()
                if not channel:
                    return
                if not isinstance(channel, discord.abc.Messageable):
                    logger.error(f"[Discord] 频道 {channel.id} 不是可发送消息的类型")
                    return
                sender = channel.send

            for index, chunk in enumerate(chunks or [""]):
                kwargs = dict(extra_kwargs) if index == 0 else {}
                if chunk:
                    kwargs["content"] = chunk
                await sender(**kwargs)

        except Exception as e:
            logger.error(f"[Discord] 发送消息时发生未知错误: {e}", exc_info=True)

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
        if not cache_complete:
            return group

        group.group_admins = []
        group.members = None if isinstance(channel, discord.Thread) else []
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
            if isinstance(channel, discord.Thread):
                continue
            try:
                if not channel.permissions_for(member).view_channel:
                    continue
            except Exception:
                continue
            group.members.append(
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
        action_rows = []
        embeds = []
        reference_message_id = None
        for i in message.chain:  # 遍历消息链
            if isinstance(i, Plain):  # 如果是文字类型的
                content_parts.append(i.text)
            elif isinstance(i, Reply):
                reference_message_id = i.id
            elif isinstance(i, At):
                content_parts.append("@everyone" if i.qq == "all" else f"<@{i.qq}>")
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
            elif isinstance(i, Video):
                try:
                    path = Path(await i.convert_to_file_path())
                    filename = path.name
                    if i.file.startswith(("http://", "https://")):
                        url_path = unquote(urlparse(i.file).path).replace("\\", "/")
                        url_filename = url_path.rsplit("/", 1)[-1]
                        if url_filename not in ("", ".", ".."):
                            filename = url_filename
                    files.append(discord.File(path, filename=filename))
                except Exception:
                    logger.warning(
                        "[Discord] Failed to process video: %s",
                        describe_media_ref(i.file),
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
            elif isinstance(i, ActionRow):
                action_rows.append(i)
            else:
                logger.debug(f"[Discord] 忽略了不支持的消息组件: {i.type}")

        if action_rows:
            if view is not None:
                logger.warning(
                    "[Discord] Common ActionRow components override a legacy Discord view."
                )
            view = action_rows_to_discord_view(action_rows)

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

    def get_interaction_custom_id(self) -> str:
        """Return the portable action ID, with legacy raw-data fallback."""
        button_interaction = self.get_button_interaction()
        if button_interaction is not None:
            return button_interaction.action_id
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
