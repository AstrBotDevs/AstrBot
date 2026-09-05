import asyncio
import re
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast

from slack_sdk.web.async_client import AsyncWebClient

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import (
    BaseMessageComponent,
    File,
    Image,
    Plain,
)
from astrbot.api.platform import Group, MessageMember


class SlackMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        web_client: AsyncWebClient,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.web_client = web_client

    @staticmethod
    async def _from_segment_to_slack_block(
        segment: BaseMessageComponent,
        web_client: AsyncWebClient,
    ) -> dict | None:
        """将消息段转换为 Slack 块格式"""
        if isinstance(segment, Plain):
            return {"type": "section", "text": {"type": "mrkdwn", "text": segment.text}}
        if isinstance(segment, Image):
            # upload file
            url = segment.url or segment.file
            if url and url.startswith("http"):
                return {
                    "type": "image",
                    "image_url": url,
                    "alt_text": "图片",
                }
            path = await segment.convert_to_file_path()
            response = await web_client.files_upload_v2(
                file=path,
                filename=Path(path).name,
            )
            if not response["ok"]:
                logger.error(f"Slack file upload failed: {response['error']}")
                return {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "图片上传失败"},
                }
            image_url = cast(list, response["files"])[0]["url_private"]
            logger.debug(f"Slack file upload response: {response}")
            return {
                "type": "image",
                "slack_file": {
                    "url": image_url,
                },
                "alt_text": "图片",
            }
        if isinstance(segment, File):
            # upload file
            url = segment.url or segment.file
            response = await web_client.files_upload_v2(
                file=url,
                filename=segment.name or "file",
            )
            if not response["ok"]:
                logger.error(f"Slack file upload failed: {response['error']}")
                return {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "文件上传失败"},
                }
            file_url = cast(list, response["files"])[0]["permalink"]
            return {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"文件: <{file_url}|{segment.name or '文件'}>",
                },
            }

    @staticmethod
    async def _parse_slack_blocks(
        message_chain: MessageChain,
        web_client: AsyncWebClient,
    ):
        """解析成 Slack 块格式"""
        blocks = []
        text_content = ""

        for segment in message_chain.chain:
            if isinstance(segment, Plain):
                text_content += segment.text
            else:
                # 如果有文本内容，先添加文本块
                if text_content.strip():
                    blocks.append(
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": text_content},
                        },
                    )
                    text_content = ""

                # 添加其他类型的块
                block = await SlackMessageEvent._from_segment_to_slack_block(
                    segment,
                    web_client,
                )
                if block:
                    blocks.append(block)

        # 如果最后还有文本内容
        if text_content.strip():
            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": text_content}},
            )

        return blocks, "" if blocks else text_content

    async def send(self, message: MessageChain) -> None:
        blocks, text = await SlackMessageEvent._parse_slack_blocks(
            message,
            self.web_client,
        )

        try:
            if self.get_group_id():
                # 发送到频道
                await self.web_client.chat_postMessage(
                    channel=self.get_group_id(),
                    text=text,
                    blocks=blocks or None,
                )
            else:
                # 发送私信
                await self.web_client.chat_postMessage(
                    channel=self.get_sender_id(),
                    text=text,
                    blocks=blocks or None,
                )
        except Exception:
            # 如果块发送失败，尝试只发送文本
            parts = []
            for segment in message.chain:
                if isinstance(segment, Plain):
                    parts.append(segment.text)
                elif isinstance(segment, File):
                    parts.append(f" [文件: {segment.name}] ")
                elif isinstance(segment, Image):
                    parts.append(" [图片] ")
            fallback_text = "".join(parts)

            if self.get_group_id():
                await self.web_client.chat_postMessage(
                    channel=self.get_group_id(),
                    text=fallback_text,
                )
            else:
                await self.web_client.chat_postMessage(
                    channel=self.get_sender_id(),
                    text=fallback_text,
                )

        await super().send(message)

    async def send_streaming(
        self,
        generator: AsyncGenerator,
        use_fallback: bool = False,
    ):
        if not use_fallback:
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

        buffer = ""
        pattern = re.compile(r"[^。？！~…]+[。？！~…]+")

        async for chain in generator:
            if isinstance(chain, MessageChain):
                for comp in chain.chain:
                    if isinstance(comp, Plain):
                        buffer += comp.text
                        if any(p in buffer for p in "。？！~…"):
                            buffer = await self.process_buffer(buffer, pattern)
                    else:
                        await self.send(MessageChain(chain=[comp]))
                        await asyncio.sleep(1.5)  # 限速

        if buffer.strip():
            await self.send(MessageChain([Plain(buffer)]))
        return await super().send_streaming(generator, use_fallback)

    async def get_group(self, group_id=None, **kwargs):
        """Gets Slack channel information and all visible members.

        Args:
            group_id: Optional Slack channel identifier.
            **kwargs: Reserved compatibility arguments.

        Returns:
            Enriched channel information, or a basic group if lookup fails.
        """
        channel_id = group_id or self.get_group_id()
        if not channel_id:
            return None

        current_group = self.message_obj.group
        group = Group(
            group_id=channel_id,
            group_name=(
                current_group.group_name
                if current_group and current_group.group_id == channel_id
                else None
            ),
        )

        try:
            channel_info = await self.web_client.conversations_info(
                channel=channel_id,
                include_num_members=True,
            )
            channel_data = cast(dict, channel_info["channel"])
            group.group_name = channel_data.get("name") or group.group_name
            group.member_count = channel_data.get("num_members")
        except Exception as exc:
            logger.debug("Slack channel info lookup failed for %s: %s", channel_id, exc)
            return group

        member_ids: list[str] = []
        cursor: str | None = None
        try:
            while True:
                request: dict[str, str | int] = {
                    "channel": channel_id,
                    "limit": 200,
                }
                if cursor:
                    request["cursor"] = cursor
                members_response = await self.web_client.conversations_members(
                    **request,
                )
                member_ids.extend(
                    str(member_id) for member_id in members_response["members"]
                )
                response_metadata = members_response.get("response_metadata") or {}
                cursor = str(response_metadata.get("next_cursor") or "")
                if not cursor:
                    break
        except Exception as exc:
            logger.debug(
                "Slack channel member lookup failed for %s: %s",
                channel_id,
                exc,
            )
            return group

        unique_member_ids = list(dict.fromkeys(member_ids))
        members: list[MessageMember] = []
        for offset in range(0, len(unique_member_ids), 20):
            member_id_batch = unique_member_ids[offset : offset + 20]
            user_responses = await asyncio.gather(
                *(
                    self.web_client.users_info(user=member_id)
                    for member_id in member_id_batch
                ),
                return_exceptions=True,
            )
            for member_id, user_response in zip(member_id_batch, user_responses):
                if isinstance(user_response, BaseException):
                    members.append(MessageMember(user_id=member_id, nickname=member_id))
                    continue
                try:
                    user_data = cast(dict, user_response["user"])
                    nickname = (
                        user_data.get("real_name") or user_data.get("name") or member_id
                    )
                except (KeyError, TypeError, AttributeError):
                    nickname = member_id
                members.append(
                    MessageMember(
                        user_id=member_id,
                        nickname=nickname,
                    ),
                )

        group.members = members
        group.member_count = group.member_count or len(members)
        return group
