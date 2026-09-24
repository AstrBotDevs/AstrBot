"""Conversation export compatibility and bounded online backup behavior."""

import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from astrbot.core import conversation_history_limits as limits
from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.dashboard.api.conversations import _export_response
from astrbot.dashboard.schemas import ConversationExportRequest
from astrbot.dashboard.services.conversation_service import (
    ConversationExport,
    ConversationService,
    ConversationServiceError,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("finish", [True, False])
async def test_portable_download_releases_temp_file(tmp_path, finish):
    archive = tmp_path / "export.zip"
    original = b"z" * 200_000
    archive.write_bytes(original)
    response = _export_response(
        ConversationExport(
            file_obj=None,
            filename="export.zip",
            mimetype="application/zip",
            file_path=archive,
        )
    )
    stream = response.body_iterator
    first = await anext(stream)
    assert len(first) == 64 * 1024
    assert archive.exists()
    if finish:
        remaining = b"".join([part async for part in stream])
        assert first + remaining == original
    else:
        await stream.aclose()
    assert not archive.exists()


@pytest.mark.asyncio
async def test_jsonl_download_preserves_bytes_and_closes():
    body = BytesIO(b'{"content":[]}\n')
    response = _export_response(
        ConversationExport(file_obj=body, filename="test.jsonl")
    )
    assert (
        b"".join([part async for part in response.body_iterator]) == b'{"content":[]}\n'
    )
    assert body.closed


@pytest.mark.asyncio
async def test_jsonl_export_content_is_unchanged():
    history = [
        {
            "role": "user",
            "content": [
                {"type": "image_ref", "occurrence_id": "image", "asset_id": "asset"}
            ],
        }
    ]
    conversation = SimpleNamespace(
        history=json.dumps(history),
        title="Example",
        persona_id=None,
        created_at=1,
        updated_at=2,
        user_id="owner",
        platform_id="test",
    )
    manager = SimpleNamespace(get_conversation=AsyncMock(return_value=conversation))
    service = ConversationService(
        SimpleNamespace(), SimpleNamespace(conversation_manager=manager)
    )
    service._get_webchat_titles = AsyncMock(return_value={})
    exported = await service.export_conversations(
        {"conversations": [{"cid": "c", "user_id": "owner"}]}
    )
    record = json.loads(exported.file_obj.read())
    assert record["content"] == history
    assert exported.mimetype == "application/jsonl"
    assert exported.file_path is None
    exported.file_obj.close()


@pytest.mark.asyncio
async def test_portable_export_requires_one_conversation():
    service = ConversationService(
        SimpleNamespace(), SimpleNamespace(conversation_manager=SimpleNamespace())
    )
    with pytest.raises(ConversationServiceError, match="一个会话"):
        await service.export_conversations(
            {
                "format": "media_zip",
                "conversations": [
                    {"cid": "a", "user_id": "u"},
                    {"cid": "b", "user_id": "u"},
                ],
            }
        )


def test_export_schema_defaults_to_jsonl():
    assert ConversationExportRequest(conversations=[]).format == "jsonl"
    assert (
        ConversationExportRequest(conversations=[], format="media_zip").format
        == "media_zip"
    )


@pytest.mark.asyncio
async def test_backup_rejects_oversized_invalid_json_before_decoding(
    temp_db, monkeypatch
):
    await temp_db.create_conversation("owner", "test", cid="large")
    async with temp_db.get_db() as session, session.begin():
        await session.execute(
            text(
                "UPDATE conversations SET content=:body WHERE conversation_id='large'"
            ),
            {"body": "[" + "坏" * 100},
        )
    monkeypatch.setattr(limits, "MAX_ONLINE_HISTORY_BYTES", 128)
    with pytest.raises(limits.HistoryTooLargeError) as raised:
        await AstrBotExporter(temp_db)._export_main_database()
    assert raised.value.byte_size == 301


@pytest.mark.asyncio
async def test_download_disconnect_before_body_cleans_archive(tmp_path):
    archive = tmp_path / "not-started.zip"
    archive.write_bytes(b"test")
    response = _export_response(
        ConversationExport(file_obj=None, filename="test.zip", file_path=archive)
    )

    async def send(message):
        raise OSError("disconnected before response headers")

    async def receive():
        return {"type": "http.disconnect"}

    with pytest.raises(Exception):
        await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
    assert not archive.exists()


@pytest.mark.asyncio
async def test_batch_jsonl_spools_and_preserves_record_order(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "astrbot.dashboard.services.conversation_service.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    history = [{"role": "user", "content": "x" * 700_000}]
    conversation = SimpleNamespace(
        history=json.dumps(history),
        title="Example",
        persona_id=None,
        created_at=1,
        updated_at=2,
        user_id="owner",
        platform_id="test",
    )
    manager = SimpleNamespace(get_conversation=AsyncMock(return_value=conversation))
    service = ConversationService(
        SimpleNamespace(), SimpleNamespace(conversation_manager=manager)
    )
    service._get_webchat_titles = AsyncMock(return_value={})
    exported = await service.export_conversations(
        {"conversations": [{"cid": cid, "user_id": "owner"} for cid in ("a", "b", "c")]}
    )
    try:
        assert exported.file_obj._rolled
        records = [json.loads(line) for line in exported.file_obj]
        assert [record["cid"] for record in records] == ["a", "b", "c"]
        assert all(record["content"] == history for record in records)
    finally:
        exported.file_obj.close()
    assert list(tmp_path.iterdir()) == []
