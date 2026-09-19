from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from astrbot.core.utils import media_utils


@pytest.mark.asyncio
async def test_model_preparation_bounds_ui_screenshot(tmp_path):
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

    prepared = await media_utils.prepare_model_image(
        str(source), max_size=1280, output_dir=tmp_path
    )

    assert prepared is not None
    output, is_montage, needs_cleanup, _ = prepared
    assert not is_montage and needs_cleanup
    assert Path(output).suffix == ".jpg"
    assert Path(output).stat().st_size < 512 * 1024
    with Image.open(output) as image:
        assert max(image.size) <= 1280
    Path(output).unlink()
