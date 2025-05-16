import asyncio
import re
import wave
import os

from typing import AsyncGenerator
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.api.message_components import Plain, At
from .client import XXXBotClient


def get_wav_duration(file_path):
    with wave.open(file_path, "rb") as wav_file:
        file_size = os.path.getsize(file_path)
        n_channels, sampwidth, framerate, n_frames = wav_file.getparams()[:4]
        if n_frames == 2147483647:
            duration = (file_size - 44) / (n_channels * sampwidth * framerate)
        elif n_frames == 0:
            duration = (file_size - 44) / (n_channels * sampwidth * framerate)
        else:
            duration = n_frames / float(framerate)
        return duration


class XXXBotPlatformEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        client: XXXBotClient,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client

    @staticmethod
    async def send_with_client(
        message: MessageChain, to_wxid: str, self_wxid: str, client: XXXBotClient
    ):
        if not to_wxid:
            logger.error("无法获取到 to_wxid。")
            return

        #  检查@
        ats = []
        ats_names = []
        for comp in message.chain:
            if isinstance(comp, At):
                ats.append(comp.qq)
                ats_names.append(comp.name)
        has_at = False

        for comp in message.chain:
            if isinstance(comp, Plain):
                # 发送文本消息
                text = comp.text
                payload = {
                    "ToWxid": to_wxid,
                    "Content": text,
                    "Type": 1,
                    "Wxid": self_wxid,  # bot 自己的 wxid
                }
                if not has_at and ats:
                    ats = f"{','.join(ats)}"
                    ats_names = f"@{' @'.join(ats_names)}"
                    text = f"{ats_names} {text}"
                    payload["Content"] = text
                    payload["At"] = ats
                    has_at = True
                await client.post_text(**payload)
            else:
                logger.debug(f"xxxbot 忽略: {comp.type}")

    async def send(self, message: MessageChain):
        to_wxid = self.message_obj.raw_message.get("to_wxid", None)
        await XXXBotPlatformEvent.send_with_client(
            message, to_wxid, self.get_self_id(), self.client
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
