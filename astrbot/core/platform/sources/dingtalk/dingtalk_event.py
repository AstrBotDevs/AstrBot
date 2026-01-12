import asyncio
from typing import cast

import dingtalk_stream

import astrbot.api.message_components as Comp
from astrbot import logger
from astrbot.api.event import AstrMessageEvent, MessageChain


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
        self,
        client: dingtalk_stream.ChatbotHandler,
        message: MessageChain,
    ):
        icm = cast(dingtalk_stream.ChatbotMessage, self.message_obj.raw_message)
        ats = []
        # fixes: #4218
        # 钉钉 at 机器人需要使用 sender_staff_id 而不是 sender_id
        for i in message.chain:
            if isinstance(i, Comp.At):
                print(i.qq, icm.sender_id, icm.sender_staff_id)
                if str(i.qq) in str(icm.sender_id or ""):
                    # 适配器会将开头的 $:LWCP_v1:$ 去掉，因此我们用 in 判断
                    ats.append(f"@{icm.sender_staff_id}")
                else:
                    ats.append(f"@{i.qq}")
        at_str = " ".join(ats)

        for segment in message.chain:
            if isinstance(segment, Comp.Plain):
                segment.text = segment.text.strip()
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    client.reply_markdown,
                    segment.text,
                    f"{at_str} {segment.text}".strip(),
                    cast(dingtalk_stream.ChatbotMessage, self.message_obj.raw_message),
                )
            elif isinstance(segment, Comp.Image):
                markdown_str = ""

                try:
                    if not segment.file:
                        logger.warning("钉钉图片 segment 缺少 file 字段，跳过")
                        continue
                    if segment.file.startswith(("http://", "https://")):
                        image_url = segment.file
                    else:
                        image_url = await segment.register_to_file_service()

                    markdown_str = f"![image]({image_url})\n\n"

                    ret = await asyncio.get_event_loop().run_in_executor(
                        None,
                        client.reply_markdown,
                        "😄",
                        markdown_str,
                        cast(
                            dingtalk_stream.ChatbotMessage, self.message_obj.raw_message
                        ),
                    )
                    logger.debug(f"send image: {ret}")

                except Exception as e:
                    logger.warning(f"钉钉图片处理失败: {e}, 跳过图片发送")
                    continue

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
            return None
        buffer.squash_plain()
        await self.send(buffer)
        return await super().send_streaming(generator, use_fallback)
