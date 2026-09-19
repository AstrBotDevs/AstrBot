import base64
import io
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PIL import Image

from astrbot.core.agent.message import ImageURLPart
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils import media_utils


def _png() -> bytes:
    stream = io.BytesIO()
    with Image.new("RGBA", (8, 6), (20, 40, 60, 128)) as image:
        image.save(stream, "PNG")
    return stream.getvalue()


@pytest.mark.asyncio
async def test_prepare_image_source_accepts_all_reference_forms(tmp_path, monkeypatch):
    data = _png()
    source = tmp_path / "image.png"
    source.write_bytes(data)
    monkeypatch.chdir(tmp_path)

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        encoded = base64.b64encode(data).decode()
        refs = [
            str(source),
            f"http://127.0.0.1:{server.server_port}/image.png",
            f"data:image/png;base64,{encoded}",
            f"base64://{encoded}",
            encoded,
        ]
        for ref in refs:
            result = await media_utils.prepare_image_source(ref)
            assert result.mime_type == "image/png"
            assert result.to_bytes() == data
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.asyncio
async def test_provider_request_passes_preparation_options():
    data = base64.b64encode(_png()).decode()
    request = ProviderRequest(
        image_urls=[f"data:image/png;base64,{data}"],
        image_preparation_options=media_utils.ImagePreparationOptions(max_size=2),
    )
    context = await request.assemble_context()
    assert context["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


@pytest.mark.asyncio
async def test_extra_image_part_prepares_copy_and_preserves_metadata(tmp_path):
    data = _png()
    source = tmp_path / "plugin.png"
    source.write_bytes(data)
    part = ImageURLPart(
        image_url=ImageURLPart.ImageURL(url=str(source), id="plugin-id", detail="high")
    ).mark_as_temp()
    request = ProviderRequest(extra_user_content_parts=[part])

    context = await request.assemble_context()
    payload = context["content"][0]
    assert payload["image_url"]["id"] == "plugin-id"
    assert payload["image_url"]["detail"] == "high"
    assert payload["_no_save"] is True
    assert payload["image_url"]["url"].startswith("data:image/png;base64,")
    assert part.image_url.url == str(source)
