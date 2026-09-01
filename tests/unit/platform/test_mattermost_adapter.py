import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

import astrbot.api.message_components as Comp
from astrbot.api.event import MessageChain
from astrbot.api.platform import MessageType
from astrbot.core.platform.astrbot_message import Group
from astrbot.core.platform.sources.mattermost.client import MattermostClient
from astrbot.core.platform.sources.mattermost.mattermost_adapter import (
    MattermostPlatformAdapter,
)
from astrbot.core.platform.sources.mattermost.mattermost_event import (
    MattermostMessageEvent,
)
from tests.fixtures.helpers import make_platform_config

pytestmark = pytest.mark.platform


def _build_adapter() -> MattermostPlatformAdapter:
    adapter = MattermostPlatformAdapter(
        make_platform_config(
            "mattermost",
            id="test_mattermost",
            mattermost_url="https://chat.example.com",
            mattermost_bot_token="test_token",
            mattermost_reconnect_delay=5.0,
        ),
        {},
        asyncio.Queue(),
    )
    adapter.bot_self_id = "bot-id"
    adapter.bot_username = "bot"
    adapter._mention_pattern = adapter._build_mention_pattern(adapter.bot_username)
    return adapter


@pytest.mark.asyncio
async def test_mattermost_convert_message_strips_leading_self_mention():
    adapter = _build_adapter()

    result = await adapter.convert_message(
        post={
            "id": "post-1",
            "channel_id": "channel-1",
            "user_id": "user-1",
            "message": "@bot /help now",
            "create_at": 1_700_000_000_000,
            "file_ids": [],
        },
        data={
            "channel_type": "O",
            "sender_name": "alice",
        },
    )

    assert result is not None
    assert result.message_str == "/help now"
    assert isinstance(result.message[0], Comp.At)
    assert result.message[0].qq == "bot-id"
    assert any(
        isinstance(component, Comp.Plain) and component.text.strip() == "/help now"
        for component in result.message
    )


@pytest.mark.asyncio
async def test_mattermost_convert_message_returns_none_without_channel_id():
    adapter = _build_adapter()

    result = await adapter.convert_message(
        post={"id": "post-1", "user_id": "user-1", "message": "hello"},
        data={"channel_type": "O", "sender_name": "alice"},
    )

    assert result is None


@pytest.mark.asyncio
async def test_mattermost_convert_message_dm_sets_friend_type_and_attachments():
    adapter = _build_adapter()
    adapter.client.parse_post_attachments = AsyncMock(
        return_value=(
            [Comp.File(name="note.txt", file="/tmp/note.txt")],
            ["/tmp/note.txt"],
        )
    )

    result = await adapter.convert_message(
        post={
            "id": "post-2",
            "channel_id": "dm-1",
            "user_id": "user-2",
            "message": "hello there",
            "create_at": 1_700_000_000,
            "file_ids": ["file-1"],
            "metadata": {
                "files": [
                    {"id": "file-1", "name": "note.txt", "mime_type": "text/plain"}
                ]
            },
        },
        data={"channel_type": "D", "sender_name": "@bob"},
    )

    assert result is not None
    assert result.type is MessageType.FRIEND_MESSAGE
    assert result.group is None
    assert result.sender.nickname == "bob"
    assert result.message_str == "hello there"
    assert isinstance(result.message[-1], Comp.File)
    assert getattr(result, "temporary_file_paths") == ["/tmp/note.txt"]
    adapter.client.parse_post_attachments.assert_awaited_once_with(
        ["file-1"],
        [{"id": "file-1", "name": "note.txt", "mime_type": "text/plain"}],
    )


def test_mattermost_parse_text_components_without_bot_username_falls_back_to_plain():
    adapter = _build_adapter()
    adapter.bot_username = ""
    adapter._mention_pattern = None

    components = adapter._parse_text_components("@bot keep literal")

    assert len(components) == 1
    assert isinstance(components[0], Comp.Plain)
    assert components[0].text == "@bot keep literal"


def test_mattermost_build_message_str_only_skips_leading_self_mention():
    message_str = MattermostPlatformAdapter._build_message_str(
        [
            Comp.At(qq="bot-id", name="bot"),
            Comp.Plain(" hi "),
            Comp.At(qq="user-2", name="alice"),
            Comp.Plain(" there"),
        ],
        fallback="@bot hi @alice there",
        self_id="bot-id",
    )

    assert message_str == "hi @alice there"


def test_mattermost_parse_timestamp_handles_milliseconds_and_fallback():
    assert (
        MattermostPlatformAdapter._parse_timestamp(1_700_000_000_123) == 1_700_000_000
    )

    with patch(
        "astrbot.core.platform.sources.mattermost.mattermost_adapter.time.time",
        return_value=1234.9,
    ):
        assert MattermostPlatformAdapter._parse_timestamp("bad") == 1234


def test_mattermost_duplicate_post_tracking_prunes_expired_entries():
    adapter = _build_adapter()
    adapter._dedup_ttl = 10.0

    with patch(
        "astrbot.core.platform.sources.mattermost.mattermost_adapter.time.monotonic",
        side_effect=[100.0, 105.0, 121.0],
    ):
        assert adapter._is_duplicate_post("post-1") is False
        assert adapter._is_duplicate_post("post-1") is True
        assert adapter._is_duplicate_post("post-1") is False

    assert adapter._seen_post_ids == {"post-1": 121.0}
    assert list(adapter._seen_post_queue) == [("post-1", 121.0)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "parsed_post"),
    [
        ({"event": "typing"}, None),
        ({"event": "posted", "data": []}, None),
        ({"event": "posted", "data": {"post": 1}}, None),
        ({"event": "posted", "data": {"post": "{}"}}, {}),
        (
            {"event": "posted", "data": {"post": "{}"}},
            {"id": "p-1", "user_id": "bot-id", "message": "self"},
        ),
        (
            {"event": "posted", "data": {"post": "{}"}},
            {"id": "p-2", "user_id": "user-1", "type": "system_join_channel"},
        ),
    ],
)
async def test_mattermost_handle_ws_event_ignores_invalid_or_non_forwardable_posts(
    payload,
    parsed_post,
):
    adapter = _build_adapter()
    adapter.client.parse_websocket_post = MagicMock(return_value=parsed_post)
    adapter.convert_message = AsyncMock()
    adapter.handle_msg = AsyncMock()

    await adapter._handle_ws_event(payload)

    adapter.convert_message.assert_not_called()
    adapter.handle_msg.assert_not_called()


@pytest.mark.asyncio
async def test_mattermost_handle_ws_event_forwards_first_post_only_once():
    adapter = _build_adapter()
    payload = {
        "event": "posted",
        "data": {
            "post": '{"id":"post-3"}',
            "channel_type": "O",
            "sender_name": "alice",
        },
    }
    parsed_post = {
        "id": "post-3",
        "channel_id": "channel-3",
        "user_id": "user-3",
        "message": "hello",
    }
    converted = object()
    adapter.client.parse_websocket_post = MagicMock(return_value=parsed_post)
    adapter.convert_message = AsyncMock(return_value=converted)
    adapter.handle_msg = AsyncMock()

    await adapter._handle_ws_event(payload)
    await adapter._handle_ws_event(payload)

    adapter.convert_message.assert_awaited_once_with(
        post=parsed_post,
        data=payload["data"],
    )
    adapter.handle_msg.assert_awaited_once_with(converted)


@pytest.mark.asyncio
async def test_mattermost_handle_ws_event_skips_when_conversion_returns_none():
    adapter = _build_adapter()
    payload = {
        "event": "posted",
        "data": {
            "post": '{"id":"post-4"}',
            "channel_type": "O",
            "sender_name": "alice",
        },
    }
    parsed_post = {
        "id": "post-4",
        "channel_id": "channel-4",
        "user_id": "user-4",
        "message": "hello",
    }
    adapter.client.parse_websocket_post = MagicMock(return_value=parsed_post)
    adapter.convert_message = AsyncMock(return_value=None)
    adapter.handle_msg = AsyncMock()

    await adapter._handle_ws_event(payload)

    adapter.convert_message.assert_awaited_once_with(
        post=parsed_post,
        data=payload["data"],
    )
    adapter.handle_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_mattermost_send_by_session_uses_session_id_directly():
    adapter = _build_adapter()
    adapter.client.send_message_chain = AsyncMock()

    await adapter.send_by_session(
        SimpleNamespace(session_id="channel-9"),
        MessageChain().message("hello mattermost"),
    )

    adapter.client.send_message_chain.assert_awaited_once()
    assert adapter.client.send_message_chain.await_args.args == (
        "channel-9",
        MessageChain().message("hello mattermost"),
    )


def _build_event() -> MattermostMessageEvent:
    message_obj = SimpleNamespace(
        temporary_file_paths=["/tmp/a.txt", "/tmp/b.txt"],
        sender=SimpleNamespace(user_id="user-1", nickname="Alice"),
        type=MessageType.GROUP_MESSAGE,
        group_id="channel-1",
        session_id="channel-1",
        message_id="msg-1",
        self_id="bot-id",
        message=[],
        message_str="hello",
        raw_message={},
    )
    return MattermostMessageEvent(
        message_str="hello",
        message_obj=message_obj,
        platform_meta=SimpleNamespace(name="mattermost", id="mattermost-test"),
        session_id="channel-1",
        client=SimpleNamespace(
            send_message_chain=AsyncMock(),
            get_channel=AsyncMock(
                return_value={"display_name": "Town Square", "name": "town-square"}
            ),
            get_channel_stats=AsyncMock(return_value={"member_count": 1}),
            get_channel_members=AsyncMock(
                return_value=[{"user_id": "user-1", "roles": "channel_user"}]
            ),
            get_users_by_ids=AsyncMock(
                return_value=[
                    {"id": "user-1", "nickname": "Alice", "username": "alice"}
                ]
            ),
        ),
    )


def test_mattermost_event_tracks_temporary_file_paths_for_cleanup():
    event = _build_event()

    assert set(event._temporary_local_files) == {"/tmp/a.txt", "/tmp/b.txt"}


@pytest.mark.asyncio
async def test_mattermost_event_send_forwards_message_chain():
    event = _build_event()

    with patch.object(
        MattermostMessageEvent.__mro__[1],
        "send",
        AsyncMock(return_value=None),
    ) as parent_send:
        await event.send(MessageChain().message("hello"))

    event._client.send_message_chain.assert_awaited_once_with(
        "channel-1",
        MessageChain().message("hello"),
    )
    parent_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_mattermost_event_send_streaming_non_fallback_batches_once():
    event = _build_event()
    event.send = AsyncMock()

    async def generator():
        yield MessageChain().message("Hello ")
        yield MessageChain().message("Mattermost")

    with patch.object(
        MattermostMessageEvent.__mro__[1],
        "send_streaming",
        AsyncMock(return_value=None),
    ) as parent_send_streaming:
        result = await event.send_streaming(generator())

    assert result is None
    event.send.assert_awaited_once()
    sent_chain = event.send.await_args.args[0]
    assert sent_chain.get_plain_text() == "Hello Mattermost"
    parent_send_streaming.assert_awaited_once()


@pytest.mark.asyncio
async def test_mattermost_event_send_streaming_non_fallback_ignores_empty_generator():
    event = _build_event()
    event.send = AsyncMock()

    async def generator():
        if False:
            yield MessageChain().message("never")

    with patch.object(
        MattermostMessageEvent.__mro__[1],
        "send_streaming",
        AsyncMock(return_value=None),
    ) as parent_send_streaming:
        result = await event.send_streaming(generator())

    assert result is None
    event.send.assert_not_awaited()
    parent_send_streaming.assert_awaited_once()


@pytest.mark.asyncio
async def test_mattermost_event_send_streaming_fallback_flushes_sentences_and_media():
    event = _build_event()
    event.send = AsyncMock()

    async def generator():
        yield MessageChain([Comp.Plain("第一句。第二句")])
        yield MessageChain([Comp.Image(file="/tmp/image.png")])
        yield MessageChain([Comp.Plain("第三句！")])

    with (
        patch.object(
            MattermostMessageEvent.__mro__[1],
            "send_streaming",
            AsyncMock(return_value=None),
        ) as parent_send_streaming,
        patch(
            "astrbot.core.platform.sources.mattermost.mattermost_event.asyncio.sleep",
            AsyncMock(),
        ),
    ):
        result = await event.send_streaming(generator(), use_fallback=True)

    assert result is None
    assert event.send.await_args_list == [
        call(MessageChain([Comp.Plain("第一句。")])),
        call(MessageChain(chain=[Comp.Image(file="/tmp/image.png")])),
        call(MessageChain([Comp.Plain("第二句第三句！")])),
    ]
    parent_send_streaming.assert_awaited_once()


@pytest.mark.asyncio
async def test_mattermost_event_get_group_maps_channel_display_name():
    event = _build_event()

    group = await event.get_group()

    assert group is not None
    assert group.group_id == "channel-1"
    assert group.group_name == "Town Square"
    assert group.member_count == 1
    assert group.members[0].user_id == "user-1"
    assert group.members[0].nickname == "Alice"


@pytest.mark.asyncio
async def test_mattermost_get_group_caps_member_pages_and_omits_truncated_list():
    event = _build_event()
    event.message_obj.group = Group(group_id="channel-1", group_name="cached")

    async def endless_members(channel_id, *, page, per_page):
        del channel_id
        return [
            {"user_id": f"user-{page}-{index}", "roles": "channel_user"}
            for index in range(per_page)
        ]

    event._client.get_channel_stats = AsyncMock(return_value={"member_count": 2500})
    event._client.get_channel_members = AsyncMock(side_effect=endless_members)
    event._client.get_users_by_ids = AsyncMock()

    group = await event.get_group()

    assert group is not event.message_obj.group
    assert group.member_count == 2500
    assert group.members is None
    assert event._client.get_channel_members.await_count == 10
    event._client.get_users_by_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_mattermost_event_get_group_returns_none_without_channel_id():
    event = _build_event()
    event.message_obj.group_id = None
    event.message_obj.session_id = ""

    group = await event.get_group(group_id=None)

    assert group is None
    event._client.get_channel.assert_not_awaited()


@pytest.mark.asyncio
async def test_mattermost_event_send_streaming_fallback_flushes_remaining_plain_text():
    event = _build_event()
    event.send = AsyncMock()

    async def generator():
        yield MessageChain([Comp.Plain("tail without punctuation")])

    with patch.object(
        MattermostMessageEvent.__mro__[1],
        "send_streaming",
        AsyncMock(return_value=None),
    ) as parent_send_streaming:
        result = await event.send_streaming(generator(), use_fallback=True)

    assert result is None
    event.send.assert_awaited_once_with(
        MessageChain([Comp.Plain("tail without punctuation")])
    )
    parent_send_streaming.assert_awaited_once()


@pytest.mark.asyncio
async def test_mattermost_ws_connect_and_listen_skips_non_json_text_frame(monkeypatch):
    adapter = _build_adapter()
    logger_debug = MagicMock()
    ws = MagicMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()

    class _WSMessage:
        def __init__(self, data: str) -> None:
            self.type = 1
            self.data = data

    class _AsyncWS:
        def __init__(self, messages):
            self._messages = iter(messages)
            self.send_json = AsyncMock()
            self.close = AsyncMock()

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._messages)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    ws = _AsyncWS([_WSMessage("not-json"), SimpleNamespace(type=257, data="")])
    adapter.client.ws_connect = AsyncMock(return_value=ws)
    adapter._handle_ws_event = AsyncMock()

    monkeypatch.setattr(
        "astrbot.core.platform.sources.mattermost.mattermost_adapter.logger.debug",
        logger_debug,
    )

    await adapter._ws_connect_and_listen()

    ws.send_json.assert_awaited_once()
    adapter._handle_ws_event.assert_not_awaited()
    logger_debug.assert_called_once()
    ws.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_mattermost_ws_connect_and_listen_background_dispatches_payloads():
    adapter = _build_adapter()
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    release_first = asyncio.Event()

    async def _handle(payload):
        post = payload["data"]["post"]
        if post == '{"id":"first"}':
            first_started.set()
            await release_first.wait()
            return
        if post == '{"id":"second"}':
            second_started.set()

    class _WSMessage:
        def __init__(self, data: str) -> None:
            self.type = 1
            self.data = data

    class _AsyncWS:
        def __init__(self, messages):
            self._messages = iter(messages)
            self.send_json = AsyncMock()
            self.close = AsyncMock()

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._messages)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    ws = _AsyncWS(
        [
            _WSMessage('{"event":"posted","data":{"post":"{\\"id\\":\\"first\\"}"}}'),
            _WSMessage('{"event":"posted","data":{"post":"{\\"id\\":\\"second\\"}"}}'),
            SimpleNamespace(type=257, data=""),
        ]
    )
    adapter.client.ws_connect = AsyncMock(return_value=ws)
    adapter._handle_ws_event = AsyncMock(side_effect=_handle)

    listener_task = asyncio.create_task(adapter._ws_connect_and_listen())
    await asyncio.wait_for(first_started.wait(), timeout=1.0)
    await asyncio.wait_for(second_started.wait(), timeout=1.0)
    release_first.set()
    await listener_task

    ws.send_json.assert_awaited_once()
    ws.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_mattermost_parse_post_attachments_maps_media_types(tmp_path):
    client = MattermostClient("https://chat.example.com", "test_token")

    file_infos = {
        "img": {"name": "image.png", "mime_type": "image/png"},
        "audio": {"name": "voice.ogg", "mime_type": "audio/ogg"},
        "video": {"name": "clip.mp4", "mime_type": "video/mp4"},
        "doc": {"name": "report.pdf", "mime_type": "application/pdf"},
    }

    client.get_file_info = AsyncMock(side_effect=lambda file_id: file_infos[file_id])
    client.download_file = AsyncMock(return_value=b"payload")

    with patch(
        "astrbot.core.platform.sources.mattermost.client.get_astrbot_temp_path",
        MagicMock(return_value=str(tmp_path)),
    ):
        components, temp_paths = await client.parse_post_attachments(
            ["img", "audio", "video", "doc"]
        )

    assert len(components) == 4
    assert isinstance(components[0], Comp.Image)
    assert isinstance(components[1], Comp.Record)
    assert components[1].file == ""
    assert components[1].url == ""
    assert isinstance(components[2], Comp.Video)
    assert isinstance(components[3], Comp.File)
    assert temp_paths == []
    client.download_file.assert_not_awaited()

    image_path = await components[0].convert_to_file_path()
    record_path = await components[1]._resolve_file_source()
    video_path = await components[2]._resolve_file_source()
    file_path = await components[3].get_file()

    assert len(temp_paths) == 4
    assert client.download_file.await_count == 4
    resolved_paths = [image_path, record_path, video_path, file_path]
    expected_names = ["image.png", "voice.ogg", "clip.mp4", "report.pdf"]
    for temp_path, expected_name in zip(resolved_paths, expected_names):
        path = Path(temp_path)
        assert path.exists()
        assert path.name.endswith(Path(expected_name).suffix)


@pytest.mark.asyncio
async def test_mattermost_parse_post_attachments_uses_post_metadata_without_fetching_info():
    client = MattermostClient("https://chat.example.com", "test_token")
    client.get_file_info = AsyncMock()
    client.download_file = AsyncMock(return_value=b"payload")

    components, temp_paths = await client.parse_post_attachments(
        ["img", "doc"],
        [
            {"id": "img", "name": "image.png", "mime_type": "image/png"},
            {"id": "doc", "name": "report.pdf", "mime_type": "application/pdf"},
        ],
    )

    assert len(components) == 2
    assert isinstance(components[0], Comp.Image)
    assert isinstance(components[1], Comp.File)
    assert temp_paths == []
    client.get_file_info.assert_not_awaited()
    client.download_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_mattermost_parse_post_attachments_fetches_info_when_metadata_lacks_mime_type():
    client = MattermostClient("https://chat.example.com", "test_token")
    client.get_file_info = AsyncMock(
        return_value={"name": "voice.ogg", "mime_type": "audio/ogg"}
    )
    client.download_file = AsyncMock(return_value=b"payload")

    components, _temp_paths = await client.parse_post_attachments(
        ["audio"],
        [{"id": "audio", "name": "voice.ogg"}],
    )

    assert len(components) == 1
    assert isinstance(components[0], Comp.Record)
    client.get_file_info.assert_awaited_once_with("audio")


def test_mattermost_create_event_does_not_promote_channel_roles():
    from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember

    adapter = _build_adapter()
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.group_id = "chan-1"
    message.session_id = "chan-1"
    message.sender = MessageMember("user-1", "tester")
    message.raw_message = {"roles": "channel_admin", "is_admin": True}
    message.message_str = "hello"
    message.message = []
    event = adapter.create_event(message)
    assert event.platform_member_role == "member"
    assert event.platform_role_source == "none"
