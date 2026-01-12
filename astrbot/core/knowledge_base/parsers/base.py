"""文档解析器基类和数据结构

定义了文档解析器的抽象接口和相关数据类。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class MediaItem:
    """多媒体项

    表示从文档中提取的多媒体资源。
    """

    media_type: str  # image, video
    file_name: str
    content: bytes
    mime_type: str


@dataclass
class ParseResult:
    """解析结果

    包含解析后的文本内容和提取的多媒体资源。
    """

    text: str
    media: list[MediaItem]


class BaseParser(ABC):
    """文档解析器基类

    所有文档解析器都应该继承此类并实现 parse 方法。
    """

    @abstractmethod
    async def parse(self, file_content: bytes, file_name: str) -> ParseResult:
        """解析文档

        Args:
            file_content: 文件内容
            file_name: 文件名

        Returns:
            ParseResult: 解析结果

        """
