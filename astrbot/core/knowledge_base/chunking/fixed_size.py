"""固定大小分块器

按照固定的字符数将文本分块,支持重叠区域。
"""

from .base import BaseChunker


class FixedSizeChunker(BaseChunker):
    """固定大小分块器

    按照固定的字符数分块,并支持块之间的重叠。
    """

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50) -> None:
        """初始化分块器

        Args:
            chunk_size: 块的大小(字符数)
            chunk_overlap: 块之间的重叠字符数

        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    async def chunk(
        self,
        text: str,
        *,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> list[str]:
        """固定大小分块

        Args:
            text: 输入文本
            chunk_size: 每个文本块的最大大小
            chunk_overlap: 每个文本块之间的重叠部分大小

        Returns:
            list[str]: 分块后的文本列表

        """
        chunk_size = self.chunk_size if chunk_size is None else chunk_size
        chunk_overlap = self.chunk_overlap if chunk_overlap is None else chunk_overlap
        if chunk_size <= 0:
            return [text]
        chunk_overlap = max(0, min(chunk_overlap, chunk_size - 1))

        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + chunk_size
            chunk = text[start:end]

            if chunk:
                chunks.append(chunk)

            # 移动窗口,保留重叠部分
            start = end - chunk_overlap

            # 防止无限循环: 如果重叠过大,直接移到end
            if start >= end or chunk_overlap >= chunk_size:
                start = end

        return chunks
