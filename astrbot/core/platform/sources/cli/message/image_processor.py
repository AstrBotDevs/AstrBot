"""图片处理模块

拆分为单一职责的小组件：
- ImageCodec: base64编解码
- ImageFileIO: 文件读写
- ImageExtractor: 从消息链提取图片
- ImageInfo: 数据结构
"""

import base64
import os
import tempfile
from dataclasses import dataclass

from astrbot import logger
from astrbot.core.message.components import Image
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

# ============================================================
# 数据结构
# ============================================================


@dataclass
class ImageInfo:
    """图片信息数据结构"""

    type: str  # "url", "file", "base64"
    url: str | None = None
    path: str | None = None
    base64_data: str | None = None
    size: int | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        """转换为字典"""
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


# ============================================================
# 原子组件：Base64编解码
# ============================================================


class ImageCodec:
    """Base64编解码器

    单一职责：仅负责base64编解码
    """

    @staticmethod
    def encode(data: bytes) -> str:
        """编码为base64"""
        return base64.b64encode(data).decode("utf-8")

    @staticmethod
    def decode(base64_str: str) -> bytes:
        """解码base64"""
        return base64.b64decode(base64_str)


# ============================================================
# 原子组件：文件I/O
# ============================================================


class ImageFileIO:
    """图片文件I/O

    单一职责：仅负责文件读写
    """

    @staticmethod
    def read(file_path: str) -> bytes | None:
        """读取文件"""
        try:
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    return f.read()
        except Exception as e:
            logger.error("Failed to read file %s: %s", file_path, e)
        return None

    @staticmethod
    def write_temp(data: bytes, suffix: str = ".png") -> str | None:
        """写入临时文件"""
        try:
            temp_dir = get_astrbot_temp_path()
            os.makedirs(temp_dir, exist_ok=True)

            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix,
                dir=temp_dir,
            )
            temp_file.write(data)
            temp_file.close()
            return temp_file.name
        except Exception as e:
            logger.error("Failed to write temp file: %s", e)
            return None


# ============================================================
# 组合组件：图片提取器
# ============================================================


class ImageExtractor:
    """图片提取器

    组合ImageCodec和ImageFileIO，从消息链提取图片信息
    """

    @staticmethod
    def extract(message_chain: MessageChain) -> list[ImageInfo]:
        """从消息链提取图片信息"""
        images = []

        for comp in message_chain.chain:
            if isinstance(comp, Image) and comp.file:
                image_info = ImageExtractor._process_image(comp.file)
                images.append(image_info)

        return images

    @staticmethod
    def _process_image(file_ref: str) -> ImageInfo:
        """处理单个图片引用"""
        if file_ref.startswith("http"):
            return ImageInfo(type="url", url=file_ref)

        elif file_ref.startswith("file:///"):
            return ImageExtractor._process_local_file(file_ref[8:])

        elif file_ref.startswith("base64://"):
            return ImageExtractor._process_base64(file_ref[9:])

        return ImageInfo(type="unknown")

    @staticmethod
    def _process_local_file(file_path: str) -> ImageInfo:
        """处理本地文件"""
        info = ImageInfo(type="file", path=file_path)

        data = ImageFileIO.read(file_path)
        if data:
            info.base64_data = ImageCodec.encode(data)
            info.size = len(data)
        else:
            info.error = "Failed to read file"

        return info

    @staticmethod
    def _process_base64(base64_data: str) -> ImageInfo:
        """处理base64数据"""
        try:
            data = ImageCodec.decode(base64_data)
            temp_path = ImageFileIO.write_temp(data)

            if temp_path:
                return ImageInfo(type="file", path=temp_path, size=len(data))
            else:
                return ImageInfo(type="base64", error="Failed to save to temp file")
        except Exception as e:
            return ImageInfo(type="base64", error=str(e))


# ============================================================
# 组合组件：消息链预处理器
# ============================================================


class ChainPreprocessor:
    """消息链预处理器

    将消息链中的本地文件图片转换为base64
    """

    @staticmethod
    def preprocess(message_chain: MessageChain) -> None:
        """预处理消息链（原地修改）"""
        for comp in message_chain.chain:
            if (
                isinstance(comp, Image)
                and comp.file
                and comp.file.startswith("file:///")
            ):
                file_path = comp.file[8:]
                data = ImageFileIO.read(file_path)
                if data:
                    comp.file = f"base64://{ImageCodec.encode(data)}"


# ============================================================
# 向后兼容：ImageProcessor门面
# ============================================================


class ImageProcessor:
    """图片处理器门面（向后兼容）

    组合所有小组件，提供统一接口
    """

    @staticmethod
    def local_file_to_base64(file_path: str) -> str | None:
        """将本地文件转换为base64"""
        data = ImageFileIO.read(file_path)
        return ImageCodec.encode(data) if data else None

    @staticmethod
    def base64_to_temp_file(base64_data: str) -> str | None:
        """将base64保存到临时文件"""
        try:
            data = ImageCodec.decode(base64_data)
            return ImageFileIO.write_temp(data)
        except Exception:
            return None

    @staticmethod
    def preprocess_chain(message_chain: MessageChain) -> None:
        """预处理消息链"""
        ChainPreprocessor.preprocess(message_chain)

    @staticmethod
    def extract_images(message_chain: MessageChain) -> list[ImageInfo]:
        """提取图片信息"""
        return ImageExtractor.extract(message_chain)

    @staticmethod
    def image_info_to_dict(image_info: ImageInfo) -> dict:
        """转换为字典"""
        return image_info.to_dict()
