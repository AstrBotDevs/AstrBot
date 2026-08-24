import asyncio
from types import SimpleNamespace

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import File
from astrbot.core.platform.sources.webchat import webchat_event
from astrbot.core.platform.sources.webchat.message_parts_helper import (
    build_webchat_message_parts,
    create_attachment_part_from_existing_file,
)


@pytest.mark.asyncio
async def test_webchat_file_send_keeps_original_filename(tmp_path, monkeypatch):
    """WebChat file payloads should carry both stored and display filenames."""
    queue = asyncio.Queue()

    async def put_back_queue(_request_id, payload):
        await queue.put(payload)
        return True

    attachments_dir = tmp_path / "attachments"
    attachments_dir.mkdir()
    source_file = tmp_path / "source.txt"
    source_file.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(webchat_event, "attachments_dir", str(attachments_dir))
    monkeypatch.setattr(
        webchat_event.webchat_queue_mgr,
        "put_back_queue",
        put_back_queue,
    )

    await webchat_event.WebChatMessageEvent._send(
        "message-1",
        MessageChain([File(name="report.txt", file=str(source_file))]),
        "webchat!user!conversation-1",
    )

    payload = await queue.get()
    stored_name, display_name = payload["data"].removeprefix("[FILE]").split("|", 1)

    assert payload["type"] == "file"
    assert display_name == "report.txt"
    assert stored_name != display_name
    assert (attachments_dir / stored_name).exists()


@pytest.mark.asyncio
async def test_attachment_part_uses_display_filename_with_stored_filename(tmp_path):
    """Attachment parts should show the display name while keeping the stored name."""
    stored_file = tmp_path / "uuid.txt"
    stored_file.write_text("payload", encoding="utf-8")

    async def insert_attachment(path, type, mime_type):
        return SimpleNamespace(
            attachment_id="attachment-1",
            path=path,
            type=type,
            mime_type=mime_type,
        )

    part = await create_attachment_part_from_existing_file(
        stored_file.name,
        attach_type="file",
        insert_attachment=insert_attachment,
        attachments_dir=tmp_path,
        display_name="../nested/report.txt",
    )

    assert part == {
        "type": "file",
        "attachment_id": "attachment-1",
        "filename": "report.txt",
        "stored_filename": "uuid.txt",
    }


@pytest.mark.asyncio
async def test_build_webchat_message_parts_preserves_payload_filename(tmp_path):
    """Attachment lookup should not overwrite the payload filename with disk name."""
    stored_file = tmp_path / "uuid.txt"
    stored_file.write_text("payload", encoding="utf-8")
    attachment = SimpleNamespace(
        attachment_id="attachment-1",
        path=str(stored_file),
        type="file",
    )

    async def get_attachment_by_id(attachment_id):
        assert attachment_id == "attachment-1"
        return attachment

    parts = await build_webchat_message_parts(
        [
            {
                "type": "file",
                "attachment_id": "attachment-1",
                "filename": r"C:\fakepath\report.txt",
            }
        ],
        get_attachment_by_id=get_attachment_by_id,
        strict=True,
    )

    assert parts == [
        {
            "type": "file",
            "attachment_id": "attachment-1",
            "filename": "report.txt",
            "path": str(stored_file),
            "stored_filename": "uuid.txt",
        }
    ]
