"""Regression contracts for shared media, database, and state policies."""

import asyncio
import io
import json
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.api import message_components as public_components
from astrbot.core.backup.importer import _write_archive_member
from astrbot.core.db.migration.sqlite_v3 import _summarize_conversations
from astrbot.core.db.po import Persona, WebChatThread
from astrbot.core.message import components
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.pipeline.process_stage import follow_up
from astrbot.core.skills.skill_manager import SkillManager


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "component_type",
    [public_components.Image, public_components.Record, public_components.Video],
)
async def test_media_registration_checks_configuration_before_resolving(
    monkeypatch, component_type
) -> None:
    resolver = AsyncMock(return_value="/tmp/media")
    register = AsyncMock(return_value="token")
    monkeypatch.setattr(component_type, "convert_to_file_path", resolver)
    monkeypatch.setattr(
        components, "file_token_service", SimpleNamespace(register_file=register)
    )
    monkeypatch.setattr(components, "astrbot_config", {})
    media = component_type(file="https://example.test/media")

    with pytest.raises(Exception, match="callback_api_base"):
        await media.register_to_file_service()
    resolver.assert_not_awaited()
    register.assert_not_awaited()

    monkeypatch.setattr(
        components, "astrbot_config", {"callback_api_base": "https://callback.test"}
    )
    assert (
        await media.register_to_file_service() == "https://callback.test/api/file/token"
    )
    resolver.assert_awaited_once_with()
    register.assert_awaited_once_with("/tmp/media")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "component_type", [public_components.Record, public_components.Video]
)
async def test_media_fallback_retains_original_source_when_explicit_path_disappears(
    tmp_path, component_type
) -> None:
    path = tmp_path / "downloaded.media"
    path.write_bytes(b"media")
    media = component_type(file="unresolved.media", path=str(path))

    assert await media._resolve_file_source() == str(path)
    path.unlink()
    assert await media._resolve_file_source() == "unresolved.media"


@pytest.mark.parametrize(
    ("member", "legacy_string"),
    [
        (public_components.ComponentType.Image, "ComponentType.Image"),
        (public_components.Button.Style.PRIMARY, "Style.PRIMARY"),
    ],
)
def test_message_enum_migration_preserves_wire_and_display_contract(
    member, legacy_string
) -> None:
    assert str(member) == legacy_string
    assert f"{member:>30}" == f"{legacy_string:>30}"
    assert json.loads(json.dumps(member)) == member.value
    assert member == member.value
    assert type(member)(member.value) is member


@pytest.mark.parametrize(
    "data", [None, True, 7, 1.5, "text", [1, False], {"nested": [1, False]}]
)
def test_json_callback_union_preserves_runtime_data_types(data) -> None:
    action = public_components.Button.CallbackAction(data=data)
    assert action.data == data
    assert type(action.data) is type(data)


def test_legacy_conversation_summaries_keep_nullable_fallbacks_and_numeric_ids() -> (
    None
):
    rows = [
        (None, None, None, None, None, None),
        ("user", 7, 10, 20, "", "persona"),
        ("user", "1234567890", 0, 0, "Chosen", ""),
    ]
    assert _summarize_conversations(rows) == [
        {
            "user_id": "",
            "cid": "unknown",
            "title": "对话 unknown",
            "persona_id": "",
            "created_at": 0,
            "updated_at": 0,
        },
        {
            "user_id": "user",
            "cid": "7",
            "title": "对话 7",
            "persona_id": "persona",
            "created_at": 10,
            "updated_at": 20,
        },
        {
            "user_id": "user",
            "cid": "1234567890",
            "title": "Chosen",
            "persona_id": "",
            "created_at": 0,
            "updated_at": 0,
        },
    ]
    assert rows[0] == (None, None, None, None, None, None)


@pytest.mark.asyncio
async def test_thread_deletion_preserves_ids_and_unrelated_parent_rows(
    database,
) -> None:
    async with database.get_db() as session, session.begin():
        session.add_all(
            [
                WebChatThread(
                    thread_id=thread_id,
                    creator="creator",
                    parent_session_id=parent,
                    parent_message_id=message_id,
                    base_event_id="event",
                    selected_text="selected",
                )
                for thread_id, parent, message_id in [
                    ("first", "parent", 1),
                    ("second", "parent", 2),
                    ("other", "another", 1),
                ]
            ]
        )

    assert await database.delete_webchat_threads_by_parent_message_ids(
        "parent", [1]
    ) == ["first"]
    assert [
        thread.thread_id
        for thread in await database.get_webchat_threads_by_parent_session("parent")
    ] == ["second"]
    assert await database.delete_webchat_threads_by_parent_session("parent") == [
        "second"
    ]
    assert [
        thread.thread_id
        for thread in await database.get_webchat_threads_by_parent_session("another")
    ] == ["other"]
    assert (
        await database.delete_webchat_threads_by_parent_message_ids("another", []) == []
    )


@pytest.mark.asyncio
async def test_follow_up_wait_cancellation_releases_condition_and_keeps_order() -> None:
    umo = "shared-policy-cancel"
    first = follow_up._allocate_follow_up_order(umo)
    second = follow_up._allocate_follow_up_order(umo)
    waiter = asyncio.create_task(
        follow_up._activate_and_wait_follow_up_turn(umo, second)
    )
    try:
        await asyncio.sleep(0)
        assert not waiter.done()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert not follow_up._FOLLOW_UP_ORDER_STATE[umo]["condition"].locked()

        await follow_up._finish_follow_up_turn(umo, first)
        await asyncio.wait_for(
            follow_up._activate_and_wait_follow_up_turn(umo, second), timeout=1
        )
        await follow_up._finish_follow_up_turn(umo, second)
        assert umo not in follow_up._FOLLOW_UP_ORDER_STATE
    finally:
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        follow_up._FOLLOW_UP_ORDER_STATE.pop(umo, None)


@pytest.mark.asyncio
async def test_follow_up_consumed_tail_is_released_when_head_finishes() -> None:
    umo = "shared-policy-consumed"
    first = follow_up._allocate_follow_up_order(umo)
    second = follow_up._allocate_follow_up_order(umo)
    try:
        await follow_up._mark_follow_up_consumed(umo, second)
        assert follow_up._FOLLOW_UP_ORDER_STATE[umo]["next_turn"] == first
        await follow_up._finish_follow_up_turn(umo, first)
        assert umo not in follow_up._FOLLOW_UP_ORDER_STATE
        await follow_up._finish_follow_up_turn(umo, first)
        assert umo not in follow_up._FOLLOW_UP_ORDER_STATE
    finally:
        follow_up._FOLLOW_UP_ORDER_STATE.pop(umo, None)


@pytest.mark.asyncio
async def test_backup_member_read_failure_does_not_overwrite_existing_destination(
    tmp_path,
) -> None:
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("valid", b"binary\x00payload")
    destination = tmp_path / "nested" / "data.bin"
    destination.parent.mkdir()
    destination.write_bytes(b"original")
    with zipfile.ZipFile(archive_bytes) as archive:
        with pytest.raises(KeyError):
            await _write_archive_member(archive, "missing", destination)
        assert destination.read_bytes() == b"original"
        await _write_archive_member(archive, "valid", destination)
    assert destination.read_bytes() == b"binary\x00payload"


def test_skill_activation_defaults_are_consistent_across_sources(
    tmp_path, monkeypatch
) -> None:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    data_dir.mkdir()
    paths = SimpleNamespace(
        skills=tmp_path / "skills", config=config_dir, data=data_dir
    )
    manager = SkillManager(astrbot_paths=paths, plugins_root=str(tmp_path / "plugins"))
    local = paths.skills / "local"
    plugin = tmp_path / "plugin_skill"
    for directory in (local, plugin):
        directory.mkdir()
        (directory / "SKILL.md").write_text(
            "---\ndescription: Test skill\n---\n", encoding="utf-8"
        )
    monkeypatch.setattr(
        manager,
        "_iter_plugin_skill_dirs",
        lambda: [("plugin", "package", plugin, False)],
    )
    manager.set_sandbox_skills_cache([{"name": "remote", "description": "Remote"}])
    manager._save_config(
        {"skills": {"local": {"active": False}, "plugin": {"active": False}}}
    )
    save = Mock(wraps=manager._save_config)
    monkeypatch.setattr(manager, "_save_config", save)

    assert [
        skill.name for skill in manager.list_skills(active_only=True, runtime="sandbox")
    ] == ["remote"]
    save.assert_called_once()
    save.reset_mock()
    assert [
        skill.name for skill in manager.list_skills(active_only=True, runtime="sandbox")
    ] == ["remote"]
    save.assert_not_called()
    assert manager._load_config()["skills"] == {
        "local": {"active": False},
        "plugin": {"active": False},
        "remote": {"active": True},
    }


def test_persona_cache_replacement_preserves_identity_order_and_absence() -> None:
    original = Persona(persona_id="existing", system_prompt="before")
    other = Persona(persona_id="other", system_prompt="other")
    replacement = Persona(persona_id="existing", system_prompt="after")
    manager = PersonaManager.__new__(PersonaManager)
    manager.personas = [original, other]

    manager._update_cached_persona("existing", replacement)
    manager._update_cached_persona(
        "missing", Persona(persona_id="missing", system_prompt="missing")
    )
    manager._update_cached_persona("other", None)

    assert manager.personas == [replacement, other]
    assert manager.personas[0] is replacement
    assert manager.personas[1] is other


@pytest.mark.asyncio
@pytest.mark.parametrize("async_listener", [False, True])
async def test_zip_download_progress_accepts_sync_and_async_listeners(
    tmp_path, monkeypatch, async_listener
) -> None:
    import httpx

    from astrbot.core.zip_updater import _RepoZipUpdater

    events = []
    payload = b"downloaded bytes"
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=payload)
    )
    updater = _RepoZipUpdater()
    monkeypatch.setattr(
        updater,
        "_create_httpx_client",
        lambda **kwargs: httpx.AsyncClient(transport=transport),
    )

    async def listener(event):
        await asyncio.sleep(0)
        events.append(event)

    target = tmp_path / "download.bin"
    await updater._download_file(
        "https://download.test/archive",
        str(target),
        progress_callback=listener if async_listener else events.append,
    )

    assert target.read_bytes() == payload
    assert events[0]["downloaded"] == 0
    assert events[-1]["downloaded"] == len(payload)
    assert events[-1]["percent"] == 1
    assert [event["downloaded"] for event in events] == sorted(
        event["downloaded"] for event in events
    )


@pytest.mark.asyncio
async def test_cancelled_zip_progress_removes_partial_file_without_replaying_request(
    tmp_path, monkeypatch
) -> None:
    import httpx

    from astrbot.core.zip_updater import _RepoZipUpdater

    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, content=b"partial")

    updater = _RepoZipUpdater()
    monkeypatch.setattr(
        updater,
        "_create_httpx_client",
        lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )

    async def listener(event):
        if event["downloaded"]:
            raise asyncio.CancelledError

    target = tmp_path / "cancelled.bin"
    with pytest.raises(asyncio.CancelledError):
        await updater._download_file(
            "https://download.test/archive", str(target), progress_callback=listener
        )

    assert not target.exists()
    assert len(requests) == 1


def test_pipeline_result_alias_remains_inspectable_for_plugin_consumers() -> None:
    from collections.abc import AsyncGenerator, Awaitable
    from typing import get_args, get_origin, get_type_hints

    from astrbot.core.pipeline.stage import Stage, StageProcessResult

    resolved = get_type_hints(Stage.process)["return"]
    assert resolved is StageProcessResult
    assert {get_origin(variant) for variant in get_args(resolved)} == {
        AsyncGenerator,
        Awaitable,
    }
