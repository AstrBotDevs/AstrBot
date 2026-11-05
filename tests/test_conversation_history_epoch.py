import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.builtin_stars.builtin_commands.commands.conversation import (
    ConversationCommands,
)
from astrbot.core.agent.message import Message
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    InternalAgentSubStage,
)
from astrbot.core.provider.entities import LLMResponse, ProviderRequest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,user_aborted", [("assistant", False), ("assistant", True), ("err", False)]
)
async def test_reset_rejects_old_history_but_accepts_next_request(
    tmp_path: Path, role: str, user_aborted: bool
):
    db = SQLiteDatabase(str(tmp_path / "history.db"))
    reset_db = SQLiteDatabase(str(tmp_path / "history.db"))
    try:
        manager = ConversationManager(db)
        reset_manager = ConversationManager(reset_db)
        umo = "test:FriendMessage:history-epoch"
        conv = await db.create_conversation(
            umo, "test", content=[{"role": "user", "content": "old"}]
        )
        cid = conv.conversation_id
        manager.session_conversations[umo] = cid
        reset_manager.session_conversations[umo] = cid
        await manager.update_conversation(umo, cid, token_usage=123)
        request = ProviderRequest(conversation=await manager.get_conversation(umo, cid))
        stage = InternalAgentSubStage()
        stage.conv_manager = manager
        extras = {"llm_checkpoint_id": "checkpoint"}
        event = SimpleNamespace(
            unified_msg_origin=umo,
            get_extra=extras.get,
            set_extra=extras.__setitem__,
            set_result=lambda result: None,
        )
        commands = ConversationCommands(
            SimpleNamespace(
                conversation_manager=reset_manager,
                get_config=lambda **kwargs: {"agent_runner": {"runner_type": "local"}},
            )
        )

        await commands.reset(event)
        await stage._save_to_history(
            event,
            request,
            LLMResponse(role=role, completion_text="late output"),
            [
                Message(role="user", content="old"),
                Message(role="assistant", content="late output"),
            ],
            runner_stats=None,
            user_aborted=user_aborted,
        )

        reset = await manager.get_conversation(umo, cid)
        assert json.loads(reset.history) == []
        assert reset.token_usage == 123

        request.conversation = reset
        await stage._save_to_history(
            event,
            request,
            LLMResponse(role="assistant", completion_text="fresh output"),
            [
                Message(role="user", content="fresh request"),
                Message(role="assistant", content="fresh output"),
            ],
            runner_stats=None,
        )
        saved = await manager.get_conversation(umo, cid)
        assert "fresh output" in saved.history
        assert "old" not in saved.history
    finally:
        await db.engine.dispose()
        await reset_db.engine.dispose()


@pytest.mark.asyncio
async def test_old_save_before_reset_and_repeated_resets(tmp_path: Path):
    db = SQLiteDatabase(str(tmp_path / "history.db"))
    try:
        conv = await db.create_conversation(
            "test:FriendMessage:epoch", "test", content=[]
        )
        cid = conv.conversation_id
        await db.update_conversation(
            cid,
            content=[{"role": "user", "content": "before reset"}],
            expected_history_epoch=0,
        )
        await db.update_conversation(cid, content=[])
        await db.update_conversation(cid, content=[])
        result = await db.update_conversation(
            cid,
            content=[{"role": "assistant", "content": "stale"}],
            token_usage=999,
            expected_history_epoch=1,
        )
        assert result is None
        saved = await db.get_conversation_by_id(cid)
        assert saved.content == []
        assert saved.token_usage == 0
        assert saved.history_epoch == 2
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_legacy_conversation_migrates_without_changing_history(tmp_path: Path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE conversations (inner_conversation_id INTEGER PRIMARY KEY, conversation_id TEXT NOT NULL UNIQUE, platform_id TEXT NOT NULL, user_id TEXT NOT NULL, content JSON, title TEXT, persona_id TEXT, token_usage INTEGER NOT NULL DEFAULT 0, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
        )
        connection.execute(
            "INSERT INTO conversations VALUES (1, 'legacy', 'test', 'test:FriendMessage:legacy', ?, NULL, NULL, 123, '2026-01-01 00:00:00', '2026-01-01 00:00:00')",
            (json.dumps([{"role": "user", "content": "keep"}]),),
        )
    db = SQLiteDatabase(str(path))
    try:
        await db.initialize()
        await db.initialize()
        saved = await db.get_conversation_by_id("legacy")
        assert saved.history_epoch == 0
        assert saved.content == [{"role": "user", "content": "keep"}]
        assert saved.token_usage == 123
    finally:
        await db.engine.dispose()
