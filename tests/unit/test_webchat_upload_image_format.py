from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image as PILImage

from astrbot.dashboard.services.chat_service import ChatService


@pytest.mark.asyncio
async def test_webchat_upload_uses_detected_image_type(tmp_path):
    image_buffer = BytesIO()
    PILImage.new("RGB", (2, 2), (255, 0, 0)).save(image_buffer, format="JPEG")

    class FakeUploadFile:
        filename = "pasted.png"
        content_type = "image/png"

        async def save(self, destination):
            with open(destination, "wb") as output:
                output.write(image_buffer.getvalue())

    class FakeDatabase:
        def __init__(self):
            self.inserted = None

        async def insert_attachment(self, path, type, mime_type):
            self.inserted = {
                "path": path,
                "type": type,
                "mime_type": mime_type,
            }
            return SimpleNamespace(attachment_id="attachment-1", path=path)

    fake_db = FakeDatabase()
    service = ChatService.__new__(ChatService)
    service.db = fake_db
    service.attachments_dir = str(tmp_path)

    result = await service.save_uploaded_file(FakeUploadFile())

    assert result["filename"].endswith(".jpg")
    assert fake_db.inserted["mime_type"] == "image/jpeg"
    assert fake_db.inserted["type"] == "image"
    assert (tmp_path / result["filename"]).exists()
    assert not (tmp_path / "pasted.png").exists()
