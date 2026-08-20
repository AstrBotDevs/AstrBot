import base64
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from PIL import Image as PILImage

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image
from astrbot.core.platform.sources.mattermost.client import MattermostClient
from astrbot.core.platform.sources.satori.satori_event import SatoriPlatformEvent
from astrbot.core.platform.sources.slack.slack_event import SlackMessageEvent
from astrbot.core.webchat.emitter import emit_webchat_response
from astrbot.core.webchat.queue_manager import WebChatQueueManager

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_satori_image_data_url_preserves_png_mime_type():
    image_buffer = BytesIO()
    PILImage.new("RGBA", (2, 2), (255, 0, 0, 128)).save(
        image_buffer,
        format="PNG",
    )
    image_ref = (
        "data:image/png;base64," + base64.b64encode(image_buffer.getvalue()).decode()
    )

    result = await SatoriPlatformEvent._convert_component_to_satori_static(
        Image(file=image_ref),
    )

    assert result.startswith('<img src="data:image/png;base64,')


@pytest.mark.asyncio
async def test_satori_image_data_url_preserves_jpeg_mime_type():
    image_buffer = BytesIO()
    PILImage.new("RGB", (2, 2), (0, 255, 0)).save(
        image_buffer,
        format="JPEG",
    )
    image_ref = (
        "data:image/jpeg;base64," + base64.b64encode(image_buffer.getvalue()).decode()
    )

    result = await SatoriPlatformEvent._convert_component_to_satori_static(
        Image(file=image_ref),
    )

    assert result.startswith('<img src="data:image/jpeg;base64,')


@pytest.mark.asyncio
async def test_webchat_image_attachment_uses_detected_extension(tmp_path):
    image_buffer = BytesIO()
    PILImage.new("RGBA", (2, 2), (255, 0, 0, 128)).save(
        image_buffer,
        format="PNG",
    )
    image_ref = (
        "data:image/png;base64," + base64.b64encode(image_buffer.getvalue()).decode()
    )
    queue_manager = WebChatQueueManager()
    queue = queue_manager.get_or_create_back_queue("message-1")
    await emit_webchat_response(
        queue_manager,
        "message-1",
        MessageChain([Image(file=image_ref)]),
        attachments_dir=tmp_path,
    )

    payload = await queue.get()
    filename = payload["data"].removeprefix("[IMAGE]")
    assert filename.endswith(".png")
    assert (tmp_path / filename).exists()


@pytest.mark.asyncio
async def test_slack_image_upload_uses_resolved_filename(tmp_path):
    image_path = tmp_path / "transparent.png"
    PILImage.new("RGBA", (2, 2), (255, 0, 0, 128)).save(image_path)
    web_client = AsyncMock()
    web_client.files_upload_v2.return_value = {
        "ok": True,
        "files": [{"url_private": "https://slack.example/files/transparent.png"}],
    }

    result = await SlackMessageEvent._from_segment_to_slack_block(
        Image(file=str(image_path)),
        web_client,
    )

    assert result is not None
    assert web_client.files_upload_v2.await_args.kwargs["filename"] == "transparent.png"


@pytest.mark.asyncio
async def test_mattermost_image_upload_uses_detected_mime_type(tmp_path):
    image_path = tmp_path / "transparent.bin"
    PILImage.new("RGBA", (2, 2), (255, 0, 0, 128)).save(image_path, format="PNG")
    client = MattermostClient("https://chat.example.com", "test_token")
    client.upload_file = AsyncMock(return_value="file-id")
    client.create_post = AsyncMock(return_value={"id": "post-1"})

    await client.send_message_chain(
        "channel-1",
        MessageChain([Image(file=str(image_path))]),
    )

    assert client.upload_file.await_args.args == (
        "channel-1",
        Path(image_path).read_bytes(),
        "transparent.bin",
        "image/png",
    )
