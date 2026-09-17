from pathlib import Path

from PIL import Image, ImageDraw

from astrbot.core.utils import media_utils


def test_prefers_smaller_lossless_encoding_for_ui_screenshot(tmp_path):
    source = tmp_path / "screenshot-ordinary.png"
    with Image.new("RGB", (1920, 1080), "white") as image:
        draw = ImageDraw.Draw(image)
        for x in range(0, 1920, 32):
            draw.line((x, 0, x, 1080), fill=(205, 205, 205), width=1)
        for y in range(0, 1080, 32):
            draw.line((0, y, 1920, y), fill=(205, 205, 205), width=1)
        for index in range(80):
            draw.text(
                (20 + (index % 10) * 185, 20 + (index // 10) * 125),
                f"UI {index:02d}",
                fill="black",
            )
        image.save(source, "PNG", optimize=True)

    output = media_utils._compress_image_sync(
        source, tmp_path, 1280, 95, True, 4 * 1024 * 1024
    )

    assert output is not None
    with Image.open(source) as original:
        resized = original.copy()
        resized.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
        png_candidate = tmp_path / "expected.png"
        jpeg_candidate = tmp_path / "expected.jpg"
        resized.save(png_candidate, "PNG", optimize=True)
        resized.save(jpeg_candidate, "JPEG", quality=95, optimize=True)
        # The old implementation always selected JPEG for opaque PNG input,
        # even when the same resized pixels have a smaller PNG encoding.
        assert png_candidate.stat().st_size < jpeg_candidate.stat().st_size
        assert max(resized.size) <= 1280
    assert Path(output).suffix == ".png"
    assert Path(output).stat().st_size == png_candidate.stat().st_size
    with Image.open(output) as image:
        assert max(image.size) <= 1280
