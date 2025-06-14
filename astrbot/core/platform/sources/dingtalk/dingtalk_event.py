import asyncio
import dingtalk_stream
import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot import logger


class DingtalkMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        client: dingtalk_stream.ChatbotHandler,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client

    async def send_with_client(
        self, client: dingtalk_stream.ChatbotHandler, message: MessageChain
    ):
        for segment in message.chain:
            if isinstance(segment, Comp.Plain):
                segment.text = segment.text.strip()
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    client.reply_markdown,
                    "AstrBot",
                    segment.text,
                    self.message_obj.raw_message,
                )
            elif isinstance(segment, Comp.Image):
                markdown_str = ""
                if segment.file and segment.file.startswith("file:///"):
                    logger.warning(
                        "dingtalk only support url image, not: " + segment.file
                    )
                    continue
                elif segment.file and segment.file.startswith("http"):
                    markdown_str += f"![image]({segment.file})\n\n"
                elif segment.file and segment.file.startswith("base64://"):
                    logger.warning("dingtalk only support url image, not base64")
                    continue
                else:
                    logger.warning(
                        "dingtalk only support url image, not: " + segment.file
                    )
                    continue

                ret = await asyncio.get_event_loop().run_in_executor(
                    None,
                    client.reply_markdown,
                    "😄",
                    markdown_str,
                    self.message_obj.raw_message,
                )
                logger.debug(f"send image: {ret}")

    async def send(self, message: MessageChain):
        await self.send_with_client(self.client, message)
        await super().send(message)

    async def send_streaming(self, generator, use_fallback: bool = False):
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
