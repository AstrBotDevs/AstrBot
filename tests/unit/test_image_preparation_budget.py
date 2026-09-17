"""Regression tests for bounded image preparation and output ownership."""

import asyncio
import base64
import io
import random
import threading
from pathlib import Path

import pytest
from PIL import Image

from astrbot.core.utils import media_utils


def test_file_base64_encoding_stream_matches_standard_library(tmp_path):
    source = tmp_path / "payload.bin"
    payload = random.Random(31).randbytes(1023 * 1024 + 5)
    source.write_bytes(payload)

    assert media_utils._encode_file_to_base64(source) == base64.b64encode(
        payload
    ).decode("ascii")


@pytest.mark.parametrize(
    "size,target", [((1280, 1280), (960, 960)), ((131, 197), (71, 103))]
)
def test_strip_resize_matches_composited_lanczos(tmp_path, size, target):
    from PIL import ImageChops

    with Image.frombytes(
        "RGBA", size, random.Random(43).randbytes(size[0] * size[1] * 4)
    ) as source:
        with (
            source.resize(target, Image.Resampling.LANCZOS) as expected,
            media_utils._resize_alpha_in_strips(source, target) as actual,
        ):
            assert actual.size == expected.size
            for color in ("black", "white"):
                with (
                    Image.new("RGBA", target, color) as background,
                    Image.alpha_composite(background, expected) as expected_view,
                    Image.alpha_composite(background, actual) as actual_view,
                    ImageChops.difference(expected_view, actual_view) as delta,
                ):
                    assert max(high for _, high in delta.getextrema()) <= 2


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


@pytest.mark.parametrize(
    "mode,save_options,expected_format",
    [("RGB", {}, "JPEG"), ("RGBA", {"lossless": True}, "PNG")],
)
def test_oversized_static_webp_avoids_pillow_decoder(
    tmp_path, monkeypatch, mode, save_options, expected_format
):
    if media_utils._get_webp_decoder() is None:
        pytest.skip("Pillow does not expose the bundled WebP decoder")

    source = tmp_path / "source.webp"
    pixel_count = 512 * 512
    channels = 4 if mode == "RGBA" else 3
    with Image.frombytes(
        mode,
        (512, 512),
        random.Random(17).randbytes(pixel_count * channels),
    ) as image:
        image.save(source, "WEBP", **save_options)

    def unexpected_pillow_open(*args, **kwargs):
        pytest.fail("Static WebP should use the preallocated decoder path")

    monkeypatch.setattr(media_utils.PILImage, "open", unexpected_pillow_open)
    output = media_utils._compress_image_sync(source, tmp_path, 64, 95, True, 20_000)
    monkeypatch.undo()

    assert output is not None
    with Image.open(output) as prepared:
        assert prepared.format == expected_format
        assert max(prepared.size) <= 64


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


def test_animation_is_preserved_when_compliant_and_rejected_when_oversized(tmp_path):
    source = tmp_path / "animated.gif"
    frames = [Image.new("RGB", (16, 12), color) for color in ("red", "blue")]
    try:
        frames[0].save(
            source,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=40,
            loop=0,
        )
    finally:
        for frame in frames:
            frame.close()

    original = source.read_bytes()
    assert media_utils._compress_image_sync(source, tmp_path, 4, 95, True) is None
    assert source.read_bytes() == original

    with pytest.raises(media_utils.ImagePayloadTooLargeError):
        media_utils._compress_image_sync(source, tmp_path, 4, 95, True, 1)
    assert list(tmp_path.glob("compressed_*")) == []


def test_webp_animation_is_preserved_without_flattening(tmp_path):
    source = tmp_path / "animated.webp"
    frames = [Image.new("RGBA", (16, 12), color) for color in ("red", "blue")]
    try:
        frames[0].save(
            source,
            format="WEBP",
            save_all=True,
            append_images=frames[1:],
            duration=40,
            loop=0,
        )
    finally:
        for frame in frames:
            frame.close()

    original = source.read_bytes()
    assert media_utils._compress_image_sync(source, tmp_path, 4, 95, True) is None
    assert source.read_bytes() == original

    with pytest.raises(media_utils.ImagePayloadTooLargeError):
        media_utils._compress_image_sync(source, tmp_path, 4, 95, True, 1)


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


@pytest.mark.parametrize("orientation", range(1, 9))
def test_thumbnail_preserves_exif_corner_placement(tmp_path, orientation):
    from PIL import ImageOps

    source = tmp_path / "corners.jpg"
    with Image.new("RGB", (800, 600), "black") as image:
        image.paste("red", (0, 0, 400, 300))
        image.paste("green", (400, 0, 800, 300))
        image.paste("blue", (0, 300, 400, 600))
        image.paste("white", (400, 300, 800, 600))
        exif = image.getexif()
        exif[274] = orientation
        image.save(source, quality=95, exif=exif)
    with Image.open(source) as image:
        expected = ImageOps.exif_transpose(image)
        expected.thumbnail((160, 160))
    try:
        output = media_utils._compress_image_sync(source, tmp_path, 160, 95, True)
        assert output is not None
        with Image.open(output) as actual:
            assert actual.size == expected.size
            assert actual.getexif().get(274, 1) == 1
            for x in (actual.width // 4, actual.width * 3 // 4):
                for y in (actual.height // 4, actual.height * 3 // 4):
                    assert (
                        max(
                            abs(a - b)
                            for a, b in zip(
                                actual.getpixel((x, y)), expected.getpixel((x, y))
                            )
                        )
                        <= 5
                    )
    finally:
        expected.close()


def test_jpeg_stops_at_first_fitting_quality(tmp_path, monkeypatch):
    path = tmp_path / "photo.jpg"
    with Image.new("RGB", (200, 100), (20, 40, 80)) as image:
        image.save(path, "JPEG", quality=95)
    qualities = []
    original_save = Image.Image.save

    def save(image, target, fmt=None, **kwargs):
        if fmt == "JPEG":
            qualities.append(kwargs.get("quality"))
        return original_save(image, target, fmt, **kwargs)

    monkeypatch.setattr(Image.Image, "save", save)
    output = media_utils._compress_image_sync(
        path, tmp_path, 100, 95, True, 4 * 1024 * 1024
    )
    assert output is not None
    assert qualities == [95]


def test_cua_tries_next_jpeg_quality_without_resizing(tmp_path, monkeypatch):
    path = tmp_path / "opaque.png"
    with Image.frombytes(
        "RGB", (120, 80), random.Random(23).randbytes(120 * 80 * 3)
    ) as image:
        image.save(path, "PNG")
    qualities = []
    original_save = Image.Image.save

    def save(image, target, fmt=None, **kwargs):
        if fmt == "JPEG":
            quality = kwargs.get("quality")
            qualities.append(quality)
            if quality == 95:
                original_save(image, target, fmt, **kwargs)
                with Path(target).open("ab") as candidate:
                    candidate.write(b"x" * 20_000)
                return
        return original_save(image, target, fmt, **kwargs)

    monkeypatch.setattr(Image.Image, "save", save)
    output = media_utils._compress_image_sync(
        path, tmp_path, 1, 95, True, 20_000, preserve_dimensions=True
    )
    assert output is not None
    assert qualities[:2] == [95, 85]
    with Image.open(output) as image:
        assert image.size == (120, 80)


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
async def test_disabled_compression_rejects_oversize_before_read(tmp_path, monkeypatch):
    source = tmp_path / "oversized.png"
    with Image.new("RGB", (32, 32), "red") as image:
        image.save(source)

    def unexpected_read(path):
        pytest.fail("Oversized source was read before checking the byte limit")

    monkeypatch.setattr(Path, "read_bytes", unexpected_read)
    with pytest.raises(media_utils.ImagePayloadTooLargeError):
        await media_utils.prepare_image_source(
            str(source),
            options=media_utils.ImagePreparationOptions(
                enabled=False, max_encoded_bytes=1
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [media_utils.ImagePayloadTooLargeError, MemoryError, OSError, ValueError]
)
async def test_agent_does_not_fall_back_to_original_on_resource_error(
    tmp_path, monkeypatch, failure
):
    source = tmp_path / "image.png"
    with Image.new("RGB", (8, 8), "red") as image:
        image.save(source)

    async def fail(*args, **kwargs):
        raise failure("bounded failure")

    monkeypatch.setattr(media_utils, "compress_image", fail)
    with pytest.raises(failure):
        await media_utils.prepare_image_source(str(source))


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [False, True])
async def test_cancelled_worker_cleans_after_exit(tmp_path, monkeypatch, timeout):
    source = tmp_path / "source"
    source.write_bytes(b"source")
    monkeypatch.setattr(media_utils, "IMAGE_COMPRESS_DEFAULT_MIN_FILE_SIZE_BYTES", 1)
    output = tmp_path / "worker-output"
    entered = threading.Event()
    release = threading.Event()
    cleaned = asyncio.Event()
    original_unlink = Path.unlink

    def unlink(path, *args, **kwargs):
        original_unlink(path, *args, **kwargs)
        if path == output:
            cleaned.set()

    monkeypatch.setattr(Path, "unlink", unlink)

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
    # A finished task can still have its cleanup callback queued on the loop.
    await asyncio.wait_for(cleaned.wait(), timeout=5)
    assert not output.exists()
    assert source.read_bytes() == b"source"
