"""Real database and asset-store coverage for catalog image sending."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.image_asset_store import ImageAssetStore
from astrbot.core.image_context import (
    MAX_CONTEXT_IMAGE_FRAMES,
    MAX_CONTEXT_IMAGE_PIXELS,
)
from astrbot.core.tools import message_tools
from astrbot.core.tools.message_tools import SendMessageToUserTool

pytest_plugins = ("test_image_retrieval",)


def _send_context(turn, *, session="test:GroupMessage:owner"):
    temporary_files = []
    extras = {}

    def cleanup_temporary_local_files():
        for path in list(temporary_files):
            Path(path).unlink(missing_ok=True)
        temporary_files.clear()

    event = SimpleNamespace(
        unified_msg_origin=session,
        role="admin",
        _has_send_oper=False,
        get_sender_id=lambda: "owner",
        track_temporary_local_file=temporary_files.append,
        untrack_temporary_local_file=lambda path: (
            temporary_files.remove(path) if path in temporary_files else None
        ),
        cleanup_temporary_local_files=cleanup_temporary_local_files,
    )
    event.set_extra = lambda key, value: extras.__setitem__(key, value)
    event.get_extra = lambda key, default=None: extras.get(key, default)
    turn.event = event
    sender = AsyncMock(return_value=True)
    context = SimpleNamespace(
        event=event,
        image_context=turn,
        context=SimpleNamespace(
            get_config=lambda umo: {
                "provider_settings": {"computer_use_require_admin": True}
            },
            send_message=sender,
        ),
    )
    return SimpleNamespace(context=context), event, sender, temporary_files


@pytest.mark.asyncio
async def test_catalog_send_copies_real_stored_asset_byte_for_byte(
    gallery, tmp_path, monkeypatch
):
    monkeypatch.setattr(message_tools, "get_astrbot_temp_path", lambda: str(tmp_path))
    occurrence_id = gallery.part.occurrence_id
    store = ImageAssetStore(
        gallery.db,
        max_pixels=MAX_CONTEXT_IMAGE_PIXELS,
        max_frames=MAX_CONTEXT_IMAGE_FRAMES,
    )
    async with store.open_image(
        conversation_id="conversation",
        occurrence_id=occurrence_id,
        user_id="owner",
        platform_id="test",
    ) as source:
        original_bytes = source.read()

    context, event, sender, temporary_files = _send_context(gallery.turn)
    result = await SendMessageToUserTool().call(
        context, messages=[{"type": "image", "occurrence_id": occurrence_id}]
    )

    assert result == "Message sent to session test:GroupMessage:owner"
    sender.assert_awaited_once()
    chain = sender.await_args.args[1]
    assert len(chain.chain) == 1
    sent_path = Path(chain.chain[0].path)
    assert sent_path.read_bytes() == original_bytes
    assert sent_path.suffix == ".png"
    assert temporary_files == [str(sent_path)]

    event.cleanup_temporary_local_files()
    assert not sent_path.exists()
    assert temporary_files == []


@pytest.mark.asyncio
async def test_catalog_send_after_conversation_deletion_is_rejected(
    gallery, tmp_path, monkeypatch
):
    monkeypatch.setattr(message_tools, "get_astrbot_temp_path", lambda: str(tmp_path))
    context, _, sender, temporary_files = _send_context(gallery.turn)
    await gallery.db.delete_conversation("conversation")

    result = await SendMessageToUserTool().call(
        context,
        messages=[{"type": "image", "occurrence_id": gallery.part.occurrence_id}],
    )

    assert result == "error: this image is unavailable in the current conversation."
    sender.assert_not_awaited()
    assert temporary_files == []


@pytest.mark.asyncio
async def test_catalog_send_to_another_session_is_rejected(
    gallery, tmp_path, monkeypatch
):
    monkeypatch.setattr(message_tools, "get_astrbot_temp_path", lambda: str(tmp_path))
    context, _, sender, temporary_files = _send_context(gallery.turn)

    result = await SendMessageToUserTool().call(
        context,
        session="test:GroupMessage:someone-else",
        messages=[{"type": "image", "occurrence_id": gallery.part.occurrence_id}],
    )

    assert (
        result == "error: catalog images can only be sent to the current conversation."
    )
    sender.assert_not_awaited()
    assert temporary_files == []
