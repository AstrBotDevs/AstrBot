"""Persistence and lookup behavior for sender suggestions."""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlmodel import select

from astrbot.core.db.po import UmoSender
from astrbot.dashboard.services.session_management_service import (
    SessionManagementService,
)


@pytest.mark.asyncio
async def test_sender_upsert_preserves_names_and_session_identity(temp_db):
    """Keep group-specific names and avoid writes for absent or unchanged names."""
    umo = "qq:GroupMessage:1000"
    await temp_db.upsert_umo_sender(umo, "123", "Alice")
    before = (await temp_db.get_umo_senders())[0][0]
    await temp_db.upsert_umo_sender(umo, "123", "Alice")
    await temp_db.upsert_umo_sender(umo, "123", "")
    unchanged = (await temp_db.get_umo_senders())[0][0]
    assert unchanged.id == before.id
    assert unchanged.sender_name == "Alice"
    assert unchanged.updated_at == before.updated_at

    await temp_db.upsert_umo_sender(umo, "123", "Alicia")
    renamed = (await temp_db.get_umo_senders())[0][0]
    assert renamed.id == before.id
    assert renamed.created_at == before.created_at
    assert renamed.updated_at != before.updated_at

    await temp_db.upsert_umo_sender("qq:GroupMessage:2000", "123", "Other card")
    await temp_db.upsert_umo_sender(umo, "456", "")
    await temp_db.upsert_umo_sender(umo, "", "Invalid")
    async with temp_db.get_db() as session:
        records = (await session.execute(select(UmoSender))).scalars().all()
    assert len(records) == 3
    assert {
        (sender.umo, sender.sender_id, sender.sender_name) for sender in records
    } == {
        (umo, "123", "Alicia"),
        ("qq:GroupMessage:2000", "123", "Other card"),
        (umo, "456", ""),
    }


@pytest.mark.asyncio
async def test_concurrent_sender_upserts_use_one_record(temp_db):
    """Cope with simultaneous messages for the same sender and session."""
    await temp_db.get_umo_senders()
    await asyncio.gather(
        *(
            temp_db.upsert_umo_sender("qq:GroupMessage:1000", "123", "Alice")
            for _ in range(3)
        )
    )
    assert len(await temp_db.get_umo_senders()) == 1


@pytest.mark.asyncio
async def test_sender_search_joins_aliases_and_escapes_wildcards(temp_db):
    """Search names and IDs literally, keeping senders without a session alias."""
    umo = "qq:GroupMessage:1000"
    await temp_db.upsert_umo_auto_name(umo, "123", "Engineering")
    await temp_db.upsert_umo_alias(umo, "admin", "Engineering", "Backend room")
    await temp_db.upsert_umo_sender(umo, "123", "Alice_100%")
    await temp_db.upsert_umo_sender("qq:FriendMessage:456", "456", "Bob")
    for search in ("ALICE", "123", "Engineering", "Backend", "100%", "_"):
        records = await temp_db.get_umo_senders(search)
        assert len(records) == 1
        sender, alias = records[0]
        assert sender.sender_id == "123"
        assert alias.user_alias == "Backend room"

    assert (await temp_db.get_umo_senders("Bob"))[0][1] is None
    assert await temp_db.get_umo_senders("missing") == []
    limited = await temp_db.get_umo_senders(limit=1)
    assert len(limited) == 1
    assert limited[0][0].sender_id == "456"

    service = SessionManagementService(MagicMock(), temp_db)
    suggestions = (await service.list_senders(" Alice "))["senders"]
    assert suggestions[0]["sender_id"] == "123"
    assert suggestions[0]["sender_name"] == "Alice_100%"
    assert suggestions[0]["platform"] == "qq"
    assert suggestions[0]["display_name"] == "Backend room"


@pytest.mark.asyncio
async def test_sender_id_resolution_returns_latest_card_for_every_id(temp_db):
    """Resolve exact IDs once each even when one sender appears in many groups."""
    await temp_db.upsert_umo_sender("qq:GroupMessage:1", "123", "Alice")
    await temp_db.upsert_umo_sender("qq:GroupMessage:2", "123", "Alice Chen")
    await temp_db.upsert_umo_sender("qq:GroupMessage:3", "1234", "Wrong sender")
    await temp_db.upsert_umo_sender("qq:FriendMessage:456", "456", "Bob")
    await temp_db.upsert_umo_sender("qq:GroupMessage:1", "123", "Alicia")
    records = await temp_db.get_umo_senders(sender_ids=["123", "456", "unknown"])
    assert {(sender.sender_id, sender.sender_name) for sender, _ in records} == {
        ("123", "Alicia"),
        ("456", "Bob"),
    }
    assert await temp_db.get_umo_senders(sender_ids=[]) == []


@pytest.mark.asyncio
async def test_sender_candidates_deduplicate_platform_and_id_before_limiting(temp_db):
    """Keep latest matching cards per instance without losing source-specific records."""
    await temp_db.upsert_umo_sender("qq:GroupMessage:bob", "456", "Bob")
    for index in range(5):
        await temp_db.upsert_umo_sender(
            f"qq:GroupMessage:{index}", "123", f"Alice {index}"
        )
    await temp_db.upsert_umo_auto_name("qq:GroupMessage:0", "123", "Engineering")
    await temp_db.upsert_umo_sender("qq-2:FriendMessage:123", "123", "Other platform")

    records = await temp_db.get_umo_senders(limit=3)
    assert [(sender.umo, sender.sender_id) for sender, _ in records] == [
        ("qq-2:FriendMessage:123", "123"),
        ("qq:GroupMessage:4", "123"),
        ("qq:GroupMessage:bob", "456"),
    ]
    matches = await temp_db.get_umo_senders("Alice")
    assert len(matches) == 1
    assert matches[0][0].sender_name == "Alice 4"
    matches = await temp_db.get_umo_senders("Engineering")
    assert len(matches) == 1
    assert matches[0][0].umo == "qq:GroupMessage:0"

    resolved = await temp_db.get_umo_senders(sender_ids=["123"])
    assert len(resolved) == 1
    assert resolved[0][0].umo == "qq-2:FriendMessage:123"


@pytest.mark.asyncio
@pytest.mark.parametrize("search", ["", "Alice"])
async def test_sender_pages_deduplicate_before_offset_and_preserve_tie_order(
    temp_db, search
):
    """Page matching identities once each, with stable ordering for equal timestamps."""
    for index in range(6):
        await temp_db.upsert_umo_sender(
            "qq:GroupMessage:room", str(index), f"Alice {index}"
        )
    await temp_db.upsert_umo_sender("qq:GroupMessage:other", "5", "Alice newer")
    await temp_db.upsert_umo_sender("qq-2:GroupMessage:room", "5", "Alice another bot")
    async with temp_db.get_db() as session:
        async with session.begin():
            records = (await session.execute(select(UmoSender))).scalars().all()
            for sender in records:
                sender.updated_at = datetime(2026, 10, 25)
    service = SessionManagementService(MagicMock(), temp_db)
    results = []
    for page in range(1, 5):
        response = await service.list_senders(search, limit=2, page=page)
        assert response["page"] == page
        assert response["has_more"] == (page < 4)
        results.extend(
            (sender["platform"], sender["sender_id"]) for sender in response["senders"]
        )
    assert results == [("qq-2", "5")] + [
        ("qq", str(index)) for index in range(5, -1, -1)
    ]
    assert (await service.list_senders(search, limit=2, page=5)) == {
        "page": 5,
        "has_more": False,
        "senders": [],
    }
    if search:
        assert (await service.list_senders("missing", limit=2))["senders"] == []


@pytest.mark.asyncio
async def test_exact_sender_resolution_supports_paging(temp_db):
    """Keep exact-ID hydration deduplicated and expose a correct final page."""
    for index in range(3):
        await temp_db.upsert_umo_sender(
            "qq:GroupMessage:room", str(index), f"User {index}"
        )
    await temp_db.upsert_umo_sender("qq:GroupMessage:other", "2", "Latest")
    service = SessionManagementService(MagicMock(), temp_db)
    first = await service.list_senders(limit=2, sender_ids=["0", "1", "2"])
    second = await service.list_senders(limit=2, sender_ids=["0", "1", "2"], page=2)
    assert [sender["sender_id"] for sender in first["senders"]] == ["2", "1"]
    assert first["has_more"] is True
    assert [sender["sender_id"] for sender in second["senders"]] == ["0"]
    assert second["has_more"] is False
    empty = await service.list_senders(sender_ids=[])
    assert empty == {"page": 1, "has_more": False, "senders": []}
