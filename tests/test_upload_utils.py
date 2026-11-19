"""Tests for the shared streaming upload save helper."""

import os
from pathlib import Path

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


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["a" * 251 + ".bin", "图" * 83 + ".bin"])
@pytest.mark.parametrize("existing", [False, True])
async def test_save_upload_stream_long_filename(
    tmp_path: Path, filename: str, existing: bool
) -> None:
    """Save valid long names without overflowing the temporary filename."""
    if os.name == "nt":
        tmp_path = Path("\\\\?\\" + str(tmp_path))
    dest = tmp_path / filename
    # Establish that the destination name itself is supported by the filesystem.
    dest.write_bytes(b"original")
    if not existing:
        dest.unlink()

    written = await save_upload_stream(FakeUpload(b"replacement"), dest)

    assert written == len(b"replacement")
    assert dest.read_bytes() == b"replacement"
    assert list(tmp_path.iterdir()) == [dest]


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["a" * 251 + ".bin", "图" * 83 + ".bin"])
async def test_save_upload_stream_long_filename_preserved_on_failure(
    tmp_path: Path, filename: str
) -> None:
    """Preserve an existing long-named file when the upload exceeds its cap."""
    if os.name == "nt":
        tmp_path = Path("\\\\?\\" + str(tmp_path))
    dest = tmp_path / filename
    dest.write_bytes(b"original")

    with pytest.raises(UploadTooLargeError):
        await save_upload_stream(FakeUpload(b"replacement"), dest, max_bytes=1)

    assert dest.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [dest]
