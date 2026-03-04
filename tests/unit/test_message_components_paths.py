import os

import pytest

from astrbot.core.message.components import File, Image, Record


@pytest.mark.asyncio
async def test_image_convert_to_file_path_returns_absolute_path(tmp_path):
    file_path = tmp_path / "img.bin"
    file_path.write_bytes(b"img")

    image = Image(file=str(file_path))
    resolved = await image.convert_to_file_path()

    assert resolved == os.path.abspath(str(file_path))


@pytest.mark.asyncio
async def test_record_convert_to_file_path_returns_absolute_path(tmp_path):
    file_path = tmp_path / "record.bin"
    file_path.write_bytes(b"record")

    record = Record(file=str(file_path))
    resolved = await record.convert_to_file_path()

    assert resolved == os.path.abspath(str(file_path))


@pytest.mark.asyncio
async def test_file_component_get_file_returns_absolute_path(tmp_path):
    file_path = tmp_path / "file.bin"
    file_path.write_bytes(b"file")

    file_component = File(name="file.bin", file=str(file_path))
    resolved = await file_component.get_file()

    assert resolved == os.path.abspath(str(file_path))


@pytest.mark.asyncio
async def test_image_convert_to_base64_raises_on_missing_file(tmp_path):
    image = Image(file=str(tmp_path / "missing.bin"))

    with pytest.raises(Exception, match="not a valid file"):
        await image.convert_to_base64()


@pytest.mark.asyncio
async def test_record_convert_to_base64_raises_on_missing_file(tmp_path):
    record = Record(file=str(tmp_path / "missing.bin"))

    with pytest.raises(Exception, match="not a valid file"):
        await record.convert_to_base64()
