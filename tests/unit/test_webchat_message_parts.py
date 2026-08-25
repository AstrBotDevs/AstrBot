import asyncio
from types import SimpleNamespace

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import (
    ActionRow,
    Button,
    ButtonInteraction,
    CallbackAction,
    File,
    UrlAction,
)
from astrbot.core.platform.button_interaction import (
    decode_button_callback,
    encode_button_callback,
)
from astrbot.core.platform.sources.webchat import webchat_event
from astrbot.core.platform.sources.webchat.message_parts_helper import (
    build_webchat_message_parts,
    create_attachment_part_from_existing_file,
    message_chain_to_storage_message_parts,
    parse_webchat_message_parts,
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


@pytest.mark.asyncio
async def test_webchat_action_row_send_uses_portable_callback_payload(monkeypatch):
    """WebChat should emit compact callback data and retain URL buttons."""
    queue = asyncio.Queue()

    async def put_back_queue(_request_id, payload):
        await queue.put(payload)
        return True

    monkeypatch.setattr(
        webchat_event.webchat_queue_mgr,
        "put_back_queue",
        put_back_queue,
    )
    row = ActionRow(
        buttons=[
            Button(
                id="approve",
                label="Approve",
                action=CallbackAction(data={"ticket": 7}),
            ),
            Button(
                id="docs",
                label="Docs",
                action=UrlAction(url="https://example.com/docs"),
            ),
        ]
    )

    await webchat_event.WebChatMessageEvent._send(
        "message-1",
        MessageChain([row]),
        "webchat!user!conversation-1",
    )

    payload = await queue.get()
    callback_action = payload["data"]["buttons"][0]["action"]
    assert payload["type"] == "actionrow"
    assert decode_button_callback(callback_action["callback_data"]) == (
        "approve",
        {"ticket": 7},
    )
    assert "data" not in callback_action
    assert payload["data"]["buttons"][1]["action"] == {
        "type": "url",
        "url": "https://example.com/docs",
    }


@pytest.mark.asyncio
async def test_webchat_button_interaction_becomes_portable_component():
    """A WebChat callback click should enter the common interaction model."""

    async def get_attachment_by_id(_attachment_id):
        raise AssertionError("button interactions must not resolve attachments")

    callback_data = encode_button_callback("choose", ["alpha", 2])
    parts = await build_webchat_message_parts(
        [
            {
                "type": "button_interaction",
                "callback_data": callback_data,
                "source_message_id": 42,
            }
        ],
        get_attachment_by_id=get_attachment_by_id,
        strict=True,
    )
    components, text_parts, has_content = await parse_webchat_message_parts(
        parts,
        strict=True,
    )

    assert has_content is True
    assert text_parts == ["choose"]
    assert len(components) == 1
    interaction = components[0]
    assert isinstance(interaction, ButtonInteraction)
    assert interaction.action_id == "choose"
    assert interaction.data == ["alpha", 2]
    assert interaction.source_message_id == "42"
    assert interaction.interaction_id


@pytest.mark.asyncio
async def test_webchat_action_row_is_persisted_with_callback_data(tmp_path):
    """Proactive WebChat messages should preserve interactive rows in history."""

    async def insert_attachment(_path, _type, _mime_type):
        raise AssertionError("action rows must not create attachments")

    parts = await message_chain_to_storage_message_parts(
        MessageChain(
            [
                ActionRow(
                    buttons=[
                        Button(
                            id="retry",
                            label="Retry",
                            action=CallbackAction(data="request-1"),
                        )
                    ],
                    fallback_text="Retry",
                )
            ]
        ),
        insert_attachment=insert_attachment,
        attachments_dir=tmp_path,
    )

    assert parts[0]["type"] == "actionrow"
    assert parts[0]["fallback_text"] == "Retry"
    callback_data = parts[0]["buttons"][0]["action"]["callback_data"]
    assert decode_button_callback(callback_data) == ("retry", "request-1")
    assert "data" not in parts[0]["buttons"][0]["action"]
