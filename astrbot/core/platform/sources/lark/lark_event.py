import base64
import json
import os
import uuid
from io import BytesIO

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateImageRequest,
    CreateImageRequestBody,
    CreateMessageReactionRequest,
    CreateMessageReactionRequestBody,
    Emoji,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)

from astrbot import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import At, Plain
from astrbot.api.message_components import Image as AstrBotImage
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.io import download_image_by_url


class LarkMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        bot: lark.Client,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.bot = bot

    @staticmethod
    async def _convert_to_lark(message: MessageChain, lark_client: lark.Client) -> list:
        ret = []
        _stage = []
        for comp in message.chain:
            if isinstance(comp, Plain):
                _stage.append({"tag": "md", "text": comp.text})
            elif isinstance(comp, At):
                _stage.append({"tag": "at", "user_id": comp.qq, "style": []})
            elif isinstance(comp, AstrBotImage):
                file_path = ""
                image_file = None

                if comp.file and comp.file.startswith("file:///"):
                    file_path = comp.file.replace("file:///", "")
                elif comp.file and comp.file.startswith("http"):
                    image_file_path = await download_image_by_url(comp.file)
                    file_path = image_file_path if image_file_path else ""
                elif comp.file and comp.file.startswith("base64://"):
                    base64_str = comp.file.removeprefix("base64://")
                    image_data = base64.b64decode(base64_str)
                    # save as temp file
                    temp_dir = os.path.join(get_astrbot_data_path(), "temp")
                    file_path = os.path.join(temp_dir, f"{uuid.uuid4()}_test.jpg")
                    with open(file_path, "wb") as f:
                        f.write(BytesIO(image_data).getvalue())
                else:
                    file_path = comp.file if comp.file else ""

                if image_file is None:
                    if not file_path:
                        logger.error("[Lark] 图片路径为空，无法上传")
                        continue
                    try:
                        image_file = open(file_path, "rb")
                    except Exception as e:
                        logger.error(f"[Lark] 无法打开图片文件: {e}")
                        continue

                request = (
                    CreateImageRequest.builder()
                    .request_body(
                        CreateImageRequestBody.builder()
                        .image_type("message")
                        .image(image_file)
                        .build(),
                    )
                    .build()
                )

                if lark_client.im is None:
                    logger.error("[Lark] API Client im 模块未初始化，无法上传图片")
                    continue

                response = await lark_client.im.v1.image.acreate(request)
                if not response.success():
                    logger.error(f"无法上传飞书图片({response.code}): {response.msg}")
                    continue

                if response.data is None:
                    logger.error("[Lark] 上传图片成功但未返回数据(data is None)")
                    continue

                image_key = response.data.image_key
                logger.debug(image_key)
                ret.append(_stage)
                ret.append([{"tag": "img", "image_key": image_key}])
                _stage.clear()
            else:
                logger.warning(f"飞书 暂时不支持消息段: {comp.type}")

        if _stage:
            ret.append(_stage)
        return ret

    async def send(self, message: MessageChain):
        res = await LarkMessageEvent._convert_to_lark(message, self.bot)
        wrapped = {
            "zh_cn": {
                "title": "",
                "content": res,
            },
        }

        request = (
            ReplyMessageRequest.builder()
            .message_id(self.message_obj.message_id)
            .request_body(
                ReplyMessageRequestBody.builder()
                .content(json.dumps(wrapped))
                .msg_type("post")
                .uuid(str(uuid.uuid4()))
                .reply_in_thread(False)
                .build(),
            )
            .build()
        )

        if self.bot.im is None:
            logger.error("[Lark] API Client im 模块未初始化，无法回复消息")
            return

        response = await self.bot.im.v1.message.areply(request)

        if not response.success():
            logger.error(f"回复飞书消息失败({response.code}): {response.msg}")

        await super().send(message)

    async def react(self, emoji: str):
        if self.bot.im is None:
            logger.error("[Lark] API Client im 模块未初始化，无法发送表情")
            return

        request = (
            CreateMessageReactionRequest.builder()
            .message_id(self.message_obj.message_id)
            .request_body(
                CreateMessageReactionRequestBody.builder()
                .reaction_type(Emoji.builder().emoji_type(emoji).build())
                .build(),
            )
            .build()
        )

        response = await self.bot.im.v1.message_reaction.acreate(request)
        if not response.success():
            logger.error(f"发送飞书表情回应失败({response.code}): {response.msg}")
            return

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
