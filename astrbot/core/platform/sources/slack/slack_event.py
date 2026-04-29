import asyncio
import re
from collections.abc import AsyncGenerator, Iterable
from typing import cast

from slack_sdk.web.async_client import AsyncWebClient

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import (
    BaseMessageComponent,
    Plain,
)
from astrbot.api.platform import Group, MessageMember

from .session_codec import (
    build_slack_text_fallbacks,
    resolve_target_from_event,
)
from .slack_send_utils import (
    build_text_fallback_from_chain,
    from_segment_to_slack_block,
    parse_slack_blocks,
    send_with_blocks_and_fallback,
)


class SlackMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        web_client: AsyncWebClient,
        text_fallbacks: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.web_client = web_client
        self.text_fallbacks = build_slack_text_fallbacks(text_fallbacks)

    @staticmethod
    async def _from_segment_to_slack_block(
        segment: BaseMessageComponent,
        web_client: AsyncWebClient,
        fallbacks: dict[str, str] | None = None,
    ) -> dict | None:
        """将消息段转换为 Slack 块格式"""
        return await from_segment_to_slack_block(
            segment=segment,
            web_client=web_client,
            fallbacks=fallbacks,
        )

    @staticmethod
    async def _parse_slack_blocks(
        message_chain: MessageChain,
        web_client: AsyncWebClient,
        fallbacks: dict[str, str] | None = None,
    ):
        """解析成 Slack 块格式"""
        return await parse_slack_blocks(
            message_chain=message_chain,
            web_client=web_client,
            fallbacks=fallbacks,
        )

    @staticmethod
    def _build_text_fallback_from_chain(
        message_chain: MessageChain,
        fallbacks: dict[str, str] | None = None,
    ) -> str:
        """Build a safe text fallback for retries when block payload is rejected."""
        return build_text_fallback_from_chain(
            message_chain=message_chain,
            fallbacks=fallbacks,
        )

    def _resolve_target(self) -> tuple[str, str | None]:
        raw_message = getattr(self.message_obj, "raw_message", None)
        return resolve_target_from_event(
            session_id=self.session_id,
            raw_message=raw_message if isinstance(raw_message, dict) else {},
            group_id=self.get_group_id(),
        )

    async def send(self, message: MessageChain) -> None:
        channel_id, thread_ts = self._resolve_target()
        await send_with_blocks_and_fallback(
            web_client=self.web_client,
            channel=channel_id,
            thread_ts=thread_ts,
            message_chain=message,
            fallbacks=self.text_fallbacks,
            parse_blocks=SlackMessageEvent._parse_slack_blocks,
            build_text_fallback=SlackMessageEvent._build_text_fallback_from_chain,
            session_id=self.session_id,
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
