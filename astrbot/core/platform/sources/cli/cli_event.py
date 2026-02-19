"""CLI消息事件模块

处理CLI平台的消息事件、消息转换和图片处理。
"""

import asyncio
import base64
import os
import tempfile
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from astrbot import logger
from astrbot.core.message.components import Image, Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

# ------------------------------------------------------------------
# 消息转换
# ------------------------------------------------------------------


class MessageConverter:
    """将文本输入转换为AstrBotMessage对象"""

    def __init__(
        self,
        default_session_id: str = "cli_session",
        user_id: str = "cli_user",
        user_nickname: str = "CLI User",
    ):
        self.default_session_id = default_session_id
        self.user_id = user_id
        self.user_nickname = user_nickname

    def convert(
        self,
        text: str,
        request_id: str | None = None,
        use_isolated_session: bool = False,
    ) -> AstrBotMessage:
        """将文本转换为AstrBotMessage"""
        message = AstrBotMessage()
        message.self_id = "cli_bot"
        message.message_str = text
        message.message = [Plain(text)]
        message.type = MessageType.FRIEND_MESSAGE
        message.message_id = str(uuid.uuid4())

        if use_isolated_session and request_id:
            message.session_id = f"cli_session_{request_id}"
        else:
            message.session_id = self.default_session_id

        message.sender = MessageMember(
            user_id=self.user_id,
            nickname=self.user_nickname,
        )
        message.raw_message = None
        return message


# ------------------------------------------------------------------
# 图片处理
# ------------------------------------------------------------------


def preprocess_chain(message_chain: MessageChain) -> None:
    """预处理消息链：将本地文件图片转换为base64"""
    for comp in message_chain.chain:
        if isinstance(comp, Image) and comp.file and comp.file.startswith("file:///"):
            file_path = comp.file[8:]
            try:
                if os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        data = f.read()
                    comp.file = f"base64://{base64.b64encode(data).decode('utf-8')}"
            except Exception as e:
                logger.error(f"[CLI] Failed to read image file {file_path}: {e}")


def extract_images(message_chain: MessageChain) -> list[dict]:
    """从消息链提取图片信息，返回字典列表"""
    images = []
    for comp in message_chain.chain:
        if isinstance(comp, Image) and comp.file:
            image_info = _process_image(comp.file)
            images.append(image_info)
    return images


def _process_image(file_ref: str) -> dict:
    """处理单个图片引用，返回字典"""
    if file_ref.startswith("http"):
        return {"type": "url", "url": file_ref}

    if file_ref.startswith("file:///"):
        return _process_local_file(file_ref[8:])

    if file_ref.startswith("base64://"):
        return _process_base64(file_ref[9:])

    return {"type": "unknown"}


def _process_local_file(file_path: str) -> dict:
    """处理本地文件"""
    result: dict[str, Any] = {"type": "file", "path": file_path}
    try:
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                data = f.read()
            result["base64_data"] = base64.b64encode(data).decode("utf-8")
            result["size"] = len(data)
        else:
            result["error"] = "Failed to read file"
    except Exception as e:
        result["error"] = str(e)
    return result


def _process_base64(base64_data: str) -> dict:
    """处理base64数据"""
    try:
        data = base64.b64decode(base64_data)
        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)
        temp_file = tempfile.NamedTemporaryFile(
            delete=False, suffix=".png", dir=temp_dir
        )
        temp_file.write(data)
        temp_file.close()
        return {"type": "file", "path": temp_file.name, "size": len(data)}
    except Exception as e:
        return {"type": "base64", "error": str(e)}


# ------------------------------------------------------------------
# 向后兼容：ImageProcessor 和 ImageInfo
# ------------------------------------------------------------------


class ImageInfo:
    """图片信息（向后兼容）"""

    def __init__(
        self, type: str, url=None, path=None, base64_data=None, size=None, error=None
    ):
        self.type = type
        self.url = url
        self.path = path
        self.base64_data = base64_data
        self.size = size
        self.error = error

    def to_dict(self) -> dict:
        result = {"type": self.type}
        if self.url:
            result["url"] = self.url
        if self.path:
            result["path"] = self.path
        if self.base64_data:
            result["base64_data"] = self.base64_data
        if self.size:
            result["size"] = self.size
        if self.error:
            result["error"] = self.error
        return result


class ImageProcessor:
    """图片处理器（向后兼容门面）"""

    @staticmethod
    def local_file_to_base64(file_path: str) -> str | None:
        try:
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    data = f.read()
                return base64.b64encode(data).decode("utf-8")
        except Exception as e:
            logger.error(f"[CLI] Failed to read file {file_path}: {e}")
        return None

    @staticmethod
    def base64_to_temp_file(base64_data: str) -> str | None:
        try:
            data = base64.b64decode(base64_data)
            temp_dir = get_astrbot_temp_path()
            os.makedirs(temp_dir, exist_ok=True)
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix=".png", dir=temp_dir
            )
            temp_file.write(data)
            temp_file.close()
            return temp_file.name
        except Exception:
            return None

    @staticmethod
    def preprocess_chain(message_chain: MessageChain) -> None:
        preprocess_chain(message_chain)

    @staticmethod
    def extract_images(message_chain: MessageChain) -> list[ImageInfo]:
        raw_images = extract_images(message_chain)
        return [
            ImageInfo(
                type=img.get("type", "unknown"),
                url=img.get("url"),
                path=img.get("path"),
                base64_data=img.get("base64_data"),
                size=img.get("size"),
                error=img.get("error"),
            )
            for img in raw_images
        ]

    @staticmethod
    def image_info_to_dict(image_info: ImageInfo) -> dict:
        return image_info.to_dict()


# ------------------------------------------------------------------
# 响应构建器（向后兼容）
# ------------------------------------------------------------------


class ResponseBuilder:
    """JSON响应构建器（向后兼容）"""

    @staticmethod
    def build_success(
        message_chain: MessageChain,
        request_id: str,
        extra: dict[str, Any] | None = None,
    ) -> str:
        import json

        response_text = message_chain.get_plain_text()
        images = ImageProcessor.extract_images(message_chain)
        result = {
            "status": "success",
            "response": response_text,
            "images": [img.to_dict() for img in images],
            "request_id": request_id,
        }
        if extra:
            result.update(extra)
        return json.dumps(result, ensure_ascii=False)

    @staticmethod
    def build_error(
        error_msg: str,
        request_id: str | None = None,
        error_code: str | None = None,
    ) -> str:
        import json

        result: dict[str, Any] = {"status": "error", "error": error_msg}
        if request_id:
            result["request_id"] = request_id
        if error_code:
            result["error_code"] = error_code
        return json.dumps(result, ensure_ascii=False)


# ------------------------------------------------------------------
# CLI消息事件
# ------------------------------------------------------------------


class CLIMessageEvent(AstrMessageEvent):
    """CLI消息事件

    Socket模式下收集管道中所有send()调用的消息，在管道完成(finalize)后统一返回。
    """

    MAX_BUFFER_SIZE = 100

    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        output_queue: asyncio.Queue,
        response_future: asyncio.Future = None,
    ):
        super().__init__(
            message_str=message_str,
            message_obj=message_obj,
            platform_meta=platform_meta,
            session_id=session_id,
        )
        self.output_queue = output_queue
        self.response_future = response_future
        self.send_buffer = None

    async def send(self, message_chain: MessageChain) -> dict[str, Any]:
        await super().send(message_chain)

        if self.response_future is not None and not self.response_future.done():
            preprocess_chain(message_chain)

            if not self.send_buffer:
                self.send_buffer = message_chain
                logger.debug("[CLI] First send: buffer initialized")
            else:
                current_size = len(self.send_buffer.chain)
                new_size = len(message_chain.chain)
                if current_size + new_size > self.MAX_BUFFER_SIZE:
                    logger.warning(
                        f"[CLI] Buffer size limit reached ({current_size} + {new_size} > {self.MAX_BUFFER_SIZE}), truncating"
                    )
                    available = self.MAX_BUFFER_SIZE - current_size
                    if available > 0:
                        self.send_buffer.chain.extend(message_chain.chain[:available])
                else:
                    self.send_buffer.chain.extend(message_chain.chain)
                logger.debug(
                    f"[CLI] Appended to buffer, total: {len(self.send_buffer.chain)}"
                )
        else:
            await self.output_queue.put(message_chain)

        return {"success": True}

    async def send_streaming(
        self,
        generator: AsyncGenerator[MessageChain, None],
        use_fallback: bool = False,
    ) -> None:
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
        await super().send_streaming(generator, use_fallback)

    async def reply(self, message_chain: MessageChain) -> dict[str, Any]:
        return await self.send(message_chain)

    async def finalize(self) -> None:
        if self.response_future and not self.response_future.done():
            if self.send_buffer:
                self.response_future.set_result(self.send_buffer)
                logger.debug(
                    f"[CLI] Pipeline done, response set with {len(self.send_buffer.chain)} components"
                )
            else:
                self.response_future.set_result(None)
                logger.debug("[CLI] Pipeline done, no response to send")
