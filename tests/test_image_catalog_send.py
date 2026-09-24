"""Conversation image catalog sending stays authorized and path-free."""

import io
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.tools import message_tools
from astrbot.core.tools.message_tools import SendMessageToUserTool


def _make_context(*, current_session="feishu:GroupMessage:oc_current", turn=None):
    temporary_files = []
    extras = {}
    event = SimpleNamespace(
        unified_msg_origin=current_session,
        role="admin",
        _has_send_oper=False,
        get_sender_id=lambda: "user-1",
        track_temporary_local_file=temporary_files.append,
        untrack_temporary_local_file=lambda path: (
            temporary_files.remove(path) if path in temporary_files else None
        ),
    )
    event.set_extra = lambda key, value: extras.__setitem__(key, value)
    event.get_extra = lambda key, default=None: extras.get(key, default)
    event.cleanup_temporary_local_files = lambda: [
        Path(path).unlink(missing_ok=True) for path in list(temporary_files)
    ]
    sender = AsyncMock(return_value=True)
    inner = SimpleNamespace(
        event=event,
        image_context=turn,
        context=SimpleNamespace(
            get_config=lambda umo: {
                "provider_settings": {"computer_use_require_admin": True}
            },
            send_message=sender,
        ),
    )
    return SimpleNamespace(context=inner), event, sender, temporary_files


class _Turn:
    configured = True
    conversation_id = "conversation-1"
    user_id = "user-1"
    platform_id = "feishu"
    event = None

    def __init__(self, *, revoke_on_authorize_call=None, mime_type="image/png"):
        self.authorize_calls = 0
        self.revoke_on_authorize_call = revoke_on_authorize_call
        self.db = _FakeDatabase(mime_type)
        self.get_reference = AsyncMock(return_value=SimpleNamespace(asset_id="asset-1"))
        self.check_visual_authorization = Mock()

    async def authorize_visuals(self, occurrence_ids):
        self.authorize_calls += 1
        if self.authorize_calls == self.revoke_on_authorize_call:
            return set()
        return set(occurrence_ids)


class _FakeDatabase:
    def __init__(self, mime_type):
        self.query_count = 0
        self.mime_type = mime_type

    @asynccontextmanager
    async def get_db(self):
        yield self

    async def get(self, model, asset_id):
        self.query_count += 1
        return SimpleNamespace(asset_id=asset_id, mime_type=self.mime_type)


def _install_fake_store(monkeypatch, *, fail=False):
    calls = []

    class FakeStore:
        def __init__(self, db, **budgets):
            assert db is not None
            assert budgets["max_pixels"] > 0 and budgets["max_frames"] > 0

        @asynccontextmanager
        async def open_image(
            self, *, conversation_id, occurrence_id, user_id, platform_id
        ):
            calls.append((conversation_id, occurrence_id, user_id, platform_id))
            if fail:
                raise PermissionError("private /data/image_assets/secret.img")
            yield io.BytesIO(b"original-image-bytes")

    monkeypatch.setattr(message_tools, "ImageAssetStore", FakeStore)
    return calls


@pytest.mark.asyncio
async def test_catalog_occurrence_sends_original_copy_and_event_cleans_it(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(message_tools, "get_astrbot_temp_path", lambda: str(tmp_path))
    store_calls = _install_fake_store(monkeypatch)
    turn = _Turn()
    ctx, event, sender, temporary_files = _make_context(turn=turn)
    turn.event = event

    result = await SendMessageToUserTool().call(
        ctx,
        messages=[{"type": "image", "occurrence_id": "occ-current"}],
    )

    assert result == "Message sent to session feishu:GroupMessage:oc_current"
    assert store_calls == [("conversation-1", "occ-current", "user-1", "feishu")]
    assert turn.authorize_calls == 2
    assert turn.get_reference.await_count == 2
    assert turn.check_visual_authorization.call_count == 2
    assert sender.await_count == 1
    chain = sender.await_args.args[1]
    image_path = Path(chain.chain[0].path)
    assert image_path.suffix == ".png"
    assert image_path.read_bytes() == b"original-image-bytes"
    assert str(image_path) in temporary_files
    event.cleanup_temporary_local_files()
    assert not image_path.exists()


@pytest.mark.asyncio
async def test_catalog_occurrence_cannot_target_another_session(monkeypatch):
    store_calls = _install_fake_store(monkeypatch)
    turn = _Turn()
    ctx, event, sender, _ = _make_context(turn=turn)
    turn.event = event

    result = await SendMessageToUserTool().call(
        ctx,
        session="feishu:GroupMessage:oc_other",
        messages=[{"type": "image", "occurrence_id": "occ-current"}],
    )

    assert (
        result == "error: catalog images can only be sent to the current conversation."
    )
    assert not store_calls
    sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_but_standard_image_mime_uses_safe_platform_suffix(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(message_tools, "get_astrbot_temp_path", lambda: str(tmp_path))
    monkeypatch.setattr(
        message_tools.mimetypes, "guess_extension", lambda mime: ".avif"
    )
    _install_fake_store(monkeypatch)
    turn = _Turn(mime_type="image/avif")
    ctx, event, sender, _ = _make_context(turn=turn)
    turn.event = event

    await SendMessageToUserTool().call(
        ctx,
        messages=[{"type": "image", "occurrence_id": "occ-current"}],
    )

    assert Path(sender.await_args.args[1].chain[0].path).suffix == ".avif"


@pytest.mark.asyncio
async def test_catalog_occurrence_rejects_path_or_url_combination(monkeypatch):
    store_calls = _install_fake_store(monkeypatch)
    turn = _Turn()
    ctx, event, sender, _ = _make_context(turn=turn)
    turn.event = event

    result = await SendMessageToUserTool().call(
        ctx,
        messages=[
            {
                "type": "image",
                "occurrence_id": "occ-current",
                "path": "ignored.png",
            }
        ],
    )

    assert "must use only one" in result
    assert not store_calls
    sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_catalog_revocation_before_send_blocks_platform_delivery(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(message_tools, "get_astrbot_temp_path", lambda: str(tmp_path))
    _install_fake_store(monkeypatch)
    turn = _Turn(revoke_on_authorize_call=2)
    ctx, event, sender, temporary_files = _make_context(turn=turn)
    turn.event = event

    result = await SendMessageToUserTool().call(
        ctx,
        messages=[{"type": "image", "occurrence_id": "occ-current"}],
    )

    assert result == "error: this image is unavailable in the current conversation."
    sender.assert_not_awaited()
    assert len(temporary_files) == 1
    assert "/data/image_assets/" not in result
    image_path = Path(temporary_files[0])
    event.cleanup_temporary_local_files()
    assert not image_path.exists()


@pytest.mark.asyncio
async def test_unassociated_catalog_asset_failure_does_not_leak_storage_path(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(message_tools, "get_astrbot_temp_path", lambda: str(tmp_path))
    _install_fake_store(monkeypatch, fail=True)
    turn = _Turn()
    ctx, event, sender, temporary_files = _make_context(turn=turn)
    turn.event = event

    result = await SendMessageToUserTool().call(
        ctx,
        messages=[{"type": "image", "occurrence_id": "unassociated"}],
    )

    assert result == "error: this image is unavailable in the current conversation."
    assert "/data/image_assets/secret.img" not in result
    assert sender.await_count == 0
    assert temporary_files == []


@pytest.mark.asyncio
async def test_ordinary_image_url_sending_remains_unchanged():
    ctx, _, sender, _ = _make_context(turn=None)

    result = await SendMessageToUserTool().call(
        ctx,
        messages=[{"type": "image", "url": "https://example.test/picture.png"}],
    )

    assert result == "Message sent to session feishu:GroupMessage:oc_current"
    assert sender.await_count == 1
    assert sender.await_args.args[1].chain[0].file == "https://example.test/picture.png"
