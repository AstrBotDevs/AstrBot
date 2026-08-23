import asyncio
import base64
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.api.message_components import Image, Record
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import MessageSession
from astrbot.core.platform.route_identity import PlatformRouteIdentity
from astrbot.core.platform.sources.discord import (
    discord_platform_adapter,
    discord_platform_event,
)
from astrbot.core.platform.sources.discord.client import DiscordBotClient
from astrbot.core.platform.sources.discord.discord_platform_adapter import (
    DiscordPlatformAdapter,
)
from astrbot.core.platform.sources.discord.discord_platform_event import (
    DiscordPlatformEvent,
)

pytestmark = pytest.mark.platform


_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)
_WAV_BYTES = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16
_WAV_PATH = "/tmp/discord_voice.wav"


def _discord_platform_meta():
    return SimpleNamespace(id="discord", name="discord")


def _discord_route_identity(target_id: str):
    return PlatformRouteIdentity(
        platform_id="discord",
        message_type=discord_platform_adapter.MessageType.GROUP_MESSAGE,
        target_id=target_id,
    )


@pytest.mark.asyncio
async def test_discord_audio_attachment_keeps_remote_record_lazy():
    adapter = DiscordPlatformAdapter.__new__(DiscordPlatformAdapter)
    adapter.bot_self_id = "1"
    adapter.client = SimpleNamespace(user=SimpleNamespace(id=1))

    message = SimpleNamespace(
        id=42,
        content="",
        channel=SimpleNamespace(id=123, guild=None),
        author=SimpleNamespace(id=2, display_name="tester"),
        attachments=[
            SimpleNamespace(
                content_type="audio/ogg",
                filename="voice.ogg",
                url="https://cdn.example/voice.ogg",
            )
        ],
        guild=None,
        role_mentions=[],
    )

    abm = await adapter.convert_message({"message": message})

    assert len(abm.message) == 1
    assert isinstance(abm.message[0], Record)
    assert abm.message[0].file == "https://cdn.example/voice.ogg"
    assert abm.message[0].url == "https://cdn.example/voice.ogg"
    assert abm.message[0].path is None


@pytest.mark.asyncio
async def test_discord_client_on_message_background_dispatches_callback():
    client = DiscordBotClient.__new__(DiscordBotClient)
    client.allow_bot_messages = False
    client._message_tasks = set()

    started = asyncio.Event()
    release = asyncio.Event()

    async def _callback(_payload: dict) -> None:
        started.set()
        await release.wait()

    client.on_message_received = _callback
    client._create_message_data = lambda _message: {"content": "hello"}  # type: ignore[method-assign]

    message = SimpleNamespace(
        author=SimpleNamespace(bot=False, name="tester"),
        content="hello",
    )

    await client.on_message(message)

    await asyncio.wait_for(started.wait(), timeout=1.0)
    release.set()
    if client._message_tasks:
        await asyncio.gather(*list(client._message_tasks), return_exceptions=True)


@pytest.mark.asyncio
async def test_discord_send_image_resolves_data_uri_with_media_resolver(monkeypatch):
    captured = {}

    class FakeDiscordFile:
        def __init__(self, fp: BytesIO, filename: str) -> None:
            captured["bytes"] = fp.read()
            captured["filename"] = filename

    monkeypatch.setattr(discord_platform_event.discord, "File", FakeDiscordFile)

    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    image_base64 = base64.b64encode(_PNG_BYTES).decode("ascii")

    content, files, view, embeds, reference_message_id = await event._parse_to_discord(
        MessageChain(
            chain=[
                Image(file=f"data:image/png;base64,{image_base64}"),
            ]
        )
    )

    assert content == ""
    assert len(files) == 1
    assert captured["bytes"] == _PNG_BYTES
    assert captured["filename"] == "image.png"
    assert view is None
    assert embeds == []
    assert reference_message_id is None


@pytest.mark.asyncio
async def test_discord_send_record_resolves_audio_with_media_resolver(monkeypatch):
    captured = {}

    class FakeDiscordFile:
        def __init__(self, fp: BytesIO, filename: str) -> None:
            captured["bytes"] = fp.read()
            captured["filename"] = filename

    monkeypatch.setattr(discord_platform_event.discord, "File", FakeDiscordFile)

    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    audio_base64 = base64.b64encode(_WAV_BYTES).decode("ascii")

    content, files, view, embeds, reference_message_id = await event._parse_to_discord(
        MessageChain(
            chain=[
                Record.fromBase64(audio_base64),
            ]
        )
    )

    assert content == ""
    assert len(files) == 1
    assert captured["bytes"] == _WAV_BYTES
    assert captured["filename"] == "audio.wav"
    assert view is None
    assert embeds == []
    assert reference_message_id is None


@pytest.mark.asyncio
async def test_discord_convert_message_strips_bot_and_role_mentions_and_keeps_plain_text():
    adapter = DiscordPlatformAdapter.__new__(DiscordPlatformAdapter)
    adapter.bot_self_id = "1"
    adapter.client = SimpleNamespace(user=SimpleNamespace(id=1))
    guild = SimpleNamespace(
        get_member=lambda _user_id: SimpleNamespace(roles=[SimpleNamespace(id=888)])
    )
    message = SimpleNamespace(
        id=43,
        content="<@1> <@&888> summarize this",
        channel=SimpleNamespace(id=321, guild=guild),
        author=SimpleNamespace(id=2, display_name="tester"),
        attachments=[],
        guild=guild,
        role_mentions=[SimpleNamespace(id=888)],
    )

    abm = await adapter.convert_message({"message": message})

    assert abm.message_str == "summarize this"
    assert len(abm.message) == 1
    assert abm.message[0].text == "summarize this"


@pytest.mark.asyncio
async def test_discord_convert_message_maps_unknown_attachment_to_file_component():
    adapter = DiscordPlatformAdapter.__new__(DiscordPlatformAdapter)
    adapter.bot_self_id = "1"
    adapter.client = SimpleNamespace(user=SimpleNamespace(id=1))

    message = SimpleNamespace(
        id=44,
        content="see file",
        channel=SimpleNamespace(id=555, guild=None),
        author=SimpleNamespace(id=2, display_name="tester"),
        attachments=[
            SimpleNamespace(
                content_type=None,
                filename="archive.zip",
                url="https://cdn.example/archive.zip",
            )
        ],
        guild=None,
        role_mentions=[],
    )

    abm = await adapter.convert_message({"message": message})

    assert abm.message_str == "see file"
    assert abm.message[0].text == "see file"
    assert abm.message[1].name == "archive.zip"
    assert abm.message[1].url == "https://cdn.example/archive.zip"


@pytest.mark.asyncio
async def test_discord_convert_message_strips_nickname_mention_prefix():
    adapter = DiscordPlatformAdapter.__new__(DiscordPlatformAdapter)
    adapter.bot_self_id = "1"
    adapter.client = SimpleNamespace(user=SimpleNamespace(id=1))

    message = SimpleNamespace(
        id=45,
        content="<@!1> please summarize",
        channel=SimpleNamespace(id=556, guild=None),
        author=SimpleNamespace(id=2, display_name="tester"),
        attachments=[],
        guild=None,
        role_mentions=[],
    )

    abm = await adapter.convert_message({"message": message})

    assert abm.message_str == "please summarize"
    assert len(abm.message) == 1
    assert abm.message[0].text == "please summarize"


@pytest.mark.asyncio
async def test_discord_handle_msg_sets_wake_when_bot_role_is_mentioned(monkeypatch):
    class FakeDiscordMessage:
        pass

    class FakeRole:
        def __init__(self, role_id: int) -> None:
            self.id = role_id

        def __hash__(self) -> int:
            return hash(self.id)

        def __eq__(self, other) -> bool:
            return isinstance(other, FakeRole) and self.id == other.id

    monkeypatch.setattr(discord_platform_adapter.discord, "Message", FakeDiscordMessage)

    adapter = DiscordPlatformAdapter.__new__(DiscordPlatformAdapter)
    adapter.client = SimpleNamespace(user=SimpleNamespace(id=1))
    committed_events = []
    adapter.commit_event = committed_events.append

    role = FakeRole(888)
    guild = SimpleNamespace(get_member=lambda _user_id: SimpleNamespace(roles=[role]))
    raw_message = FakeDiscordMessage()
    raw_message.mentions = []
    raw_message.role_mentions = [role]
    raw_message.guild = guild

    message = SimpleNamespace(
        raw_message=raw_message,
        message_str="hello",
        session_id="555",
        message=[],
    )

    def fake_create_event(_message, _followup_webhook=None):
        return SimpleNamespace(
            interaction_followup_webhook=None,
            is_wake=False,
            is_at_or_wake_command=False,
        )

    adapter.create_event = fake_create_event

    await adapter.handle_msg(message)

    assert len(committed_events) == 1
    assert committed_events[0].is_wake is True
    assert committed_events[0].is_at_or_wake_command is True


@pytest.mark.asyncio
async def test_discord_handle_msg_skips_when_client_not_ready():
    adapter = DiscordPlatformAdapter.__new__(DiscordPlatformAdapter)
    adapter.config = {"id": "test_discord"}
    adapter.client = SimpleNamespace(user=None)
    adapter.commit_event = MagicMock()

    message = SimpleNamespace(
        raw_message=object(),
        message_str="hello",
        session_id="555",
        message=[],
    )

    adapter.create_event = MagicMock(
        return_value=SimpleNamespace(interaction_followup_webhook=None)
    )

    await adapter.handle_msg(message)

    adapter.commit_event.assert_not_called()


@pytest.mark.asyncio
async def test_discord_handle_msg_ignores_non_message_raw_payload(monkeypatch):
    class FakeDiscordMessage:
        pass

    monkeypatch.setattr(discord_platform_adapter.discord, "Message", FakeDiscordMessage)

    adapter = DiscordPlatformAdapter.__new__(DiscordPlatformAdapter)
    adapter.client = SimpleNamespace(user=SimpleNamespace(id=1))
    adapter.commit_event = MagicMock()

    message = SimpleNamespace(
        raw_message=object(),
        message_str="hello",
        session_id="555",
        message=[],
    )

    def fake_create_event(_message, _followup_webhook=None):
        return SimpleNamespace(
            interaction_followup_webhook=None,
            is_wake=False,
            is_at_or_wake_command=False,
        )

    adapter.create_event = fake_create_event

    await adapter.handle_msg(message)

    adapter.commit_event.assert_not_called()


@pytest.mark.asyncio
async def test_discord_handle_msg_slash_command_wakes_without_mention_checks():
    adapter = DiscordPlatformAdapter.__new__(DiscordPlatformAdapter)
    adapter.client = SimpleNamespace(user=SimpleNamespace(id=1))
    committed_events = []
    adapter.commit_event = committed_events.append

    message = SimpleNamespace(
        raw_message=object(),
        message_str="/hello",
        session_id="555",
        message=[],
    )

    def fake_create_event(_message, _followup_webhook=None):
        return SimpleNamespace(
            interaction_followup_webhook=object(),
            is_wake=False,
            is_at_or_wake_command=False,
        )

    adapter.create_event = fake_create_event

    await adapter.handle_msg(message, followup_webhook=object())

    assert len(committed_events) == 1
    assert committed_events[0].is_wake is True
    assert committed_events[0].is_at_or_wake_command is True


@pytest.mark.asyncio
async def test_discord_send_by_session_guesses_group_when_channel_id_is_invalid():
    adapter = DiscordPlatformAdapter.__new__(DiscordPlatformAdapter)
    adapter.config = {"id": "test_discord"}
    adapter._background_tasks = set()
    adapter.bot_self_id = "1"
    adapter.client = SimpleNamespace(user=SimpleNamespace(display_name="bot"))
    temp_event = SimpleNamespace(send=AsyncMock())
    seen_messages = []

    def fake_create_event(message_obj, _followup_webhook=None):
        seen_messages.append(message_obj)
        return temp_event

    adapter.create_event = fake_create_event

    await adapter.send_by_session(
        MessageSession(
            "discord", discord_platform_adapter.MessageType.GROUP_MESSAGE, "bad-channel"
        ),
        MessageChain(chain=[]).message("hello"),
    )

    temp_event.send.assert_awaited_once()
    assert seen_messages[0].type == discord_platform_adapter.MessageType.GROUP_MESSAGE
    assert seen_messages[0].group_id == "bad-channel"
    assert seen_messages[0].session_id == "bad-channel"
    assert seen_messages[0].message_str == "hello"


@pytest.mark.asyncio
async def test_discord_send_by_session_returns_early_when_client_not_ready():
    adapter = DiscordPlatformAdapter.__new__(DiscordPlatformAdapter)
    adapter.config = {"id": "test_discord"}
    adapter.bot_self_id = "1"
    adapter.client = SimpleNamespace(user=None)
    adapter.create_event = MagicMock()

    await adapter.send_by_session(
        MessageSession(
            "discord", discord_platform_adapter.MessageType.FRIEND_MESSAGE, "123"
        ),
        MessageChain(chain=[]).message("hello"),
    )

    adapter.create_event.assert_not_called()


@pytest.mark.asyncio
async def test_discord_send_by_session_uses_friend_message_for_dm_channel():
    adapter = DiscordPlatformAdapter.__new__(DiscordPlatformAdapter)
    adapter.config = {"id": "test_discord"}
    adapter._background_tasks = set()
    adapter.bot_self_id = "1"
    adapter.client = SimpleNamespace(
        user=SimpleNamespace(display_name="bot"),
        get_channel=MagicMock(return_value=SimpleNamespace(id=321, guild=None)),
    )
    temp_event = SimpleNamespace(send=AsyncMock())
    seen_messages = []

    def fake_create_event(message_obj, _followup_webhook=None):
        seen_messages.append(message_obj)
        return temp_event

    adapter.create_event = fake_create_event

    await adapter.send_by_session(
        MessageSession(
            "discord", discord_platform_adapter.MessageType.FRIEND_MESSAGE, "321"
        ),
        MessageChain(chain=[]).message("hello dm"),
    )

    temp_event.send.assert_awaited_once()
    assert seen_messages[0].type == discord_platform_adapter.MessageType.FRIEND_MESSAGE
    assert seen_messages[0].group_id == "321"
    assert seen_messages[0].session_id == "321"


@pytest.mark.asyncio
async def test_discord_event_send_uses_reference_for_regular_messages_only(monkeypatch):
    client = SimpleNamespace(
        get_message=MagicMock(return_value="reply-ref"),
        get_channel=MagicMock(),
        fetch_channel=AsyncMock(),
    )
    channel = SimpleNamespace(send=AsyncMock(), id=123)

    regular_event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    regular_event._client = client
    regular_event.interaction_followup_webhook = None
    regular_event._background_tasks = set()
    regular_event._extras = {}
    regular_event.session = MessageSession(
        "discord",
        discord_platform_adapter.MessageType.GROUP_MESSAGE,
        "123",
    )
    regular_event.platform_meta = _discord_platform_meta()
    regular_event.route_identity = _discord_route_identity("123")
    regular_event.message_obj = SimpleNamespace(
        sender=SimpleNamespace(user_id="1"),
        type=discord_platform_adapter.MessageType.GROUP_MESSAGE,
        group_id="123",
    )
    regular_event._parse_to_discord = AsyncMock(
        return_value=("hello", [], None, [], "42")
    )
    regular_event._get_channel = AsyncMock(return_value=channel)
    monkeypatch.setattr(discord_platform_event.discord.abc, "Messageable", object)

    await regular_event.send(MessageChain().message("hello"))

    sent_kwargs = channel.send.await_args.kwargs
    assert sent_kwargs["content"] == "hello"
    assert sent_kwargs["reference"] == "reply-ref"

    followup = SimpleNamespace(send=AsyncMock())
    followup_event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    followup_event._client = client
    followup_event.interaction_followup_webhook = followup
    followup_event._background_tasks = set()
    followup_event._extras = {}
    followup_event.session = MessageSession(
        "discord",
        discord_platform_adapter.MessageType.GROUP_MESSAGE,
        "123",
    )
    followup_event.platform_meta = _discord_platform_meta()
    followup_event.route_identity = _discord_route_identity("123")
    followup_event.message_obj = regular_event.message_obj
    followup_event._parse_to_discord = AsyncMock(
        return_value=("hello", [], None, [], "42")
    )

    await followup_event.send(MessageChain().message("hello"))

    assert "reference" not in followup.send.await_args.kwargs


@pytest.mark.asyncio
async def test_discord_event_send_ignores_empty_payload():
    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    event._client = SimpleNamespace()
    event.interaction_followup_webhook = None
    event.platform_meta = _discord_platform_meta()
    event.route_identity = _discord_route_identity("123")
    event._parse_to_discord = AsyncMock(return_value=("", [], None, [], None))
    event._get_channel = AsyncMock()

    with patch.object(
        discord_platform_event.AstrMessageEvent,
        "send",
        AsyncMock(return_value=None),
    ) as parent_send:
        await event.send(MessageChain(chain=[]))

    event._get_channel.assert_not_awaited()
    parent_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_discord_event_send_skips_non_messageable_channel(monkeypatch):
    client = SimpleNamespace()
    channel = SimpleNamespace(id=123)
    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    event._client = client
    event.interaction_followup_webhook = None
    event.platform_meta = _discord_platform_meta()
    event.route_identity = _discord_route_identity("123")
    event._parse_to_discord = AsyncMock(return_value=("hello", [], None, [], None))
    event._get_channel = AsyncMock(return_value=channel)
    monkeypatch.setattr(
        discord_platform_event.discord.abc,
        "Messageable",
        type("FakeMessageable", (), {}),
    )

    with patch.object(
        discord_platform_event.AstrMessageEvent,
        "send",
        AsyncMock(return_value=None),
    ) as parent_send:
        await event.send(MessageChain().message("hello"))

    parent_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_discord_event_get_channel_uses_fetch_when_cache_misses():
    client = SimpleNamespace(
        get_channel=MagicMock(return_value=None),
        fetch_channel=AsyncMock(return_value="fetched-channel"),
    )
    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    event._client = client
    event.route_identity = _discord_route_identity("456")

    result = await event._get_channel()

    assert result == "fetched-channel"
    client.get_channel.assert_called_once_with(456)
    client.fetch_channel.assert_awaited_once_with(456)


@pytest.mark.asyncio
async def test_discord_event_get_channel_returns_none_for_invalid_session_id():
    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    event._client = SimpleNamespace(get_channel=MagicMock(), fetch_channel=AsyncMock())
    event.route_identity = _discord_route_identity("not-a-number")

    result = await event._get_channel()

    assert result is None
    event._client.get_channel.assert_not_called()
    event._client.fetch_channel.assert_not_awaited()


@pytest.mark.asyncio
async def test_discord_event_get_channel_returns_none_when_fetch_forbidden(monkeypatch):
    forbidden_error = discord_platform_event.discord.errors.Forbidden(
        response=SimpleNamespace(status=403, reason="Forbidden"),
        message="forbidden",
    )
    client = SimpleNamespace(
        get_channel=MagicMock(return_value=None),
        fetch_channel=AsyncMock(side_effect=forbidden_error),
    )
    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    event._client = client
    event.route_identity = _discord_route_identity("456")
    logger_error = MagicMock()

    monkeypatch.setattr(discord_platform_event.logger, "error", logger_error)

    result = await event._get_channel()

    assert result is None
    client.get_channel.assert_called_once_with(456)
    client.fetch_channel.assert_awaited_once_with(456)
    logger_error.assert_called_once()


@pytest.mark.asyncio
async def test_discord_event_send_streaming_aggregates_plain_segments_once():
    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    event.send = AsyncMock()

    async def generator():
        yield MessageChain().message("Hello ")
        yield MessageChain().message("Discord")

    with patch.object(
        discord_platform_event.AstrMessageEvent,
        "send_streaming",
        AsyncMock(return_value="stream-finished"),
    ) as parent_send_streaming:
        result = await event.send_streaming(generator())

    assert result == "stream-finished"
    event.send.assert_awaited_once()
    sent_chain = event.send.await_args.args[0]
    assert len(sent_chain.chain) == 1
    assert sent_chain.chain[0].text == "Hello Discord"
    parent_send_streaming.assert_awaited_once()


@pytest.mark.asyncio
async def test_discord_event_send_swallow_followup_send_error_without_parent_success_side_effect(
    monkeypatch,
):
    followup = SimpleNamespace(
        send=AsyncMock(side_effect=RuntimeError("followup failed"))
    )
    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    event._client = SimpleNamespace(get_message=MagicMock())
    event.interaction_followup_webhook = followup
    event.platform_meta = _discord_platform_meta()
    event.route_identity = _discord_route_identity("123")
    event._parse_to_discord = AsyncMock(return_value=("hello", [], None, [], None))
    logger_error = MagicMock()

    monkeypatch.setattr(discord_platform_event.logger, "error", logger_error)

    with patch.object(
        discord_platform_event.AstrMessageEvent,
        "send",
        AsyncMock(return_value=None),
    ) as parent_send:
        result = await event.send(MessageChain().message("hello"))

    followup.send.assert_awaited_once_with(content="hello")
    parent_send.assert_not_awaited()
    logger_error.assert_called_once()
    assert result.success is False
    assert result.target == "123"


@pytest.mark.asyncio
async def test_discord_parse_to_discord_converts_remote_image_to_embed():
    class FakeEmbed:
        def __init__(self) -> None:
            self.image_url = None

        def set_image(self, *, url: str):
            self.image_url = url
            return self

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(discord_platform_event.discord, "Embed", FakeEmbed)
    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)

    try:
        (
            content,
            files,
            view,
            embeds,
            reference_message_id,
        ) = await event._parse_to_discord(
            MessageChain(chain=[Image(file="https://cdn.example/image.png")])
        )
    finally:
        monkeypatch.undo()

    assert content == ""
    assert files == []
    assert view is None
    assert len(embeds) == 1
    assert embeds[0].image_url == "https://cdn.example/image.png"
    assert reference_message_id is None


@pytest.mark.asyncio
async def test_discord_parse_to_discord_skips_missing_file_path():
    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    file_component = discord_platform_event.File(
        name="report.txt", url="https://cdn.example/report.txt"
    )

    with patch.object(
        type(file_component),
        "get_file",
        AsyncMock(return_value=None),
    ):
        (
            content,
            files,
            view,
            embeds,
            reference_message_id,
        ) = await event._parse_to_discord(MessageChain(chain=[file_component]))

    assert content == ""
    assert files == []
    assert view is None
    assert embeds == []
    assert reference_message_id is None


@pytest.mark.asyncio
async def test_discord_parse_to_discord_skips_record_without_file_or_url():
    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    record = discord_platform_event.Record(file=None)

    content, files, view, embeds, reference_message_id = await event._parse_to_discord(
        MessageChain(chain=[record])
    )

    assert content == ""
    assert files == []
    assert view is None
    assert embeds == []
    assert reference_message_id is None


@pytest.mark.asyncio
async def test_discord_parse_to_discord_keeps_long_content_and_reply_id():
    event = DiscordPlatformEvent.__new__(DiscordPlatformEvent)
    long_text = "A" * 2100

    content, files, view, embeds, reference_message_id = await event._parse_to_discord(
        MessageChain(
            chain=[
                discord_platform_event.Reply(id="77", chain=[]),
                discord_platform_event.At(qq="123"),
                discord_platform_event.Plain(long_text),
            ]
        )
    )

    assert content.startswith("<@123>A")
    assert len(content) == len("<@123>") + 2100
    assert files == []
    assert view is None
    assert embeds == []
    assert reference_message_id == "77"


def _discord_adapter() -> DiscordPlatformAdapter:
    adapter = DiscordPlatformAdapter.__new__(DiscordPlatformAdapter)
    adapter.config = {"id": "discord-test"}
    adapter.client = SimpleNamespace()
    return adapter


def _discord_group_message(
    *,
    owner_id=1,
    author_id=2,
    administrator: bool | None = False,
    include_member: bool = True,
) -> discord_platform_adapter.AstrBotMessage:
    from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
    from astrbot.core.platform.message_type import MessageType

    member = None
    if include_member:
        member = SimpleNamespace(
            guild_permissions=None
            if administrator is None
            else SimpleNamespace(administrator=administrator)
        )
    raw = SimpleNamespace(
        guild=SimpleNamespace(owner_id=owner_id),
        author=SimpleNamespace(id=author_id, display_name="tester"),
        member=member,
        channel=SimpleNamespace(id=123, guild=SimpleNamespace(id=9)),
    )
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.group_id = "123"
    message.session_id = "123"
    message.sender = MessageMember(user_id=str(author_id), nickname="tester")
    message.raw_message = raw
    message.message_str = "hello"
    message.message = []
    return message


def test_discord_group_owner_admin_member_and_unknown_roles():
    adapter = _discord_adapter()
    owner = adapter.create_event(
        _discord_group_message(owner_id=2, author_id=2, administrator=False)
    )
    admin = adapter.create_event(
        _discord_group_message(owner_id=1, author_id=2, administrator=True)
    )
    member = adapter.create_event(
        _discord_group_message(owner_id=1, author_id=2, administrator=False)
    )
    unknown = adapter.create_event(_discord_group_message(include_member=False))
    missing_perms = adapter.create_event(_discord_group_message(administrator=None))
    assert owner.platform_member_role == "owner"
    assert admin.platform_member_role == "admin"
    assert member.platform_member_role == "member"
    assert unknown.platform_member_role == "unknown"
    assert missing_perms.platform_member_role == "unknown"


def test_discord_private_message_does_not_use_guild_owner():
    from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
    from astrbot.core.platform.message_type import MessageType

    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.session_id = "dm-1"
    message.sender = MessageMember(user_id="2", nickname="tester")
    message.raw_message = SimpleNamespace(
        guild=SimpleNamespace(owner_id=2),
        author=SimpleNamespace(id=2),
        member=SimpleNamespace(guild_permissions=SimpleNamespace(administrator=True)),
    )
    message.message_str = "hello"
    message.message = []
    event = _discord_adapter().create_event(message)
    assert event.platform_member_role == "member"
    assert event.platform_role_source == "none"


@pytest.mark.asyncio
async def test_discord_group_owner_role_stays_in_current_session(tmp_path):
    from astrbot.core.auth.service import AuthorizationService
    from astrbot.core.db.sqlite import SQLiteDatabase
    from tests.fixtures.auth import assert_platform_role_stays_in_session

    event = _discord_adapter().create_event(
        _discord_group_message(owner_id=2, author_id=2)
    )
    db = SQLiteDatabase(str(tmp_path / "discord-auth.db"))
    await db.initialize()
    service = AuthorizationService(db)
    await service.start()
    try:
        await assert_platform_role_stays_in_session(
            service,
            platform_instance="discord",
            sender_id="2",
            platform_role=event.platform_member_role,
            current_umo="discord:GroupMessage:123",
            other_umo="discord:GroupMessage:999",
        )
    finally:
        await service.close()
        await db.close()
