import json
import uuid
import lark_oapi as lark
from typing import List
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain, Image as AstrBotImage, At
from astrbot.core.utils.io import download_image_by_url
from lark_oapi.api.im.v1 import *
from astrbot import logger


class LarkMessageEvent(AstrMessageEvent):
    def __init__(
        self, message_str, message_obj, platform_meta, session_id, bot: lark.Client
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.bot = bot

    @staticmethod
    async def _convert_to_lark(message: MessageChain, lark_client: lark.Client) -> List:
        ret = []
        _stage = []
        for comp in message.chain:
            if isinstance(comp, Plain):
                _stage.append({"tag": "md", "text": comp.text})
            elif isinstance(comp, At):
                _stage.append({"tag": "at", "user_id": comp.qq, "style": []})
            elif isinstance(comp, AstrBotImage):
                file_path = ""
                if comp.file and comp.file.startswith("file:///"):
                    file_path = comp.file.replace("file:///", "")
                elif comp.file and comp.file.startswith("http"):
                    image_file_path = await download_image_by_url(comp.file)
                    file_path = image_file_path
                elif comp.file and comp.file.startswith("base64://"):
                    pass
                else:
                    file_path = comp.file

                request = (
                    CreateImageRequest.builder()
                    .request_body(
                        CreateImageRequestBody.builder()
                        .image_type("message")
                        .image(open(file_path, "rb"))
                        .build()
                    )
                    .build()
                )
                response = await lark_client.im.v1.image.acreate(request)
                if not response.success():
                    logger.error(f"无法上传飞书图片({response.code}): {response.msg}")
                image_key = response.data.image_key
                print(image_key)
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
            }
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
                .build()
            )
            .build()
        )

        response = await self.bot.im.v1.message.areply(request)

        if not response.success():
            logger.error(f"回复飞书消息失败({response.code}): {response.msg}")

        await super().send(message)
