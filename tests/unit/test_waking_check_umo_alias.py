"""Tests for automatic UMO names recorded by the waking stage."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.pipeline.waking_check.stage import WakingCheckStage
from astrbot.core.pipeline.waking_check.umo_auto_name import UmoAutoNameRecorder
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.session_plugin_manager import SessionPluginManager


def make_group_event(group_id: str, group_name: str | None, message: str = "/hello"):
    """Create a group event carrying wake and display metadata.

    Args:
        group_id: Platform group identifier.
        group_name: Platform group display name.
        message: Event message text.

    Returns:
        Mocked group message event.
    """
    event = MagicMock()
    event.unified_msg_origin = f"test-platform:GroupMessage:{group_id}"
    event.message_obj = SimpleNamespace(
        type=MessageType.GROUP_MESSAGE,
        group=SimpleNamespace(group_name=group_name),
    )
    event.message_str = message
    event.is_wake = False
    event.role = "member"
    event.get_group_id.return_value = group_id
    event.get_sender_id.return_value = "sender-1"
    event.get_self_id.return_value = "bot-1"
    event.get_messages.return_value = [MagicMock()]
    event.is_private_chat.return_value = False
    event.get_platform_name.return_value = "test-platform"
    event.get_extra.side_effect = lambda key=None, default=None: default
    return event


async def make_stage(db_helper: MagicMock) -> WakingCheckStage:
    """Initialize a waking stage with automatic-name persistence enabled.

    Args:
        db_helper: Mock database used by the stage writer.

    Returns:
        Initialized waking stage.
    """
    stage = WakingCheckStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "admins_id": [],
                "wake_prefix": ["/"],
                "plugin_set": ["*"],
                "platform_settings": {
                    "friend_message_needs_wake_prefix": True,
                },
            },
            astrbot_config_id="test-conf-id",
            db_helper=db_helper,
        )
    )
    return stage


@pytest.mark.asyncio
async def test_waking_stage_records_only_awakened_events(monkeypatch):
    """Record a name immediately after waking and ignore ambient messages."""
    db_helper = MagicMock()
    db_helper.upsert_umo_auto_name = AsyncMock()
    stage = await make_stage(db_helper)
    monkeypatch.setattr(
        "astrbot.core.pipeline.waking_check.stage.star_handlers_registry.get_handlers_by_event_type",
        lambda *_args, **_kwargs: [],
    )

    async def return_handlers(_event, handlers):
        return handlers

    monkeypatch.setattr(
        SessionPluginManager,
        "filter_handlers_by_session",
        return_handlers,
    )

    ignored_event = make_group_event("group-1", "Engineering", "hello")
    await stage.process(ignored_event)
    assert stage._umo_auto_name_recorder._writer_task is None

    awakened_event = make_group_event("group-1", "Engineering")
    await stage.process(awakened_event)
    writer_task = stage._umo_auto_name_recorder._writer_task
    assert writer_task is not None
    await writer_task

    db_helper.upsert_umo_auto_name.assert_awaited_once_with(
        umo="test-platform:GroupMessage:group-1",
        creator_sender_id="sender-1",
        auto_name="Engineering",
    )


@pytest.mark.asyncio
async def test_waking_stage_coalesces_auto_name_changes():
    """Persist only the latest name from an event burst for one UMO."""
    db_helper = MagicMock()
    db_helper.upsert_umo_auto_name = AsyncMock()
    recorder = UmoAutoNameRecorder(db_helper, "test-conf-id")

    for group_name in ("Engineering", "Engineering", "Renamed"):
        recorder.schedule(make_group_event("group-1", group_name))

    writer_task = recorder._writer_task
    assert writer_task is not None
    await writer_task

    db_helper.upsert_umo_auto_name.assert_awaited_once_with(
        umo="test-platform:GroupMessage:group-1",
        creator_sender_id="sender-1",
        auto_name="Renamed",
    )


@pytest.mark.asyncio
async def test_waking_stage_skips_missing_group_and_sender_names():
    """Do not persist ID fallbacks when platform names are unavailable."""
    db_helper = MagicMock()
    db_helper.upsert_umo_auto_name = AsyncMock()
    recorder = UmoAutoNameRecorder(db_helper, "test-conf-id")

    recorder.schedule(make_group_event("group-1", None))

    friend_event = MagicMock()
    friend_event.unified_msg_origin = "test-platform:FriendMessage:sender-2"
    friend_event.message_obj = SimpleNamespace(group=None)
    friend_event.get_group_id.return_value = ""
    friend_event.get_sender_name.return_value = ""
    friend_event.get_sender_id.return_value = "sender-2"
    recorder.schedule(friend_event)

    assert recorder._writer_task is None
    assert not recorder._cache
    db_helper.upsert_umo_auto_name.assert_not_awaited()


@pytest.mark.asyncio
async def test_waking_stage_bounds_auto_name_cache():
    """Evict old UMO names when the per-stage cache reaches its bound."""
    db_helper = MagicMock()
    db_helper.upsert_umo_auto_name = AsyncMock()
    recorder = UmoAutoNameRecorder(db_helper, "test-conf-id")

    with patch(
        "astrbot.core.pipeline.waking_check.umo_auto_name.MAX_UMO_AUTO_NAME_CACHE_SIZE",
        2,
    ):
        for index in range(3):
            recorder.schedule(make_group_event(f"group-{index}", f"Group {index}"))

        writer_task = recorder._writer_task
        assert writer_task is not None
        await writer_task

    assert list(recorder._cache) == [
        "test-platform:GroupMessage:group-1",
        "test-platform:GroupMessage:group-2",
    ]
    assert db_helper.upsert_umo_auto_name.await_count == 2


@pytest.mark.asyncio
async def test_waking_stage_retries_after_database_failure():
    """Evict a failed cache entry so a later wake retries the write."""
    db_helper = MagicMock()
    db_helper.upsert_umo_auto_name = AsyncMock(
        side_effect=[RuntimeError("database unavailable"), None]
    )
    recorder = UmoAutoNameRecorder(db_helper, "test-conf-id")
    event = make_group_event("group-1", "Engineering")

    with patch("astrbot.core.pipeline.waking_check.umo_auto_name.logger"):
        recorder.schedule(event)
        first_writer = recorder._writer_task
        assert first_writer is not None
        await first_writer

    assert event.unified_msg_origin not in recorder._cache

    recorder.schedule(event)
    second_writer = recorder._writer_task
    assert second_writer is not None
    await second_writer

    assert db_helper.upsert_umo_auto_name.await_count == 2


@pytest.mark.asyncio
async def test_waking_stage_writer_does_not_block_processing():
    """Return from the waking stage while its database writer is blocked."""
    database_started = asyncio.Event()
    release_database = asyncio.Event()

    async def block_database_write(**kwargs):  # noqa: ARG001
        database_started.set()
        await release_database.wait()

    db_helper = MagicMock()
    db_helper.upsert_umo_auto_name = AsyncMock(side_effect=block_database_write)
    recorder = UmoAutoNameRecorder(db_helper, "test-conf-id")
    recorder.schedule(make_group_event("group-1", "Engineering"))

    await asyncio.wait_for(database_started.wait(), timeout=1.0)
    release_database.set()
    writer_task = recorder._writer_task
    if writer_task is not None:
        await writer_task
