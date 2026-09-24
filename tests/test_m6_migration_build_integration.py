"""Exercise legacy image migration through the normal main-agent build path."""

import base64
import json
import sqlite3
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import event
from sqlmodel import select

from astrbot.core import astr_main_agent as main
from astrbot.core import image_asset_store
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db.po import ConversationImageRef, ImageAsset
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.message.components import Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.provider.provider import Provider


def image_data_uri() -> str:
    """Create a small deterministic PNG as a legacy inline image."""
    image = Image.new("RGB", (12, 8), "purple")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def legacy_image(url: str) -> dict:
    """Wrap a URL in the legacy OpenAI image part shape."""
    return {"type": "image_url", "image_url": {"url": url}}


@pytest_asyncio.fixture
async def build_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_root = tmp_path / "data"
    temp_root = data_root / "temp"
    temp_root.mkdir(parents=True)
    monkeypatch.setattr(
        image_asset_store, "get_astrbot_data_path", lambda: str(data_root)
    )
    monkeypatch.setattr(
        "astrbot.core.image_history_migration.get_astrbot_temp_path",
        lambda: str(temp_root),
    )

    db = SQLiteDatabase(str(tmp_path / "build-migration.db"))
    await db.initialize()
    db.inited = True

    message = AstrBotMessage()
    message.message = [Plain(text="Please refer to the earlier picture.")]
    message.message_str = "Please refer to the earlier picture."
    message.type = MessageType.FRIEND_MESSAGE
    message.sender = MessageMember(user_id="user", nickname="User")
    message.self_id = "bot"
    event = AstrMessageEvent(
        message.message_str,
        message,
        PlatformMetadata(name="test", id="platform", description="test"),
        "session",
    )
    event.is_at_or_wake_command = True
    event.send = AsyncMock()
    event.send_typing = AsyncMock()
    event.stop_typing = AsyncMock()
    umo = event.unified_msg_origin
    platform_id = event.get_platform_id()
    cid = "legacy-conversation"
    await db.create_conversation(umo, platform_id, cid=cid)

    context = MagicMock(spec=main.Context)
    context.conversation_manager = SimpleNamespace(db=db)
    context.get_config.return_value = {"provider_ltm_settings": {}}
    context.subagent_orchestrator = None

    provider = MagicMock(spec=Provider)
    provider.provider_config = {
        "id": "vision-chat",
        "modalities": ["text", "image", "tool_use"],
        "max_context_tokens": 32_000,
    }
    provider.text_chat = AsyncMock()
    provider.text_chat_stream = AsyncMock()
    provider.completion = AsyncMock()

    try:
        yield db, data_root, event, context, provider, cid, umo, platform_id
    finally:
        await db.engine.dispose()


async def run_build(event, context, provider, conversation, *, enabled: bool | None):
    """Build a main agent while replacing unrelated model and plugin work."""
    req = ProviderRequest(
        prompt="Please refer to the earlier picture.",
        contexts=json.loads(conversation.history),
        conversation=conversation,
    )
    config = main.MainAgentBuildConfig(
        tool_call_timeout=60,
        provider_settings=(
            {"image_context_enabled": enabled}
            if enabled is not None
            else {"unrelated_setting": True}
        ),
        computer_use_runtime="none",
        add_cron_tools=False,
    )
    runner = MagicMock()
    runner.reset = AsyncMock()
    with (
        patch.object(main, "AgentRunner", return_value=runner),
        patch.object(main, "AstrAgentContext"),
        patch.object(main, "_decorate_llm_request", AsyncMock()),
        patch.object(main, "_apply_kb", AsyncMock()),
        patch.object(main, "_apply_web_search_tools", AsyncMock()),
        patch.object(main, "_plugin_tool_fix"),
        patch.object(main, "_apply_web_search_citation_prompt"),
        patch.object(main, "prepare_request_images", AsyncMock()),
    ):
        result = await main.build_main_agent(
            event=event,
            plugin_context=context,
            config=config,
            provider=provider,
            req=req,
        )
    return result, req, runner


async def read_rows(db, model):
    async with db.get_db() as session:
        return list((await session.execute(select(model))).scalars())


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, None])
async def test_first_enabled_chat_build_migrates_history_without_caption_call(
    build_env,
    enabled,
):
    db, data_root, event, context, provider, cid, umo, platform_id = build_env
    history = [
        {"role": "user", "content": [legacy_image(image_data_uri())]},
        {"role": "assistant", "content": "The image showed a purple square."},
    ]
    await db.update_conversation(cid, content=history)
    conversation = await ConversationManager(db).get_conversation(umo, cid)
    assert conversation is not None

    result, req, _runner = await run_build(
        event, context, provider, conversation, enabled=enabled
    )

    assert result is not None
    assert req.image_context is not None
    assert req.contexts[0]["content"][0]["type"] == "image_ref"
    assert "data:image/" not in json.dumps(req.contexts)
    assert req.contexts[0]["content"][0]["description_status"] == "pending"
    stored = await db.get_conversation_by_id(cid)
    assert stored is not None
    assert stored.content == req.contexts
    assets = await read_rows(db, ImageAsset)
    refs = await read_rows(db, ConversationImageRef)
    assert len(assets) == len(refs) == 1
    assert assets[0].source_kind == "legacy_model_input"
    assert (data_root / "image_assets" / assets[0].storage_key).is_file()
    provider.text_chat.assert_not_awaited()
    provider.text_chat_stream.assert_not_awaited()
    provider.completion.assert_not_awaited()
    event.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_preserves_per_message_image_order_across_legacy_turns(build_env):
    db, _data_root, event, context, provider, cid, umo, _platform_id = build_env
    history = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Compare these."},
                legacy_image(image_data_uri()),
                legacy_image(image_data_uri()),
            ],
        },
        {"role": "assistant", "content": "First comparison."},
        {"role": "user", "content": [legacy_image(image_data_uri())]},
        {"role": "assistant", "content": "Second turn."},
        {"role": "user", "content": [legacy_image(image_data_uri())]},
        {"role": "assistant", "content": "Third turn."},
    ]
    await db.update_conversation(cid, content=history)
    conversation = await ConversationManager(db).get_conversation(umo, cid)
    assert conversation is not None

    result, req, _runner = await run_build(
        event, context, provider, conversation, enabled=True
    )

    assert result is not None
    checkpoints = [
        item["content"]["id"]
        for item in req.contexts
        if item.get("role") == "_checkpoint"
    ]
    assert len(checkpoints) == 3
    user_references = [
        [
            part["occurrence_id"]
            for part in item["content"]
            if isinstance(part, dict) and part.get("type") == "image_ref"
        ]
        for item in req.contexts
        if item.get("role") == "user"
    ]
    assert [len(occurrences) for occurrences in user_references] == [2, 1, 1]
    refs = await read_rows(db, ConversationImageRef)
    refs_by_occurrence = {ref.occurrence_id: ref for ref in refs}
    assert [
        (
            refs_by_occurrence[occurrence_id].checkpoint_id,
            refs_by_occurrence[occurrence_id].image_index,
        )
        for occurrences in user_references
        for occurrence_id in occurrences
    ] == [
        (checkpoints[0], 0),
        (checkpoints[0], 1),
        (checkpoints[1], 0),
        (checkpoints[2], 0),
    ]


@pytest.mark.asyncio
async def test_failed_build_migration_keeps_history_and_never_starts_model(build_env):
    db, _data_root, event, context, provider, cid, umo, _platform_id = build_env
    invalid = [
        {"role": "user", "content": [legacy_image("data:image/png;base64,broken!")]}
    ]
    await db.update_conversation(cid, content=invalid)
    conversation = await ConversationManager(db).get_conversation(umo, cid)
    assert conversation is not None
    attempted_history = json.loads(conversation.history)

    result, _req, runner = await run_build(
        event, context, provider, conversation, enabled=True
    )

    assert result is None
    stored = await db.get_conversation_by_id(cid)
    assert stored is not None
    assert stored.content == attempted_history
    assert await read_rows(db, ImageAsset) == []
    assert await read_rows(db, ConversationImageRef) == []
    provider.text_chat.assert_not_awaited()
    provider.text_chat_stream.assert_not_awaited()
    provider.completion.assert_not_awaited()
    event.send.assert_not_awaited()
    assert "原对话保持不变" in event.get_extra(main.LLM_ERROR_MESSAGE_EXTRA_KEY)
    assert "没有发送给模型" in event.get_extra(main.LLM_ERROR_MESSAGE_EXTRA_KEY)
    runner.reset.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_build_does_not_migrate_legacy_history(build_env):
    db, _data_root, event, context, provider, cid, umo, _platform_id = build_env
    history = [{"role": "user", "content": [legacy_image(image_data_uri())]}]
    await db.update_conversation(cid, content=history)
    conversation = await ConversationManager(db).get_conversation(umo, cid)
    assert conversation is not None

    result, req, _runner = await run_build(
        event, context, provider, conversation, enabled=False
    )

    assert result is not None
    assert req.image_context is None
    assert req.contexts == history
    stored = await db.get_conversation_by_id(cid)
    assert stored is not None
    assert stored.content == history
    assert await read_rows(db, ImageAsset) == []
    assert event.send.await_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("multi_platform_indexed", [False, True])
async def test_list_rechecks_original_owner_filter_after_second_connection_update(
    tmp_path: Path, multi_platform_indexed: bool
):
    db_path = tmp_path / "list-owner-race.db"
    db = SQLiteDatabase(str(db_path))
    await db.initialize()
    db.inited = True
    await db.create_conversation("owner-a:FriendMessage:user", "platform", cid="shared")
    await db.update_conversation(
        "shared", content=[{"role": "user", "content": "owner-a body"}]
    )
    statements = []

    def record_index_query(
        _connection, _cursor, statement, _parameters, _context, _many
    ):
        statements.append(statement)

    event.listen(db.engine.sync_engine, "before_cursor_execute", record_index_query)
    original_get_db = db.get_db
    size_queries_seen = 0

    @asynccontextmanager
    async def get_db_with_interleaved_owner_update():
        nonlocal size_queries_seen
        async with original_get_db() as session:

            class SessionProxy:
                def __getattr__(self, name):
                    return getattr(session, name)

                async def execute(self, statement, *args, **kwargs):
                    nonlocal size_queries_seen
                    result = await session.execute(statement, *args, **kwargs)
                    if (
                        "length(CAST(conversations.content AS BLOB))"
                        not in str(statement)
                        or size_queries_seen
                    ):
                        return result
                    size_rows = result.all()
                    size_queries_seen += 1
                    with sqlite3.connect(db_path) as other_connection:
                        other_connection.execute(
                            "UPDATE conversations SET user_id = ?, content = ? "
                            "WHERE conversation_id = ?",
                            (
                                "owner-b:FriendMessage:user",
                                '[{"role":"user","content":"owner-b secret"}]',
                                "shared",
                            ),
                        )
                    return SimpleNamespace(all=lambda: size_rows)

            yield SessionProxy()

    db.get_db = get_db_with_interleaved_owner_update
    query_options = {}
    if multi_platform_indexed:
        query_options.update(
            platform_ids=["platform", "other"],
            platforms=["platform", "other"],
        )
    fallback_error_seen = False
    try:
        try:
            rows, _total = await db.get_filtered_conversations(
                page=1,
                page_size=10,
                include_history=True,
                umo_query="owner-a",
                **query_options,
            )
        except ValueError as error:
            assert "changed" in str(error)
            fallback_error_seen = True
            rows = []
    finally:
        event.remove(db.engine.sync_engine, "before_cursor_execute", record_index_query)
        await db.engine.dispose()

    assert size_queries_seen == 1
    assert (
        any(
            "INDEXED BY ix_conversations_created_at_inner_id" in statement
            for statement in statements
        )
        is multi_platform_indexed
    )
    if multi_platform_indexed:
        assert fallback_error_seen
    assert all(row.user_id == "owner-a:FriendMessage:user" for row in rows)
    assert all("owner-b secret" not in str(row.content) for row in rows)


@pytest.mark.asyncio
async def test_migration_cas_does_not_overwrite_another_sqlite_connection(build_env):
    db, _data_root, _event, _context, _provider, cid, _umo, platform_id = build_env
    original = [{"role": "user", "content": [legacy_image(image_data_uri())]}]
    concurrent = [{"role": "user", "content": "written by another connection"}]
    await db.update_conversation(cid, content=original)
    original_update = db.update_conversation

    async def concurrent_write_before_cas(*args, **kwargs):
        with sqlite3.connect(db.db_path) as other_connection:
            other_connection.execute(
                "UPDATE conversations SET content = ? WHERE conversation_id = ?",
                (json.dumps(concurrent), cid),
            )
        return await original_update(*args, **kwargs)

    db.update_conversation = concurrent_write_before_cas
    from astrbot.core.image_history_migration import (
        ImageHistoryMigrationError,
        migrate_legacy_image_history,
    )

    with pytest.raises(ImageHistoryMigrationError) as error:
        await migrate_legacy_image_history(
            db,
            cid,
            original,
            user_id=build_env[6],
            platform_id=platform_id,
        )

    assert error.value.reason == "history_changed"
    stored = await db.get_conversation_by_id(cid)
    assert stored is not None
    assert stored.content == concurrent
