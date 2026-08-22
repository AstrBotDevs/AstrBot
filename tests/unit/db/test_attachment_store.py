import pytest

from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_attachment_reads_and_deletes_return_expected_counts(
    temp_db: SQLiteDatabase,
):
    first = await temp_db.insert_attachment(
        path="/tmp/a.txt",
        type="file",
        mime_type="text/plain",
    )
    second = await temp_db.insert_attachment(
        path="/tmp/b.png",
        type="image",
        mime_type="image/png",
    )

    fetched = await temp_db.get_attachments([second.attachment_id, first.attachment_id])
    assert {attachment.attachment_id for attachment in fetched} == {
        first.attachment_id,
        second.attachment_id,
    }
    assert await temp_db.delete_attachment("missing") is False

    deleted_count = await temp_db.delete_attachments(
        [first.attachment_id, "missing", second.attachment_id]
    )

    assert deleted_count == 2
    assert await temp_db.get_attachment_by_id(first.attachment_id) is None
    assert await temp_db.get_attachment_by_id(second.attachment_id) is None
    assert await temp_db.delete_attachments([]) == 0


@pytest.mark.asyncio
async def test_get_attachments_returns_empty_for_empty_input(temp_db: SQLiteDatabase):
    assert await temp_db.get_attachments([]) == []
