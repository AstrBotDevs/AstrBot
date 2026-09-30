"""Pixel, error and lifecycle contracts for the stage's image encoder."""

import asyncio
import errno
import random
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from astrbot.core.utils import media_utils as media
from astrbot.core.utils.io import DownloadFileHTTPError


@pytest.fixture(autouse=True)
def isolated_temp(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "get_astrbot_temp_path", lambda: str(tmp_path / "temp"))


async def _prepare_image_path(*args, **kwargs):
    """Path-only view of prepare_model_image for pixel-focused assertions."""
    prepared = await media.prepare_model_image(*args, **kwargs)
    return None if prepared is None else prepared[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "BMP", "WEBP", "GIF"])
async def test_oversized_opaque_stills_become_jpeg_without_mutating_source(
    tmp_path, fmt
):
    source = tmp_path / "misleading.jpg"
    Image.new("RGB", (200, 100), "red").save(source, fmt)
    original = source.read_bytes()
    path = await _prepare_image_path(str(source), max_size=80, output_dir=tmp_path)
    assert path and Path(path).is_file() and Path(path) != source
    assert path.endswith(".jpg")
    with Image.open(path) as image:
        assert image.format == "JPEG" and getattr(image, "n_frames", 1) == 1
        assert image.size == (80, 40)
        assert abs(image.getpixel((40, 20))[0] - 255) <= 3
    assert source.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", ["JPEG", "PNG"])
@pytest.mark.parametrize("file_uri", [False, True])
async def test_compliant_stills_reuse_source_without_copying(tmp_path, fmt, file_uri):
    source = tmp_path / f"ok.{fmt.lower()}"
    Image.new("RGB", (200, 100), "red").save(source, fmt)
    original = source.read_bytes()
    output = tmp_path / "output"
    prepared = await media.prepare_model_image(
        source.as_uri() if file_uri else str(source), max_size=1280, output_dir=output
    )
    assert prepared == (str(source), False, False, str(source))
    assert not output.exists()
    assert source.read_bytes() == original


@pytest.mark.asyncio
async def test_rotated_jpeg_is_normalized_to_upright_jpeg(tmp_path):
    source = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (200, 100), "red").save(source, exif=exif)
    original = source.read_bytes()
    path = await _prepare_image_path(str(source), max_size=1280, output_dir=tmp_path)
    assert path and Path(path).read_bytes() != original
    with Image.open(path) as image:
        assert image.format == "JPEG" and image.size == (100, 200)
        assert image.getexif().get(274, 1) == 1
    assert source.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", ["PNG", "WEBP"])
async def test_transparent_images_shrink_without_losing_alpha(tmp_path, fmt):
    source = tmp_path / f"alpha.{fmt.lower()}"
    pixels = random.Random(9703).randbytes(1280 * 960 * 3)
    image = Image.frombytes("RGB", (1280, 960), pixels)
    image.putalpha(128)
    image.save(source, fmt, lossless=True)
    original = source.read_bytes()
    path = await _prepare_image_path(str(source), max_size=1280, output_dir=tmp_path)
    assert path and Path(path).stat().st_size < 512 * 1024
    with Image.open(path) as result:
        assert result.format == "PNG" and result.mode == "RGBA"
        assert max(result.size) < 1280
        assert result.getchannel("A").getextrema() == (128, 128)
    assert source.read_bytes() == original


@pytest.mark.asyncio
async def test_16bit_jpeg_conversion_scales_instead_of_clipping(tmp_path):
    source = tmp_path / "gradient.png"
    size = (2000, 100)
    row = b"".join(
        int(x * 65535 / (size[0] - 1)).to_bytes(2, "little") for x in range(size[0])
    )
    Image.frombytes("I;16", size, row * size[1]).save(source)
    path = await _prepare_image_path(str(source), max_size=1280, output_dir=tmp_path)
    assert path and path.endswith(".jpg")
    with Image.open(path) as image:
        assert image.format == "JPEG" and image.mode == "L"
        low, high = image.getextrema()
        assert low < 50 and high > 200


@pytest.mark.asyncio
async def test_jpeg_transcode_preserves_icc_profile(tmp_path):
    ImageCms = pytest.importorskip("PIL.ImageCms")
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (2000, 100), "red").save(source, icc_profile=icc)
    path = await _prepare_image_path(str(source), max_size=1280, output_dir=tmp_path)
    assert path and path.endswith(".jpg")
    with Image.open(path) as result:
        assert result.format == "JPEG"
        assert result.info.get("icc_profile") == icc


@pytest.mark.asyncio
async def test_cmyk_icc_profile_is_not_attached_to_rgb_jpeg(tmp_path):
    ImageCms = pytest.importorskip("PIL.ImageCms")
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    source = tmp_path / "cmyk.jpg"
    Image.new("CMYK", (2000, 100), (0, 255, 255, 0)).save(source, icc_profile=icc)
    path = await _prepare_image_path(str(source), max_size=1280, output_dir=tmp_path)
    assert path and path.endswith(".jpg")
    with Image.open(path) as result:
        assert result.format == "JPEG" and result.mode == "RGB"
        assert not result.info.get("icc_profile")


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP", "BMP"])
async def test_opaque_images_fit_the_byte_limit(tmp_path, fmt):
    source = tmp_path / f"noise.{fmt.lower()}"
    pixels = random.Random(9703).randbytes(1280 * 960 * 3)
    Image.frombytes("RGB", (1280, 960), pixels).save(source, fmt, quality=100)
    original = source.read_bytes()
    path = await _prepare_image_path(str(source), max_size=1280, output_dir=tmp_path)
    assert path and Path(path).stat().st_size < 512 * 1024
    with Image.open(path) as result:
        assert result.format == "JPEG" and max(result.size) <= 1280
    assert source.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", ["JPEG", "PNG"])
@pytest.mark.parametrize("size", [512 * 1024 - 1, 512 * 1024, 512 * 1024 + 1])
async def test_byte_limit_is_strict_even_for_dimension_compliant_images(
    tmp_path, fmt, size
):
    source = tmp_path / f"small.{fmt.lower()}"
    Image.new("RGB", (32, 16), "red").save(source, fmt)
    original = source.read_bytes().ljust(size, b"\0")
    source.write_bytes(original)
    path = await _prepare_image_path(str(source), max_size=1280, output_dir=tmp_path)
    assert path and Path(path).stat().st_size < 512 * 1024
    assert (Path(path).read_bytes() == original) == (size < 512 * 1024)
    assert source.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", ["JPEG", "PNG"])
async def test_oversized_metadata_cannot_bypass_byte_limit(tmp_path, fmt):
    source = tmp_path / f"metadata.{fmt.lower()}"
    image = Image.new("RGBA" if fmt == "PNG" else "RGB", (32, 16), "red")
    image.save(source, fmt, icc_profile=random.Random(512).randbytes(600 * 1024))
    original = source.read_bytes()
    assert len(original) >= 512 * 1024
    path = await _prepare_image_path(str(source), max_size=1280, output_dir=tmp_path)
    assert path and Path(path).stat().st_size < 512 * 1024
    with Image.open(path) as result:
        assert result.size == (32, 16)
        assert not result.info.get("icc_profile")
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
    path = await _prepare_image_path(str(source), max_size=1280, output_dir=tmp_path)
    indices = [0, 1] if count == 2 else [0, 1, 3, 4, 6, 7, 8, 10, 11]
    with Image.open(path) as image:
        assert image.format == "JPEG" and getattr(image, "n_frames", 1) == 1
        assert image.size == (36, 24)
        for cell in range(9):
            expected = colors[indices[cell]] if cell < len(indices) else (255, 255, 255)
            pixel = image.getpixel(((cell % 3) * 12 + 6, (cell // 3) * 8 + 4))
            assert all(abs(actual - want) <= 6 for actual, want in zip(pixel, expected))
    small = await _prepare_image_path(str(source), max_size=18, output_dir=tmp_path)
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
    path = await _prepare_image_path(str(source), max_size=80, output_dir=tmp_path)
    with Image.open(path) as result:
        assert (
            result.format == "JPEG" and result.size == (40, 80) and result.mode == "RGB"
        )
        assert result.getexif().get(274, 1) == 1
        assert all(
            abs(actual - want) <= 6
            for actual, want in zip(result.getpixel((20, 40)), (255, 0, 0))
        )
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
    path = await _prepare_image_path(str(source), max_size=80, output_dir=tmp_path)
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
    path = await _prepare_image_path(str(source), max_size=16, output_dir=tmp_path)
    with Image.open(path) as result:
        actual = result.convert("L")
        assert actual.getextrema()[0] < 255
        expected_l = expected.convert("L")
        diff = sum(abs(a - b) for a, b in zip(actual.tobytes(), expected_l.tobytes()))
        assert diff <= 8 * actual.width * actual.height


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "size,limit", [((2560, 1280), 1280), ((5120, 2560), 1280), ((513, 257), 128)]
)
async def test_16bit_gradient_normalizes_to_8bit_jpeg(tmp_path, size, limit):
    source = tmp_path / "gradient.png"
    row = b"".join(
        int(x * 65535 / (size[0] - 1)).to_bytes(2, "little") for x in range(size[0])
    )
    Image.frombytes("I;16", size, row * size[1]).save(source)
    original = source.read_bytes()
    path = await _prepare_image_path(str(source), max_size=limit, output_dir=tmp_path)
    with Image.open(path) as result:
        assert result.format == "JPEG" and result.mode == "L"
        assert result.size == (limit, limit // 2)
        low, high = result.getextrema()
        assert low < 50 and high > 200
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
async def test_working_files_are_independent_without_shared_cache(tmp_path):
    source = tmp_path / "source.bmp"
    Image.new("RGB", (32, 16), "red").save(source)
    output = tmp_path / "output"
    first = await _prepare_image_path(str(source), max_size=16, output_dir=output)
    second = await _prepare_image_path(str(source), max_size=16, output_dir=output)
    assert first != second and Path(first).read_bytes() == Path(second).read_bytes()
    assert set(output.iterdir()) == {Path(first), Path(second)}
    Path(first).unlink()
    assert Path(second).is_file() and source.is_file()


@pytest.mark.asyncio
async def test_work_file_failure_skips_image(tmp_path):
    source = tmp_path / "source.bmp"
    Image.new("RGB", (32, 16), "red").save(source)
    path = await _prepare_image_path(str(source), max_size=16, output_dir=tmp_path)
    assert Path(path).is_file()
    assert (
        await _prepare_image_path(str(source), max_size=16, output_dir=source) is None
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
    assert await _prepare_image_path("ref", max_size=1280, output_dir=tmp_path) is None


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
        await _prepare_image_path("ref", max_size=1280, output_dir=tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 404, 503])
async def test_real_download_status_failure_is_skipped_without_secret_logs(
    tmp_path, monkeypatch, caplog, status
):
    from astrbot.core.utils.io import _raise_for_download_status

    async def download(url, target):
        _raise_for_download_status(SimpleNamespace(status=status), url)

    monkeypatch.setattr(media, "download_file", download)
    result = await _prepare_image_path(
        "https://example.com/image?token=secret-token",
        max_size=1280,
        output_dir=tmp_path,
    )
    assert result is None
    assert "secret-token" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [2, 12])
async def test_repeated_animation_preparation_reports_montage(tmp_path, count):
    """Repeated animated inputs produce independent montage previews."""
    frames = [Image.new("RGB", (12, 8), (index * 20, 0, 0)) for index in range(count)]
    source = tmp_path / "animation.gif"
    frames[0].save(
        source, "GIF", save_all=True, append_images=frames[1:], duration=100, loop=0
    )

    prepared = await media.prepare_model_image(
        str(source), max_size=1280, output_dir=tmp_path
    )
    assert prepared and prepared[1] is True
    assert Path(prepared[0]).is_file()

    repeated = await media.prepare_model_image(
        str(source), max_size=1280, output_dir=tmp_path
    )
    assert repeated and repeated[1] is True
    assert Path(repeated[0]).read_bytes() == Path(prepared[0]).read_bytes()


@pytest.mark.asyncio
async def test_apng_with_cover_reports_montage(tmp_path):
    """An APNG with a cover still reports an animation montage."""
    frames = [Image.new("RGB", (12, 8), (index * 20, 0, 0)) for index in range(3)]
    # An APNG cover frame precedes the animation frames it is not part of.
    frames.insert(0, Image.new("RGB", (12, 8), "blue"))
    source = tmp_path / "animation.png"
    frames[0].save(
        source,
        "PNG",
        save_all=True,
        append_images=frames[1:],
        default_image=True,
        duration=100,
        loop=0,
    )
    prepared = await media.prepare_model_image(
        str(source), max_size=1280, output_dir=tmp_path
    )
    assert prepared and prepared[1] is True


@pytest.mark.asyncio
async def test_still_image_reports_no_montage(tmp_path):
    """Still images do not report a montage, so no notice is built."""
    source = tmp_path / "still.png"
    Image.new("RGB", (32, 16), "red").save(source)
    prepared = await media.prepare_model_image(
        str(source), max_size=1280, output_dir=tmp_path
    )
    assert prepared is not None
    assert prepared[1] is False
