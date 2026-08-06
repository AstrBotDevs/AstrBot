import asyncio
import re
from collections.abc import AsyncGenerator

from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import Group, MessageMember
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.send_result import PlatformSendResult

from .client import MattermostClient


class MattermostMessageEvent(AstrMessageEvent):
    _FALLBACK_SENTENCE_PATTERN = re.compile(r"[^。？！~…]+[。？！~…]+")

    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        client: MattermostClient,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self._client = client
        for path in getattr(message_obj, "temporary_file_paths", []):
            self.track_temporary_local_file(path)

    async def send(self, message: MessageChain) -> PlatformSendResult | None:
        await self._client.send_message_chain(self.get_session_id(), message)
        return await super().send(message)

    async def send_streaming(
        self,
        generator: AsyncGenerator,
        use_fallback: bool = False,
    ):
        return await self.send_non_streaming_response(
            generator,
            use_fallback=use_fallback,
            sentence_pattern=self._FALLBACK_SENTENCE_PATTERN,
            sleep=asyncio.sleep,
            record_empty=True,
        )

    async def get_group(self, group_id=None, **kwargs):
        channel_id = group_id or self.get_group_id()
        if not channel_id:
            return None
        channel = await self._client.get_channel(channel_id)
        return Group(
            group_id=channel_id,
            group_name=channel.get("display_name") or channel.get("name") or channel_id,
            group_owner="",
            group_admins=[],
            members=[
                MessageMember(
                    user_id=self.get_sender_id(),
                    nickname=self.get_sender_name(),
                )
            ],
        )
