import asyncio
import re
from collections.abc import AsyncGenerator, Iterable
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

from .session_codec import decode_slack_session_id


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
                filename="image.jpg",
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
        fallback_parts = []

        for segment in message_chain.chain:
            if isinstance(segment, Plain):
                text_content += segment.text
                fallback_parts.append(segment.text)
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
                    if isinstance(segment, Image):
                        fallback_parts.append("[图片]")
                    elif isinstance(segment, File):
                        fallback_parts.append(
                            f"[文件:{segment.name or '文件'}]",
                        )
                    else:
                        fallback_parts.append("[消息]")

        # 如果最后还有文本内容
        if text_content.strip():
            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": text_content}},
            )

        fallback_text = "".join(fallback_parts).strip() or "消息"
        return blocks, fallback_text if blocks else text_content

    def _resolve_group_target(self) -> tuple[str, str | None]:
        channel_id = self.get_group_id()
        parsed_channel_id, parsed_thread_ts = decode_slack_session_id(self.session_id)
        if not channel_id:
            channel_id = parsed_channel_id

        raw_message = getattr(self.message_obj, "raw_message", None)
        raw_thread_ts = None
        if isinstance(raw_message, dict):
            raw_thread_ts = raw_message.get("thread_ts")
        if raw_thread_ts is not None and raw_thread_ts != "":
            return channel_id, str(raw_thread_ts)
        return channel_id, parsed_thread_ts

    def _resolve_friend_target(self) -> tuple[str, str | None]:
        parsed_channel_id, parsed_thread_ts = decode_slack_session_id(self.session_id)
        raw_message = getattr(self.message_obj, "raw_message", None)
        raw_channel_id = ""
        raw_thread_ts = None
        if isinstance(raw_message, dict):
            raw_channel = raw_message.get("channel")
            if raw_channel is not None and raw_channel != "":
                raw_channel_id = str(raw_channel)
            raw_thread_ts = raw_message.get("thread_ts")

        channel_id = raw_channel_id or parsed_channel_id or self.get_sender_id()
        if raw_thread_ts is not None and raw_thread_ts != "":
            return channel_id, str(raw_thread_ts)
        return channel_id, parsed_thread_ts

    async def send(self, message: MessageChain) -> None:
        blocks, text = await SlackMessageEvent._parse_slack_blocks(
            message,
            self.web_client,
        )
        safe_text = text or "消息"

        try:
            if self.get_group_id():
                channel_id, thread_ts = self._resolve_group_target()
                message_payload = {
                    "channel": channel_id,
                    "text": safe_text,
                    "blocks": blocks or None,
                }
                if thread_ts:
                    message_payload["thread_ts"] = thread_ts
                await self.web_client.chat_postMessage(**message_payload)
            else:
                channel_id, thread_ts = self._resolve_friend_target()
                message_payload = {
                    "channel": channel_id,
                    "text": safe_text,
                    "blocks": blocks or None,
                }
                if thread_ts:
                    message_payload["thread_ts"] = thread_ts
                await self.web_client.chat_postMessage(**message_payload)
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
            fallback_text = "".join(parts) or "消息"

            if self.get_group_id():
                channel_id, thread_ts = self._resolve_group_target()
                fallback_payload = {
                    "channel": channel_id,
                    "text": fallback_text,
                }
                if thread_ts:
                    fallback_payload["thread_ts"] = thread_ts
                await self.web_client.chat_postMessage(**fallback_payload)
            else:
                channel_id, thread_ts = self._resolve_friend_target()
                fallback_payload = {
                    "channel": channel_id,
                    "text": fallback_text,
                }
                if thread_ts:
                    fallback_payload["thread_ts"] = thread_ts
                await self.web_client.chat_postMessage(**fallback_payload)

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
                channel=channel_id,
            )

            members = []
            for member_id in cast(Iterable, members_response["members"]):
                try:
                    user_info = await self.web_client.users_info(user=member_id)
                    user_data = cast(dict, user_info["user"])
                    members.append(
                        MessageMember(
                            user_id=member_id,
                            nickname=user_data.get("real_name")
                            or user_data.get("name", member_id),
                        ),
                    )
                except Exception:
                    # 如果获取用户信息失败，使用默认信息
                    members.append(MessageMember(user_id=member_id, nickname=member_id))

            channel_data = cast(dict, channel_info["channel"])
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
