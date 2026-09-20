import base64
from io import BytesIO

import pytest
from PIL import Image as PILImage

from astrbot.core.agent.runners.coze.coze_agent_runner import CozeAgentRunner
from astrbot.core.agent.runners.dify.dify_agent_runner import DifyAgentRunner


def _png_data_url() -> tuple[str, bytes]:
    image_buffer = BytesIO()
    PILImage.new("RGBA", (1, 1), (255, 0, 0, 255)).save(image_buffer, format="PNG")
    image_bytes = image_buffer.getvalue()
    return (
        f"data:image/png;base64,{base64.b64encode(image_bytes).decode()}",
        image_bytes,
    )


@pytest.mark.asyncio
async def test_dify_image_upload_uses_media_resolver_for_data_url():
    image_ref, image_bytes = _png_data_url()
    captured: dict[str, object] = {}

    class _FakeDifyClient:
        async def file_upload(self, **kwargs):
            captured.update(kwargs)
            return {"id": "file-1"}

    runner = DifyAgentRunner.__new__(DifyAgentRunner)
    runner.api_client = _FakeDifyClient()

    payload = await runner._upload_image_for_dify(image_ref, "session-1")

    assert payload == {
        "type": "image",
        "transfer_method": "local_file",
        "upload_file_id": "file-1",
    }
    assert captured["file_data"] == image_bytes
    assert captured["mime_type"] == "image/png"
    assert captured["file_name"] == "image.png"


@pytest.mark.asyncio
async def test_coze_image_upload_uses_media_resolver_for_data_url():
    image_ref, image_bytes = _png_data_url()
    captured: dict[str, bytes] = {}

    class _FakeCozeClient:
        async def upload_file(self, file_data: bytes) -> str:
            captured["file_data"] = file_data
            return "file-1"

    runner = CozeAgentRunner.__new__(CozeAgentRunner)
    runner.api_client = _FakeCozeClient()
    runner.file_id_cache = {}

    file_id = await runner._download_and_upload_image(image_ref, "session-1")

    assert file_id == "file-1"
    assert captured["file_data"] == image_bytes
    assert list(runner.file_id_cache["session-1"].values()) == ["file-1"]
