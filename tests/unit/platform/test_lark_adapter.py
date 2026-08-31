from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import astrbot.api.message_components as Comp
import astrbot.core.platform.sources.lark.lark_adapter as lark_adapter_module
from astrbot.api.platform import MessageType
from astrbot.core.platform.sources.lark.lark_adapter import LarkPlatformAdapter

pytestmark = pytest.mark.platform


def _adapter() -> LarkPlatformAdapter:
    adapter = LarkPlatformAdapter.__new__(LarkPlatformAdapter)
    adapter.bot_name = "astrbot"
    adapter.bot_open_id = "bot-open"
    adapter.event_id_timestamps = {}
    adapter.lark_api = SimpleNamespace(
        im=SimpleNamespace(
            v1=SimpleNamespace(
                message=SimpleNamespace(aget=AsyncMock()),
            )
        )
    )
    return adapter


def test_lark_parse_post_content_flattens_nested_and_mixed_components():
    adapter = _adapter()

    result = adapter._parse_post_content(
        {
            "content": [
                [{"tag": "text", "text": "hello"}],
                {"tag": "img", "image_key": "img-1"},
                "skip-me",
                [{"tag": "a", "text": "Doc", "href": "https://example.com"}],
            ]
        }
    )

    assert result == [
        {"tag": "text", "text": "hello"},
        {"tag": "img", "image_key": "img-1"},
        {"tag": "a", "text": "Doc", "href": "https://example.com"},
    ]


@pytest.mark.asyncio
async def test_lark_parse_message_components_text_dispatches_mentions_and_plain_text():
    adapter = _adapter()

    components = await adapter._parse_message_components(
        message_id="msg-text",
        message_type="text",
        content={"text": " hello @_user_1 world "},
        at_map={"@_user_1": Comp.At(qq="ou_1", name="Alice")},
    )

    assert [type(component) for component in components] == [
        Comp.Plain,
        Comp.At,
        Comp.Plain,
    ]
    assert adapter._build_message_str_from_components(components) == (
        "hello @Alice world"
    )


def test_lark_build_message_str_skips_leading_self_mention_by_id():
    adapter = _adapter()
    components = [
        Comp.At(qq="bot-open", name="astrbot"),
        Comp.Plain("hi"),
    ]

    assert (
        adapter._build_message_str_from_components(
            components,
            bot_self_id="bot-open",
            bot_name="astrbot",
        )
        == "hi"
    )
    assert [type(component) for component in components] == [Comp.At, Comp.Plain]


def test_lark_build_message_str_skips_leading_self_mention_by_name():
    adapter = _adapter()
    components = [
        Comp.At(qq="", name="astrbot"),
        Comp.Plain("help"),
    ]

    assert (
        adapter._build_message_str_from_components(
            components,
            bot_self_id="bot-open",
            bot_name="astrbot",
        )
        == "help"
    )


def test_lark_build_message_str_keeps_non_self_and_quoted_mentions():
    adapter = _adapter()
    components = [
        Comp.At(qq="ou_1", name="Alice"),
        Comp.Plain("hi"),
        Comp.At(qq="bot-open", name="astrbot"),
    ]

    assert (
        adapter._build_message_str_from_components(
            components,
            bot_self_id="bot-open",
            bot_name="astrbot",
        )
        == "@Alice hi @astrbot"
    )
    assert adapter._build_message_str_from_components(components) == (
        "@Alice hi @astrbot"
    )


@pytest.mark.asyncio
async def test_lark_parse_message_components_post_parses_mentions_links_and_images():
    adapter = _adapter()

    async def fake_download_message_resource(**kwargs):
        assert kwargs == {
            "message_id": "msg-1",
            "file_key": "img-1",
            "resource_type": "image",
        }
        return b"image-bytes"

    adapter._download_message_resource = fake_download_message_resource

    components = await adapter._parse_message_components(
        message_id="msg-1",
        message_type="post",
        content={
            "content": [
                [
                    {"tag": "at", "user_id": "ou_1"},
                    {"tag": "text", "text": " hello "},
                    {
                        "tag": "a",
                        "text": "Doc",
                        "href": "https://example.com/docs",
                    },
                    {"tag": "img", "image_key": "img-1"},
                ]
            ]
        },
        at_map={"ou_1": Comp.At(qq="ou_1", name="Alice")},
    )

    assert [type(component) for component in components] == [
        Comp.At,
        Comp.Plain,
        Comp.Plain,
        Comp.Image,
    ]
    assert components[0].qq == "ou_1"
    assert components[0].name == "Alice"
    assert components[1].text == "hello"
    assert components[2].text == "Doc(https://example.com/docs)"
    assert components[3].file == ""
    await components[3]._resolve_deferred_source()
    assert components[3].file.startswith("base64://")
    assert adapter._build_message_str_from_components(components) == (
        "@Alice hello Doc(https://example.com/docs) [image]"
    )


@pytest.mark.asyncio
async def test_lark_parse_message_components_file_requires_message_id_and_file_key():
    adapter = _adapter()
    adapter._download_file_resource_to_temp = AsyncMock()

    no_message_id = await adapter._parse_message_components(
        message_id=None,
        message_type="file",
        content={"file_key": "file-1", "file_name": "report.pdf"},
        at_map={},
    )
    no_file_key = await adapter._parse_message_components(
        message_id="msg-1",
        message_type="file",
        content={"file_name": "report.pdf"},
        at_map={},
    )

    assert no_message_id == []
    assert no_file_key == []
    adapter._download_file_resource_to_temp.assert_not_called()


@pytest.mark.asyncio
async def test_lark_parse_message_components_file_resolves_lazily_and_tracks_path():
    adapter = _adapter()
    adapter._download_file_resource_to_temp = AsyncMock(
        return_value="C:/tmp/report.pdf"
    )
    tracked_paths: list[str] = []

    components = await adapter._parse_message_components(
        message_id="msg-file",
        message_type="file",
        content={"file_key": "file-1", "file_name": "report.pdf"},
        at_map={},
        temporary_file_paths=tracked_paths,
    )

    assert len(components) == 1
    assert isinstance(components[0], Comp.File)
    adapter._download_file_resource_to_temp.assert_not_awaited()
    await components[0]._resolve_file_if_needed()
    assert components[0].file_ == "C:/tmp/report.pdf"
    assert tracked_paths == ["C:/tmp/report.pdf"]


@pytest.mark.asyncio
async def test_lark_parse_message_components_audio_keeps_lazy_record():
    adapter = _adapter()
    adapter._download_file_resource_to_temp = AsyncMock(return_value="/tmp/audio.opus")

    components = await adapter._parse_message_components(
        message_id="msg-2",
        message_type="audio",
        content={"file_key": "audio-1"},
        at_map={},
    )

    assert len(components) == 1
    assert isinstance(components[0], Comp.Record)
    assert components[0].file == ""
    adapter._download_file_resource_to_temp.assert_not_awaited()


@pytest.mark.asyncio
async def test_lark_parse_message_components_audio_requires_file_key():
    adapter = _adapter()
    adapter._download_file_resource_to_temp = AsyncMock()

    components = await adapter._parse_message_components(
        message_id="msg-audio",
        message_type="audio",
        content={},
        at_map={},
    )

    assert components == []
    adapter._download_file_resource_to_temp.assert_not_awaited()


@pytest.mark.asyncio
async def test_lark_parse_message_components_image_and_media_require_message_id(
    monkeypatch,
):
    adapter = _adapter()
    adapter._download_message_resource = AsyncMock()
    adapter._download_file_resource_to_temp = AsyncMock()
    logger_error = MagicMock()
    monkeypatch.setattr(lark_adapter_module.logger, "error", logger_error)

    image_components = await adapter._parse_message_components(
        message_id=None,
        message_type="image",
        content={"image_key": "img-1"},
        at_map={},
    )
    media_components = await adapter._parse_message_components(
        message_id=None,
        message_type="post",
        content={"content": [[{"tag": "media", "file_key": "media-1"}]]},
        at_map={},
    )

    assert image_components == []
    assert media_components == []
    adapter._download_message_resource.assert_not_awaited()
    adapter._download_file_resource_to_temp.assert_not_awaited()
    assert logger_error.call_count == 2


@pytest.mark.asyncio
async def test_lark_parse_standalone_image_keeps_lazy_failure_as_empty_source():
    adapter = _adapter()
    adapter._download_message_resource = AsyncMock(return_value=None)

    components = await adapter._parse_message_components(
        message_id="msg-image",
        message_type="image",
        content={"image_key": "image-1"},
        at_map={},
    )

    assert len(components) == 1
    assert isinstance(components[0], Comp.Image)
    adapter._download_message_resource.assert_not_awaited()
    await components[0]._resolve_deferred_source()
    assert components[0].file == ""


@pytest.mark.asyncio
async def test_lark_parse_post_media_resolves_lazily_and_tracks_path():
    adapter = _adapter()
    adapter._download_file_resource_to_temp = AsyncMock(
        return_value="C:/tmp/post-video.mp4"
    )
    tracked_paths: list[str] = []

    components = await adapter._parse_message_components(
        message_id="msg-post",
        message_type="post",
        content={
            "content": [
                [
                    {
                        "tag": "media",
                        "file_key": "media-1",
                        "file_name": "clip.mp4",
                    }
                ]
            ]
        },
        at_map={},
        temporary_file_paths=tracked_paths,
    )

    assert len(components) == 1
    assert isinstance(components[0], Comp.Video)
    adapter._download_file_resource_to_temp.assert_not_awaited()
    await components[0]._resolve_deferred_source()
    assert components[0].file == "C:/tmp/post-video.mp4"
    assert tracked_paths == ["C:/tmp/post-video.mp4"]


@pytest.mark.asyncio
async def test_lark_parse_media_resolves_lazily_and_requires_file_key():
    adapter = _adapter()
    adapter._download_file_resource_to_temp = AsyncMock(return_value="C:/tmp/video.mp4")
    tracked_paths: list[str] = []

    missing_key = await adapter._parse_message_components(
        message_id="msg-media",
        message_type="media",
        content={"file_name": "clip.mp4"},
        at_map={},
    )
    components = await adapter._parse_message_components(
        message_id="msg-media",
        message_type="media",
        content={"file_key": "media-1", "file_name": "clip.mp4"},
        at_map={},
        temporary_file_paths=tracked_paths,
    )

    assert missing_key == []
    assert len(components) == 1
    assert isinstance(components[0], Comp.Video)
    await components[0]._resolve_deferred_source()
    assert components[0].file == "C:/tmp/video.mp4"
    assert tracked_paths == ["C:/tmp/video.mp4"]


@pytest.mark.asyncio
async def test_lark_parse_unknown_message_type_returns_empty_components():
    adapter = _adapter()

    components = await adapter._parse_message_components(
        message_id="msg-unknown",
        message_type="unsupported",
        content={"text": "ignored"},
        at_map={},
    )

    assert components == []


@pytest.mark.asyncio
async def test_lark_build_reply_from_parent_id_builds_reply_chain_from_message():
    adapter = _adapter()
    parent_message = SimpleNamespace(
        message_id="parent-1",
        sender=SimpleNamespace(id="open-parent-123456"),
        create_time=1710000000123,
        body=SimpleNamespace(content='{"text":"hello @_user_1"}'),
        msg_type="text",
        mentions=[
            SimpleNamespace(
                key="@_user_1",
                id=SimpleNamespace(open_id="ou_1"),
                name="Alice",
            )
        ],
    )
    adapter.lark_api.im.v1.message.aget = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(items=[parent_message]),
            code=0,
            msg="ok",
        )
    )

    reply = await adapter._build_reply_from_parent_id("parent-1")

    assert reply is not None
    assert reply.id == "parent-1"
    assert reply.sender_id == "open-parent-123456"
    assert reply.sender_nickname == "open-par"
    assert reply.time == 1710000000
    assert reply.message_str == "hello @Alice"
    assert reply.text == "hello @Alice"
    assert [type(component) for component in reply.chain] == [Comp.Plain, Comp.At]


@pytest.mark.asyncio
async def test_lark_build_reply_from_parent_id_falls_back_to_lightweight_reply_on_timeout():
    adapter = _adapter()
    adapter.lark_api.im.v1.message.aget = AsyncMock(side_effect=TimeoutError)

    reply = await adapter._build_reply_from_parent_id("parent-timeout")

    assert reply is not None
    assert reply.id == "parent-timeout"
    assert not reply.chain
    assert reply.message_str == ""


@pytest.mark.asyncio
async def test_lark_convert_msg_builds_group_message_with_reply_and_self_mention():
    adapter = _adapter()
    adapter._build_reply_from_parent_id = AsyncMock(
        return_value=Comp.Reply(
            id="parent-1",
            chain=[Comp.Plain("quoted")],
            sender_id="open-parent",
            sender_nickname="open-par",
            time=1,
            message_str="quoted",
            text="quoted",
        )
    )
    adapter.handle_msg = AsyncMock()
    event = SimpleNamespace(
        event=SimpleNamespace(
            message=SimpleNamespace(
                create_time="1710000000123",
                chat_type="group",
                chat_id="chat-group-1",
                parent_id="parent-1",
                mentions=[
                    SimpleNamespace(
                        key="@_user_1",
                        id=SimpleNamespace(open_id="bot-open"),
                        name="astrbot",
                    )
                ],
                content='{"text":"@_user_1 hi"}',
                message_type="text",
                message_id="msg-1",
            ),
            sender=SimpleNamespace(
                sender_id=SimpleNamespace(open_id="user-open-1"),
            ),
        )
    )

    await adapter.convert_msg(event)

    adapter._build_reply_from_parent_id.assert_awaited_once()
    assert adapter._build_reply_from_parent_id.await_args.args[0] == "parent-1"
    assert adapter._build_reply_from_parent_id.await_args.args[1] == []
    adapter.handle_msg.assert_awaited_once()
    abm = adapter.handle_msg.await_args.args[0]
    assert abm.type == MessageType.GROUP_MESSAGE
    assert abm.group_id == "chat-group-1"
    assert abm.session_id == "chat-group-1"
    assert abm.self_id == "bot-open"
    assert abm.sender.user_id == "user-open-1"
    assert abm.message_id == "msg-1"
    assert [type(component) for component in abm.message] == [
        Comp.Reply,
        Comp.At,
        Comp.Plain,
    ]
    assert abm.message[1].qq == "bot-open"
    assert abm.message[1].name == "astrbot"
    assert abm.message_str == "hi"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        "[]",
    ],
)
async def test_lark_convert_msg_rejects_bad_message_content(
    monkeypatch,
    content,
):
    adapter = _adapter()
    adapter.handle_msg = AsyncMock()
    log_mock = MagicMock()
    monkeypatch.setattr(lark_adapter_module.logger, "error", log_mock)

    event = SimpleNamespace(
        event=SimpleNamespace(
            message=SimpleNamespace(
                create_time="1710000000123",
                chat_type="p2p",
                chat_id="chat-1",
                parent_id=None,
                mentions=[],
                content=content,
                message_type="text",
                message_id="msg-1",
            ),
            sender=SimpleNamespace(
                sender_id=SimpleNamespace(open_id="user-open-1"),
            ),
        )
    )

    await adapter.convert_msg(event)

    adapter.handle_msg.assert_not_awaited()
    log_mock.assert_called_once()


@pytest.mark.asyncio
async def test_lark_convert_msg_returns_when_sender_or_message_id_missing(monkeypatch):
    adapter = _adapter()
    adapter.handle_msg = AsyncMock()
    logger_error = MagicMock()
    monkeypatch.setattr(lark_adapter_module.logger, "error", logger_error)

    event_missing_message_id = SimpleNamespace(
        event=SimpleNamespace(
            message=SimpleNamespace(
                create_time="1710000000123",
                chat_type="p2p",
                chat_id="chat-1",
                parent_id=None,
                mentions=[],
                content='{"text":"hello"}',
                message_type="text",
                message_id=None,
            ),
            sender=SimpleNamespace(
                sender_id=SimpleNamespace(open_id="user-open-1"),
            ),
        )
    )
    event_missing_sender = SimpleNamespace(
        event=SimpleNamespace(
            message=SimpleNamespace(
                create_time="1710000000123",
                chat_type="p2p",
                chat_id="chat-1",
                parent_id=None,
                mentions=[],
                content='{"text":"hello"}',
                message_type="text",
                message_id="msg-2",
            ),
            sender=SimpleNamespace(
                sender_id=SimpleNamespace(open_id=None),
            ),
        )
    )

    await adapter.convert_msg(event_missing_message_id)
    await adapter.convert_msg(event_missing_sender)

    adapter.handle_msg.assert_not_awaited()
    assert logger_error.call_count == 2


@pytest.mark.asyncio
async def test_lark_handle_webhook_event_deduplicates_and_dispatches_supported_events(
    monkeypatch,
):
    adapter = _adapter()
    adapter.do_v2_msg_event = MagicMock()

    class FakeProcessor:
        def __init__(self, callback):
            self.callback = callback

        def type(self):
            return lambda payload: {"parsed": payload}

        def do(self, data):
            self.callback(data)

    monkeypatch.setattr(
        lark_adapter_module,
        "P2ImMessageReceiveV1Processor",
        FakeProcessor,
    )

    payload = {
        "header": {
            "event_id": "evt-1",
            "event_type": "im.message.receive_v1",
        }
    }

    await adapter.handle_webhook_event(payload)
    await adapter.handle_webhook_event(payload)

    adapter.do_v2_msg_event.assert_called_once_with({"parsed": payload})


@pytest.mark.asyncio
async def test_lark_handle_webhook_event_swallows_processor_exceptions(monkeypatch):
    adapter = _adapter()

    class BrokenProcessor:
        def __init__(self, callback):
            self.callback = callback

        def type(self):
            raise RuntimeError("bad payload")

    monkeypatch.setattr(
        lark_adapter_module,
        "P2ImMessageReceiveV1Processor",
        BrokenProcessor,
    )

    await adapter.handle_webhook_event(
        {
            "header": {
                "event_id": "evt-2",
                "event_type": "im.message.receive_v1",
            }
        }
    )


@pytest.mark.asyncio
async def test_lark_download_file_resource_to_temp_returns_none_when_resource_missing():
    adapter = _adapter()
    adapter._download_message_resource = AsyncMock(return_value=None)

    result = await adapter._download_file_resource_to_temp(
        message_id="msg-3",
        file_key="file-3",
        message_type="file",
        file_name="report.pdf",
    )

    assert result is None
    adapter._download_message_resource.assert_awaited_once_with(
        message_id="msg-3",
        file_key="file-3",
        resource_type="file",
    )


@pytest.mark.asyncio
async def test_lark_webhook_callback_returns_500_when_server_missing():
    adapter = _adapter()
    adapter.webhook_server = None

    result = await adapter.webhook_callback(SimpleNamespace())

    assert result == ({"error": "Webhook server not initialized"}, 500)


def test_lark_clean_expired_events_drops_old_entries():
    adapter = _adapter()
    adapter.event_id_timestamps = {
        "old": 0.0,
        "fresh": 1_800_000_000.0,
    }

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(lark_adapter_module.time, "time", lambda: 1_800_001_000.0)
        adapter._clean_expired_events()

    assert adapter.event_id_timestamps == {"fresh": 1_800_000_000.0}


def test_lark_is_duplicate_event_records_new_ids_and_rejects_existing():
    adapter = _adapter()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(lark_adapter_module.time, "time", lambda: 1234.0)
        assert adapter._is_duplicate_event("evt-1") is False
        assert adapter.event_id_timestamps["evt-1"] == 1234.0
        assert adapter._is_duplicate_event("evt-1") is True


@pytest.mark.asyncio
async def test_lark_run_webhook_logs_when_server_missing_or_uuid_missing(monkeypatch):
    adapter = _adapter()
    adapter.connection_mode = "webhook"
    adapter.webhook_server = None
    adapter.config = {}
    adapter._refresh_bot_info = AsyncMock()
    logger_error = MagicMock()
    logger_warning = MagicMock()
    monkeypatch.setattr(lark_adapter_module.logger, "error", logger_error)
    monkeypatch.setattr(lark_adapter_module.logger, "warning", logger_warning)

    await adapter.run()

    logger_error.assert_called_once()

    adapter.webhook_server = SimpleNamespace()
    logger_error.reset_mock()
    adapter.config = {}

    await adapter.run()

    logger_warning.assert_called_once()
    logger_error.assert_not_called()


@pytest.mark.asyncio
async def test_lark_run_socket_mode_refresh_failure_does_not_block_connect(monkeypatch):
    adapter = _adapter()
    adapter.connection_mode = "socket"
    adapter.client = SimpleNamespace(_connect=AsyncMock())
    adapter._refresh_bot_info = AsyncMock(side_effect=RuntimeError("bot info failed"))
    logger_error = MagicMock()
    monkeypatch.setattr(lark_adapter_module.logger, "error", logger_error)

    await adapter.run()

    adapter.client._connect.assert_awaited_once()
    logger_error.assert_called_once()


def test_lark_unified_webhook_requires_webhook_mode_and_uuid():
    adapter = _adapter()
    adapter.config = {"lark_connection_mode": "webhook", "webhook_uuid": "uuid-1"}
    assert adapter.unified_webhook() is True

    adapter.config = {"lark_connection_mode": "socket", "webhook_uuid": "uuid-1"}
    assert adapter.unified_webhook() is False

    adapter.config = {"lark_connection_mode": "webhook"}
    assert adapter.unified_webhook() is False


def test_lark_create_event_does_not_promote_group_roles():
    from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember

    adapter = _adapter()
    adapter.config = {"id": "lark-test"}
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.group_id = "chat-1"
    message.session_id = "chat-1"
    message.sender = MessageMember("ou_1", "tester")
    message.raw_message = SimpleNamespace(sender=SimpleNamespace(role="owner"))
    message.message_str = "hello"
    message.message = []
    event = adapter.create_event(message)
    assert event.platform_member_role == "member"
    assert event.platform_role_source == "none"
