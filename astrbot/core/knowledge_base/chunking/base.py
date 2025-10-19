"""文档分块器基类

定义了文档分块处理的抽象接口。
"""

from abc import ABC, abstractmethod


class BaseChunker(ABC):
    """分块器基类

    所有分块器都应该继承此类并实现 chunk 方法。
    """

    @abstractmethod
    async def chunk(self, text: str) -> list[str]:
        """将文本分块

        Args:
            text: 输入文本

        Returns:
            list[str]: 分块后的文本列表
        """
