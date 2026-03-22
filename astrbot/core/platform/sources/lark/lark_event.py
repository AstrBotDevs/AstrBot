import asyncio
import base64
import json
import os
import uuid
from io import BytesIO

import aiofiles
import anyio
import lark_oapi as lark
from lark_oapi.api.cardkit.v1 import (
    ContentCardElementRequest,
    ContentCardElementRequestBody,
    CreateCardRequest,
    CreateCardRequestBody,
    SettingsCardRequest,
    SettingsCardRequestBody,
)
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
from astrbot.api.message_components import (
    At,
    File,
    Plain,
    Record,
    Video,
)
from astrbot.api.message_components import (
    Image as AstrBotImage,
)
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_image_by_url
from astrbot.core.utils.media_utils import (
    convert_audio_to_opus,
    convert_video_format,
    get_media_duration,
)
from astrbot.core.utils.metrics import Metric


class LarkMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        bot: lark.Client,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.bot = bot

    @staticmethod
    async def _send_im_message(
        lark_client: lark.Client,
        *,
        content: str,
        msg_type: str,
        reply_message_id: str | None = None,
        receive_id: str | None = None,
        receive_id_type: str | None = None,
    ) -> bool:
        """发送飞书 IM 消息的通用辅助函数

        Args:
            lark_client: 飞书客户端
            content: 消息内容(JSON字符串)
            msg_type: 消息类型(post/file/audio/media等)
            reply_message_id: 回复的消息ID(用于回复消息)
            receive_id: 接收者ID(用于主动发送)
            receive_id_type: 接收者ID类型(用于主动发送)

        Returns:
            是否发送成功
        """
        if lark_client.im is None:
            logger.error("[Lark] API Client im 模块未初始化")
            return False

        if reply_message_id:
            request = (
                ReplyMessageRequest.builder()
                .message_id(reply_message_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .content(content)
                    .msg_type(msg_type)
                    .uuid(str(uuid.uuid4()))
                    .reply_in_thread(False)
                    .build()
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
                    "[Lark] 主动发送消息时,receive_id 和 receive_id_type 不能为空",
                )
                return False

            request = (
                CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .content(content)
                    .msg_type(msg_type)
                    .uuid(str(uuid.uuid4()))
                    .build()
                )
                .build()
            )
            response = await lark_client.im.v1.message.acreate(request)

        if not response.success():
            logger.error(f"[Lark] 发送飞书消息失败({response.code}): {response.msg}")
            return False

        return True

    @staticmethod
    async def _upload_lark_file(
        lark_client: lark.Client,
        *,
        path: str,
        file_type: str,
        duration: int | None = None,
    ) -> str | None:
        """上传文件到飞书的通用辅助函数

        Args:
            lark_client: 飞书客户端
            path: 文件路径
            file_type: 文件类型(stream/opus/mp4等)
            duration: 媒体时长(毫秒),可选

        Returns:
            成功返回file_key,失败返回None
        """
        path_obj = anyio.Path(path)
        if not path or not await path_obj.exists():
            logger.error(f"[Lark] 文件不存在: {path}")
            return None

        if lark_client.im is None:
            logger.error("[Lark] API Client im 模块未初始化,无法上传文件")
            return None

        try:
            async with aiofiles.open(path, "rb") as file_obj:
                body_builder = (
                    CreateFileRequestBody.builder()
                    .file_type(file_type)
                    .file_name(os.path.basename(path))
                    .file(file_obj)
                )
                if duration is not None:
                    body_builder.duration(duration)

                request = (
                    CreateFileRequest.builder()
                    .request_body(body_builder.build())
                    .build()
                )
                response = await lark_client.im.v1.file.acreate(request)

                if not response.success():
                    logger.error(
                        f"[Lark] 无法上传文件({response.code}): {response.msg}"
                    )
                    return None

                if response.data is None:
                    logger.error("[Lark] 上传文件成功但未返回数据(data is None)")
                    return None

                file_key = response.data.file_key
                logger.debug(f"[Lark] 文件上传成功: {file_key}")
                return file_key

        except Exception as e:
            logger.error(f"[Lark] 无法打开或上传文件: {e}")
            return None

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
                    temp_dir = get_astrbot_temp_path()
                    file_path = os.path.join(
                        temp_dir,
                        f"lark_image_{uuid.uuid4().hex[:8]}.jpg",
                    )
                    async with aiofiles.open(file_path, "wb") as f:
                        await f.write(BytesIO(image_data).getvalue())
                else:
                    file_path = comp.file if comp.file else ""

                if image_file is None:
                    if not file_path:
                        logger.error("[Lark] 图片路径为空,无法上传")
                        continue
                    try:
                        image_file = await anyio.to_thread.run_sync(
                            open, file_path, "rb"
                        )
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
                    logger.error("[Lark] API Client im 模块未初始化,无法上传图片")
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
                # 文件将通过 _send_file_message 方法单独发送,这里跳过
                logger.debug("[Lark] 检测到文件组件,将单独发送")
                continue
            elif isinstance(comp, Record):
                # 音频将通过 _send_audio_message 方法单独发送,这里跳过
                logger.debug("[Lark] 检测到音频组件,将单独发送")
                continue
            elif isinstance(comp, Video):
                # 视频将通过 _send_media_message 方法单独发送,这里跳过
                logger.debug("[Lark] 检测到视频组件,将单独发送")
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
    ) -> None:
        """通用的消息链发送方法

        Args:
            message_chain: 要发送的消息链
            lark_client: 飞书客户端
            reply_message_id: 回复的消息ID(用于回复消息)
            receive_id: 接收者ID(用于主动发送)
            receive_id_type: 接收者ID类型,如 'open_id', 'chat_id'(用于主动发送)
        """
        if lark_client.im is None:
            logger.error("[Lark] API Client im 模块未初始化")
            return

        # 分离文件､音频､视频组件和其他组件
        file_components: list[File] = []
        audio_components: list[Record] = []
        media_components: list[Video] = []
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

        # 先发送非文件内容(如果有)
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
                await LarkMessageEvent._send_im_message(
                    lark_client,
                    content=json.dumps(wrapped),
                    msg_type="post",
                    reply_message_id=reply_message_id,
                    receive_id=receive_id,
                    receive_id_type=receive_id_type,
                )

        # 发送附件
        for file_comp in file_components:
            await LarkMessageEvent._send_file_message(
                file_comp, lark_client, reply_message_id, receive_id, receive_id_type
            )

        for audio_comp in audio_components:
            await LarkMessageEvent._send_audio_message(
                audio_comp, lark_client, reply_message_id, receive_id, receive_id_type
            )

        for media_comp in media_components:
            await LarkMessageEvent._send_media_message(
                media_comp, lark_client, reply_message_id, receive_id, receive_id_type
            )

    async def send(self, message: MessageChain) -> None:
        """发送消息链到飞书,然后交给父类做框架级发送/记录"""
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
    ) -> None:
        """发送文件消息

        Args:
            file_comp: 文件组件
            lark_client: 飞书客户端
            reply_message_id: 回复的消息ID(用于回复消息)
            receive_id: 接收者ID(用于主动发送)
            receive_id_type: 接收者ID类型(用于主动发送)
        """
        file_path = file_comp.file or ""
        file_key = await LarkMessageEvent._upload_lark_file(
            lark_client, path=file_path, file_type="stream"
        )
        if not file_key:
            return

        content = json.dumps({"file_key": file_key})
        await LarkMessageEvent._send_im_message(
            lark_client,
            content=content,
            msg_type="file",
            reply_message_id=reply_message_id,
            receive_id=receive_id,
            receive_id_type=receive_id_type,
        )

    @staticmethod
    async def _send_audio_message(
        audio_comp: Record,
        lark_client: lark.Client,
        reply_message_id: str | None = None,
        receive_id: str | None = None,
        receive_id_type: str | None = None,
    ) -> None:
        """发送音频消息

        Args:
            audio_comp: 音频组件
            lark_client: 飞书客户端
            reply_message_id: 回复的消息ID(用于回复消息)
            receive_id: 接收者ID(用于主动发送)
            receive_id_type: 接收者ID类型(用于主动发送)
        """
        # 获取音频文件路径
        try:
            original_audio_path = await audio_comp.convert_to_file_path()
        except Exception as e:
            logger.error(f"[Lark] 无法获取音频文件路径: {e}")
            return

        if (
            not original_audio_path
            or not await anyio.Path(original_audio_path).exists()
        ):
            logger.error(f"[Lark] 音频文件不存在: {original_audio_path}")
            return

        # 转换为opus格式
        converted_audio_path = None
        try:
            audio_path = await convert_audio_to_opus(original_audio_path)
            # 如果转换后路径与原路径不同,说明生成了新文件
            if audio_path != original_audio_path:
                converted_audio_path = audio_path
            else:
                audio_path = original_audio_path
        except Exception as e:
            logger.error(f"[Lark] 音频格式转换失败,将尝试直接上传: {e}")
            # 如果转换失败,继续尝试直接上传原始文件
            audio_path = original_audio_path

        # 获取音频时长
        duration = await get_media_duration(audio_path)

        # 上传音频文件
        file_key = await LarkMessageEvent._upload_lark_file(
            lark_client,
            path=audio_path,
            file_type="opus",
            duration=duration,
        )

        # 清理转换后的临时音频文件
        if converted_audio_path and await anyio.Path(converted_audio_path).exists():
            try:
                await anyio.Path(converted_audio_path).unlink()
                logger.debug(f"[Lark] 已删除转换后的音频文件: {converted_audio_path}")
            except Exception as e:
                logger.warning(f"[Lark] 删除转换后的音频文件失败: {e}")

        if not file_key:
            return

        await LarkMessageEvent._send_im_message(
            lark_client,
            content=json.dumps({"file_key": file_key}),
            msg_type="audio",
            reply_message_id=reply_message_id,
            receive_id=receive_id,
            receive_id_type=receive_id_type,
        )

    @staticmethod
    async def _send_media_message(
        media_comp: Video,
        lark_client: lark.Client,
        reply_message_id: str | None = None,
        receive_id: str | None = None,
        receive_id_type: str | None = None,
    ) -> None:
        """发送视频消息

        Args:
            media_comp: 视频组件
            lark_client: 飞书客户端
            reply_message_id: 回复的消息ID(用于回复消息)
            receive_id: 接收者ID(用于主动发送)
            receive_id_type: 接收者ID类型(用于主动发送)
        """
        # 获取视频文件路径
        try:
            original_video_path = await media_comp.convert_to_file_path()
        except Exception as e:
            logger.error(f"[Lark] 无法获取视频文件路径: {e}")
            return

        if (
            not original_video_path
            or not await anyio.Path(original_video_path).exists()
        ):
            logger.error(f"[Lark] 视频文件不存在: {original_video_path}")
            return

        # 转换为mp4格式
        converted_video_path = None
        try:
            video_path = await convert_video_format(original_video_path, "mp4")
            # 如果转换后路径与原路径不同,说明生成了新文件
            if video_path != original_video_path:
                converted_video_path = video_path
            else:
                video_path = original_video_path
        except Exception as e:
            logger.error(f"[Lark] 视频格式转换失败,将尝试直接上传: {e}")
            # 如果转换失败,继续尝试直接上传原始文件
            video_path = original_video_path

        # 获取视频时长
        duration = await get_media_duration(video_path)

        # 上传视频文件
        file_key = await LarkMessageEvent._upload_lark_file(
            lark_client,
            path=video_path,
            file_type="mp4",
            duration=duration,
        )

        # 清理转换后的临时视频文件
        if converted_video_path and await anyio.Path(converted_video_path).exists():
            try:
                await anyio.Path(converted_video_path).unlink()
                logger.debug(f"[Lark] 已删除转换后的视频文件: {converted_video_path}")
            except Exception as e:
                logger.warning(f"[Lark] 删除转换后的视频文件失败: {e}")

        if not file_key:
            return

        await LarkMessageEvent._send_im_message(
            lark_client,
            content=json.dumps({"file_key": file_key}),
            msg_type="media",
            reply_message_id=reply_message_id,
            receive_id=receive_id,
            receive_id_type=receive_id_type,
        )

    async def react(self, emoji: str) -> None:
        if self.bot.im is None:
            logger.error("[Lark] API Client im 模块未初始化,无法发送表情")
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

    async def _create_streaming_card(self) -> str | None:
        """创建一个开启流式更新模式的卡片实体,返回 card_id｡"""
        if self.bot.cardkit is None:
            logger.error("[Lark] API Client cardkit 模块未初始化")
            return None

        card_json = {
            "schema": "2.0",
            "header": {
                "title": {"content": "", "tag": "plain_text"},
            },
            "config": {
                "streaming_mode": True,
                "summary": {"content": ""},
                "streaming_config": {
                    "print_frequency_ms": {"default": 50},
                    "print_step": {"default": 2},
                    "print_strategy": "fast",
                },
            },
            "body": {
                "elements": [
                    {
                        "tag": "markdown",
                        "content": "",
                        "element_id": "markdown_1",
                    }
                ]
            },
        }

        request = (
            CreateCardRequest.builder()
            .request_body(
                CreateCardRequestBody.builder()
                .type("card_json")
                .data(json.dumps(card_json, ensure_ascii=False))
                .build()
            )
            .build()
        )

        try:
            response = await self.bot.cardkit.v1.card.acreate(request)
        except Exception as e:
            logger.error(f"[Lark] 创建流式卡片实体失败: {e}")
            return None

        if not response.success():
            logger.error(
                f"[Lark] 创建流式卡片实体失败({response.code}): {response.msg}"
            )
            return None

        if response.data is None or not response.data.card_id:
            logger.error("[Lark] 创建流式卡片实体成功但未返回 card_id")
            return None

        card_id = response.data.card_id
        logger.debug(f"[Lark] 创建流式卡片实体成功: {card_id}")
        return card_id

    async def _send_card_message(
        self,
        card_id: str,
        reply_message_id: str | None = None,
        receive_id: str | None = None,
        receive_id_type: str | None = None,
    ) -> bool:
        """将卡片实体作为 interactive 消息发送｡"""
        content = json.dumps(
            {"type": "card", "data": {"card_id": card_id}},
            ensure_ascii=False,
        )
        return await self._send_im_message(
            self.bot,
            content=content,
            msg_type="interactive",
            reply_message_id=reply_message_id,
            receive_id=receive_id,
            receive_id_type=receive_id_type,
        )

    async def _update_streaming_text(
        self,
        card_id: str,
        content: str,
        sequence: int,
    ) -> bool:
        """调用 CardKit 流式更新文本接口,向 markdown_1 组件推送全量文本｡"""
        if self.bot.cardkit is None:
            logger.error("[Lark] API Client cardkit 模块未初始化")
            return False

        request = (
            ContentCardElementRequest.builder()
            .card_id(card_id)
            .element_id("markdown_1")
            .request_body(
                ContentCardElementRequestBody.builder()
                .content(content)
                .sequence(sequence)
                .uuid(str(uuid.uuid4()))
                .build()
            )
            .build()
        )

        try:
            response = await self.bot.cardkit.v1.card_element.acontent(request)
        except Exception as e:
            logger.debug(f"[Lark] 流式更新文本失败 (ignored): {e}")
            return False

        if not response.success():
            logger.debug(f"[Lark] 流式更新文本失败({response.code}): {response.msg}")
            return False

        return True

    async def _close_streaming_mode(
        self,
        card_id: str,
        sequence: int,
    ) -> None:
        """关闭卡片的流式更新模式,使其可正常转发､摘要恢复｡"""
        if self.bot.cardkit is None:
            logger.error("[Lark] API Client cardkit 模块未初始化")
            return

        settings_json = json.dumps(
            {"config": {"streaming_mode": False}},
            ensure_ascii=False,
        )

        request = (
            SettingsCardRequest.builder()
            .card_id(card_id)
            .request_body(
                SettingsCardRequestBody.builder()
                .settings(settings_json)
                .sequence(sequence)
                .uuid(str(uuid.uuid4()))
                .build()
            )
            .build()
        )

        try:
            response = await self.bot.cardkit.v1.card.asettings(request)
        except Exception as e:
            logger.error(f"[Lark] 关闭流式模式失败: {e}")
            return

        if not response.success():
            logger.error(f"[Lark] 关闭流式模式失败({response.code}): {response.msg}")
        else:
            logger.debug(f"[Lark] 流式模式已关闭: {card_id}")

    async def _fallback_send_streaming(self, generator, use_fallback: bool = False):
        """回退到非流式发送:缓冲全部文本后一次性发送,并保留父类副作用｡"""
        buffer = None
        async for chain in generator:
            if not buffer:
                buffer = chain
            else:
                buffer.chain.extend(chain.chain)

        if buffer:
            buffer.squash_plain()
            await self.send(buffer)

        await Metric.upload(msg_event_tick=1, adapter_name=self.platform_meta.name)
        self._has_send_oper = True

    async def send_streaming(self, generator, use_fallback: bool = False):
        """使用 CardKit 流式卡片实现打字机效果｡

        流程:首字到来时创建卡片实体 ￫ 发送消息 ￫ 流式更新文本 ￫ 关闭流式模式｡
        卡片创建延迟到第一个文本 token 到达时,避免工具调用阶段就渲染空卡片｡
        使用解耦发送循环,LLM token 到达时只更新 buffer 并唤醒发送协程,
        发送频率由网络 RTT 自然限流｡
        """
        # Lazy-init: card & sender loop created on first text token
        card_id = None
        sequence = 0
        delta = ""
        last_sent = ""
        done = False
        text_changed = asyncio.Event()
        sender_task = None
        fallback_used = False  # 回退路径已处理 Metric,避免重复上报

        async def _sender_loop() -> None:
            """信号驱动的文本发送循环,有新内容就发,RTT 自然限流｡"""
            nonlocal sequence, last_sent
            while not done:
                await text_changed.wait()
                text_changed.clear()
                snapshot = delta
                if snapshot and snapshot != last_sent:
                    sequence += 1
                    ok = await self._update_streaming_text(card_id, snapshot, sequence)
                    if ok:
                        last_sent = snapshot
                    if delta != snapshot:
                        text_changed.set()

        async def _consume_rest_and_fallback(gen, initial_text: str) -> None:
            """Card creation failed; consume remaining chunks and send non-streaming."""
            nonlocal fallback_used
            fallback_used = True
            buffer = MessageChain().message(initial_text) if initial_text else None
            async for chain in gen:
                if not isinstance(chain, MessageChain):
                    continue
                if buffer is None:
                    buffer = chain
                else:
                    buffer.chain.extend(chain.chain)
            if buffer:
                buffer.squash_plain()
                await self.send(buffer)
            await Metric.upload(msg_event_tick=1, adapter_name=self.platform_meta.name)
            self._has_send_oper = True

        async def _flush_and_close_card() -> None:
            """补发最终文本并关闭当前卡片的流式模式｡"""
            nonlocal sequence
            if delta and delta != last_sent:
                sequence += 1
                await self._update_streaming_text(card_id, delta, sequence)
            sequence += 1
            await self._close_streaming_mode(card_id, sequence)

        try:
            async for chain in generator:
                if not isinstance(chain, MessageChain):
                    continue

                if chain.type == "break":
                    # Tool call boundary: close current card, next text
                    # token will lazily create a new one below the tool
                    # status message.
                    if card_id and sender_task:
                        done = True
                        text_changed.set()
                        await sender_task
                        await _flush_and_close_card()
                        # Reset for lazy new-card creation
                        card_id = None
                        sequence = 0
                        delta = ""
                        last_sent = ""
                        done = False
                        sender_task = None
                    continue

                for comp in chain.chain:
                    if isinstance(comp, Plain):
                        delta += comp.text

                        # Lazy card creation on first text token
                        if card_id is None:
                            card_id = await self._create_streaming_card()
                            if not card_id:
                                logger.warning(
                                    "[Lark] 无法创建流式卡片,回退到非流式发送"
                                )
                                await _consume_rest_and_fallback(generator, delta)
                                return

                            sent = await self._send_card_message(
                                card_id,
                                reply_message_id=self.message_obj.message_id,
                            )
                            if not sent:
                                logger.error(
                                    "[Lark] 发送流式卡片消息失败,回退到非流式发送"
                                )
                                await _consume_rest_and_fallback(generator, delta)
                                return

                            logger.info("[Lark] 流式输出: 使用 CardKit 流式卡片")
                            sender_task = asyncio.create_task(_sender_loop())

                        text_changed.set()
        finally:
            done = True
            text_changed.set()
            if sender_task:
                await sender_task

        # If no text was produced at all, no card was created
        if card_id is None:
            if not fallback_used:
                await Metric.upload(
                    msg_event_tick=1, adapter_name=self.platform_meta.name
                )
                self._has_send_oper = True
            return

        await _flush_and_close_card()

        # 内联父类 send_streaming 的副作用
        await Metric.upload(msg_event_tick=1, adapter_name=self.platform_meta.name)
        self._has_send_oper = True
