import asyncio
import io
import base64
import pytest
from PIL import Image
from astrbot.core.utils.media_utils import MediaResolver


@pytest.mark.asyncio
async def test_gif_transcoded_to_png():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), (255, 0, 0)).save(buf, format="GIF")
    b64_gif = "base64://" + base64.b64encode(buf.getvalue()).decode()
    resolver = MediaResolver(b64_gif, media_type="image")
    res = await resolver.to_base64_data()
    assert res is not None
    assert res.mime_type == "image/png"
    assert res.base64_data
