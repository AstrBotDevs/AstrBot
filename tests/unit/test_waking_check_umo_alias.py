"""Tests for automatic UMO names recorded by the waking stage."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import astrbot.core.pipeline.waking_check.stage as waking
from astrbot.core.command import CommandCatalogStore
from astrbot.core.pipeline.waking_check.umo_auto_name import UmoAutoNameRecorder
from astrbot.core.platform.message_type import MessageType
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.utils.task_utils import cancel_tracked_tasks


def make_group_event(group_id: str, group_name: str | None, message: str = "/hello"):
    """Create a group event carrying wake and display metadata."""
    event = MagicMock()
    event.unified_msg_origin = f"test-platform:GroupMessage:{group_id}"
    event.message_obj = SimpleNamespace(
        type=MessageType.GROUP_MESSAGE,
        group=SimpleNamespace(group_name=group_name),
    )
    event.message_str = message
    event.is_wake = False
    event.role = "member"
    event.platform_member_role = "unknown"
    event.platform_role_source = "none"
    event.platform_role_expires_at = None
    event.session_id = group_id
    event._extras = {}
    event.get_group_id.return_value = group_id
    event.get_sender_id.return_value = "sender-1"
    event.get_sender_name.return_value = "Alice"
    event.get_self_id.return_value = "bot-1"
    event.get_messages.return_value = []
    event.send = AsyncMock()
    event.attach_authorization = None
    event.is_private_chat.return_value = False
    event.get_platform_name.return_value = "test-platform"
    event.get_platform_id.return_value = "test-platform"
    event.get_extra.side_effect = lambda key=None, default=None: (
        event._extras if key is None else event._extras.get(key, default)
    )
    event.set_extra.side_effect = lambda key, value: event._extras.__setitem__(
        key, value
    )
    return event


async def make_stage(store: MagicMock) -> tuple[waking.WakingCheckStage, set]:
    """Initialize a waking stage with automatic-name persistence enabled."""
    background_tasks: set[asyncio.Task] = set()
    stage = waking.WakingCheckStage()
    command_catalog = CommandCatalogStore()
    catalogs = RuntimeCatalogs()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "command_prefixes": ["/"],
                "plugin_set": ["*"],
                "llm_access": {
                    "prefixes": ["/"],
                    "private": "open",
                    "group": "prefix",
                    "reply_to_bot": False,
                },
                "platform_settings": {
                    "no_permission_reply": True,
                    "ignore_bot_self_message": False,
                    "ignore_at_all": False,
                    "unique_session": False,
                },
            },
            astrbot_config_id="test-conf-id",
            plugin_catalog=SimpleNamespace(
                get_command_catalog=lambda *_args: command_catalog,
            ),
            preferences=SimpleNamespace(get_async=AsyncMock(return_value={})),
            handlers=catalogs.handlers,
            plugins=catalogs.plugins,
            execution_context=SimpleNamespace(
                database=store,
                background_tasks=background_tasks,
            ),
        )
    )
    stage.session_plugins.filter_handlers_by_session = AsyncMock(
        side_effect=lambda _, handlers: handlers
    )
    return stage, background_tasks


@pytest.mark.asyncio
async def test_waking_stage_records_only_awakened_events():
    """Record a name immediately after waking and ignore ambient messages."""
    store = MagicMock()
    store.upsert_umo_auto_name = AsyncMock()
    stage, _background_tasks = await make_stage(store)

    ignored_event = make_group_event("group-1", "Engineering", "hello")
    await stage.process(ignored_event)
    assert stage._umo_auto_name_recorder._writer_task is None

    awakened_event = make_group_event("group-1", "Engineering")
    await stage.process(awakened_event)
    writer_task = stage._umo_auto_name_recorder._writer_task
    assert writer_task is not None
    await writer_task

    store.upsert_umo_auto_name.assert_awaited_once_with(
        umo="test-platform:GroupMessage:group-1",
        creator_sender_id="sender-1",
        auto_name="Engineering",
    )


@pytest.mark.asyncio
async def test_waking_stage_records_plugin_handler_wake():
    """Record a name when a plugin handler wakes an otherwise ambient message."""
    store = MagicMock()
    store.upsert_umo_auto_name = AsyncMock()
    stage, _background_tasks = await make_stage(store)
    stage._collect_activated_handlers = AsyncMock(return_value=([object()], {}, False))

    event = make_group_event("group-1", "Engineering", "hello")
    await stage.process(event)
    writer_task = stage._umo_auto_name_recorder._writer_task
    assert writer_task is not None
    await writer_task

    assert event.is_wake is True
    store.upsert_umo_auto_name.assert_awaited_once()


@pytest.mark.asyncio
async def test_waking_stage_skips_self_message_and_permission_denied():
    """Do not persist names on early stop_event returns."""
    store = MagicMock()
    store.upsert_umo_auto_name = AsyncMock()
    stage, _background_tasks = await make_stage(store)
    stage.ignore_bot_self_message = True

    self_event = make_group_event("group-1", "Engineering")
    self_event.get_sender_id.return_value = "bot-1"
    await stage.process(self_event)
    assert stage._umo_auto_name_recorder._writer_task is None

    denied_event = make_group_event("group-1", "Engineering")
    stage._collect_activated_handlers = AsyncMock(return_value=([], {}, True))
    await stage.process(denied_event)
    assert stage._umo_auto_name_recorder._writer_task is None
    store.upsert_umo_auto_name.assert_not_awaited()


@pytest.mark.asyncio
async def test_waking_stage_coalesces_auto_name_changes():
    """Persist only the latest name from an event burst for one UMO."""
    store = MagicMock()
    store.upsert_umo_auto_name = AsyncMock()
    recorder = UmoAutoNameRecorder(store, "test-conf-id")

    for group_name in ("Engineering", "Engineering", "Renamed"):
        recorder.schedule(make_group_event("group-1", group_name))

    writer_task = recorder._writer_task
    assert writer_task is not None
    await writer_task

    store.upsert_umo_auto_name.assert_awaited_once_with(
        umo="test-platform:GroupMessage:group-1",
        creator_sender_id="sender-1",
        auto_name="Renamed",
    )


@pytest.mark.asyncio
async def test_waking_stage_skips_missing_group_and_sender_names():
    """Do not persist ID fallbacks when platform names are unavailable."""
    store = MagicMock()
    store.upsert_umo_auto_name = AsyncMock()
    recorder = UmoAutoNameRecorder(store, "test-conf-id")

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
    store.upsert_umo_auto_name.assert_not_awaited()


@pytest.mark.asyncio
async def test_waking_stage_bounds_auto_name_cache():
    """Evict old UMO names when the per-stage cache reaches its bound."""
    store = MagicMock()
    store.upsert_umo_auto_name = AsyncMock()
    recorder = UmoAutoNameRecorder(store, "test-conf-id")

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
    assert store.upsert_umo_auto_name.await_count == 2


@pytest.mark.asyncio
async def test_waking_stage_retries_after_database_failure():
    """Evict a failed cache entry so a later wake retries the write."""
    store = MagicMock()
    store.upsert_umo_auto_name = AsyncMock(
        side_effect=[RuntimeError("database unavailable"), None]
    )
    recorder = UmoAutoNameRecorder(store, "test-conf-id")
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

    assert store.upsert_umo_auto_name.await_count == 2


@pytest.mark.asyncio
async def test_waking_stage_writer_does_not_block_processing():
    """Return from the waking stage while its database writer is blocked."""
    database_started = asyncio.Event()
    release_database = asyncio.Event()

    async def block_database_write(**kwargs):  # noqa: ARG001
        database_started.set()
        await release_database.wait()

    store = MagicMock()
    store.upsert_umo_auto_name = AsyncMock(side_effect=block_database_write)
    recorder = UmoAutoNameRecorder(store, "test-conf-id")
    recorder.schedule(make_group_event("group-1", "Engineering"))

    await asyncio.wait_for(database_started.wait(), timeout=1.0)
    release_database.set()
    writer_task = recorder._writer_task
    if writer_task is not None:
        await writer_task


@pytest.mark.asyncio
async def test_writer_writes_name_queued_during_in_flight_flush():
    """Keep flushing when schedule() queues another UMO mid-write."""
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    async def write_name(*, umo, creator_sender_id, auto_name):  # noqa: ARG001
        if umo.endswith(":group-1"):
            first_started.set()
            await release_first.wait()

    store = MagicMock()
    store.upsert_umo_auto_name = AsyncMock(side_effect=write_name)
    recorder = UmoAutoNameRecorder(store, "test-conf-id")

    recorder.schedule(make_group_event("group-1", "Engineering"))
    await asyncio.wait_for(first_started.wait(), timeout=1.0)
    recorder.schedule(make_group_event("group-2", "Design"))
    release_first.set()
    writer_task = recorder._writer_task
    assert writer_task is not None
    await asyncio.wait_for(writer_task, timeout=1.0)

    written = [
        call.kwargs["umo"] for call in store.upsert_umo_auto_name.await_args_list
    ]
    assert written == [
        "test-platform:GroupMessage:group-1",
        "test-platform:GroupMessage:group-2",
    ]


@pytest.mark.asyncio
async def test_cancelled_writer_does_not_respawn_until_reschedule():
    """Cancel leaves pending work; a later schedule() starts a new tracked writer."""
    first_started = asyncio.Event()
    block_first = asyncio.Event()
    write_count = 0

    async def write_name(*, umo, creator_sender_id, auto_name):  # noqa: ARG001
        nonlocal write_count
        write_count += 1
        if write_count == 1:
            first_started.set()
            await block_first.wait()

    store = MagicMock()
    store.upsert_umo_auto_name = AsyncMock(side_effect=write_name)
    background_tasks: set[asyncio.Task] = set()
    recorder = UmoAutoNameRecorder(store, "test-conf-id", background_tasks)

    recorder.schedule(make_group_event("group-1", "Engineering"))
    await asyncio.wait_for(first_started.wait(), timeout=1.0)
    first_writer = recorder._writer_task
    assert first_writer is not None

    recorder.schedule(make_group_event("group-2", "Design"))
    first_writer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_writer

    leftover = [task for task in background_tasks if not task.done()]
    assert leftover == []
    written = [
        call.kwargs["umo"] for call in store.upsert_umo_auto_name.await_args_list
    ]
    assert "test-platform:GroupMessage:group-2" not in written

    recorder.schedule(make_group_event("group-2", "Design"))
    second_writer = recorder._writer_task
    assert second_writer is not None
    assert second_writer is not first_writer
    assert second_writer in background_tasks
    await asyncio.wait_for(second_writer, timeout=1.0)

    written = [
        call.kwargs["umo"] for call in store.upsert_umo_auto_name.await_args_list
    ]
    assert "test-platform:GroupMessage:group-2" in written


@pytest.mark.asyncio
async def test_cancel_tracked_tasks_does_not_leave_running_writer():
    """Shutdown must not respawn an untracked writer after cancelling the set."""
    first_started = asyncio.Event()
    block_first = asyncio.Event()

    async def write_name(*, umo, creator_sender_id, auto_name):  # noqa: ARG001
        if umo.endswith(":group-1"):
            first_started.set()
            await block_first.wait()

    store = MagicMock()
    store.upsert_umo_auto_name = AsyncMock(side_effect=write_name)
    background_tasks: set[asyncio.Task] = set()
    recorder = UmoAutoNameRecorder(store, "test-conf-id", background_tasks)

    recorder.schedule(make_group_event("group-1", "Engineering"))
    await asyncio.wait_for(first_started.wait(), timeout=1.0)
    recorder.schedule(make_group_event("group-2", "Design"))

    await cancel_tracked_tasks(background_tasks)

    writer_tasks = [
        task
        for task in asyncio.all_tasks()
        if task.get_name().startswith("umo_auto_name_writer:")
    ]
    assert all(task.done() for task in writer_tasks)
    assert background_tasks == set()
    assert recorder._writer_task is None or recorder._writer_task.done()
    written = [
        call.kwargs["umo"] for call in store.upsert_umo_auto_name.await_args_list
    ]
    assert "test-platform:GroupMessage:group-2" not in written


@pytest.mark.asyncio
async def test_cancelled_write_retries_same_name_on_reschedule():
    """Clear the cache on cancel so the same automatic name can be written again."""
    first_started = asyncio.Event()
    block_first = asyncio.Event()
    call_count = 0

    async def write_name(**kwargs):  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            first_started.set()
            await block_first.wait()

    store = MagicMock()
    store.upsert_umo_auto_name = AsyncMock(side_effect=write_name)
    background_tasks: set[asyncio.Task] = set()
    recorder = UmoAutoNameRecorder(store, "test-conf-id", background_tasks)
    event = make_group_event("group-1", "Engineering")

    recorder.schedule(event)
    await asyncio.wait_for(first_started.wait(), timeout=1.0)
    first_writer = recorder._writer_task
    assert first_writer is not None
    first_writer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_writer

    assert event.unified_msg_origin not in recorder._cache

    recorder.schedule(event)
    second_writer = recorder._writer_task
    assert second_writer is not None
    assert second_writer in background_tasks
    await asyncio.wait_for(second_writer, timeout=1.0)
    assert store.upsert_umo_auto_name.await_count == 2
