"""Tests for the shared streaming upload save helper."""

import pytest

from astrbot.core.utils.upload import (
    COPY_BLOCK_SIZE,
    UploadTooLargeError,
    save_upload_stream,
)


class FakeUpload:
    """Minimal async upload object: seek + bounded read."""

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    async def seek(self, pos: int) -> int:
        self._pos = pos
        return self._pos

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._data) - self._pos
        block = self._data[self._pos : self._pos + size]
        self._pos += len(block)
        return block


@pytest.mark.asyncio
async def test_save_upload_stream_writes_all_bytes(tmp_path):
    data = b"x" * (COPY_BLOCK_SIZE * 2 + 123)
    dest = tmp_path / "out.bin"

    written = await save_upload_stream(FakeUpload(data), dest)

    assert written == len(data)
    assert dest.read_bytes() == data


@pytest.mark.asyncio
async def test_save_upload_stream_respects_max_bytes(tmp_path):
    data = b"x" * (COPY_BLOCK_SIZE + 1)
    dest = tmp_path / "out.bin"

    with pytest.raises(UploadTooLargeError):
        await save_upload_stream(FakeUpload(data), dest, max_bytes=COPY_BLOCK_SIZE)

    # The partial file must not survive a rejected upload.
    assert not dest.exists()


@pytest.mark.asyncio
async def test_save_upload_stream_preserves_existing_dest_on_failure(tmp_path):
    """A failed overwrite must not destroy a pre-existing destination."""
    dest = tmp_path / "out.bin"
    dest.write_bytes(b"original")

    with pytest.raises(UploadTooLargeError):
        await save_upload_stream(
            FakeUpload(b"x" * (COPY_BLOCK_SIZE + 1)),
            dest,
            max_bytes=COPY_BLOCK_SIZE,
        )

    assert dest.read_bytes() == b"original"
    # Only the uniquely named temp file is removed; nothing is left behind.
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.asyncio
async def test_save_upload_stream_allows_exact_limit(tmp_path):
    data = b"x" * COPY_BLOCK_SIZE
    dest = tmp_path / "out.bin"

    written = await save_upload_stream(
        FakeUpload(data), dest, max_bytes=COPY_BLOCK_SIZE
    )

    assert written == COPY_BLOCK_SIZE
    assert dest.read_bytes() == data
