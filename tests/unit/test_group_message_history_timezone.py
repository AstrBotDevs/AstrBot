"""Group message history timestamps must follow the configured timezone."""

import csv
import io
import os
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import update

from astrbot.core.astr_agent_runtime.tools.message_tools import (
    GetGroupMessageHistoryTool,
)
from astrbot.core.db.po import PlatformMessageHistory
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager


def _parse(result: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    rows = csv.reader(io.StringIO(result))
    header = next(rows)
    messages: list[dict[str, str]] = []
    metadata: dict[str, str] = {}
    for row in rows:
        if len(row) == 1 and "=" in row[0]:
            key, value = row[0].split("=", 1)
            metadata[key] = value
        else:
            messages.append(dict(zip(header, row, strict=True)))
    return messages, metadata


async def _seed(db: SQLiteDatabase, manager, umo: str, created_at: datetime):
    """Insert one group message and pin its stored (naive UTC) timestamp."""
    await manager.insert_message_chain(
        platform_id="test",
        user_id=umo,
        message_chain=MessageChain([Plain("hello")]),
        role="user",
        sender_id="user-1",
        sender_name="Alice",
        max_messages=10,
    )
    async with db.engine.begin() as connection:
        await connection.execute(
            update(PlatformMessageHistory).values(created_at=created_at)
        )


def _context(manager, umo: str, extra_cfg: dict):
    event = SimpleNamespace(
        unified_msg_origin=umo,
        get_message_type=lambda: MessageType.GROUP_MESSAGE,
        get_platform_id=lambda: "test",
        get_extra=lambda key, default=None: default,
    )
    config = {
        "provider_ltm_settings": {
            "group_message_history_enable": True,
            "group_message_history_max_cnt": 10,
        },
        **extra_cfg,
    }
    return SimpleNamespace(
        context=SimpleNamespace(
            event=event,
            context=SimpleNamespace(
                get_config=lambda umo: config,
                message_history_manager=manager,
            ),
        )
    )


@pytest.mark.asyncio
async def test_history_time_uses_configured_timezone(tmp_path):
    """A naive-UTC stored value is rendered in the configured IANA timezone."""
    db = SQLiteDatabase(str(tmp_path / "timezone.db"))
    manager = PlatformMessageHistoryManager(db)
    umo = "test:GroupMessage:group-tz"

    try:
        await _seed(db, manager, umo, datetime(2026, 11, 21, 13, 1))

        messages, metadata = _parse(
            await GetGroupMessageHistoryTool().call(
                _context(manager, umo, {"timezone": "Asia/Shanghai"})
            )
        )

        assert messages[0]["time"] == "2026-11-21 21:01"
        assert metadata["time_notice"] == "Times are in Asia/Shanghai (UTC+08:00)."
        # Other columns and metadata must stay untouched.
        assert messages[0]["sender"] == "Alice"
        assert messages[0]["text"] == "hello"
        assert metadata["has_more"] == "false"
        assert "untrusted data" in metadata["notice"]
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_history_time_rolls_over_the_date(tmp_path):
    """UTC 23:30 must render as the next day in UTC+8."""
    db = SQLiteDatabase(str(tmp_path / "rollover.db"))
    manager = PlatformMessageHistoryManager(db)
    umo = "test:GroupMessage:group-rollover"

    try:
        await _seed(db, manager, umo, datetime(2026, 11, 20, 23, 30))

        messages, _ = _parse(
            await GetGroupMessageHistoryTool().call(
                _context(manager, umo, {"timezone": "Asia/Shanghai"})
            )
        )

        assert messages[0]["time"] == "2026-11-21 07:30"
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_history_time_falls_back_to_local_timezone(tmp_path):
    """An empty timezone keeps working and advertises local time."""
    db = SQLiteDatabase(str(tmp_path / "local.db"))
    manager = PlatformMessageHistoryManager(db)
    umo = "test:GroupMessage:group-local"

    try:
        await _seed(db, manager, umo, datetime(2026, 11, 21, 13, 1))

        messages, metadata = _parse(
            await GetGroupMessageHistoryTool().call(
                _context(manager, umo, {"timezone": ""})
            )
        )

        expected = datetime(2026, 11, 21, 13, 1, tzinfo=timezone.utc).astimezone()
        assert messages[0]["time"] == expected.strftime("%Y-%m-%d %H:%M")
        assert metadata["time_notice"].startswith("Times are in local time (UTC")
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_history_time_tolerates_invalid_timezone(tmp_path):
    """An invalid IANA name must not break the tool."""
    db = SQLiteDatabase(str(tmp_path / "invalid.db"))
    manager = PlatformMessageHistoryManager(db)
    umo = "test:GroupMessage:group-invalid"

    try:
        await _seed(db, manager, umo, datetime(2026, 11, 21, 13, 1))

        messages, metadata = _parse(
            await GetGroupMessageHistoryTool().call(
                _context(manager, umo, {"timezone": "Bad/Zone"})
            )
        )

        expected = datetime(2026, 11, 21, 13, 1, tzinfo=timezone.utc).astimezone()
        assert messages[0]["time"] == expected.strftime("%Y-%m-%d %H:%M")
        assert metadata["time_notice"].startswith("Times are in local time (UTC")
    finally:
        await db.engine.dispose()


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="POSIX TZ switching only")
@pytest.mark.asyncio
async def test_notice_offset_follows_configured_zone_not_host(tmp_path, monkeypatch):
    """With the host on UTC, the notice must still report the configured offset."""
    db = SQLiteDatabase(str(tmp_path / "host-utc.db"))
    manager = PlatformMessageHistoryManager(db)
    umo = "test:GroupMessage:group-host-utc"

    old_tz = os.environ.get("TZ")
    try:
        await _seed(db, manager, umo, datetime(2026, 11, 21, 13, 1))
        monkeypatch.setenv("TZ", "UTC")
        time.tzset()

        messages, metadata = _parse(
            await GetGroupMessageHistoryTool().call(
                _context(manager, umo, {"timezone": "Asia/Shanghai"})
            )
        )

        assert messages[0]["time"] == "2026-11-21 21:01"
        assert metadata["time_notice"] == "Times are in Asia/Shanghai (UTC+08:00)."
    finally:
        if old_tz is None:
            monkeypatch.delenv("TZ", raising=False)
        else:
            monkeypatch.setenv("TZ", old_tz)
        time.tzset()
        await db.engine.dispose()
