"""Regression tests for bounded image preparation and output ownership."""

import asyncio
import io
import random
import threading
from pathlib import Path

import pytest
from PIL import Image

from astrbot.core.utils import media_utils


@pytest.mark.parametrize(
    "image_format,mode", [("PNG", "RGBA"), ("JPEG", "RGB"), ("WEBP", "RGBA")]
)
def test_compliant_bytes_are_preserved(tmp_path, image_format, mode):
    path = tmp_path / "original"
    with Image.new(mode, (32, 20)) as image:
        image.save(path, image_format)
    original = path.read_bytes()
    result = media_utils._compress_image_sync(path, tmp_path, 1280, 95, True)
    assert result is None
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_pixel_compliant_noise_fits_byte_budget(tmp_path):
    source = tmp_path / "noise.png"
    with Image.frombytes(
        "RGBA", (1280, 1280), random.Random(7).randbytes(1280 * 1280 * 4)
    ) as image:
        image.save(source)
    budget = 4 * 1024 * 1024
    assert 4 * ((source.stat().st_size + 2) // 3) > budget
    result = media_utils._compress_image_sync(source, tmp_path, 1280, 95, True, budget)
    assert result is not None
    assert 4 * ((Path(result).stat().st_size + 2) // 3) <= budget
    with Image.open(result) as image:
        assert image.mode == "RGBA"
        assert image.width < 1280


def test_screenshot_preserves_oriented_coordinates(tmp_path):
    path = tmp_path / "oriented.jpg"
    with Image.frombytes(
        "RGB", (120, 80), random.Random(1).randbytes(120 * 80 * 3)
    ) as image:
        exif = image.getexif()
        exif[274] = 6
        image.save(path, quality=100, exif=exif)
    output = media_utils._compress_image_sync(
        path, tmp_path, 10, 80, True, 10_000, preserve_dimensions=True
    )
    assert output is not None
    with Image.open(output) as image:
        assert image.size == (80, 120)
        assert image.getexif().get(274, 1) == 1


def test_impossible_screenshot_budget_rejects_without_resizing(tmp_path):
    path = tmp_path / "screenshot.png"
    with Image.new("RGBA", (100, 60), (20, 100, 50, 127)) as image:
        image.save(path)
    with pytest.raises(media_utils.ImagePayloadTooLargeError):
        media_utils._compress_image_sync(
            path, tmp_path, 1, 95, True, 1, preserve_dimensions=True
        )
    assert list(tmp_path.iterdir()) == [path]


def test_write_failure_removes_partial_candidate(tmp_path, monkeypatch):
    source = io.BytesIO()
    with Image.new("RGB", (100, 60)) as image:
        image.save(source, "PNG")

    def fail_write(image, path, *args, **kwargs):
        Path(path).write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(Image.Image, "save", fail_write)
    with pytest.raises(OSError, match="disk full"):
        media_utils._compress_image_sync(source.getvalue(), tmp_path, 10, 95, True)
    assert not list(tmp_path.iterdir())


def test_decode_failure_leaves_no_output(tmp_path):
    with pytest.raises(OSError):
        media_utils._compress_image_sync(b"invalid", tmp_path, 10, 95, True)
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [media_utils.ImagePayloadTooLargeError, MemoryError]
)
async def test_agent_does_not_fall_back_to_original_on_resource_error(
    monkeypatch, failure
):
    from astrbot.core import astr_main_agent

    async def fail(*args, **kwargs):
        raise failure("bounded failure")

    monkeypatch.setattr(astr_main_agent, "compress_image", fail)
    with pytest.raises(failure):
        await astr_main_agent._compress_image_for_provider("image.png", {})


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [False, True])
async def test_cancelled_worker_cleans_after_exit(tmp_path, monkeypatch, timeout):
    source = tmp_path / "source"
    source.write_bytes(b"source")
    output = tmp_path / "worker-output"
    entered = threading.Event()
    release = threading.Event()

    def blocked_worker(*args, **kwargs):
        entered.set()
        release.wait(5)
        output.write_bytes(b"prepared")
        return str(output)

    monkeypatch.setattr(media_utils, "_compress_image_sync", blocked_worker)
    task = asyncio.create_task(media_utils.compress_image(str(source)))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        if timeout:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(task, timeout=0.01)
        else:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    finally:
        release.set()
    # Let the shielded worker and its cleanup callback finish.
    for _ in range(100):
        await asyncio.sleep(0.01)
        if not any(
            not pending.done()
            for pending in asyncio.all_tasks()
            if pending is not asyncio.current_task()
        ):
            break
    assert not output.exists()
    assert source.read_bytes() == b"source"


@pytest.mark.asyncio
async def test_file_read_preserves_compliant_png_and_mime(tmp_path, monkeypatch):
    from astrbot.core.computer import file_read_utils

    monkeypatch.setattr(file_read_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    source = io.BytesIO()
    with Image.new("RGBA", (20, 10), (5, 10, 15, 100)) as image:
        image.save(source, "PNG")
    import base64

    result = await file_read_utils._compress_image_bytes_to_base64(source.getvalue())
    assert result["mime_type"] == "image/png"
    assert base64.b64decode(result["base64"]) == source.getvalue()
    assert not list(tmp_path.iterdir())
