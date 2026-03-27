"""Tests for conversation persona inheritance behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.builtin_stars.builtin_commands.commands.conversation import (
    ConversationCommands,
)
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.persona_utils import PERSONA_NONE_MARKER


@pytest.mark.asyncio
async def test_new_conversation_inherits_current_persona_when_not_provided():
    db = MagicMock()
    db.get_conversation_by_id = AsyncMock(
        return_value=SimpleNamespace(persona_id="psychologist")
    )
    db.create_conversation = AsyncMock(
        return_value=SimpleNamespace(conversation_id="new-cid")
    )

    manager = ConversationManager(db)
    manager.session_conversations["test:private:u1"] = "old-cid"

    with patch(
        "astrbot.core.conversation_mgr.sp.session_put",
        new=AsyncMock(return_value=None),
    ):
        await manager.new_conversation("test:private:u1", platform_id="test")

    assert db.create_conversation.await_args.kwargs["persona_id"] == "psychologist"


@pytest.mark.asyncio
async def test_new_conversation_does_not_inherit_persona_none_marker():
    db = MagicMock()
    db.get_conversation_by_id = AsyncMock(
        return_value=SimpleNamespace(persona_id=PERSONA_NONE_MARKER)
    )
    db.create_conversation = AsyncMock(
        return_value=SimpleNamespace(conversation_id="new-cid")
    )

    manager = ConversationManager(db)
    manager.session_conversations["test:private:u1"] = "old-cid"

    with patch(
        "astrbot.core.conversation_mgr.sp.session_put",
        new=AsyncMock(return_value=None),
    ):
        await manager.new_conversation("test:private:u1", platform_id="test")

    assert db.create_conversation.await_args.kwargs["persona_id"] is None


@pytest.mark.asyncio
async def test_new_conversation_keeps_explicit_persona_id():
    db = MagicMock()
    db.get_conversation_by_id = AsyncMock(
        return_value=SimpleNamespace(persona_id="psychologist")
    )
    db.create_conversation = AsyncMock(
        return_value=SimpleNamespace(conversation_id="new-cid")
    )

    manager = ConversationManager(db)
    manager.session_conversations["test:private:u1"] = "old-cid"

    with patch(
        "astrbot.core.conversation_mgr.sp.session_put",
        new=AsyncMock(return_value=None),
    ):
        await manager.new_conversation(
            "test:private:u1",
            platform_id="test",
            persona_id="teacher",
        )

    assert db.create_conversation.await_args.kwargs["persona_id"] == "teacher"


@pytest.mark.asyncio
async def test_get_current_persona_id_returns_none_for_none_marker():
    context = MagicMock()
    context.conversation_manager.get_curr_conversation_id = AsyncMock(
        return_value="old-cid"
    )
    context.conversation_manager.get_conversation = AsyncMock(
        return_value=MagicMock(persona_id=PERSONA_NONE_MARKER)
    )

    command = ConversationCommands(context)

    result = await command._get_current_persona_id("test:private:u1")

    assert result is None
