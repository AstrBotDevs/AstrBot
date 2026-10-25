"""Persistence and lookup behavior for sender suggestions."""

import asyncio
from unittest.mock import MagicMock

import pytest

from astrbot.dashboard.services.session_management_service import SessionManagementService


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
    records = await temp_db.get_umo_senders()
    assert len(records) == 3
    assert {(sender.umo, sender.sender_id, sender.sender_name) for sender, _ in records} == {
        (umo, "123", "Alicia"),
        ("qq:GroupMessage:2000", "123", "Other card"),
        (umo, "456", ""),
    }


@pytest.mark.asyncio
async def test_concurrent_sender_upserts_use_one_record(temp_db):
    """Cope with simultaneous messages for the same sender and session."""
    await temp_db.get_umo_senders()
    await asyncio.gather(
        *(temp_db.upsert_umo_sender("qq:GroupMessage:1000", "123", "Alice") for _ in range(3))
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
        ("123", "Alicia"), ("456", "Bob"),
    }
    assert await temp_db.get_umo_senders(sender_ids=[]) == []
