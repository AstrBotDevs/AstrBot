from collections.abc import Callable
from .base import BaseChunker


class RecursiveCharacterChunker(BaseChunker):
    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        length_function: Callable[[str], int] = len,
        is_separator_regex: bool = False,
        separators: list[str] | None = None,
    ):
        """
        初始化递归字符文本分割器

        Args:
            chunk_size: 每个文本块的最大大小
            chunk_overlap: 每个文本块之间的重叠部分大小
            length_function: 计算文本长度的函数
            is_separator_regex: 分隔符是否为正则表达式
            separators: 用于分割文本的分隔符列表，按优先级排序
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.length_function = length_function
        self.is_separator_regex = is_separator_regex

        # 默认分隔符列表，按优先级从高到低
        self.separators = separators or [
            "\n\n",  # 段落
            "\n",  # 换行
            "。",  # 中文句子
            "，",  # 中文逗号
            ". ",  # 句子
            ", ",  # 逗号分隔
            " ",  # 单词
            "",  # 字符
        ]

    async def chunk(self, text: str, **kwargs) -> list[str]:
        """
        递归地将文本分割成块

        Args:
            text: 要分割的文本
            chunk_size: 每个文本块的最大大小
            chunk_overlap: 每个文本块之间的重叠部分大小

        Returns:
            分割后的文本块列表
        """
        if not text:
            return []

        overlap = kwargs.get("chunk_overlap", self.chunk_overlap)
        chunk_size = kwargs.get("chunk_size", self.chunk_size)

        text_length = self.length_function(text)
        if text_length <= chunk_size:
            return [text]

        for separator in self.separators:
            if separator == "":
                return self._split_by_character(text, chunk_size, overlap)

            if separator in text:
                splits = text.split(separator)
                # 重新添加分隔符（除了最后一个片段）
                splits = [s + separator for s in splits[:-1]] + [splits[-1]]
                splits = [s for s in splits if s]
                if len(splits) == 1:
                    continue

                # 递归合并分割后的文本块
                final_chunks = []
                current_chunk = []
                current_chunk_length = 0

                for split in splits:
                    split_length = self.length_function(split)

                    # 如果单个分割部分已经超过了chunk_size，需要递归分割
                    if split_length > chunk_size:
                        # 先处理当前积累的块
                        if current_chunk:
                            combined_text = "".join(current_chunk)
                            final_chunks.extend(
                                await self.chunk(
                                    combined_text,
                                    chunk_size=chunk_size,
                                    chunk_overlap=overlap,
                                )
                            )
                            current_chunk = []
                            current_chunk_length = 0

                        # 递归分割过大的部分
                        final_chunks.extend(
                            await self.chunk(
                                split, chunk_size=chunk_size, chunk_overlap=overlap
                            )
                        )
                    # 如果添加这部分会使当前块超过chunk_size
                    elif current_chunk_length + split_length > chunk_size:
                        # 合并当前块并添加到结果中
                        combined_text = "".join(current_chunk)
                        final_chunks.append(combined_text)

                        # 处理重叠部分
                        overlap_start = max(0, len(combined_text) - overlap)
                        if overlap_start > 0:
                            overlap_text = combined_text[overlap_start:]
                            current_chunk = [overlap_text, split]
                            current_chunk_length = (
                                self.length_function(overlap_text) + split_length
                            )
                        else:
                            current_chunk = [split]
                            current_chunk_length = split_length
                    else:
                        # 添加到当前块
                        current_chunk.append(split)
                        current_chunk_length += split_length

                # 处理剩余的块
                if current_chunk:
                    final_chunks.append("".join(current_chunk))

                return final_chunks

        return [text]

    def _split_by_character(
        self, text: str, chunk_size: int | None = None, overlap: int | None = None
    ) -> list[str]:
        """
        按字符级别分割文本

        Args:
            text: 要分割的文本

        Returns:
            分割后的文本块列表
        """
        chunk_size = chunk_size or self.chunk_size
        overlap = overlap or self.chunk_overlap
        result = []
        for i in range(0, len(text), chunk_size - overlap):
            end = min(i + chunk_size, len(text))
            result.append(text[i:end])
            if end == len(text):
                break

        return result
