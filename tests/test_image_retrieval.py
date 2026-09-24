"""Controlled rereads preserve grants, assets, and current provider boundaries."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from PIL import Image
from sqlmodel import select

from astrbot.core import image_asset_store as storage
from astrbot.core import image_context as images
from astrbot.core.agent.message import ImageRefPart, Message, TextPart
from astrbot.core.db.po import ConversationImageRef, ImageAsset
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.image_request_budget import ImageRequestBudget
from astrbot.core.tools.image_tools import ImageCatalogTool, ReadImageTool


@pytest_asyncio.fixture
async def gallery(tmp_path, monkeypatch):
    monkeypatch.setattr(
        storage, "get_astrbot_data_path", lambda: str(tmp_path / "data")
    )
    monkeypatch.setattr(images, "get_astrbot_temp_path", lambda: str(tmp_path / "temp"))
    db = SQLiteDatabase(str(tmp_path / "test.db"))
    await db.initialize()
    db.inited = True
    await db.create_conversation("owner", "test", cid="conversation")
    source = tmp_path / "source.png"
    Image.new("RGB", (80, 40), "orange").save(source)
    files = []
    event = SimpleNamespace(track_temporary_local_file=files.append)
    original = images.ImageTurnContext(db, "conversation", "cp1")
    part = await original.capture(
        str(source), source_message_id="reply-id", max_size=64, event=event
    )
    history = [
        {"role": "user", "content": [part.model_dump()]},
        {"role": "assistant", "content": "seen"},
        {"role": "_checkpoint", "content": {"id": "cp1"}},
    ]
    await db.update_conversation(
        "conversation", content=history, image_refs=list(original.references.values())
    )
    source.unlink()
    turn = images.ImageTurnContext(db, "conversation", "cp2")
    provider = SimpleNamespace(provider_config={"modalities": ["image", "tool_use"]})
    turn.configure(
        user_id="owner",
        platform_id="test",
        event=event,
        max_size=64,
        provider=provider,
        budget=ImageRequestBudget(),
    )
    yield SimpleNamespace(
        db=db,
        turn=turn,
        original=original,
        part=part,
        history=history,
        files=files,
        event=event,
    )
    await db.engine.dispose()


@pytest.mark.asyncio
async def test_reread_original_survives_cache_without_new_asset_or_reference(gallery):
    before = gallery.part.model_dump()
    result = await gallery.turn.read_existing(gallery.part.occurrence_id)
    assert "queued" in result
    assert Path(gallery.turn.pending_visuals[gallery.part.occurrence_id]).exists()
    assert gallery.turn.references == {}
    assert gallery.part.model_dump() == before
    async with gallery.db.get_db() as session:
        assert len((await session.execute(select(ImageAsset))).scalars().all()) == 1
        assert (
            len((await session.execute(select(ConversationImageRef))).scalars().all())
            == 1
        )


@pytest.mark.asyncio
async def test_cached_preview_does_not_bypass_deleted_grant(gallery):
    await gallery.turn.open_preview(gallery.part.occurrence_id)
    await gallery.db.delete_conversation("conversation")
    with pytest.raises(PermissionError):
        await gallery.turn.open_preview(gallery.part.occurrence_id)


@pytest.mark.asyncio
async def test_catalog_has_no_paths_and_exact_reply_filter(gallery):
    result = await gallery.turn.catalog(source_message_id="reply-id")
    assert result["images"][0]["occurrence_id"] == gallery.part.occurrence_id
    assert "asset_id" not in json.dumps(result)
    assert "storage_key" not in json.dumps(result)
    assert not (await gallery.turn.catalog(source_message_id="another"))["images"]


@pytest.mark.asyncio
async def test_project_refreshes_annotation_without_mutation(gallery):
    occurrence = gallery.part.occurrence_id
    assert "updated" in await gallery.turn.update_note(
        occurrence, "It is a bag, not a cat."
    )
    message = Message(role="user", content=[gallery.part])
    projected = await gallery.turn.project_messages([message])
    assert isinstance(message.content[0], ImageRefPart)
    assert isinstance(projected[0].content[0], TextPart)
    assert "User annotation" in projected[0].content[0].text
    assert "bag" in projected[0].content[0].text
    assert (await gallery.turn.get_reference(occurrence)).description == ""


@pytest.mark.asyncio
async def test_projection_and_read_refuse_other_owner(gallery):
    gallery.turn.user_id = "someone-else"
    assert "unavailable" in await gallery.turn.read_existing(gallery.part.occurrence_id)
    assert gallery.turn.budget.review_triggers == 0
    projected = await gallery.turn.project_messages(
        [Message(role="user", content=[gallery.part])]
    )
    assert "unavailable" in projected[0].content[0].text


@pytest.mark.asyncio
async def test_repeated_reviews_remain_available_and_counted(gallery):
    occurrence = gallery.part.occurrence_id
    for _ in range(20):
        assert "queued" in await gallery.turn.read_existing(occurrence)
    assert gallery.turn.budget.review_triggers == 20
    assert len(gallery.turn.pending_visuals) == 1


@pytest.mark.asyncio
async def test_nonvisual_directed_answer_does_not_queue_image(gallery, monkeypatch):
    from astrbot.core import image_description

    caption = AsyncMock(return_value="The label says OPEN.")
    monkeypatch.setattr(image_description, "describe_images", caption)
    gallery.turn.caption_provider = object()
    gallery.turn.provider = SimpleNamespace(
        provider_config={"modalities": ["text", "tool_use"]}
    )
    answer = await gallery.turn.read_existing(
        gallery.part.occurrence_id, question="Read the label"
    )
    assert answer == "The label says OPEN."
    assert not gallery.turn.pending_visuals
    assert caption.call_args.kwargs["question"] == "Read the label"
    assert not caption.call_args.kwargs["refresh"]


@pytest.mark.asyncio
async def test_explicit_refresh_uses_structured_caption(gallery, monkeypatch):
    from astrbot.core import image_description

    caption = AsyncMock(return_value=None)
    monkeypatch.setattr(image_description, "describe_images", caption)
    gallery.turn.caption_provider = object()
    await gallery.turn.read_existing(
        gallery.part.occurrence_id, refresh_description=True
    )
    assert caption.call_args.kwargs["refresh"] is True
    assert gallery.part.occurrence_id in gallery.turn.pending_visuals


@pytest.mark.asyncio
async def test_previous_turn_requires_one_authorized_user_image(gallery):
    assert (
        await gallery.turn.previous_input(gallery.history) == gallery.part.occurrence_id
    )
    history = gallery.history + [
        {"role": "user", "content": "new text"},
        {"role": "_checkpoint", "content": {"id": "cp2"}},
    ]
    assert await gallery.turn.previous_input(history) is None


@pytest.mark.asyncio
async def test_tools_accept_only_scoped_occurrence_and_bounded_arguments(gallery):
    wrapper = SimpleNamespace(context=SimpleNamespace(image_context=gallery.turn))
    result = await ImageCatalogTool().call(wrapper, query="x" * 257)
    assert "256" in result
    result = await ReadImageTool().call(
        wrapper, occurrence_id="not-authorized", owner="owner"
    )
    assert "unavailable" in result


@pytest.mark.asyncio
async def test_collect_known_reply_does_not_download_or_capture(gallery, monkeypatch):
    from astrbot.core import astr_main_agent as main
    from astrbot.core.db.po import Conversation
    from astrbot.core.message.components import Image as ImageComponent
    from astrbot.core.message.components import Reply

    conversation = Conversation(
        cid="conversation",
        user_id="owner",
        platform_id="test",
        history=json.dumps(gallery.history),
    )
    monkeypatch.setattr(main, "_get_session_conv", AsyncMock(return_value=conversation))
    extras = {}
    event = SimpleNamespace(
        message_str="Inspect this",
        message_obj=SimpleNamespace(
            message_id="new",
            message=[
                Reply(
                    id="reply-id",
                    chain=[ImageComponent.fromFileSystem("/expired/image.png")],
                )
            ],
        ),
        get_extra=extras.get,
        set_extra=extras.__setitem__,
        track_temporary_local_file=lambda path: None,
        untrack_temporary_local_file=lambda path: None,
    )
    request, _ = await main.collect_initial_request(
        event,
        SimpleNamespace(conversation_manager=SimpleNamespace(db=gallery.db)),
        main.MainAgentBuildConfig(
            tool_call_timeout=60, provider_settings={"image_context_enabled": True}
        ),
    )
    assert not request.image_urls
    assert (
        extras["image_existing_inputs"][0][0].occurrence_id
        == gallery.part.occurrence_id
    )
    assert extras["image_existing_inputs"][0][1] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("forged", [False, True])
async def test_collect_regeneration_accepts_only_internal_marker(
    gallery, monkeypatch, forged
):
    from astrbot.core import astr_main_agent as main
    from astrbot.core.db.po import Conversation

    await gallery.db.update_conversation(
        "conversation",
        content=[],
        expected_history=gallery.history,
        image_checkpoint_replacement=("cp1", "cp2", [gallery.part.occurrence_id]),
    )
    conversation = Conversation(
        cid="conversation", user_id="owner", platform_id="test", history="[]"
    )
    monkeypatch.setattr(main, "_get_session_conv", AsyncMock(return_value=conversation))
    marker = images.ImageRegeneration(
        "conversation", "cp2", (gallery.part.occurrence_id,)
    )
    extras = {
        "llm_checkpoint_id": "cp2",
        "image_regeneration": marker.__dict__ if forged else marker,
    }
    event = SimpleNamespace(
        message_str="Regenerate",
        message_obj=SimpleNamespace(message_id="new", message=[]),
        get_extra=extras.get,
        set_extra=extras.__setitem__,
        track_temporary_local_file=lambda path: None,
        untrack_temporary_local_file=lambda path: None,
    )
    await main.collect_initial_request(
        event,
        SimpleNamespace(conversation_manager=SimpleNamespace(db=gallery.db)),
        main.MainAgentBuildConfig(
            tool_call_timeout=60, provider_settings={"image_context_enabled": True}
        ),
    )
    if forged:
        assert extras["image_existing_inputs"] == []
    else:
        assert extras["image_existing_inputs"][0][0].checkpoint_id == "cp2"
        assert extras["image_existing_inputs"][0][1] is True
        assert Path(
            await gallery.turn.open_preview(gallery.part.occurrence_id)
        ).exists()


@pytest.mark.asyncio
async def test_provider_switch_rebinds_implicit_caption_but_keeps_explicit(gallery):
    fallback = SimpleNamespace(provider_config={"modalities": ["image"]})
    await gallery.turn.prepare_step(fallback, "fallback-model")
    assert gallery.turn.caption_provider is fallback
    assert gallery.turn.caption_model == "fallback-model"
    gallery.turn.caption_explicit = True
    gallery.turn.caption_provider = None
    await gallery.turn.prepare_step(fallback, "other-model")
    assert gallery.turn.caption_provider is None


@pytest.mark.asyncio
async def test_service_regeneration_rebinds_then_skips_expired_display_image(gallery):
    from astrbot.core.conversation_mgr import ConversationManager
    from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
    from astrbot.dashboard.services.chat_service import ChatService

    await gallery.db.create_platform_session("user", session_id="session")
    manager = PlatformMessageHistoryManager(gallery.db)
    user = await manager.insert(
        "webchat",
        "session",
        {
            "type": "user",
            "message": [
                {"type": "image", "path": "/expired/cache.png"},
                {"type": "plain", "text": "describe"},
            ],
        },
        llm_checkpoint_id="cp1",
    )
    bot = await manager.insert(
        "webchat",
        "session",
        {"type": "bot", "message": "seen"},
        llm_checkpoint_id="cp1",
    )
    service = object.__new__(ChatService)
    service.db = gallery.db
    service.conv_mgr = ConversationManager(gallery.db)
    service.core_lifecycle = SimpleNamespace(
        astrbot_config_mgr=SimpleNamespace(
            get_conf=lambda umo: {"provider_settings": {"image_context_enabled": True}}
        )
    )
    service.platform_history_mgr = manager
    service.load_current_conversation_history = AsyncMock(
        return_value=("conversation", gallery.history)
    )
    service.get_sorted_platform_history = AsyncMock(return_value=[user, bot])
    service.delete_threads_by_ids = AsyncMock()
    payload = await service.prepare_regenerate_message_payload(
        "user", {"session_id": "session", "message_id": bot.id}
    )
    marker = payload["_image_regeneration"]
    assert isinstance(marker, images.ImageRegeneration)
    rows = await gallery.db.get_conversation_images(
        "conversation", list(marker.occurrence_ids), user_id="owner", platform_id="test"
    )
    assert rows[0].checkpoint_id == marker.checkpoint_id

    class StopAfterParts(Exception):
        pass

    service.build_user_message_parts = AsyncMock(side_effect=StopAfterParts)
    with pytest.raises(StopAfterParts):
        await service.build_chat_stream("user", payload)
    parts = service.build_user_message_parts.call_args.args[0]
    assert parts == [{"type": "plain", "text": "describe"}]
    payload["_image_regeneration"] = marker.__dict__
    with pytest.raises(StopAfterParts):
        await service.build_chat_stream("user", payload)
    assert service.build_user_message_parts.call_args.args[0][0]["type"] == "image"


@pytest.mark.asyncio
async def test_hook_deleting_explicit_retrieval_marker_removes_its_visual(gallery):
    from astrbot.core.provider.entities import ProviderRequest
    from astrbot.core.utils.image_input import prepare_request_images

    occurrence = gallery.part.occurrence_id
    await gallery.turn.read_existing(occurrence)
    marker = TextPart(text="Explicit image review").mark_as_temp()
    gallery.turn.part_visual_keys[id(marker)] = occurrence
    request = ProviderRequest(image_context=gallery.turn, extra_user_content_parts=[])
    await prepare_request_images(request, gallery.event, max_size=64, prepared={})
    assert not gallery.turn.pending_visuals
