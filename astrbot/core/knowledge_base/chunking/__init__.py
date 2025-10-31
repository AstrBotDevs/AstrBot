"""文档分块模块"""

from .base import BaseChunker
from .fixed_size import FixedSizeChunker

__all__ = [
    "BaseChunker",
    "FixedSizeChunker",
]
