import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, File, Image, Plain, Record, Video
from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.line.line_adapter import LinePlatformAdapter
from astrbot.core.platform.sources.line.line_api import LineAPIClient
from astrbot.core.platform.sources.line.line_event import LineMessageEvent

pytestmark = pytest.mark.platform


def _adapter() -> LinePlatformAdapter:
    adapter = LinePlatformAdapter.__new__(LinePlatformAdapter)
    adapter.config = {"id": "line-test", "unified_webhook_mode": True}
    adapter.destination = "dest-bot"
    adapter.settings = {}
    adapter._event_id_timestamps = {}
    adapter.shutdown_event = MagicMock()
    adapter.line_api = SimpleNamespace(
        get_message_content=AsyncMock(),
        verify_signature=MagicMock(return_value=True),
        close=AsyncMock(),
    )
    return adapter


def _platform_meta():
    return SimpleNamespace(
        name="line",
        description="LINE",
        id="line-test",
        support_streaming_message=False,
    )


def test_line_parse_text_with_mentions_splits_user_mentions_and_plain_text():
    adapter = _adapter()

    components = adapter._parse_text_with_mentions(
        "Hello @Alice and @all",
        {
            "mentionees": [
                {"index": 6, "length": 6, "type": "user", "userId": "user-1"},
                {"index": 17, "length": 4, "type": "all"},
            ]
        },
    )

    assert [type(component) for component in components] == [Plain, At, Plain, Plain]
    assert components[0].text == "Hello "
    assert components[1].qq == "user-1"
    assert components[1].name == "Alice"
    assert components[2].text == " and "
    assert components[3].text == "@all"


def test_line_parse_text_with_mentions_ignores_invalid_mention_entries():
    adapter = _adapter()

    components = adapter._parse_text_with_mentions(
        "hello @alice",
        {
            "mentionees": [
                "bad-entry",
                {"index": "1", "length": 5, "type": "user", "userId": "user-1"},
            ]
        },
    )

    assert len(components) == 1
    assert isinstance(components[0], Plain)
    assert components[0].text == "hello @alice"


@pytest.mark.asyncio
async def test_line_convert_message_maps_group_message_and_external_image():
    adapter = _adapter()

    result = await adapter.convert_message(
        {
            "type": "message",
            "mode": "active",
            "timestamp": 1710000000123,
            "webhookEventId": "evt-1",
            "source": {
                "type": "group",
                "groupId": "group-1",
                "userId": "user-1",
            },
            "message": {
                "id": "msg-1",
                "type": "image",
                "contentProvider": {
                    "type": "external",
                    "originalContentUrl": "https://example.test/image.png",
                },
            },
        }
    )

    assert result is not None
    assert result.type == MessageType.GROUP_MESSAGE
    assert result.group.group_id == "group-1"
    assert result.session_id == "group-1"
    assert result.sender.user_id == "user-1"
    assert result.self_id == "dest-bot"
    assert result.timestamp == 1710000000
    assert result.message_str == "[image]"
    assert result.message[0].file == "https://example.test/image.png"


@pytest.mark.asyncio
async def test_line_convert_message_uses_fallback_self_id_and_current_time(monkeypatch):
    adapter = _adapter()
    adapter.destination = ""
    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_adapter.time.time",
        lambda: 1234.8,
    )

    result = await adapter.convert_message(
        {
            "type": "message",
            "source": {"type": "user", "userId": "user-1"},
            "message": {"type": "text", "text": "hello"},
        }
    )

    assert result is not None
    assert result.self_id == "line-test"
    assert result.timestamp == 1234
    assert result.session_id == "user-1"


@pytest.mark.asyncio
async def test_line_convert_message_maps_room_without_user_to_group_sender_fallback():
    adapter = _adapter()

    result = await adapter.convert_message(
        {
            "type": "message",
            "source": {
                "type": "room",
                "roomId": "room-1",
            },
            "message": {
                "id": "msg-room",
                "type": "text",
                "text": "hello room",
            },
        }
    )

    assert result is not None
    assert result.type == MessageType.GROUP_MESSAGE
    assert result.session_id == "room-1"
    assert result.sender.user_id == "room-1"
    assert result.message_str == "hello room"


@pytest.mark.asyncio
async def test_line_convert_message_unknown_source_becomes_other_message():
    adapter = _adapter()

    result = await adapter.convert_message(
        {
            "type": "message",
            "source": {"type": "beacon"},
            "message": {"type": "sticker", "id": "msg-sticker"},
        }
    )

    assert result is not None
    assert result.type == MessageType.OTHER_MESSAGE
    assert result.session_id == "unknown"
    assert result.sender.user_id == "unknown"
    assert result.message_str == "[sticker]"


@pytest.mark.asyncio
async def test_line_convert_message_returns_none_for_non_message_or_standby_or_bad_shapes():
    adapter = _adapter()

    assert await adapter.convert_message({"type": "follow"}) is None
    assert (
        await adapter.convert_message(
            {
                "type": "message",
                "mode": "standby",
                "source": {"type": "user", "userId": "user-1"},
                "message": {"type": "text", "text": "ignored"},
            }
        )
        is None
    )
    assert (
        await adapter.convert_message(
            {
                "type": "message",
                "source": "bad-source",
                "message": {"type": "text", "text": "ignored"},
            }
        )
        is None
    )
    assert (
        await adapter.convert_message(
            {
                "type": "message",
                "source": {"type": "user", "userId": "user-1"},
                "message": "bad-message",
            }
        )
        is None
    )


@pytest.mark.asyncio
async def test_line_parse_message_components_file_keeps_lazy_component_when_download_fails():
    adapter = _adapter()
    adapter.line_api.get_message_content = AsyncMock(return_value=None)

    components = await adapter._parse_line_message_components(
        {"id": "file-1", "type": "file", "fileName": "report.pdf"}
    )

    assert len(components) == 1
    assert isinstance(components[0], File)
    assert components[0].name == "report.pdf"
    assert await components[0].get_file() == ""


@pytest.mark.asyncio
async def test_line_parse_message_components_image_keeps_lazy_component_when_download_fails():
    adapter = _adapter()
    adapter.line_api.get_message_content = AsyncMock(return_value=None)

    components = await adapter._parse_line_message_components(
        {"id": "img-1", "type": "image"}
    )

    assert len(components) == 1
    assert isinstance(components[0], Image)
    await components[0]._resolve_deferred_source()
    assert components[0].file == ""


@pytest.mark.asyncio
async def test_line_build_file_component_uses_downloaded_filename_when_available():
    adapter = _adapter()
    adapter.line_api.get_message_content = AsyncMock(
        return_value=(b"file-bytes", "application/pdf", "invoice.pdf")
    )

    component = await adapter._build_file_component(
        "msg-file",
        {"id": "msg-file", "type": "file", "fileName": "fallback.bin"},
    )

    assert isinstance(component, File)
    assert component.name == "fallback.bin"
    assert component.file == ""

    resolved = await component.get_file()

    assert component.name == "invoice.pdf"
    assert resolved.endswith(".pdf")


@pytest.mark.asyncio
async def test_line_build_image_component_downloads_binary_content_when_no_external_url():
    adapter = _adapter()
    adapter.line_api.get_message_content = AsyncMock(
        return_value=(b"image-bytes", "image/png", "photo.png")
    )

    component = await adapter._build_image_component(
        "msg-image",
        {"id": "msg-image", "type": "image"},
    )

    assert isinstance(component, Image)
    assert component.file == ""

    await component._resolve_deferred_source()

    assert component.file.endswith(".png")


@pytest.mark.asyncio
async def test_line_send_by_session_pushes_built_messages(monkeypatch):
    adapter = _adapter()
    adapter.line_api.push_message = AsyncMock()

    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_event.LineMessageEvent.build_line_messages",
        AsyncMock(return_value=[{"type": "text", "text": "hello"}]),
    )
    with patch(
        "astrbot.core.platform.platform.Platform.send_by_session",
        AsyncMock(),
    ) as super_send:
        await adapter.send_by_session(
            SimpleNamespace(
                session_id="user-1", message_type=MessageType.FRIEND_MESSAGE
            ),
            MessageChain([Plain("hello")]),
        )

    adapter.line_api.push_message.assert_awaited_once_with(
        "user-1",
        [{"type": "text", "text": "hello"}],
    )
    super_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_line_send_by_session_skips_push_for_empty_built_messages(monkeypatch):
    adapter = _adapter()
    adapter.line_api.push_message = AsyncMock()

    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_event.LineMessageEvent.build_line_messages",
        AsyncMock(return_value=[]),
    )
    with patch(
        "astrbot.core.platform.platform.Platform.send_by_session",
        AsyncMock(),
    ) as super_send:
        await adapter.send_by_session(
            SimpleNamespace(
                session_id="user-1", message_type=MessageType.FRIEND_MESSAGE
            ),
            MessageChain(chain=[]),
        )

    adapter.line_api.push_message.assert_not_called()
    super_send.assert_awaited_once()


def test_line_meta_returns_configured_platform_metadata():
    adapter = _adapter()

    meta = adapter.meta()

    assert meta.name == "line"
    assert meta.id == "line-test"
    assert meta.support_streaming_message is False


@pytest.mark.asyncio
async def test_line_run_logs_webhook_uuid_and_waits_for_shutdown(monkeypatch):
    adapter = _adapter()
    adapter.config["webhook_uuid"] = "uuid-1"
    adapter.shutdown_event = SimpleNamespace(wait=AsyncMock())
    logged = []

    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_adapter.log_webhook_info",
        lambda name, webhook_uuid: logged.append((name, webhook_uuid)),
    )

    await adapter.run()

    assert logged == [("line-test(LINE)", "uuid-1")]
    adapter.shutdown_event.wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_line_run_warns_when_webhook_uuid_missing(monkeypatch):
    adapter = _adapter()
    adapter.config["webhook_uuid"] = ""
    adapter.shutdown_event = SimpleNamespace(wait=AsyncMock())
    warnings = []

    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_adapter.logger.warning",
        lambda message, *args, **kwargs: warnings.append(str(message)),
    )

    await adapter.run()

    assert any("webhook_uuid 为空" in message for message in warnings)
    adapter.shutdown_event.wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_line_terminate_sets_shutdown_and_closes_api():
    adapter = _adapter()
    adapter.shutdown_event = MagicMock()

    await adapter.terminate()

    adapter.shutdown_event.set.assert_called_once_with()
    adapter.line_api.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_line_handle_webhook_event_skips_duplicates_and_non_message_events():
    adapter = _adapter()
    adapter.convert_message = AsyncMock(
        side_effect=[SimpleNamespace(message_id="msg-1"), None]
    )
    adapter.handle_msg = AsyncMock()

    await adapter.handle_webhook_event(
        {
            "destination": "new-destination",
            "events": [
                {"webhookEventId": "evt-1", "type": "message", "message": {}},
                {"webhookEventId": "evt-1", "type": "message", "message": {}},
                {"webhookEventId": "evt-2", "type": "follow"},
            ],
        }
    )

    assert adapter.destination == "new-destination"
    assert adapter.convert_message.await_count == 2
    adapter.handle_msg.assert_awaited_once()


@pytest.mark.asyncio
async def test_line_handle_webhook_event_ignores_non_list_events_and_bad_entries():
    adapter = _adapter()
    adapter.convert_message = AsyncMock(return_value=None)
    adapter.handle_msg = AsyncMock()

    await adapter.handle_webhook_event({"destination": "dest-1", "events": "bad"})
    await adapter.handle_webhook_event(
        {"events": ["bad-entry", {"webhookEventId": "evt-3", "type": "message"}]}
    )

    assert adapter.destination == "dest-1"
    adapter.convert_message.assert_awaited_once_with(
        {"webhookEventId": "evt-3", "type": "message"}
    )
    adapter.handle_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_line_handle_webhook_event_skips_when_convert_message_returns_none():
    adapter = _adapter()
    adapter.convert_message = AsyncMock(return_value=None)
    adapter.handle_msg = AsyncMock()

    await adapter.handle_webhook_event(
        {"events": [{"webhookEventId": "evt-1", "type": "message", "message": {}}]}
    )

    adapter.convert_message.assert_awaited_once()
    adapter.handle_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_line_handle_webhook_event_processes_batch_entries_concurrently():
    adapter = _adapter()
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_handled = asyncio.Event()

    async def _convert_message(event):
        if event["webhookEventId"] == "evt-1":
            first_started.set()
            await release_first.wait()
            return SimpleNamespace(message_id="msg-1")
        return SimpleNamespace(message_id="msg-2")

    async def _handle_msg(message):
        if message.message_id == "msg-2":
            second_handled.set()

    adapter.convert_message = AsyncMock(side_effect=_convert_message)
    adapter.handle_msg = AsyncMock(side_effect=_handle_msg)

    task = asyncio.create_task(
        adapter.handle_webhook_event(
            {
                "events": [
                    {"webhookEventId": "evt-1", "type": "message", "message": {}},
                    {"webhookEventId": "evt-2", "type": "message", "message": {}},
                ]
            }
        )
    )

    await asyncio.wait_for(first_started.wait(), timeout=1.0)
    await asyncio.wait_for(second_handled.wait(), timeout=1.0)
    release_first.set()
    await task

    assert adapter.convert_message.await_count == 2
    assert adapter.handle_msg.await_count == 2


@pytest.mark.asyncio
async def test_line_webhook_callback_rejects_bad_signature_bad_body_and_non_dict_payload():
    adapter = _adapter()
    adapter.handle_webhook_event = AsyncMock()

    bad_signature_request = SimpleNamespace(
        get_data=AsyncMock(return_value=b"body"),
        get_json=AsyncMock(),
        headers={"x-line-signature": "sig"},
    )
    adapter.line_api.verify_signature = MagicMock(return_value=False)
    assert await adapter.webhook_callback(bad_signature_request) == (
        "invalid signature",
        400,
    )

    bad_body_request = SimpleNamespace(
        get_data=AsyncMock(return_value=b"body"),
        get_json=AsyncMock(side_effect=RuntimeError("bad json")),
        headers={"x-line-signature": "sig"},
    )
    adapter.line_api.verify_signature = MagicMock(return_value=True)
    assert await adapter.webhook_callback(bad_body_request) == ("bad request", 400)

    non_dict_request = SimpleNamespace(
        get_data=AsyncMock(return_value=b"body"),
        get_json=AsyncMock(return_value=["bad"]),
        headers={"x-line-signature": "sig"},
    )
    assert await adapter.webhook_callback(non_dict_request) == ("bad request", 400)
    adapter.handle_webhook_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_line_webhook_callback_accepts_valid_payload():
    adapter = _adapter()
    adapter.handle_webhook_event = AsyncMock()

    request = SimpleNamespace(
        get_data=AsyncMock(return_value=b"body"),
        get_json=AsyncMock(return_value={"events": []}),
        headers={"x-line-signature": "sig"},
    )

    assert await adapter.webhook_callback(request) == ("ok", 200)
    adapter.line_api.verify_signature.assert_called_once_with(b"body", "sig")
    adapter.handle_webhook_event.assert_awaited_once_with({"events": []})


@pytest.mark.asyncio
async def test_line_build_audio_component_uses_external_url_with_media_resolver(
    monkeypatch,
):
    adapter = _adapter()

    media_resolver = MagicMock()
    media_resolver.to_path = AsyncMock(return_value="C:/tmp/converted.wav")
    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_adapter.MediaResolver",
        MagicMock(return_value=media_resolver),
    )

    component = await adapter._build_audio_component(
        "msg-audio",
        {
            "type": "audio",
            "contentProvider": {
                "type": "external",
                "originalContentUrl": "https://example.test/audio.m4a",
            },
        },
    )

    assert component is not None
    assert component.file == ""
    assert component.url == ""
    media_resolver.to_path.assert_not_awaited()

    await component._resolve_deferred_source()

    assert component.file == "C:/tmp/converted.wav"
    assert component.path == "C:/tmp/converted.wav"
    media_resolver.to_path.assert_awaited_once_with(target_format="wav")
    adapter.line_api.get_message_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_line_build_audio_component_downloads_and_converts_content(
    monkeypatch, tmp_path
):
    adapter = _adapter()
    adapter.line_api.get_message_content = AsyncMock(
        return_value=(b"audio-bytes", "audio/mp4", "voice.m4a")
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_adapter.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    media_resolver = MagicMock()
    media_resolver.to_path = AsyncMock(return_value="C:/tmp/voice.wav")
    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_adapter.MediaResolver",
        MagicMock(return_value=media_resolver),
    )

    component = await adapter._build_audio_component(
        "msg-audio",
        {"id": "msg-audio", "type": "audio"},
    )

    assert component is not None
    assert component.file == ""
    assert list(tmp_path.glob("*.m4a")) == []
    media_resolver.to_path.assert_not_awaited()

    await component._resolve_deferred_source()

    assert component.file == "C:/tmp/voice.wav"
    saved_files = list(tmp_path.glob("voice_msg-audio_*.m4a"))
    assert len(saved_files) == 1
    assert saved_files[0].read_bytes() == b"audio-bytes"
    media_resolver.to_path.assert_awaited_once_with(target_format="wav")


@pytest.mark.asyncio
async def test_line_build_video_component_returns_none_when_download_fails():
    adapter = _adapter()
    adapter.line_api.get_message_content = AsyncMock(return_value=None)

    component = await adapter._build_video_component(
        "msg-video",
        {"id": "msg-video", "type": "video"},
    )

    assert isinstance(component, Video)
    await component._resolve_deferred_source()
    assert component.file == ""


@pytest.mark.asyncio
async def test_line_build_video_component_stores_downloaded_video(
    monkeypatch, tmp_path
):
    adapter = _adapter()
    adapter.line_api.get_message_content = AsyncMock(
        return_value=(b"video-bytes", "video/mp4", "clip.mp4")
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_adapter.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )

    component = await adapter._build_video_component(
        "msg-video",
        {"id": "msg-video", "type": "video"},
    )

    assert component is not None
    assert component.file == ""
    assert list(tmp_path.glob("*.mp4")) == []

    await component._resolve_deferred_source()

    assert component.file.endswith(".mp4")
    assert component.path == component.file
    saved_files = list(tmp_path.glob("clip_msg-video_*.mp4"))
    assert len(saved_files) == 1
    assert saved_files[0].read_bytes() == b"video-bytes"


def test_line_guess_suffix_prefers_mimetype_and_falls_back():
    assert (
        LinePlatformAdapter._guess_suffix("audio/mp4; charset=utf-8", ".wav") == ".m4a"
    )
    assert LinePlatformAdapter._guess_suffix(None, ".wav") == ".wav"


def test_line_store_temp_content_sanitizes_original_name(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_adapter.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )

    stored = LinePlatformAdapter._store_temp_content(
        "file",
        "msg-1",
        b"payload",
        ".txt",
        original_name="../bad name?.txt",
    )

    path = Path(stored)
    assert path.exists()
    assert path.read_bytes() == b"payload"
    assert path.name.startswith("bad_name_")
    assert path.suffix == ".txt"


def test_line_get_external_content_url_requires_external_provider():
    assert (
        LinePlatformAdapter._get_external_content_url(
            {"contentProvider": {"type": "external", "originalContentUrl": "https://a"}}
        )
        == "https://a"
    )
    assert (
        LinePlatformAdapter._get_external_content_url(
            {"contentProvider": {"type": "line"}}
        )
        == ""
    )
    assert (
        LinePlatformAdapter._get_external_content_url({"contentProvider": "bad"}) == ""
    )


def test_line_build_message_str_covers_known_components_and_unknown_fallback():
    class UnknownComponent:
        type = "mystery"

    message = LinePlatformAdapter._build_message_str(
        [
            Plain("hello"),
            At(qq="u1", name="Alice"),
            Image.fromURL("https://example.test/a.png"),
            Video.fromURL("https://example.test/v.mp4"),
            Record(file="voice.wav"),
            File(name="report.pdf", file="report.pdf"),
            UnknownComponent(),
        ]
    )

    assert message == "hello @Alice [image] [video] [audio] report.pdf [mystery]"


def test_line_create_event_wraps_message_with_line_context():
    adapter = _adapter()
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "bot"
    message.sender = MessageMember(user_id="user-1", nickname="Alice")
    message.session_id = "user-1"
    message.message_id = "msg-1"
    message.message = [Plain("hello")]
    message.message_str = "hello"

    event = adapter.create_event(message)

    assert isinstance(event, LineMessageEvent)
    assert event.line_api is adapter.line_api
    assert event.message_str == "hello"
    assert event.session_id == "user-1"
    assert event.platform_member_role == "member"
    assert event.platform_role_source == "none"


@pytest.mark.asyncio
async def test_line_handle_msg_commits_created_event(monkeypatch):
    adapter = _adapter()
    event = object()
    abm = SimpleNamespace(message_str="hello", session_id="user-1")

    monkeypatch.setattr(adapter, "create_event", lambda message: event)
    commit_event = MagicMock()
    monkeypatch.setattr(adapter, "commit_event", commit_event)

    await adapter.handle_msg(abm)

    commit_event.assert_called_once_with(event)


def test_line_clean_expired_events_removes_only_old_entries(monkeypatch):
    adapter = _adapter()
    adapter._event_id_timestamps = {
        "expired": 100.0,
        "fresh": 1000.0,
    }
    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_adapter.time.time", lambda: 2000.1
    )

    adapter._clean_expired_events()

    assert adapter._event_id_timestamps == {"fresh": 1000.0}


def test_line_is_duplicate_event_reaccepts_event_after_expiration(monkeypatch):
    adapter = _adapter()
    current = {"value": 100.0}
    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_adapter.time.time",
        lambda: current["value"],
    )

    assert adapter._is_duplicate_event("evt-1") is False
    assert adapter._is_duplicate_event("evt-1") is True

    current["value"] = 2001.0

    assert adapter._is_duplicate_event("evt-1") is False


def _line_event(message, line_api) -> LineMessageEvent:
    return LineMessageEvent(
        message_str=message.message_str,
        message_obj=message,
        platform_meta=PlatformMetadata(
            name="line",
            description="LINE",
            id="line-test",
            support_streaming_message=False,
        ),
        session_id=message.session_id,
        line_api=line_api,
    )


@pytest.mark.asyncio
async def test_line_get_group_fills_summary_and_count_without_members():
    adapter = _adapter()
    message = await adapter.convert_message(
        {
            "type": "message",
            "source": {"type": "group", "groupId": "C-group", "userId": "U-sender"},
            "message": {"id": "message-1", "type": "text", "text": "hello"},
        }
    )
    assert message is not None
    inbound = message.group
    adapter.line_api.get_group_summary = AsyncMock(
        return_value={
            "groupId": "C-group",
            "groupName": "LINE group",
            "pictureUrl": "https://example.com/group.png",
        }
    )
    adapter.line_api.get_chat_member_count = AsyncMock(return_value=2)
    adapter.line_api.get_chat_member_ids = AsyncMock(return_value=["U-one"])
    adapter.line_api.get_chat_member_profile = AsyncMock()

    result = await _line_event(message, adapter.line_api).get_group()

    assert result is not inbound
    assert result.group_id == "C-group"
    assert result.group_name == "LINE group"
    assert result.group_avatar == "https://example.com/group.png"
    assert result.member_count == 2
    assert result.members is None
    adapter.line_api.get_group_summary.assert_awaited_once_with("C-group")
    adapter.line_api.get_chat_member_count.assert_awaited_once_with("group", "C-group")
    adapter.line_api.get_chat_member_ids.assert_not_awaited()
    adapter.line_api.get_chat_member_profile.assert_not_awaited()


@pytest.mark.asyncio
async def test_line_get_room_uses_count_without_summary_or_members():
    adapter = _adapter()
    message = await adapter.convert_message(
        {
            "type": "message",
            "source": {"type": "room", "roomId": "R-room", "userId": "U-sender"},
            "message": {"id": "message-1", "type": "text", "text": "hello"},
        }
    )
    assert message is not None
    adapter.line_api.get_group_summary = AsyncMock()
    adapter.line_api.get_chat_member_count = AsyncMock(return_value=3)
    adapter.line_api.get_chat_member_ids = AsyncMock()
    adapter.line_api.get_chat_member_profile = AsyncMock()

    result = await _line_event(message, adapter.line_api).get_group()

    assert result.group_id == "R-room"
    assert result.group_name is None
    assert result.member_count == 3
    assert result.members is None
    adapter.line_api.get_group_summary.assert_not_awaited()
    adapter.line_api.get_chat_member_count.assert_awaited_once_with("room", "R-room")
    adapter.line_api.get_chat_member_ids.assert_not_awaited()
    adapter.line_api.get_chat_member_profile.assert_not_awaited()


@pytest.mark.asyncio
async def test_line_get_group_keeps_inbound_name_when_apis_fail():
    adapter = _adapter()
    message = await adapter.convert_message(
        {
            "type": "message",
            "source": {
                "type": "group",
                "groupId": "C-group",
                "userId": "U-sender",
                "groupName": "Webhook group",
            },
            "message": {"id": "message-1", "type": "text", "text": "hello"},
        }
    )
    assert message is not None
    inbound = message.group
    adapter.line_api.get_group_summary = AsyncMock(side_effect=RuntimeError("denied"))
    adapter.line_api.get_chat_member_count = AsyncMock(
        side_effect=RuntimeError("denied")
    )
    adapter.line_api.get_chat_member_ids = AsyncMock()

    result = await _line_event(message, adapter.line_api).get_group()

    assert result is not inbound
    assert result.group_id == "C-group"
    assert result.group_name == "Webhook group"
    assert result.member_count is None
    assert result.members is None
    adapter.line_api.get_chat_member_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_line_member_id_api_follows_pagination_tokens():
    client = LineAPIClient(
        channel_access_token="test-token",
        channel_secret="test-secret",
    )
    client._get_json = AsyncMock(
        side_effect=[
            {"memberIds": ["U-one"], "next": "next-page"},
            {"memberIds": ["U-two", "U-one"]},
        ]
    )

    result = await client.get_chat_member_ids("group", "C-group")

    assert result == ["U-one", "U-two"]
    assert client._get_json.await_count == 2
    assert client._get_json.await_args_list[0].kwargs["params"] is None
    assert client._get_json.await_args_list[1].kwargs["params"] == {
        "start": "next-page"
    }


@pytest.mark.asyncio
async def test_line_member_id_api_returns_none_when_restricted():
    client = LineAPIClient(
        channel_access_token="test-token",
        channel_secret="test-secret",
    )
    client._get_json = AsyncMock(return_value=None)

    result = await client.get_chat_member_ids("room", "R-room")

    assert result is None


@pytest.mark.asyncio
async def test_line_group_summary_and_member_count_helpers():
    client = LineAPIClient(
        channel_access_token="test-token",
        channel_secret="test-secret",
    )
    client._get_json = AsyncMock(
        side_effect=[
            {"groupName": "LINE group", "pictureUrl": "https://example.com/g.png"},
            {"count": 4},
            None,
        ]
    )

    summary = await client.get_group_summary("C-group")
    count = await client.get_chat_member_count("group", "C-group")
    profile = await client.get_chat_member_profile("group", "C-group", "U-one")

    assert summary["groupName"] == "LINE group"
    assert count == 4
    assert profile is None
    assert client._get_json.await_count == 3
