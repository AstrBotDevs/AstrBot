import asyncio
import re
from typing import AsyncGenerator
from slack_sdk.web.async_client import AsyncWebClient
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import (
    Image,
    Plain,
    File,
    BaseMessageComponent,
)
from astrbot.api.platform import Group, MessageMember
from astrbot.api import logger


class SlackMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        web_client: AsyncWebClient,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.web_client = web_client

    @staticmethod
    async def _from_segment_to_slack_block(
        segment: BaseMessageComponent, web_client: AsyncWebClient
    ) -> dict:
        """将消息段转换为 Slack 块格式"""
        if isinstance(segment, Plain):
            return {"type": "section", "text": {"type": "mrkdwn", "text": segment.text}}
        elif isinstance(segment, Image):
            # upload file
            url = segment.url or segment.file
            if url.startswith("http"):
                return {
                    "type": "image",
                    "image_url": url,
                    "alt_text": "图片",
                }
            path = await segment.convert_to_file_path()
            response = await web_client.files_upload_v2(
                file=path,
                filename="image.jpg",
            )
            if not response["ok"]:
                logger.error(f"Slack file upload failed: {response['error']}")
                return {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "图片上传失败"},
                }
            image_url = response["files"][0]["url_private"]
            logger.debug(f"Slack file upload response: {response}")
            return {
                "type": "image",
                "slack_file": {
                    "url": image_url,
                },
                "alt_text": "图片",
            }
        elif isinstance(segment, File):
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
            file_url = response["files"][0]["permalink"]
            return {"type": "section", "text": {"type": "mrkdwn", "text": f"文件: <{file_url}|{segment.name or '文件'}>"}}
        else:
            return {"type": "section", "text": {"type": "mrkdwn", "text": str(segment)}}

    @staticmethod
    async def _parse_slack_blocks(
        message_chain: MessageChain, web_client: AsyncWebClient
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
                        }
                    )
                    text_content = ""

                # 添加其他类型的块
                block = await SlackMessageEvent._from_segment_to_slack_block(
                    segment, web_client
                )
                blocks.append(block)

        # 如果最后还有文本内容
        if text_content.strip():
            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": text_content}}
            )

        return blocks, "" if blocks else text_content

    async def send(self, message: MessageChain):
        blocks, text = await SlackMessageEvent._parse_slack_blocks(
            message, self.web_client
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
            fallback_text = ""
            for segment in message.chain:
                if isinstance(segment, Plain):
                    fallback_text += segment.text
                elif isinstance(segment, File):
                    fallback_text += f" [文件: {segment.name}] "
                elif isinstance(segment, Image):
                    fallback_text += " [图片] "

            if self.get_group_id():
                await self.web_client.chat_postMessage(
                    channel=self.get_group_id(), text=fallback_text
                )
            else:
                await self.web_client.chat_postMessage(
                    channel=self.get_sender_id(), text=fallback_text
                )

        await super().send(message)

    async def send_streaming(
        self, generator: AsyncGenerator, use_fallback: bool = False
    ):
        if not use_fallback:
            buffer = None
            async for chain in generator:
                if not buffer:
                    buffer = chain
                else:
                    buffer.chain.extend(chain.chain)
            if not buffer:
                return
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
        if group_id:
            channel_id = group_id
        elif self.get_group_id():
            channel_id = self.get_group_id()
        else:
            return None

        try:
            # 获取频道信息
            channel_info = await self.web_client.conversations_info(channel=channel_id)

            # 获取频道成员
            members_response = await self.web_client.conversations_members(
                channel=channel_id
            )

            members = []
            for member_id in members_response["members"]:
                try:
                    user_info = await self.web_client.users_info(user=member_id)
                    user_data = user_info["user"]
                    members.append(
                        MessageMember(
                            user_id=member_id,
                            nickname=user_data.get("real_name")
                            or user_data.get("name", member_id),
                        )
                    )
                except Exception:
                    # 如果获取用户信息失败，使用默认信息
                    members.append(MessageMember(user_id=member_id, nickname=member_id))

            channel_data = channel_info["channel"]
            return Group(
                group_id=channel_id,
                group_name=channel_data.get("name", ""),
                group_avatar="",
                group_admins=[],  # Slack 的管理员信息需要特殊权限获取
                group_owner=channel_data.get("creator", ""),
                members=members,
            )
        except Exception:
            return None
