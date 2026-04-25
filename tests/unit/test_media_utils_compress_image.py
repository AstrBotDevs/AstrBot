"""Tests for media_utils.compress_image()."""

import base64
from pathlib import Path

import pytest
from PIL import Image as PILImage

from astrbot.core.utils import media_utils


@pytest.mark.asyncio
async def test_compress_image_downscales_small_files_exceeding_max_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))

    img_path = tmp_path / "big.png"
    with PILImage.new("RGB", (1900, 2532), color=(255, 0, 0)) as img:
        img.save(img_path, format="PNG", optimize=True)

    assert img_path.stat().st_size < 1024 * 1024

    compressed_path = await media_utils.compress_image(str(img_path), max_size=1280)

    assert compressed_path != str(img_path)
    assert Path(compressed_path).exists()
    with PILImage.open(compressed_path) as compressed_img:
        assert max(compressed_img.size) <= 1280


@pytest.mark.asyncio
async def test_compress_image_skips_small_files_within_max_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))

    img_path = tmp_path / "small.png"
    with PILImage.new("RGB", (800, 600), color=(0, 0, 255)) as img:
        img.save(img_path, format="PNG", optimize=True)

    assert img_path.stat().st_size < 1024 * 1024

    compressed_path = await media_utils.compress_image(str(img_path), max_size=1280)

    assert compressed_path == str(img_path)


@pytest.mark.asyncio
async def test_compress_image_downscales_data_url_even_when_small(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))

    buffer = Path(tmp_path) / "big.png"
    with PILImage.new("RGB", (1900, 2532), color=(0, 255, 0)) as img:
        img.save(buffer, format="PNG", optimize=True)
    raw = buffer.read_bytes()

    assert len(raw) < 1024 * 1024

    encoded = base64.b64encode(raw).decode()
    data_url = f"data:image/png;base64,{encoded}"
    compressed_path = await media_utils.compress_image(data_url, max_size=1280)

    assert compressed_path != data_url
    assert Path(compressed_path).exists()
    with PILImage.open(compressed_path) as compressed_img:
        assert max(compressed_img.size) <= 1280

