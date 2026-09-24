"""Managed user inputs preserve originals without persisting model payloads."""

import copy
import errno
import hashlib
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
from astrbot.core.agent.message import ImageRefPart, ImageURLPart, Message, TextPart
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db.po import (
    Conversation,
    ConversationImageRef,
    ConversationV2,
    ImageAsset,
)
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    InternalAgentSubStage,
)
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.utils.image_input import prepare_request_images


@pytest_asyncio.fixture
async def env(tmp_path, monkeypatch):
    monkeypatch.setattr(
        storage, "get_astrbot_data_path", lambda: str(tmp_path / "data")
    )
    monkeypatch.setattr(images, "get_astrbot_temp_path", lambda: str(tmp_path / "temp"))
    db = SQLiteDatabase(str(tmp_path / "db.sqlite"))
    await db.initialize()
    db.inited = True
    await db.create_conversation("owner", "test", cid="conversation")
    source = tmp_path / "original.png"
    Image.new("RGB", (200, 100), "orange").save(source)
    files = []
    event = SimpleNamespace(
        unified_msg_origin="owner",
        get_extra=lambda key: "checkpoint" if key == "llm_checkpoint_id" else None,
        track_temporary_local_file=files.append,
        message_obj=SimpleNamespace(message_id="source-message"),
    )
    context = images.ImageTurnContext(db, "conversation", "checkpoint")
    request = ProviderRequest(
        prompt="Describe this",
        image_urls=[str(source)],
        image_context=context,
        image_sources={str(source): ("source-message", 0)},
        conversation=Conversation(
            cid="conversation", user_id="owner", platform_id="test", history="[]"
        ),
    )
    yield SimpleNamespace(
        db=db, source=source, event=event, context=context, request=request, files=files
    )
    await db.engine.dispose()


async def all_rows(db, model):
    async with db.get_db() as session:
        return list((await session.execute(select(model))).scalars())


@pytest.mark.asyncio
async def test_three_preparation_passes_capture_once_and_keep_original_bytes(env):
    prepared = {}
    for _ in range(3):
        await prepare_request_images(
            env.request, env.event, max_size=64, prepared=prepared
        )
    assert not env.request.image_urls
    assert len(env.context.pending_visuals) == len(env.context.references) == 1
    assets = await all_rows(env.db, ImageAsset)
    assert len(assets) == 1
    original = env.source.read_bytes()
    assert assets[0].sha256 == hashlib.sha256(original).hexdigest()
    stored = (
        Path(storage.get_astrbot_data_path()) / "image_assets" / assets[0].storage_key
    )
    assert stored.read_bytes() == original
    preview = next(iter(env.context.pending_visuals.values()))
    with Image.open(preview) as image:
        assert max(image.size) == 64
    payload = await env.request.assemble_context()
    assert not any(part["type"] == "image_url" for part in payload["content"])
    assert "base64" not in json.dumps(payload)
    assert (
        next(iter(env.context.references.values())).source_message_id
        == "source-message"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "final_response", [None, LLMResponse(role="assistant", completion_text="answer")]
)
async def test_both_history_save_branches_commit_trusted_references(
    env, final_response
):
    await prepare_request_images(env.request, env.event, max_size=64, prepared={})
    messages = [Message.model_validate(await env.request.assemble_context())]
    if final_response:
        messages.append(Message(role="assistant", content="answer"))
    stage = InternalAgentSubStage()
    stage.conv_manager = ConversationManager(env.db)
    await stage._save_to_history(env.event, env.request, final_response, messages, None)
    refs = await all_rows(env.db, ConversationImageRef)
    assert len(refs) == 1 and refs[0].checkpoint_id == "checkpoint"
    history = (await all_rows(env.db, ConversationV2))[0].content
    assert history[-1] == {"role": "_checkpoint", "content": {"id": "checkpoint"}}
    assert "image_ref" in json.dumps(history) and "image_url" not in json.dumps(history)


@pytest.mark.asyncio
async def test_hook_deletion_removes_pending_visual_and_does_not_authorize(env):
    await prepare_request_images(env.request, env.event, max_size=64, prepared={})
    env.context.project_for_hook(env.request)
    assert all(
        isinstance(part, TextPart) for part in env.request.extra_user_content_parts
    )
    env.request.extra_user_content_parts.clear()
    env.context.restore_after_hook(env.request)
    await prepare_request_images(env.request, env.event, max_size=64, prepared={})
    assert not env.context.pending_visuals
    stage = InternalAgentSubStage()
    stage.conv_manager = ConversationManager(env.db)
    await stage._save_to_history(
        env.event,
        env.request,
        LLMResponse(role="assistant", completion_text="answer"),
        [
            Message(role="user", content="text"),
            Message(role="assistant", content="answer"),
        ],
        None,
    )
    assert not await all_rows(env.db, ConversationImageRef)
    assert (await all_rows(env.db, ImageAsset))[0].state == "available"


@pytest.mark.asyncio
async def test_hook_cannot_restore_authorization_by_copying_text(env):
    await prepare_request_images(env.request, env.event, max_size=64, prepared={})
    env.context.project_for_hook(env.request)
    env.request.extra_user_content_parts = [
        copy.deepcopy(part) for part in env.request.extra_user_content_parts
    ]
    env.context.restore_after_hook(env.request)
    await prepare_request_images(env.request, env.event, max_size=64, prepared={})
    assert not env.context.pending_visuals
    assert not any(
        isinstance(part, ImageRefPart) for part in env.request.extra_user_content_parts
    )


@pytest.mark.asyncio
async def test_unchanged_hook_projection_preserves_markers_and_new_input(env, tmp_path):
    prepared = {}
    await prepare_request_images(env.request, env.event, max_size=64, prepared=prepared)
    original = env.request.extra_user_content_parts[0]
    env.context.project_for_hook(env.request)
    extra = tmp_path / "plugin.png"
    Image.new("RGB", (8, 8), "blue").save(extra)
    env.request.extra_user_content_parts.append(
        ImageURLPart(image_url=ImageURLPart.ImageURL(url=str(extra)))
    )
    env.context.restore_after_hook(env.request)
    assert env.request.extra_user_content_parts[0] is original
    await prepare_request_images(env.request, env.event, max_size=64, prepared=prepared)
    assert len(env.context.pending_visuals) == len(env.context.references) == 2


@pytest.mark.asyncio
async def test_hook_conversation_replacement_is_rejected(env):
    await prepare_request_images(env.request, env.event, max_size=64, prepared={})
    env.context.project_for_hook(env.request)
    env.request.conversation = Conversation(
        cid="other", user_id="owner", platform_id="test"
    )
    with pytest.raises(ValueError, match="conversation changed"):
        env.context.restore_after_hook(env.request)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [storage.ImageStorageCapacityError("full"), OSError("disk unavailable")]
)
async def test_storage_failure_uses_valid_transient_preview(env, monkeypatch, failure):
    monkeypatch.setattr(
        storage.ImageAssetStore, "import_file", AsyncMock(side_effect=failure)
    )
    part = await env.context.capture(str(env.source), max_size=64, event=env.event)
    assert isinstance(part, TextPart) and part._no_save
    assert len(env.context.pending_visuals) == 1 and not env.context.references
    assert "current request" in env.context.notices[0]
    assert not await all_rows(env.db, ImageAsset)


@pytest.mark.asyncio
async def test_library_full_does_not_allow_corrupt_image_fallback(env, monkeypatch):
    monkeypatch.setattr(
        storage.ImageAssetStore,
        "import_file",
        AsyncMock(side_effect=storage.ImageStorageCapacityError("full")),
    )
    env.source.write_bytes(b"not an image")
    preview = AsyncMock()
    monkeypatch.setattr(images, "prepare_model_image", preview)
    part = await env.context.capture(str(env.source), max_size=64, event=env.event)
    assert isinstance(part, TextPart)
    assert not env.context.pending_visuals
    assert len(env.context.notices) == 1 and "rejected" in env.context.notices[0]
    preview.assert_not_awaited()


@pytest.mark.asyncio
async def test_pixels_rejected_before_model_preview(env, monkeypatch):
    monkeypatch.setattr(images, "MAX_CONTEXT_IMAGE_PIXELS", 100)
    preview = AsyncMock()
    monkeypatch.setattr(images, "prepare_model_image", preview)
    await env.context.capture(str(env.source), max_size=64, event=env.event)
    preview.assert_not_awaited()
    assert not env.context.pending_visuals and not await all_rows(env.db, ImageAsset)


@pytest.mark.asyncio
async def test_temporary_input_has_no_persistent_asset(env):
    part = await env.context.capture(
        str(env.source), temporary=True, max_size=64, event=env.event
    )
    assert part._no_save and not env.context.references
    assert len(env.context.pending_visuals) == 1
    assert not await all_rows(env.db, ImageAsset)


@pytest.mark.asyncio
async def test_tool_repeated_path_captures_fresh_image_after_consumption(env):
    first = await env.context.capture(str(env.source), max_size=64, event=env.event)
    env.context.pending_visuals.clear()
    Image.new("RGB", (200, 100), "blue").save(env.source)
    second = await env.context.capture(str(env.source), max_size=64, event=env.event)
    assert first.occurrence_id != second.occurrence_id
    assert len(env.context.pending_visuals) == 1
    assets = await all_rows(env.db, ImageAsset)
    assert len({asset.sha256 for asset in assets}) == 2


@pytest.mark.asyncio
async def test_temporary_marker_survives_repeated_prepare_and_hook(env):
    env.request.image_urls = []
    env.request.extra_user_content_parts = [
        ImageURLPart(
            image_url=ImageURLPart.ImageURL(url=str(env.source))
        ).mark_as_temp()
    ]
    prepared = {}
    await prepare_request_images(env.request, env.event, max_size=64, prepared=prepared)
    env.context.project_for_hook(env.request)
    env.context.restore_after_hook(env.request)
    for _ in range(2):
        await prepare_request_images(
            env.request, env.event, max_size=64, prepared=prepared
        )
    assert all(part._no_save for part in env.request.extra_user_content_parts)
    assert len(env.context.pending_visuals) == 1
    assert not env.context.references and not await all_rows(env.db, ImageAsset)


@pytest.mark.asyncio
async def test_saved_original_preview_failure_notice_is_accurate(env, monkeypatch):
    monkeypatch.setattr(images, "prepare_model_image", AsyncMock(return_value=None))
    await env.context.capture(str(env.source), max_size=64, event=env.event)
    assert len(await all_rows(env.db, ImageAsset)) == 1
    assert not env.context.references and not env.context.pending_visuals
    assert "original was stored" in env.context.notices[0]


@pytest.mark.asyncio
async def test_source_metadata_is_local_to_each_message(env, tmp_path):
    for index in range(2):
        source = tmp_path / f"reply-{index}.png"
        Image.new("RGB", (8, 8), "blue").save(source)
        env.request.image_urls.append(str(source))
        env.request.image_sources[str(source)] = ("reply-message", index)
    await prepare_request_images(env.request, env.event, max_size=64, prepared={})
    assert [
        (ref.source_message_id, ref.image_index)
        for ref in env.context.references.values()
    ] == [("source-message", 0), ("reply-message", 0), ("reply-message", 1)]


@pytest.mark.asyncio
async def test_collect_records_reply_id_and_each_source_image_order(
    env, tmp_path, monkeypatch
):
    from astrbot.core import astr_main_agent as main
    from astrbot.core.message.components import Image as ImageComponent
    from astrbot.core.message.components import Reply

    reply_paths = []
    for index in range(2):
        path = tmp_path / f"quoted-{index}.png"
        Image.new("RGB", (8, 8), "blue").save(path)
        reply_paths.append(path)
    extras = {}
    event = SimpleNamespace(
        message_str="look",
        message_obj=SimpleNamespace(
            message_id="current",
            message=[
                ImageComponent.fromFileSystem(str(env.source)),
                Reply(
                    id="quoted-original",
                    chain=[
                        ImageComponent.fromFileSystem(str(path)) for path in reply_paths
                    ],
                ),
            ],
        ),
        get_extra=lambda key: extras.get(key),
        set_extra=lambda key, value: extras.__setitem__(key, value),
        track_temporary_local_file=lambda path: None,
        untrack_temporary_local_file=lambda path: None,
    )
    monkeypatch.setattr(
        main, "_get_session_conv", AsyncMock(return_value=env.request.conversation)
    )
    request, _ = await main.collect_initial_request(
        event,
        SimpleNamespace(conversation_manager=SimpleNamespace(db=env.db)),
        main.MainAgentBuildConfig(
            tool_call_timeout=60, provider_settings={"image_context_enabled": True}
        ),
    )
    assert request.image_sources == {
        str(env.source): ("current", 0),
        str(reply_paths[0]): ("quoted-original", 0),
        str(reply_paths[1]): ("quoted-original", 1),
    }


@pytest.mark.asyncio
async def test_hook_marking_projection_temporary_keeps_visual_without_grant(env):
    await prepare_request_images(env.request, env.event, max_size=64, prepared={})
    env.context.project_for_hook(env.request)
    env.request.extra_user_content_parts[0].mark_as_temp()
    env.context.restore_after_hook(env.request)
    await prepare_request_images(env.request, env.event, max_size=64, prepared={})
    assert len(env.context.pending_visuals) == 1
    assert not isinstance(env.request.extra_user_content_parts[0], ImageRefPart)

    stage = InternalAgentSubStage()
    stage.conv_manager = ConversationManager(env.db)
    await stage._save_to_history(
        env.event,
        env.request,
        LLMResponse(role="assistant", completion_text="answer"),
        [
            Message.model_validate(await env.request.assemble_context()),
            Message(role="assistant", content="answer"),
        ],
        None,
    )
    assert not await all_rows(env.db, ConversationImageRef)


@pytest.mark.asyncio
@pytest.mark.parametrize("number", [errno.ENOMEM, errno.EMFILE, errno.ENFILE])
async def test_resource_exhaustion_does_not_retry_validation_or_preview(
    env, monkeypatch, number
):
    monkeypatch.setattr(
        storage.ImageAssetStore,
        "import_file",
        AsyncMock(side_effect=OSError(number, "resource exhausted")),
    )
    validate = AsyncMock()
    preview = AsyncMock()
    monkeypatch.setattr(images, "run_image_io", validate)
    monkeypatch.setattr(images, "prepare_model_image", preview)
    with pytest.raises(OSError) as raised:
        await env.context.capture(str(env.source), max_size=64, event=env.event)
    assert raised.value.errno == number
    validate.assert_not_awaited()
    preview.assert_not_awaited()
    assert not env.context.notices


@pytest.mark.asyncio
async def test_hook_new_history_image_enters_current_turn(env):
    env.request.image_urls = []
    env.context.project_for_hook(env.request)
    env.request.contexts.append(
        {
            "role": "user",
            "content": [{"type": "image_url", "image_url": {"url": str(env.source)}}],
        }
    )
    env.context.restore_after_hook(env.request)
    await prepare_request_images(env.request, env.event, max_size=64, prepared={})
    assert not any(
        part.get("type") == "image_url"
        for message in env.request.contexts
        if isinstance(message["content"], list)
        for part in message["content"]
    )
    assert len(env.context.references) == 1
    assert next(iter(env.context.references.values())).checkpoint_id == "checkpoint"


@pytest.mark.asyncio
async def test_hook_unchanged_legacy_image_remains_for_migration(env):
    env.request.image_urls = []
    original = {"type": "image_url", "image_url": {"url": str(env.source)}}
    env.request.contexts = [{"role": "user", "content": [original]}]
    env.context.project_for_hook(env.request)
    env.context.restore_after_hook(env.request)
    await prepare_request_images(env.request, env.event, max_size=64, prepared={})
    assert env.request.contexts[0]["content"][0] is original
    assert not env.context.references and not env.context.pending_visuals


@pytest.mark.asyncio
async def test_hook_in_place_legacy_replacement_is_new_temporary_input(env, tmp_path):
    env.request.image_urls = []
    original = {"type": "image_url", "image_url": {"url": str(env.source)}}
    env.request.contexts = [{"role": "user", "content": [original]}]
    env.context.project_for_hook(env.request)
    updated = tmp_path / "changed.png"
    Image.new("RGB", (8, 8), "blue").save(updated)
    original["image_url"]["url"] = str(updated)
    original["_no_save"] = True
    env.context.restore_after_hook(env.request)
    await prepare_request_images(env.request, env.event, max_size=64, prepared={})
    assert env.request.contexts[0]["content"] == "[Image attached to current request]"
    assert len(env.context.pending_visuals) == 1 and not env.context.references
    assert env.request.extra_user_content_parts[0]._no_save


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True])
async def test_hook_message_temporary_flag_never_creates_persistent_grant(
    env, existing
):
    from astrbot.core.agent.message import bind_checkpoint_messages

    env.request.image_urls = []
    message = {
        "role": "user",
        "content": [{"type": "image_url", "image_url": {"url": str(env.source)}}],
    }
    if existing:
        env.request.contexts = [message]
    env.context.project_for_hook(env.request)
    if existing:
        env.request.contexts[0]["_no_save"] = True
    else:
        message["_no_save"] = True
        env.request.contexts.append(message)
    env.context.restore_after_hook(env.request)
    await prepare_request_images(env.request, env.event, max_size=64, prepared={})
    stage = InternalAgentSubStage()
    stage.conv_manager = ConversationManager(env.db)
    messages = bind_checkpoint_messages(env.request.contexts)
    messages.extend(
        [
            Message.model_validate(await env.request.assemble_context()),
            Message(role="assistant", content="answer"),
        ]
    )
    await stage._save_to_history(
        env.event,
        env.request,
        LLMResponse(role="assistant", completion_text="answer"),
        messages,
        None,
    )
    assert not await all_rows(env.db, ConversationImageRef)
    assert not await all_rows(env.db, ImageAsset)
    history = (await all_rows(env.db, ConversationV2))[0].content
    assert "image_url" not in json.dumps(history) and "image_ref" not in json.dumps(
        history
    )
    if not existing:
        assert len(env.context.pending_visuals) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("temporary", [False, True])
async def test_hook_typed_history_image_is_captured_and_leaves_nonempty_message(
    env, temporary
):
    env.request.image_urls = []
    env.context.project_for_hook(env.request)
    part = ImageURLPart(image_url=ImageURLPart.ImageURL(url=str(env.source)))
    if temporary:
        part.mark_as_temp()
    env.request.contexts.append({"role": "user", "content": [part]})
    env.context.restore_after_hook(env.request)
    await prepare_request_images(env.request, env.event, max_size=64, prepared={})
    assert env.request.contexts[0]["content"] == "[Image attached to current request]"
    assert len(env.context.pending_visuals) == 1
    assert len(env.context.references) == (0 if temporary else 1)
    assert env.request.extra_user_content_parts[0]._no_save is temporary


@pytest.mark.asyncio
async def test_hook_unchanged_typed_legacy_image_is_not_migrated(env):
    env.request.image_urls = []
    env.request.contexts = [
        {
            "role": "user",
            "content": [
                ImageURLPart(image_url=ImageURLPart.ImageURL(url=str(env.source)))
            ],
        }
    ]
    env.context.project_for_hook(env.request)
    assert isinstance(env.request.contexts[0]["content"][0], dict)
    env.context.restore_after_hook(env.request)
    await prepare_request_images(env.request, env.event, max_size=64, prepared={})
    assert env.request.contexts[0]["content"][0]["type"] == "image_url"
    assert not env.context.references and not env.context.pending_visuals


@pytest.mark.asyncio
async def test_hook_deepcopied_legacy_inline_is_preserved_only_to_original_count(env):
    env.request.image_urls = []
    legacy = {"type": "image_url", "image_url": {"url": str(env.source)}}
    env.request.contexts = [{"role": "user", "content": [legacy]}]
    env.context.project_for_hook(env.request)
    env.request.contexts = copy.deepcopy(env.request.contexts)
    env.request.contexts[0]["content"].append(copy.deepcopy(legacy))
    env.context.restore_after_hook(env.request)
    await prepare_request_images(env.request, env.event, max_size=64, prepared={})
    assert env.request.contexts[0]["content"] == [legacy]
    assert len(env.context.pending_visuals) == len(env.context.references) == 1


@pytest.mark.asyncio
async def test_collect_empty_settings_uses_global_enabled_byte_limit(env, monkeypatch):
    from astrbot.core import astr_main_agent as main
    from astrbot.core.message.components import Image as ImageComponent

    calls = []
    real_resolver = main.MediaResolver

    def recording_resolver(ref, **kwargs):
        calls.append(kwargs)
        return real_resolver(ref, **kwargs)

    monkeypatch.setattr(main, "MediaResolver", recording_resolver)
    monkeypatch.setattr(
        main, "_get_session_conv", AsyncMock(return_value=env.request.conversation)
    )
    extras = {}
    event = SimpleNamespace(
        unified_msg_origin="owner",
        message_str="look",
        message_obj=SimpleNamespace(
            message_id="current",
            message=[ImageComponent.fromFileSystem(str(env.source))],
        ),
        get_extra=lambda key: extras.get(key),
        set_extra=lambda key, value: extras.__setitem__(key, value),
        track_temporary_local_file=lambda path: None,
        untrack_temporary_local_file=lambda path: None,
    )
    context = SimpleNamespace(
        get_config=lambda **kwargs: {
            "provider_settings": {"image_context_enabled": True}
        }
    )
    await main.collect_initial_request(
        event, context, main.MainAgentBuildConfig(tool_call_timeout=60)
    )
    assert calls == [
        {"media_type": "image", "max_bytes": storage.DEFAULT_MAX_FILE_BYTES}
    ]
