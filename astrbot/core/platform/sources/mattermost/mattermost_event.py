import asyncio
import re
from collections.abc import AsyncGenerator

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain
from astrbot.api.platform import Group, MessageMember

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
        self.client = client
        for path in getattr(message_obj, "temporary_file_paths", []):
            self.track_temporary_local_file(path)

    async def send(self, message: MessageChain) -> None:
        await self.client.send_message_chain(self.get_session_id(), message)
        await super().send(message)

    async def send_streaming(
        self,
        generator: AsyncGenerator,
        use_fallback: bool = False,
    ) -> None:
        await super().send_streaming(generator, use_fallback)

        if not use_fallback:
            message_buffer: MessageChain | None = None
            async for chain in generator:
                if not message_buffer:
                    message_buffer = chain
                else:
                    message_buffer.chain.extend(chain.chain)
            if not message_buffer:
                return None
            message_buffer.squash_plain()
            await self.send(message_buffer)
            return None

        text_buffer = ""

        async for chain in generator:
            if isinstance(chain, MessageChain):
                for comp in chain.chain:
                    if isinstance(comp, Plain):
                        text_buffer += comp.text
                        if any(p in text_buffer for p in "。？！~…"):
                            text_buffer = await self.process_buffer(
                                text_buffer,
                                self._FALLBACK_SENTENCE_PATTERN,
                            )
                    else:
                        await self.send(MessageChain(chain=[comp]))
                        await asyncio.sleep(1.5)

        if text_buffer.strip():
            await self.send(MessageChain([Plain(text_buffer)]))
        return None

    async def get_group(self, group_id=None, **kwargs):
        channel_id = group_id or self.get_group_id()
        if not channel_id:
            return None
        channel = await self.client.get_channel(channel_id)
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
