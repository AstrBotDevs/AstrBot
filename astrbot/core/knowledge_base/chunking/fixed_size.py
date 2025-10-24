"""固定大小分块器

按照固定的字符数将文本分块,支持重叠区域。
"""

from astrbot.core.knowledge_base.chunking.base import BaseChunker


class FixedSizeChunker(BaseChunker):
    """固定大小分块器

    按照固定的字符数分块,并支持块之间的重叠。
    """

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        """初始化分块器

        Args:
            chunk_size: 块的大小(字符数)
            chunk_overlap: 块之间的重叠字符数
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    async def chunk(self, text: str, **kwargs) -> list[str]:
        """固定大小分块

        Args:
            text: 输入文本

        Returns:
            list[str]: 分块后的文本列表
        """
        chunk_size = kwargs.get("chunk_size", self.chunk_size)
        chunk_overlap = kwargs.get("chunk_overlap", self.chunk_overlap)

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
