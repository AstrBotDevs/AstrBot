"""Pixel, error and lifecycle contracts for the stage's PNG encoder."""

import asyncio
import errno
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from astrbot.core.utils import media_utils as media
from astrbot.core.utils.io import DownloadFileHTTPError


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "get_astrbot_temp_path", lambda: str(tmp_path / "cache"))


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "BMP", "WEBP", "GIF"])
async def test_still_formats_return_owned_png_without_mutating_source(tmp_path, fmt):
    source = tmp_path / "misleading.jpg"
    Image.new("RGB", (200, 100), "red").save(source, fmt)
    original = source.read_bytes()
    path = await media.prepare_model_image(
        str(source), max_size=80, output_dir=tmp_path
    )
    assert path and Path(path).is_file() and Path(path) != source
    with Image.open(path) as image:
        assert image.format == "PNG" and getattr(image, "n_frames", 1) == 1
        assert image.size == (80, 40)
        assert image.getpixel((40, 20))[0] >= 250
    assert source.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fmt,cover", [("GIF", False), ("WEBP", False), ("PNG", False), ("PNG", True)]
)
@pytest.mark.parametrize("count", [2, 12])
async def test_animation_sampling_cover_and_blank_cells(tmp_path, fmt, cover, count):
    colors = [(index * 20, 0, 0) for index in range(count)]
    frames = [Image.new("RGB", (12, 8), color) for color in colors]
    if cover:
        frames.insert(0, Image.new("RGB", (12, 8), "blue"))
    source = tmp_path / "animation.bin"
    frames[0].save(
        source,
        fmt,
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
        lossless=True,
        **({"default_image": cover} if fmt == "PNG" else {}),
    )
    original = source.read_bytes()
    path = await media.prepare_model_image(
        str(source), max_size=1280, output_dir=tmp_path
    )
    indices = [0, 1] if count == 2 else [0, 1, 3, 4, 6, 7, 8, 10, 11]
    with Image.open(path) as image:
        assert image.format == "PNG" and getattr(image, "n_frames", 1) == 1
        assert image.size == (36, 24)
        for cell in range(9):
            expected = colors[indices[cell]] if cell < len(indices) else (255, 255, 255)
            assert (
                image.getpixel(((cell % 3) * 12 + 6, (cell // 3) * 8 + 4)) == expected
            )
    small = await media.prepare_model_image(
        str(source), max_size=18, output_dir=tmp_path
    )
    with Image.open(small) as image:
        assert image.size == (18, 12)
    assert source.read_bytes() == original


@pytest.mark.asyncio
async def test_exif_and_cmyk_are_preserved_for_display(tmp_path):
    source = tmp_path / "oriented.jpg"
    exif = Image.Exif()
    exif[274] = 6
    image = Image.new("CMYK", (200, 100), (0, 255, 255, 0))
    image.save(source, exif=exif)
    original = source.read_bytes()
    path = await media.prepare_model_image(
        str(source), max_size=80, output_dir=tmp_path
    )
    with Image.open(path) as result:
        assert result.size == (40, 80) and result.mode == "RGB"
        assert result.getexif().get(274, 1) == 1
        assert result.getpixel((20, 40)) == (255, 0, 0)
    assert source.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,color", [("RGBA", (255, 0, 0, 128)), ("RGB", (255, 0, 0)), ("L", 128)]
)
async def test_alpha_and_color_key_survive_downscaling(tmp_path, mode, color):
    source = tmp_path / "alpha.png"
    Image.new(mode, (200, 100), color).save(
        source, **({} if mode == "RGBA" else {"transparency": color})
    )
    path = await media.prepare_model_image(
        str(source), max_size=80, output_dir=tmp_path
    )
    with Image.open(path) as result:
        assert result.size == (80, 40) and result.mode == "RGBA"
        assert result.getpixel((40, 20))[3] == (128 if mode == "RGBA" else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["P", "1"])
async def test_palette_and_binary_thin_lines_use_lanczos(tmp_path, mode):
    source = tmp_path / "lines.png"
    image = Image.new(mode, (64, 64), 255)
    if mode == "P":
        image.putpalette([value for i in range(256) for value in (i, i, i)])
    for y in range(64):
        image.putpixel((0, y), 0)
    image.save(source)
    expected = image.convert("RGB" if mode == "P" else "L")
    expected.thumbnail((16, 16), Image.Resampling.LANCZOS)
    path = await media.prepare_model_image(
        str(source), max_size=16, output_dir=tmp_path
    )
    with Image.open(path) as result:
        assert result.convert("L").getextrema()[0] < 255
        assert result.convert("L").tobytes() == expected.convert("L").tobytes()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "size,limit", [((2560, 1280), 1280), ((5120, 2560), 1280), ((513, 257), 128)]
)
async def test_16bit_gradient_survives_large_reduction(tmp_path, size, limit):
    source = tmp_path / "gradient.png"
    row = b"".join(
        int(x * 65535 / (size[0] - 1)).to_bytes(2, "little") for x in range(size[0])
    )
    Image.frombytes("I;16", size, row * size[1]).save(source)
    original = source.read_bytes()
    path = await media.prepare_model_image(
        str(source), max_size=limit, output_dir=tmp_path
    )
    with Image.open(path) as result:
        assert result.mode == "I;16" and result.size == (limit, limit // 2)
        low, high = result.getextrema()
        assert low < 1000 and high > 64000
        values = [result.getpixel((x, 0)) for x in range(limit)]
        assert values == sorted(values) and len(set(values)) == limit
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, 1280),
        (True, 1280),
        ("bad", 1280),
        (0, 1280),
        (2, 1280),
        (float("inf"), 1280),
        ("640", 640),
        (640.0, 640),
        (640.5, 1280),
        (3, 3),
    ],
)
def test_size_normalization(value, expected):
    assert media.normalize_model_image_max_size(value) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_cache", [b"", b"bad", None, "jpeg"])
async def test_bad_cache_rebuilt_and_work_files_independent(
    tmp_path, monkeypatch, bad_cache
):
    source = tmp_path / "source.bmp"
    Image.new("RGB", (32, 16), "red").save(source)
    first = await media.prepare_model_image(
        str(source), max_size=16, output_dir=tmp_path
    )
    cache = next((tmp_path / "cache" / media.CONVERT_CACHE_DIR_NAME).glob("*.png"))
    if bad_cache is None:
        cache.unlink()
    elif bad_cache == "jpeg":
        Image.new("RGB", (16, 8), "blue").save(cache, "JPEG")
    else:
        cache.write_bytes(bad_cache)
    second = await media.prepare_model_image(
        str(source), max_size=16, output_dir=tmp_path
    )
    assert first != second and Path(first).read_bytes() == Path(second).read_bytes()
    Path(first).unlink()
    assert cache.is_file() and Path(second).is_file()
    encode = Mock(side_effect=AssertionError("valid cache must skip encoding"))
    monkeypatch.setattr(media, "_encode_image_frame_bytes", encode)
    third = await media.prepare_model_image(
        str(source), max_size=16, output_dir=tmp_path
    )
    assert Path(third).read_bytes() == Path(second).read_bytes()


@pytest.mark.asyncio
async def test_unwritable_cache_bypassed_but_work_file_failure_skips(tmp_path):
    source = tmp_path / "source.bmp"
    Image.new("RGB", (32, 16), "red").save(source)
    (tmp_path / "cache").write_text("blocks directory creation")
    path = await media.prepare_model_image(
        str(source), max_size=16, output_dir=tmp_path
    )
    assert Path(path).is_file()
    assert (
        await media.prepare_model_image(str(source), max_size=16, output_dir=source)
        is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        ValueError("bad"),
        OSError("decode"),
        DownloadFileHTTPError(404, "https://example.com/?secret=hidden"),
    ],
)
async def test_recoverable_image_failures_skip(tmp_path, monkeypatch, error):
    async def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(media.MediaResolver, "_resolve_path", fail)
    assert (
        await media.prepare_model_image("ref", max_size=1280, output_dir=tmp_path)
        is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        asyncio.CancelledError(),
        MemoryError(),
        OSError(errno.ENOMEM, "memory"),
        TypeError("bug"),
        RuntimeError("bug"),
    ],
)
async def test_fatal_image_failures_propagate(tmp_path, monkeypatch, error):
    async def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(media.MediaResolver, "_resolve_path", fail)
    with pytest.raises(type(error)):
        await media.prepare_model_image("ref", max_size=1280, output_dir=tmp_path)


def test_cache_publication_is_atomic_and_closes_file(tmp_path, monkeypatch):
    output = tmp_path / "cache.png"
    original_replace = media.os.replace

    def replace(source, target):
        assert Path(source).read_bytes() == b"complete"
        assert not output.exists()
        original_replace(source, target)

    monkeypatch.setattr(media.os, "replace", replace)
    media._publish_image_cache_atomic(output, b"complete")
    assert output.read_bytes() == b"complete" and not list(tmp_path.glob("*.tmp"))


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 404, 503])
async def test_real_download_status_failure_is_skipped_without_secret_logs(
    tmp_path, monkeypatch, caplog, status
):
    from astrbot.core.utils.io import _raise_for_download_status

    async def download(url, target):
        _raise_for_download_status(SimpleNamespace(status=status), url)

    monkeypatch.setattr(media, "download_file", download)
    result = await media.prepare_model_image(
        "https://example.com/image?token=secret-token",
        max_size=1280,
        output_dir=tmp_path,
    )
    assert result is None
    assert "secret-token" not in caplog.text
