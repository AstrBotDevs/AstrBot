"""分块参数校验的单元测试。

``validate_chunk_params`` 是分块器在进入滑动窗口循环前的守卫：非正的 chunk_size
会让窗口永不前进，负的 chunk_overlap 会让窗口倒退，两者都会挂死分块器。
"""

import pytest

from astrbot.core.knowledge_base.chunking.base import validate_chunk_params
from astrbot.core.knowledge_base.chunking.fixed_size import FixedSizeChunker
from astrbot.core.knowledge_base.chunking.recursive import RecursiveCharacterChunker


@pytest.mark.parametrize(
    ("chunk_size", "chunk_overlap"),
    [
        (0, 0),
        (-1, 0),
        (True, 0),  # bool 是 int 子类，但不该被当作合法大小
        ("512", 0),
        (None, 0),
        (512, -1),
        (512, True),
        (512, "1"),
        (512, None),
    ],
)
def test_validate_chunk_params_rejects_invalid(chunk_size, chunk_overlap):
    with pytest.raises(ValueError):
        validate_chunk_params(chunk_size, chunk_overlap)


def test_validate_chunk_params_accepts_valid():
    validate_chunk_params(1, 0)
    validate_chunk_params(512, 50)
    validate_chunk_params(512, 511)


@pytest.mark.asyncio
async def test_fixed_size_chunker_rejects_invalid_params():
    chunker = FixedSizeChunker(chunk_size=0, chunk_overlap=0)
    with pytest.raises(ValueError):
        await chunker.chunk("some text")

    chunker = FixedSizeChunker(chunk_size=10, chunk_overlap=-1)
    with pytest.raises(ValueError):
        await chunker.chunk("some text")

    # kwargs 覆盖同样要经过校验
    chunker = FixedSizeChunker()
    with pytest.raises(ValueError):
        await chunker.chunk("some text", chunk_size=0)


@pytest.mark.asyncio
async def test_recursive_chunker_rejects_invalid_params():
    chunker = RecursiveCharacterChunker(chunk_size=0, chunk_overlap=0)
    with pytest.raises(ValueError):
        await chunker.chunk("some text")

    chunker = RecursiveCharacterChunker(chunk_size=10, chunk_overlap=-5)
    with pytest.raises(ValueError):
        await chunker.chunk("some text")
