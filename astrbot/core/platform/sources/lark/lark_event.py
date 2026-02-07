import base64
import json
import os
import uuid
from io import BytesIO

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateFileRequest,
    CreateFileRequestBody,
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
from astrbot.api.message_components import At, File, Plain, Record, Video
from astrbot.api.message_components import Image as AstrBotImage
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.io import download_image_by_url
from astrbot.core.utils.media_utils import (
    convert_audio_to_opus,
    convert_video_format,
    get_media_duration,
)


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
            elif isinstance(comp, File):
                # 文件将通过 _send_file_message 方法单独发送，这里跳过
                logger.debug("[Lark] 检测到文件组件，将单独发送")
                continue
            elif isinstance(comp, Record):
                # 音频将通过 _send_audio_message 方法单独发送，这里跳过
                logger.debug("[Lark] 检测到音频组件，将单独发送")
                continue
            elif isinstance(comp, Video):
                # 视频将通过 _send_media_message 方法单独发送，这里跳过
                logger.debug("[Lark] 检测到视频组件，将单独发送")
                continue
            else:
                logger.warning(f"飞书 暂时不支持消息段: {comp.type}")

        if _stage:
            ret.append(_stage)
        return ret

    @staticmethod
    async def send_message_chain(
        message_chain: MessageChain,
        lark_client: lark.Client,
        reply_message_id: str | None = None,
        receive_id: str | None = None,
        receive_id_type: str | None = None,
    ):
        """通用的消息链发送方法

        Args:
            message_chain: 要发送的消息链
            lark_client: 飞书客户端
            reply_message_id: 回复的消息ID（用于回复消息）
            receive_id: 接收者ID（用于主动发送）
            receive_id_type: 接收者ID类型，如 'open_id', 'chat_id'（用于主动发送）
        """
        if lark_client.im is None:
            logger.error("[Lark] API Client im 模块未初始化")
            return

        # 分离文件、音频、视频组件和其他组件
        file_components = []
        audio_components = []
        media_components = []
        other_components = []

        for comp in message_chain.chain:
            if isinstance(comp, File):
                file_components.append(comp)
            elif isinstance(comp, Record):
                audio_components.append(comp)
            elif isinstance(comp, Video):
                media_components.append(comp)
            else:
                other_components.append(comp)

        # 先发送非文件内容（如果有）
        if other_components:
            temp_chain = MessageChain()
            temp_chain.chain = other_components
            res = await LarkMessageEvent._convert_to_lark(temp_chain, lark_client)

            if res:  # 只在有内容时发送
                wrapped = {
                    "zh_cn": {
                        "title": "",
                        "content": res,
                    },
                }

                # 根据是回复还是主动发送构建不同的请求
                if reply_message_id:
                    request = (
                        ReplyMessageRequest.builder()
                        .message_id(reply_message_id)
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
                    response = await lark_client.im.v1.message.areply(request)
                else:
                    # 主动推送消息

                    if receive_id_type is None or receive_id is None:
                        logger.error(
                            "[Lark] 主动发送消息时，receive_id 和 receive_id_type 不能为空",
                        )
                        return

                    from lark_oapi.api.im.v1 import (
                        CreateMessageRequest,
                        CreateMessageRequestBody,
                    )

                    request = (
                        CreateMessageRequest.builder()
                        .receive_id_type(receive_id_type)
                        .request_body(
                            CreateMessageRequestBody.builder()
                            .receive_id(receive_id)
                            .content(json.dumps(wrapped))
                            .msg_type("post")
                            .uuid(str(uuid.uuid4()))
                            .build(),
                        )
                        .build()
                    )
                    response = await lark_client.im.v1.message.acreate(request)

                if not response.success():
                    logger.error(f"发送飞书消息失败({response.code}): {response.msg}")

        # 然后单独发送文件消息
        for file_comp in file_components:
            await LarkMessageEvent._send_file_message(
                file_comp, lark_client, reply_message_id, receive_id, receive_id_type
            )

        # 发送音频消息
        for audio_comp in audio_components:
            await LarkMessageEvent._send_audio_message(
                audio_comp, lark_client, reply_message_id, receive_id, receive_id_type
            )

        # 发送视频消息
        for media_comp in media_components:
            await LarkMessageEvent._send_media_message(
                media_comp, lark_client, reply_message_id, receive_id, receive_id_type
            )

    async def send(self, message: MessageChain):
        await LarkMessageEvent.send_message_chain(
            message,
            self.bot,
            reply_message_id=self.message_obj.message_id,
        )
        await super().send(message)

    @staticmethod
    async def _send_file_message(
        file_comp: File,
        lark_client: lark.Client,
        reply_message_id: str | None = None,
        receive_id: str | None = None,
        receive_id_type: str | None = None,
    ):
        """发送文件消息

        Args:
            file_comp: 文件组件
            lark_client: 飞书客户端
            reply_message_id: 回复的消息ID（用于回复消息）
            receive_id: 接收者ID（用于主动发送）
            receive_id_type: 接收者ID类型（用于主动发送）
        """
        file_path = file_comp.file if file_comp.file else ""

        if not file_path:
            logger.error("[Lark] 文件路径为空，无法上传")
            return

        if lark_client.im is None:
            logger.error("[Lark] API Client im 模块未初始化，无法上传文件")
            return

        try:
            with open(file_path, "rb") as file_obj:
                request = (
                    CreateFileRequest.builder()
                    .request_body(
                        CreateFileRequestBody.builder()
                        .file_type("stream")
                        .file_name(os.path.basename(file_path))
                        .file(file_obj)
                        .build(),
                    )
                    .build()
                )

                response = await lark_client.im.v1.file.acreate(request)

                if not response.success():
                    logger.error(f"无法上传飞书文件({response.code}): {response.msg}")
                    return

                if response.data is None:
                    logger.error("[Lark] 上传文件成功但未返回数据(data is None)")
                    return

                file_key = response.data.file_key
                logger.debug(f"[Lark] 文件上传成功: {file_key}")
        except Exception as e:
            logger.error(f"[Lark] 无法打开或上传文件: {e}")
            return

        # 发送文件消息
        file_content = json.dumps({"file_key": file_key})

        # 根据是回复还是主动发送构建不同的请求
        if reply_message_id:
            request = (
                ReplyMessageRequest.builder()
                .message_id(reply_message_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .content(file_content)
                    .msg_type("file")
                    .uuid(str(uuid.uuid4()))
                    .reply_in_thread(False)
                    .build(),
                )
                .build()
            )
            response = await lark_client.im.v1.message.areply(request)
        else:
            from lark_oapi.api.im.v1 import (
                CreateMessageRequest,
                CreateMessageRequestBody,
            )

            if receive_id_type is None or receive_id is None:
                logger.error(
                    "[Lark] 主动发送消息时，receive_id 和 receive_id_type 不能为空",
                )
                return

            request = (
                CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .content(file_content)
                    .msg_type("file")
                    .uuid(str(uuid.uuid4()))
                    .build(),
                )
                .build()
            )
            response = await lark_client.im.v1.message.acreate(request)

        if not response.success():
            logger.error(f"发送飞书文件消息失败({response.code}): {response.msg}")
            return

    @staticmethod
    async def _send_audio_message(
        audio_comp: Record,
        lark_client: lark.Client,
        reply_message_id: str | None = None,
        receive_id: str | None = None,
        receive_id_type: str | None = None,
    ):
        """发送音频消息

        Args:
            audio_comp: 音频组件
            lark_client: 飞书客户端
            reply_message_id: 回复的消息ID（用于回复消息）
            receive_id: 接收者ID（用于主动发送）
            receive_id_type: 接收者ID类型（用于主动发送）
        """
        # 获取音频文件路径
        try:
            original_audio_path = await audio_comp.convert_to_file_path()
        except Exception as e:
            logger.error(f"[Lark] 无法获取音频文件路径: {e}")
            return

        if not original_audio_path or not os.path.exists(original_audio_path):
            logger.error(f"[Lark] 音频文件不存在: {original_audio_path}")
            return

        # 转换为opus格式
        converted_audio_path = None
        try:
            audio_path = await convert_audio_to_opus(original_audio_path)
            # 如果转换后路径与原路径不同，说明生成了新文件
            if audio_path != original_audio_path:
                converted_audio_path = audio_path
            else:
                audio_path = original_audio_path
        except Exception as e:
            logger.error(f"[Lark] 音频格式转换失败，将尝试直接上传: {e}")
            # 如果转换失败，继续尝试直接上传原始文件
            audio_path = original_audio_path

        # 获取音频时长
        duration = await get_media_duration(audio_path)

        if lark_client.im is None:
            logger.error("[Lark] API Client im 模块未初始化，无法上传音频")
            return

        # 上传音频文件
        try:
            with open(audio_path, "rb") as audio_obj:
                # 构建请求体，设置file_type为opus
                request_body_builder = (
                    CreateFileRequestBody.builder()
                    .file_type("opus")
                    .file_name(os.path.basename(audio_path))
                    .file(audio_obj)
                )

                # 如果成功获取时长，添加duration参数
                if duration is not None:
                    request_body_builder.duration(duration)

                request = (
                    CreateFileRequest.builder()
                    .request_body(request_body_builder.build())
                    .build()
                )

                response = await lark_client.im.v1.file.acreate(request)

                # 删除转换后的临时音频文件
                if converted_audio_path and os.path.exists(converted_audio_path):
                    try:
                        os.remove(converted_audio_path)
                        logger.debug(
                            f"[Lark] 已删除转换后的音频文件: {converted_audio_path}"
                        )
                    except Exception as e:
                        logger.warning(f"[Lark] 删除转换后的音频文件失败: {e}")

                if not response.success():
                    logger.error(f"无法上传飞书音频({response.code}): {response.msg}")
                    return

                if response.data is None:
                    logger.error("[Lark] 上传音频成功但未返回数据(data is None)")
                    return

                file_key = response.data.file_key
                logger.debug(f"[Lark] 音频上传成功: {file_key}")
        except Exception as e:
            logger.error(f"[Lark] 无法打开或上传音频文件: {e}")
            return

        # 发送音频消息
        audio_content = json.dumps({"file_key": file_key})

        # 根据是回复还是主动发送构建不同的请求
        if reply_message_id:
            request = (
                ReplyMessageRequest.builder()
                .message_id(reply_message_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .content(audio_content)
                    .msg_type("audio")
                    .uuid(str(uuid.uuid4()))
                    .reply_in_thread(False)
                    .build(),
                )
                .build()
            )
            response = await lark_client.im.v1.message.areply(request)
        else:
            from lark_oapi.api.im.v1 import (
                CreateMessageRequest,
                CreateMessageRequestBody,
            )

            if receive_id_type is None or receive_id is None:
                logger.error(
                    "[Lark] 主动发送消息时，receive_id 和 receive_id_type 不能为空",
                )
                return

            request = (
                CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .content(audio_content)
                    .msg_type("audio")
                    .uuid(str(uuid.uuid4()))
                    .build(),
                )
                .build()
            )
            response = await lark_client.im.v1.message.acreate(request)

        if not response.success():
            logger.error(f"发送飞书音频消息失败({response.code}): {response.msg}")
            return

    @staticmethod
    async def _send_media_message(
        media_comp: Video,
        lark_client: lark.Client,
        reply_message_id: str | None = None,
        receive_id: str | None = None,
        receive_id_type: str | None = None,
    ):
        """发送视频消息

        Args:
            media_comp: 视频组件
            lark_client: 飞书客户端
            reply_message_id: 回复的消息ID（用于回复消息）
            receive_id: 接收者ID（用于主动发送）
            receive_id_type: 接收者ID类型（用于主动发送）
        """
        # 获取视频文件路径
        try:
            original_video_path = await media_comp.convert_to_file_path()
        except Exception as e:
            logger.error(f"[Lark] 无法获取视频文件路径: {e}")
            return

        if not original_video_path or not os.path.exists(original_video_path):
            logger.error(f"[Lark] 视频文件不存在: {original_video_path}")
            return

        # 转换为mp4格式
        converted_video_path = None
        try:
            video_path = await convert_video_format(original_video_path, "mp4")
            # 如果转换后路径与原路径不同，说明生成了新文件
            if video_path != original_video_path:
                converted_video_path = video_path
            else:
                video_path = original_video_path
        except Exception as e:
            logger.error(f"[Lark] 视频格式转换失败，将尝试直接上传: {e}")
            # 如果转换失败，继续尝试直接上传原始文件
            video_path = original_video_path

        # 获取视频时长
        duration = await get_media_duration(video_path)

        if lark_client.im is None:
            logger.error("[Lark] API Client im 模块未初始化，无法上传视频")
            return

        # 上传视频文件
        try:
            with open(video_path, "rb") as video_obj:
                # 构建请求体，设置file_type为mp4
                request_body_builder = (
                    CreateFileRequestBody.builder()
                    .file_type("mp4")
                    .file_name(os.path.basename(video_path))
                    .file(video_obj)
                )

                # 如果成功获取时长，添加duration参数
                if duration is not None:
                    request_body_builder.duration(duration)

                request = (
                    CreateFileRequest.builder()
                    .request_body(request_body_builder.build())
                    .build()
                )

                response = await lark_client.im.v1.file.acreate(request)

                # 删除转换后的临时视频文件
                if converted_video_path and os.path.exists(converted_video_path):
                    try:
                        os.remove(converted_video_path)
                        logger.debug(
                            f"[Lark] 已删除转换后的视频文件: {converted_video_path}"
                        )
                    except Exception as e:
                        logger.warning(f"[Lark] 删除转换后的视频文件失败: {e}")

                if not response.success():
                    logger.error(f"无法上传飞书视频({response.code}): {response.msg}")
                    return

                if response.data is None:
                    logger.error("[Lark] 上传视频成功但未返回数据(data is None)")
                    return

                file_key = response.data.file_key
        except Exception as e:
            logger.error(f"[Lark] 无法打开或上传视频文件: {e}")
            return
        logger.debug(f"[Lark] 视频上传成功: {file_key}")

        # 发送视频消息
        media_content_dict = {"file_key": file_key}
        media_content = json.dumps(media_content_dict)

        # 根据是回复还是主动发送构建不同的请求
        if reply_message_id:
            request = (
                ReplyMessageRequest.builder()
                .message_id(reply_message_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .content(media_content)
                    .msg_type("media")
                    .uuid(str(uuid.uuid4()))
                    .reply_in_thread(False)
                    .build(),
                )
                .build()
            )
            response = await lark_client.im.v1.message.areply(request)
        else:
            from lark_oapi.api.im.v1 import (
                CreateMessageRequest,
                CreateMessageRequestBody,
            )

            if receive_id_type is None or receive_id is None:
                logger.error(
                    "[Lark] 主动发送消息时，receive_id 和 receive_id_type 不能为空",
                )
                return

            request = (
                CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .content(media_content)
                    .msg_type("media")
                    .uuid(str(uuid.uuid4()))
                    .build(),
                )
                .build()
            )
            response = await lark_client.im.v1.message.acreate(request)

        if not response.success():
            logger.error(f"发送飞书视频消息失败({response.code}): {response.msg}")
            return

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
