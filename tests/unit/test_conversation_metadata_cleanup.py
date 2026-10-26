"""Tests for UMO metadata cleanup on conversation deletion."""

import asyncio
from types import SimpleNamespace

import pytest

from astrbot.dashboard.api import conversations as conversations_api
from astrbot.dashboard.schemas import ConversationBatchDeleteRequest
from astrbot.dashboard.services.conversation_service import ConversationService

UMO = "qq:GroupMessage:1000"
UMO_OTHER = "qq:GroupMessage:2000"


async def seed_alias(db, umo: str = UMO) -> None:
    await db.upsert_umo_alias(
        umo=umo,
        creator_sender_id="sender-1",
        auto_name="Engineering Group",
        user_alias="Backend Room",
    )


# ====
# Database layer
# ====


@pytest.mark.asyncio
async def test_delete_umo_alias_removes_record(temp_db):
    await seed_alias(temp_db)

    assert await temp_db.delete_umo_alias(UMO) is True
    assert await temp_db.get_umo_alias(UMO) is None


@pytest.mark.asyncio
async def test_delete_umo_alias_returns_false_when_missing(temp_db):
    assert await temp_db.delete_umo_alias(UMO) is False


@pytest.mark.asyncio
async def test_metadata_cleanup_deletes_when_no_conversation_reference(temp_db):
    await seed_alias(temp_db)
    await temp_db.upsert_umo_sender(UMO, "sender-1", "Alice")

    outcome = await temp_db.delete_umo_metadata_if_unreferenced(UMO)

    assert outcome == {
        "alias_deleted": True,
        "senders_deleted": 1,
        "retained": False,
    }
    assert await temp_db.get_umo_alias(UMO) is None
    senders = await temp_db.get_umo_senders(sender_ids=["sender-1"])
    assert all(sender.umo != UMO for sender, _ in senders)


@pytest.mark.asyncio
async def test_metadata_cleanup_retains_when_other_conversation_exists(temp_db):
    await temp_db.create_conversation(user_id=UMO, platform_id="qq")
    await seed_alias(temp_db)
    await temp_db.upsert_umo_sender(UMO, "sender-1", "Alice")

    outcome = await temp_db.delete_umo_metadata_if_unreferenced(UMO)

    assert outcome == {
        "alias_deleted": False,
        "senders_deleted": 0,
        "retained": True,
    }
    assert await temp_db.get_umo_alias(UMO) is not None


@pytest.mark.asyncio
async def test_metadata_cleanup_handles_missing_alias(temp_db):
    outcome = await temp_db.delete_umo_metadata_if_unreferenced(UMO)

    assert outcome == {
        "alias_deleted": False,
        "senders_deleted": 0,
        "retained": False,
    }


@pytest.mark.asyncio
async def test_metadata_cleanup_only_touches_target_umo(temp_db):
    await seed_alias(temp_db)
    await seed_alias(temp_db, UMO_OTHER)
    await temp_db.create_conversation(user_id=UMO_OTHER, platform_id="qq")

    outcome = await temp_db.delete_umo_metadata_if_unreferenced(UMO)

    assert outcome["alias_deleted"] is True
    assert await temp_db.get_umo_alias(UMO) is None
    assert await temp_db.get_umo_alias(UMO_OTHER) is not None


# ====
# Service layer
# ====


class FakeConversationManager:
    """Minimal conversation manager that really deletes rows from temp_db."""

    def __init__(self, db) -> None:
        self.db = db
        self.deleted: list[tuple[str, str]] = []

    async def delete_conversation(
        self, unified_msg_origin: str, conversation_id: str | None = None
    ) -> None:
        self.deleted.append((unified_msg_origin, conversation_id or ""))
        await self.db.delete_conversation(cid=conversation_id)


def make_service(db):
    manager = FakeConversationManager(db)
    lifecycle = SimpleNamespace(conversation_manager=manager)
    return ConversationService(db_helper=db, core_lifecycle=lifecycle), manager


@pytest.mark.asyncio
async def test_service_single_delete_removes_last_conversation_metadata(temp_db):
    conversation = await temp_db.create_conversation(user_id=UMO, platform_id="qq")
    await seed_alias(temp_db)
    await temp_db.upsert_umo_sender(UMO, "sender-1", "Alice")
    service, _ = make_service(temp_db)

    result = await service.delete_conversation(
        {
            "user_id": UMO,
            "cid": conversation.conversation_id,
            "cleanup_metadata": True,
        }
    )

    assert result["metadata_cleanup"] == {
        "deleted_aliases": 1,
        "deleted_senders": 1,
        "retained_umos": [],
    }
    assert await temp_db.get_umo_alias(UMO) is None


@pytest.mark.asyncio
async def test_service_single_delete_keeps_metadata_with_other_conversation(temp_db):
    first = await temp_db.create_conversation(user_id=UMO, platform_id="qq")
    await temp_db.create_conversation(user_id=UMO, platform_id="qq")
    await seed_alias(temp_db)
    service, _ = make_service(temp_db)

    result = await service.delete_conversation(
        {
            "user_id": UMO,
            "cid": first.conversation_id,
            "cleanup_metadata": True,
        }
    )

    assert result["metadata_cleanup"]["deleted_aliases"] == 0
    assert result["metadata_cleanup"]["retained_umos"] == [UMO]
    assert await temp_db.get_umo_alias(UMO) is not None


@pytest.mark.asyncio
async def test_service_default_delete_keeps_metadata(temp_db):
    conversation = await temp_db.create_conversation(user_id=UMO, platform_id="qq")
    await seed_alias(temp_db)
    service, _ = make_service(temp_db)

    result = await service.delete_conversation(
        {"user_id": UMO, "cid": conversation.conversation_id}
    )

    assert "metadata_cleanup" not in result
    assert await temp_db.get_umo_alias(UMO) is not None


@pytest.mark.asyncio
async def test_service_batch_delete_cleans_after_all_cids_removed(temp_db):
    first = await temp_db.create_conversation(user_id=UMO, platform_id="qq")
    second = await temp_db.create_conversation(user_id=UMO, platform_id="qq")
    await seed_alias(temp_db)
    service, _ = make_service(temp_db)

    result = await service.delete_conversation(
        {
            "conversations": [
                {"user_id": UMO, "cid": first.conversation_id},
                {"user_id": UMO, "cid": second.conversation_id},
            ],
            "cleanup_metadata": True,
        }
    )

    assert result["deleted_count"] == 2
    assert result["metadata_cleanup"]["deleted_aliases"] == 1
    assert result["metadata_cleanup"]["retained_umos"] == []
    assert await temp_db.get_umo_alias(UMO) is None


@pytest.mark.asyncio
async def test_service_batch_delete_mixes_retained_and_cleaned_umos(temp_db):
    keep_one = await temp_db.create_conversation(user_id=UMO, platform_id="qq")
    await temp_db.create_conversation(user_id=UMO, platform_id="qq")
    other = await temp_db.create_conversation(user_id=UMO_OTHER, platform_id="qq")
    await seed_alias(temp_db)
    await seed_alias(temp_db, UMO_OTHER)
    service, _ = make_service(temp_db)

    result = await service.delete_conversation(
        {
            "conversations": [
                {"user_id": UMO, "cid": keep_one.conversation_id},
                {"user_id": UMO_OTHER, "cid": other.conversation_id},
            ],
            "cleanup_metadata": True,
        }
    )

    assert result["metadata_cleanup"]["deleted_aliases"] == 1
    assert result["metadata_cleanup"]["retained_umos"] == [UMO]
    assert await temp_db.get_umo_alias(UMO) is not None
    assert await temp_db.get_umo_alias(UMO_OTHER) is None


@pytest.mark.asyncio
async def test_service_cleanup_without_alias_does_not_fail(temp_db):
    conversation = await temp_db.create_conversation(user_id=UMO, platform_id="qq")
    service, _ = make_service(temp_db)

    result = await service.delete_conversation(
        {
            "user_id": UMO,
            "cid": conversation.conversation_id,
            "cleanup_metadata": True,
        }
    )

    assert result["metadata_cleanup"] == {
        "deleted_aliases": 0,
        "deleted_senders": 0,
        "retained_umos": [],
    }


@pytest.mark.asyncio
async def test_metadata_cleanup_retained_flag_requires_existing_metadata(temp_db):
    await temp_db.create_conversation(user_id=UMO, platform_id="qq")

    outcome = await temp_db.delete_umo_metadata_if_unreferenced(UMO)

    assert outcome == {
        "alias_deleted": False,
        "senders_deleted": 0,
        "retained": False,
    }


class FailingCleanupDB:
    """Delegates to a real database but fails the metadata cleanup call."""

    def __init__(self, db) -> None:
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    async def delete_umo_metadata_if_unreferenced(self, umo: str) -> dict:
        raise RuntimeError("database is locked")


@pytest.mark.asyncio
async def test_service_cleanup_error_does_not_fail_deletion(temp_db):
    conversation = await temp_db.create_conversation(user_id=UMO, platform_id="qq")
    await seed_alias(temp_db)
    service, _ = make_service(FailingCleanupDB(temp_db))

    result = await service.delete_conversation(
        {
            "user_id": UMO,
            "cid": conversation.conversation_id,
            "cleanup_metadata": True,
        }
    )

    assert result["message"] == "对话删除成功"
    assert result["metadata_cleanup"]["error"] == "database is locked"
    assert result["metadata_cleanup"]["deleted_aliases"] == 0


@pytest.mark.asyncio
async def test_service_batch_cleanup_only_covers_successful_deletions(temp_db):
    conversation = await temp_db.create_conversation(user_id=UMO, platform_id="qq")
    await seed_alias(temp_db)
    await seed_alias(temp_db, UMO_OTHER)
    service, _ = make_service(temp_db)

    result = await service.delete_conversation(
        {
            "conversations": [
                {"user_id": UMO, "cid": conversation.conversation_id},
                "broken-item",
                {"user_id": UMO_OTHER, "cid": "missing-cid"},
            ],
            "cleanup_metadata": True,
        }
    )

    assert result["deleted_count"] == 2
    assert result["failed_count"] == 1
    assert await temp_db.get_umo_alias(UMO) is None
    assert await temp_db.get_umo_alias(UMO_OTHER) is None


@pytest.mark.asyncio
async def test_concurrent_conversation_creation_and_cleanup_do_not_error(temp_db):
    """Cleanup racing new conversations must not raise lock/consistency errors."""
    await seed_alias(temp_db)

    async def create():
        await temp_db.create_conversation(user_id=UMO, platform_id="qq")

    async def cleanup():
        await temp_db.delete_umo_metadata_if_unreferenced(UMO)

    results = await asyncio.gather(
        *[create() for _ in range(10)],
        *[cleanup() for _ in range(10)],
        return_exceptions=True,
    )

    assert not [result for result in results if isinstance(result, Exception)]


# ====
# API layer parameter passing
# ====


class RecordingService:
    def __init__(self) -> None:
        self.payload: dict | None = None

    async def delete_conversation(self, payload: dict) -> dict:
        self.payload = payload
        return {"message": "ok"}


@pytest.mark.asyncio
async def test_api_single_delete_forwards_cleanup_flag():
    service = RecordingService()

    await conversations_api.delete_conversation(
        conversation_id="cid-1",
        user_id=UMO,
        cleanup_metadata=True,
        _auth=None,
        service=service,
    )

    assert service.payload == {
        "user_id": UMO,
        "cid": "cid-1",
        "cleanup_metadata": True,
    }


@pytest.mark.asyncio
async def test_api_single_delete_defaults_cleanup_flag_to_false():
    service = RecordingService()

    await conversations_api.delete_conversation(
        conversation_id="cid-1",
        user_id=UMO,
        cleanup_metadata=False,
        _auth=None,
        service=service,
    )

    assert service.payload["cleanup_metadata"] is False


@pytest.mark.asyncio
async def test_api_batch_delete_forwards_cleanup_flag():
    service = RecordingService()

    await conversations_api.batch_delete_conversations(
        payload=ConversationBatchDeleteRequest(
            conversations=[{"user_id": UMO, "cid": "cid-1"}],
            cleanup_metadata=True,
        ),
        _auth=None,
        service=service,
    )

    assert service.payload is not None
    assert service.payload["cleanup_metadata"] is True
    assert service.payload["conversations"] == [{"user_id": UMO, "cid": "cid-1"}]
