"""文档分块器基类

定义了文档分块处理的抽象接口。
"""

from abc import ABC, abstractmethod


def validate_chunk_params(chunk_size: int, chunk_overlap: int) -> None:
    """Validate chunking parameters before splitting.

    A non-positive ``chunk_size`` makes the sliding window never advance (the
    loop never terminates), and a negative ``chunk_overlap`` moves it backwards
    — both hang the chunker. Reject invalid values up front instead.
    """
    if (
        not isinstance(chunk_size, int)
        or isinstance(chunk_size, bool)
        or chunk_size <= 0
    ):
        raise ValueError(f"chunk_size must be a positive integer, got {chunk_size!r}")
    if (
        not isinstance(chunk_overlap, int)
        or isinstance(chunk_overlap, bool)
        or chunk_overlap < 0
    ):
        raise ValueError(
            f"chunk_overlap must be a non-negative integer, got {chunk_overlap!r}"
        )


class BaseChunker(ABC):
    """分块器基类

    所有分块器都应该继承此类并实现 chunk 方法。
    """

    @abstractmethod
    async def chunk(self, text: str, **kwargs) -> list[str]:
        """将文本分块

        Args:
            text: 输入文本

        Returns:
            list[str]: 分块后的文本列表

        """
