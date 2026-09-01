import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, File, Image, Plain, Record, Video
from astrbot.api.platform import MessageType
from astrbot.core.platform.astr_message_event import MessageSession
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.route_identity import PlatformRouteIdentity
from astrbot.core.platform.sources.dingtalk import dingtalk_adapter
from astrbot.core.platform.sources.dingtalk.dingtalk_adapter import (
    DINGTALK_RECONNECT_INITIAL_DELAY,
    DINGTALK_RECONNECT_MAX_DELAY,
    DingtalkPlatformAdapter,
    _dingtalk_reconnect_delay,
)
from astrbot.core.platform.sources.dingtalk.dingtalk_event import DingtalkMessageEvent

pytestmark = pytest.mark.platform


def _dingtalk_platform_meta():
    return SimpleNamespace(id="dingtalk", name="dingtalk")


def _dingtalk_route_identity(target_id: str):
    return PlatformRouteIdentity(
        platform_id="dingtalk",
        message_type=MessageType.FRIEND_MESSAGE,
        target_id=target_id,
    )


def test_dingtalk_reconnect_delay_uses_exponential_backoff():
    assert [_dingtalk_reconnect_delay(i) for i in range(1, 5)] == [
        10,
        20,
        40,
        80,
    ]


def test_dingtalk_reconnect_delay_has_minimum_delay():
    assert _dingtalk_reconnect_delay(0) == DINGTALK_RECONNECT_INITIAL_DELAY
    assert _dingtalk_reconnect_delay(-1) == DINGTALK_RECONNECT_INITIAL_DELAY


def test_dingtalk_reconnect_delay_is_capped():
    assert _dingtalk_reconnect_delay(20) == DINGTALK_RECONNECT_MAX_DELAY


def _build_adapter() -> DingtalkPlatformAdapter:
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.config = {"id": "test_dingtalk"}
    adapter._background_tasks = set()
    adapter.client_id = "robot-code"
    adapter.client_secret = "client-secret"
    adapter.preferences = SimpleNamespace(
        put_async=AsyncMock(),
        get_async=AsyncMock(return_value=""),
    )
    return adapter


@pytest.mark.asyncio
async def test_dingtalk_reconnect_delay_wakes_on_terminate(monkeypatch):
    class ObservedEvent:
        def __init__(self) -> None:
            self._event = threading.Event()
            self.wait_started = threading.Event()
            self.wait_timeout: float | None = None

        def is_set(self) -> bool:
            return self._event.is_set()

        def set(self) -> None:
            self._event.set()

        def wait(self, timeout: float | None = None) -> bool:
            self.wait_timeout = timeout
            self.wait_started.set()
            return self._event.wait(timeout)

    class FailingClient:
        websocket = None

        async def start(self) -> None:
            raise RuntimeError("connect failed")

    terminated_event = ObservedEvent()
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.client_ = FailingClient()
    adapter._shutdown_event = threading.Event()
    adapter._terminated_event = terminated_event

    monkeypatch.setattr(dingtalk_adapter, "_dingtalk_reconnect_delay", lambda _: 60)

    run_task = asyncio.create_task(adapter.run())
    try:
        wait_started = await asyncio.to_thread(terminated_event.wait_started.wait, 1)
        assert wait_started
        assert terminated_event.wait_timeout == 60

        await adapter.terminate()
        await asyncio.wait_for(run_task, timeout=1)
    finally:
        if not run_task.done():
            await adapter.terminate()
            run_task.cancel()
            await asyncio.gather(run_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_dingtalk_callback_raw_process_wraps_ack_headers(monkeypatch):
    ack_headers = SimpleNamespace(message_id=None, content_type=None)

    class FakeAckMessage:
        STATUS_OK = 200

        def __init__(self) -> None:
            self.code = None
            self.headers = ack_headers
            self.data = None

    class FakeHeaders:
        CONTENT_TYPE_APPLICATION_JSON = "application/json"

    class FakeCallbackClient:
        def __init__(self, credential, logger=None):
            self.credential = credential
            self.logger = logger
            self.registered = None

        def register_callback_handler(self, topic, handler) -> None:
            self.registered = (topic, handler)

    monkeypatch.setattr(dingtalk_adapter, "AckMessage", FakeAckMessage)
    monkeypatch.setattr(dingtalk_adapter, "Headers", FakeHeaders)
    monkeypatch.setattr(
        dingtalk_adapter.dingtalk_stream,
        "Credential",
        lambda client_id, client_secret: (client_id, client_secret),
    )
    monkeypatch.setattr(
        dingtalk_adapter.dingtalk_stream,
        "DingTalkStreamClient",
        FakeCallbackClient,
    )
    monkeypatch.setattr(
        dingtalk_adapter.dingtalk_stream,
        "ChatbotMessage",
        SimpleNamespace(
            TOPIC="topic-chatbot",
            from_dict=lambda data: data,
        ),
    )

    adapter = DingtalkPlatformAdapter(
        {"id": "test_dingtalk", "client_id": "robot-code", "client_secret": "secret"},
        {},
        asyncio.Queue(),
    )
    adapter.convert_msg = AsyncMock(return_value="abm")
    adapter.handle_msg = AsyncMock()

    ack = await adapter.client.raw_process(
        SimpleNamespace(
            data={"msg": "payload"},
            headers=SimpleNamespace(message_id="msg-123"),
        )
    )

    adapter.convert_msg.assert_awaited_once_with({"msg": "payload"})
    adapter.handle_msg.assert_awaited_once_with("abm")
    assert ack.code == FakeAckMessage.STATUS_OK
    assert ack.headers.message_id == "msg-123"
    assert ack.headers.content_type == "application/json"
    assert ack.data == {"response": "OK"}


@pytest.mark.asyncio
async def test_dingtalk_get_access_token_uses_http_timeout(monkeypatch):
    adapter = _build_adapter()
    adapter.client_ = SimpleNamespace(
        get_access_token=MagicMock(side_effect=RuntimeError("no cached token"))
    )
    seen: dict[str, object] = {}

    class FakeResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def json(self):
            return {"data": {"accessToken": "token-123"}}

        async def text(self):
            return ""

    class FakeSession:
        def __init__(self, *, timeout=None, **kwargs):
            seen["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(dingtalk_adapter.aiohttp, "ClientSession", FakeSession)

    token = await adapter.get_access_token()

    assert token == "token-123"
    assert seen["timeout"] is dingtalk_adapter._DINGTALK_HTTP_TIMEOUT


@pytest.mark.asyncio
async def test_dingtalk_convert_msg_rich_text_group_parses_mentions_and_images():
    adapter = _build_adapter()
    adapter.download_ding_file = AsyncMock(return_value="/tmp/rich.jpg")
    adapter._remember_sender_binding = AsyncMock()

    message = SimpleNamespace(
        create_at=1_700_000_000_123,
        conversation_type="2",
        sender_id="$:LWCP_v1:$user-1",
        sender_nick="Alice",
        chatbot_user_id="$:LWCP_v1:$bot-1",
        message_id="msg-1",
        at_users=[
            SimpleNamespace(dingtalk_id="$:LWCP_v1:$user-2"),
            SimpleNamespace(dingtalk_id=None),
        ],
        conversation_id="group-1",
        message_type="richText",
        robot_code="robot-code",
        extensions={"content": {}},
        rich_text_content=SimpleNamespace(
            rich_text_list=[
                {"text": " hello "},
                {"type": "picture", "downloadCode": "pic-1"},
                {"type": "picture"},
            ]
        ),
        sender_staff_id="",
    )

    result = await adapter.convert_msg(message)

    assert result.timestamp == 1_700_000_000
    assert result.type is MessageType.GROUP_MESSAGE
    assert result.sender.user_id == "user-1"
    assert result.self_id == "bot-1"
    assert result.group_id == "group-1"
    assert result.session_id == "group-1"
    assert result.message_id == "msg-1"
    assert result.message_str == "hello"
    assert isinstance(result.message[0], At)
    assert result.message[0].qq == "user-2"
    assert isinstance(result.message[1], At)
    assert result.message[1].qq == "unknown"
    assert isinstance(result.message[2], Plain)
    assert result.message[2].text == " hello "
    assert isinstance(result.message[3], Image)
    assert result.message[3].file == ""
    adapter.download_ding_file.assert_not_awaited()
    adapter._remember_sender_binding.assert_awaited_once_with(message, result)


@pytest.mark.asyncio
async def test_dingtalk_rich_text_strips_a_duplicate_leading_self_mention():
    adapter = _build_adapter()
    adapter._remember_sender_binding = AsyncMock()
    message = SimpleNamespace(
        create_at=1_700_000_000_000,
        conversation_type="2",
        sender_id="user",
        sender_nick="Alice",
        chatbot_user_id="bot",
        message_id="message",
        at_users=[SimpleNamespace(dingtalk_id="bot")],
        is_in_at_list=True,
        conversation_id="conversation",
        message_type="richText",
        robot_code="robot",
        extensions={"content": {}},
        rich_text_content=SimpleNamespace(
            rich_text_list=[{"text": "@ExampleBot"}, {"text": "/server"}]
        ),
        sender_staff_id="",
    )

    result = await adapter.convert_msg(message)

    assert result.message_str == "/server"
    assert len(result.message) == 2
    assert isinstance(result.message[0], At)
    assert result.message[0].qq == "bot"
    assert isinstance(result.message[1], Plain)
    assert result.message[1].text == "/server"


@pytest.mark.asyncio
async def test_dingtalk_rich_text_preserves_text_in_a_leading_self_mention_segment():
    adapter = _build_adapter()
    adapter._remember_sender_binding = AsyncMock()
    message = SimpleNamespace(
        create_at=1_700_000_000_000,
        conversation_type="2",
        sender_id="user",
        sender_nick="Alice",
        chatbot_user_id="bot",
        message_id="message",
        at_users=[SimpleNamespace(dingtalk_id="bot")],
        is_in_at_list=True,
        conversation_id="conversation",
        message_type="richText",
        robot_code="robot",
        extensions={"content": {}},
        rich_text_content=SimpleNamespace(
            rich_text_list=[{"text": "@ExampleBot /server"}]
        ),
        sender_staff_id="",
    )

    result = await adapter.convert_msg(message)

    assert result.message_str == "/server"
    assert [
        component.text for component in result.message if isinstance(component, Plain)
    ] == ["/server"]


@pytest.mark.asyncio
async def test_dingtalk_rich_text_does_not_treat_missing_ids_as_self_mention():
    adapter = _build_adapter()
    adapter._remember_sender_binding = AsyncMock()
    message = SimpleNamespace(
        create_at=1_700_000_000_000,
        conversation_type="2",
        sender_id="user",
        sender_nick="Alice",
        chatbot_user_id=None,
        message_id="message",
        at_users=[SimpleNamespace(dingtalk_id=None)],
        is_in_at_list=True,
        conversation_id="conversation",
        message_type="richText",
        robot_code="robot",
        extensions={"content": {}},
        rich_text_content=SimpleNamespace(
            rich_text_list=[{"text": "@ExampleBot"}, {"text": "/server"}]
        ),
        sender_staff_id="",
    )

    result = await adapter.convert_msg(message)

    assert result.message_str == "@ExampleBot/server"


@pytest.mark.asyncio
async def test_dingtalk_rich_text_preserves_a_non_self_leading_mention():
    adapter = _build_adapter()
    adapter._remember_sender_binding = AsyncMock()
    message = SimpleNamespace(
        create_at=1_700_000_000_000,
        conversation_type="2",
        sender_id="user",
        sender_nick="Alice",
        chatbot_user_id="bot",
        message_id="message",
        at_users=[
            SimpleNamespace(dingtalk_id="other-user"),
            SimpleNamespace(dingtalk_id="bot"),
        ],
        is_in_at_list=True,
        conversation_id="conversation",
        message_type="richText",
        robot_code="robot",
        extensions={"content": {}},
        rich_text_content=SimpleNamespace(
            rich_text_list=[
                {"text": "@AnotherUser"},
                {"text": "@ExampleBot"},
                {"text": "/server"},
            ]
        ),
        sender_staff_id="",
    )

    result = await adapter.convert_msg(message)

    assert result.message_str == "@AnotherUser@ExampleBot/server"
    assert [
        component.text for component in result.message if isinstance(component, Plain)
    ] == [
        "@AnotherUser",
        "@ExampleBot",
        "/server",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("use_markdown", "expected_key", "expected_param"),
    [
        (None, "sampleMarkdown", {"title": "AstrBot", "text": "first\nsecond"}),
        (True, "sampleMarkdown", {"title": "AstrBot", "text": "first\nsecond"}),
        (False, "sampleText", {"content": "first\nsecond"}),
    ],
)
async def test_dingtalk_text_respects_markdown_mode(
    use_markdown,
    expected_key,
    expected_param,
):
    adapter = _build_adapter()
    sent: list[dict] = []

    async def capture_group_message(**kwargs) -> None:
        sent.append(kwargs)

    adapter._send_group_message = capture_group_message
    message_chain = MessageChain().message("first\nsecond").use_markdown(use_markdown)

    await adapter._send_message_chain(
        "group",
        "conversation",
        "robot",
        message_chain,
    )

    assert sent == [
        {
            "open_conversation_id": "conversation",
            "robot_code": "robot",
            "msg_key": expected_key,
            "msg_param": expected_param,
        }
    ]


@pytest.mark.asyncio
async def test_dingtalk_convert_msg_private_text_persists_staff_binding():
    adapter = _build_adapter()

    message = SimpleNamespace(
        create_at=1_700_000_100_000,
        conversation_type="1",
        sender_id="$:LWCP_v1:$user-9",
        sender_nick="Bob",
        chatbot_user_id="$:LWCP_v1:$bot-1",
        message_id="msg-9",
        at_users=[],
        conversation_id="ignored",
        message_type="text",
        robot_code="robot-code",
        extensions={"content": "not-a-dict"},
        text=SimpleNamespace(content=" hi there "),
        sender_staff_id="staff-9",
    )

    with patch.object(adapter.preferences, "put_async", AsyncMock()) as put_async:
        result = await adapter.convert_msg(message)

    assert result.type is MessageType.FRIEND_MESSAGE
    assert result.session_id == "user-9"
    assert result.message_str == "hi there"
    assert len(result.message) == 1
    assert isinstance(result.message[0], Plain)
    put_async.assert_awaited_once_with(
        "global",
        str(
            MessageSession(
                platform_name="test_dingtalk",
                message_type=MessageType.FRIEND_MESSAGE,
                session_id="user-9",
            )
        ),
        "dingtalk_staffid",
        "staff-9",
    )


@pytest.mark.asyncio
async def test_dingtalk_convert_msg_picture_without_robot_code_skips_download():
    adapter = _build_adapter()
    adapter.download_ding_file = AsyncMock()
    adapter._remember_sender_binding = AsyncMock()

    message = SimpleNamespace(
        create_at=1_700_000_200_000,
        conversation_type="2",
        sender_id="$:LWCP_v1:$user-2",
        sender_nick="Carol",
        chatbot_user_id="$:LWCP_v1:$bot-1",
        message_id="msg-picture",
        at_users=[],
        conversation_id="group-2",
        message_type="picture",
        robot_code="",
        extensions={"content": {}},
        image_content=SimpleNamespace(download_code="pic-2"),
        sender_staff_id="",
    )

    result = await adapter.convert_msg(message)

    assert result.message == []
    assert result.message_str == ""
    adapter.download_ding_file.assert_not_called()
    adapter._remember_sender_binding.assert_awaited_once_with(message, result)


@pytest.mark.asyncio
async def test_dingtalk_convert_msg_file_download_failure_leaves_message_empty():
    adapter = _build_adapter()
    adapter.download_ding_file = AsyncMock(return_value="")
    adapter._remember_sender_binding = AsyncMock()

    message = SimpleNamespace(
        create_at=1_700_000_250_000,
        conversation_type="2",
        sender_id="$:LWCP_v1:$user-3",
        sender_nick="Dora",
        chatbot_user_id="$:LWCP_v1:$bot-1",
        message_id="msg-file",
        at_users=[],
        conversation_id="group-3",
        message_type="file",
        robot_code="robot-code",
        extensions={"content": {"downloadCode": "file-1", "fileName": "report.pdf"}},
        sender_staff_id="",
    )

    result = await adapter.convert_msg(message)

    assert len(result.message) == 1
    assert isinstance(result.message[0], File)
    adapter.download_ding_file.assert_not_awaited()
    adapter._remember_sender_binding.assert_awaited_once_with(message, result)


@pytest.mark.asyncio
async def test_dingtalk_convert_msg_audio_uses_default_amr_extension_lazily():
    adapter = _build_adapter()
    adapter.download_ding_file = AsyncMock(return_value="/tmp/voice.amr")
    adapter._remember_sender_binding = AsyncMock()

    message = SimpleNamespace(
        create_at=1_700_000_260_000,
        conversation_type="1",
        sender_id="$:LWCP_v1:$user-4",
        sender_nick="Eve",
        chatbot_user_id="$:LWCP_v1:$bot-1",
        message_id="msg-audio",
        at_users=[],
        conversation_id="ignored",
        message_type="audio",
        robot_code="robot-code",
        extensions={"content": {"downloadCode": "voice-1"}},
        sender_staff_id="",
    )

    result = await adapter.convert_msg(message)

    assert len(result.message) == 1
    assert isinstance(result.message[0], Record)
    assert result.message[0].file == ""
    adapter.download_ding_file.assert_not_awaited()
    adapter._remember_sender_binding.assert_awaited_once_with(message, result)


@pytest.mark.asyncio
async def test_dingtalk_rich_text_image_resolves_download_lazily():
    adapter = _build_adapter()
    adapter.download_ding_file = AsyncMock(return_value="/tmp/rich.jpg")
    adapter._remember_sender_binding = AsyncMock()

    message = SimpleNamespace(
        create_at=1_700_000_000_123,
        conversation_type="2",
        sender_id="$:LWCP_v1:$user-1",
        sender_nick="Alice",
        chatbot_user_id="$:LWCP_v1:$bot-1",
        message_id="msg-1",
        at_users=[],
        conversation_id="group-1",
        message_type="richText",
        robot_code="robot-code",
        extensions={"content": {}},
        rich_text_content=SimpleNamespace(
            rich_text_list=[
                {"type": "picture", "downloadCode": "pic-1"},
            ]
        ),
        sender_staff_id="",
    )

    result = await adapter.convert_msg(message)

    image = result.message[0]
    assert isinstance(image, Image)
    assert image.file == ""
    adapter.download_ding_file.assert_not_awaited()

    with patch(
        "astrbot.core.message.components.MediaResolver",
        return_value=SimpleNamespace(to_path=AsyncMock(return_value="/tmp/rich.jpg")),
    ) as media_resolver:
        resolved_path = await image.convert_to_file_path()

    assert resolved_path == "/tmp/rich.jpg"
    adapter.download_ding_file.assert_awaited_once_with("pic-1", "robot-code", "jpg")
    media_resolver.assert_called_once_with("/tmp/rich.jpg", media_type="image")


@pytest.mark.asyncio
async def test_dingtalk_audio_record_resolves_download_lazily():
    adapter = _build_adapter()
    adapter.download_ding_file = AsyncMock(return_value="/tmp/voice.amr")
    adapter._remember_sender_binding = AsyncMock()

    message = SimpleNamespace(
        create_at=1_700_000_260_000,
        conversation_type="1",
        sender_id="$:LWCP_v1:$user-4",
        sender_nick="Eve",
        chatbot_user_id="$:LWCP_v1:$bot-1",
        message_id="msg-audio",
        at_users=[],
        conversation_id="ignored",
        message_type="audio",
        robot_code="robot-code",
        extensions={"content": {"downloadCode": "voice-1"}},
        sender_staff_id="",
    )

    result = await adapter.convert_msg(message)

    record = result.message[0]
    assert isinstance(record, Record)
    adapter.download_ding_file.assert_not_awaited()

    media_resolver = SimpleNamespace(to_path=AsyncMock(return_value="/tmp/voice.wav"))
    with patch(
        "astrbot.core.message.components.MediaResolver",
        return_value=media_resolver,
    ) as resolver_factory:
        resolved_path = await record.convert_to_file_path()

    assert resolved_path == "/tmp/voice.wav"
    adapter.download_ding_file.assert_awaited_once_with("voice-1", "robot-code", "amr")
    resolver_factory.assert_called_once_with(
        "/tmp/voice.amr",
        media_type="audio",
        default_suffix=".wav",
    )
    media_resolver.to_path.assert_awaited_once_with(target_format="wav")


@pytest.mark.asyncio
async def test_dingtalk_file_resolves_download_lazily(tmp_path):
    adapter = _build_adapter()
    downloaded = tmp_path / "downloaded.pdf"
    downloaded.write_bytes(b"payload")
    adapter.download_ding_file = AsyncMock(return_value=str(downloaded))
    adapter._remember_sender_binding = AsyncMock()

    message = SimpleNamespace(
        create_at=1_700_000_250_000,
        conversation_type="2",
        sender_id="$:LWCP_v1:$user-3",
        sender_nick="Dora",
        chatbot_user_id="$:LWCP_v1:$bot-1",
        message_id="msg-file",
        at_users=[],
        conversation_id="group-3",
        message_type="file",
        robot_code="robot-code",
        extensions={"content": {"downloadCode": "file-1", "fileName": "report.pdf"}},
        sender_staff_id="",
    )

    result = await adapter.convert_msg(message)

    file_seg = result.message[0]
    assert isinstance(file_seg, File)
    adapter.download_ding_file.assert_not_awaited()

    resolved_path = await file_seg.get_file()

    assert resolved_path == str(downloaded)
    adapter.download_ding_file.assert_awaited_once_with("file-1", "robot-code", "pdf")


@pytest.mark.asyncio
async def test_dingtalk_convert_msg_file_without_name_uses_downloaded_basename(
    tmp_path,
):
    adapter = _build_adapter()
    downloaded = tmp_path / "downloaded.bin"
    downloaded.write_bytes(b"payload")
    adapter.download_ding_file = AsyncMock(return_value=str(downloaded))
    adapter._remember_sender_binding = AsyncMock()

    message = SimpleNamespace(
        create_at=1_700_000_270_000,
        conversation_type="2",
        sender_id="$:LWCP_v1:$user-5",
        sender_nick="Frank",
        chatbot_user_id="$:LWCP_v1:$bot-1",
        message_id="msg-file-2",
        at_users=[],
        conversation_id="group-5",
        message_type="file",
        robot_code="robot-code",
        extensions={"content": {"downloadCode": "file-2"}},
        sender_staff_id="",
    )

    result = await adapter.convert_msg(message)

    adapter.download_ding_file.assert_not_awaited()
    assert len(result.message) == 1
    assert isinstance(result.message[0], File)
    assert result.message[0].name == "dingtalk_file.file"
    resolved_path = await result.message[0].get_file()
    adapter.download_ding_file.assert_awaited_once_with("file-2", "robot-code", "file")
    assert result.message[0].name == "downloaded.bin"
    assert result.message[0].file_ == str(downloaded)
    assert resolved_path == str(downloaded)
    adapter._remember_sender_binding.assert_awaited_once_with(message, result)


@pytest.mark.asyncio
async def test_dingtalk_prepare_voice_for_dingtalk_prefers_existing_or_ogg():
    adapter = _build_adapter()

    same_path, converted = await adapter._prepare_voice_for_dingtalk("voice.ogg")
    assert same_path == "voice.ogg"
    assert converted is False

    with patch.object(
        dingtalk_adapter, "convert_audio_format", AsyncMock(return_value="voice.ogg")
    ) as convert_audio_format:
        converted_path, converted = await adapter._prepare_voice_for_dingtalk(
            "voice.mp3"
        )

    assert converted_path == "voice.ogg"
    assert converted is True
    convert_audio_format.assert_awaited_once_with("voice.mp3", "ogg")


@pytest.mark.asyncio
async def test_dingtalk_prepare_voice_for_dingtalk_falls_back_to_amr():
    adapter = _build_adapter()

    with patch.object(
        dingtalk_adapter,
        "convert_audio_format",
        AsyncMock(side_effect=[RuntimeError("ogg failed"), "voice.amr"]),
    ) as convert_audio_format:
        converted_path, converted = await adapter._prepare_voice_for_dingtalk(
            "voice.mp3"
        )

    assert converted_path == "voice.amr"
    assert converted is True
    assert convert_audio_format.await_args_list == [
        call("voice.mp3", "ogg"),
        call("voice.mp3", "amr"),
    ]


@pytest.mark.asyncio
async def test_dingtalk_send_message_chain_with_incoming_routes_group_messages():
    adapter = _build_adapter()
    adapter.send_message_chain_to_group = AsyncMock()
    adapter.send_message_chain_to_user = AsyncMock()

    incoming_message = SimpleNamespace(
        conversation_type="2",
        conversation_id="group-42",
        sender_id="$:LWCP_v1:$user-1",
        sender_staff_id="staff-1",
    )
    chain = MessageChain().message("hello")

    await adapter.send_message_chain_with_incoming(incoming_message, chain)

    adapter.send_message_chain_to_group.assert_awaited_once_with(
        open_conversation_id="group-42",
        robot_code="robot-code",
        message_chain=chain,
    )
    adapter.send_message_chain_to_user.assert_not_called()


@pytest.mark.asyncio
async def test_dingtalk_send_message_chain_with_incoming_private_uses_fallback_staff_id():
    adapter = _build_adapter()
    adapter.send_message_chain_to_group = AsyncMock()
    adapter.send_message_chain_to_user = AsyncMock()
    adapter._get_sender_staff_id = AsyncMock(return_value="staff-from-store")

    incoming_message = SimpleNamespace(
        conversation_type="1",
        conversation_id="ignored",
        sender_id="$:LWCP_v1:$user-7",
        sender_staff_id="",
    )
    chain = MessageChain().message("hello")

    await adapter.send_message_chain_with_incoming(incoming_message, chain)

    adapter._get_sender_staff_id.assert_awaited_once()
    session = adapter._get_sender_staff_id.await_args.args[0]
    assert isinstance(session, MessageSession)
    assert session.platform_name == "test_dingtalk"
    assert session.message_type is MessageType.FRIEND_MESSAGE
    assert session.session_id == "user-7"
    adapter.send_message_chain_to_group.assert_not_called()
    adapter.send_message_chain_to_user.assert_awaited_once_with(
        staff_id="staff-from-store",
        robot_code="robot-code",
        message_chain=chain,
    )


@pytest.mark.asyncio
async def test_dingtalk_send_by_session_private_falls_back_to_session_id_when_staff_missing():
    adapter = _build_adapter()
    adapter._get_sender_staff_id = AsyncMock(return_value="")
    adapter.send_message_chain_to_group = AsyncMock()
    adapter.send_message_chain_to_user = AsyncMock()

    session = MessageSession(
        platform_name="test_dingtalk",
        message_type=MessageType.FRIEND_MESSAGE,
        session_id="user-12",
    )
    chain = MessageChain().message("hello")

    await adapter.send_by_session(session, chain)

    adapter.send_message_chain_to_group.assert_not_called()
    adapter.send_message_chain_to_user.assert_awaited_once_with(
        staff_id="user-12",
        robot_code="robot-code",
        message_chain=chain,
    )


@pytest.mark.asyncio
async def test_dingtalk_send_by_session_group_uses_group_sender():
    adapter = _build_adapter()
    adapter._get_sender_staff_id = AsyncMock()
    adapter.send_message_chain_to_group = AsyncMock()
    adapter.send_message_chain_to_user = AsyncMock()

    session = MessageSession(
        platform_name="test_dingtalk",
        message_type=MessageType.GROUP_MESSAGE,
        session_id="group-12",
    )
    chain = MessageChain().message("hello")

    await adapter.send_by_session(session, chain)

    adapter._get_sender_staff_id.assert_not_called()
    adapter.send_message_chain_to_group.assert_awaited_once_with(
        open_conversation_id="group-12",
        robot_code="robot-code",
        message_chain=chain,
    )
    adapter.send_message_chain_to_user.assert_not_called()


@pytest.mark.asyncio
async def test_dingtalk_remember_sender_binding_swallows_storage_errors():
    adapter = _build_adapter()
    abm = SimpleNamespace(
        type=MessageType.FRIEND_MESSAGE,
        sender=SimpleNamespace(user_id="user-9"),
    )
    message = SimpleNamespace(sender_staff_id="staff-9")

    with patch.object(
        adapter.preferences, "put_async", AsyncMock(side_effect=RuntimeError("db down"))
    ):
        await adapter._remember_sender_binding(message, abm)


@pytest.mark.asyncio
async def test_dingtalk_send_message_chain_sends_record_and_cleans_converted_audio():
    adapter = _build_adapter()
    adapter._send_group_message = AsyncMock()
    adapter._prepare_voice_for_dingtalk = AsyncMock(return_value=("voice.ogg", True))
    adapter.upload_media = AsyncMock(return_value="media-voice")
    adapter._safe_remove_file = MagicMock()

    record = Record(file="voice.mp3", url="voice.mp3")

    with (
        patch.object(
            Record, "convert_to_file_path", AsyncMock(return_value="voice.mp3")
        ) as convert_to_file_path,
        patch.object(
            dingtalk_adapter, "get_media_duration", AsyncMock(return_value=2400)
        ),
    ):
        await adapter._send_message_chain(
            target_type="group",
            target_id="group-1",
            robot_code="robot-code",
            message_chain=MessageChain(chain=[record]),
        )

    convert_to_file_path.assert_awaited_once()
    adapter._prepare_voice_for_dingtalk.assert_awaited_once_with("voice.mp3")
    adapter.upload_media.assert_awaited_once_with("voice.ogg", "voice")
    adapter._send_group_message.assert_awaited_once_with(
        open_conversation_id="group-1",
        robot_code="robot-code",
        msg_key="sampleAudio",
        msg_param={"mediaId": "media-voice", "duration": "2400"},
    )
    adapter._safe_remove_file.assert_called_once_with("voice.ogg")


@pytest.mark.asyncio
async def test_dingtalk_send_message_chain_skips_blank_plain_without_at_text():
    adapter = _build_adapter()
    adapter._send_group_message = AsyncMock()
    adapter._send_private_message = AsyncMock()

    await adapter._send_message_chain(
        target_type="group",
        target_id="group-1",
        robot_code="robot-code",
        message_chain=MessageChain(chain=[Plain("   ")]),
    )

    adapter._send_group_message.assert_not_called()
    adapter._send_private_message.assert_not_called()


@pytest.mark.asyncio
async def test_dingtalk_send_message_chain_sends_at_text_even_when_plain_is_blank():
    adapter = _build_adapter()
    adapter._send_group_message = AsyncMock()

    await adapter._send_message_chain(
        target_type="group",
        target_id="group-1",
        robot_code="robot-code",
        message_chain=MessageChain(chain=[Plain("   ")]),
        at_str="@staff-1",
    )

    adapter._send_group_message.assert_awaited_once_with(
        open_conversation_id="group-1",
        robot_code="robot-code",
        msg_key="sampleMarkdown",
        msg_param={"title": "AstrBot", "text": "@staff-1"},
    )


@pytest.mark.asyncio
async def test_dingtalk_send_message_chain_sends_video_and_cleans_temp_files():
    adapter = _build_adapter()
    adapter._send_private_message = AsyncMock()
    adapter.upload_media = AsyncMock(side_effect=["video-media", "cover-media"])
    adapter._safe_remove_file = MagicMock()

    video = Video(file="clip.mov")

    with (
        patch.object(
            Video, "convert_to_file_path", AsyncMock(return_value="clip.mov")
        ) as convert_to_file_path,
        patch.object(
            dingtalk_adapter,
            "convert_video_format",
            AsyncMock(return_value="clip.mp4"),
        ) as convert_video_format,
        patch.object(
            dingtalk_adapter,
            "extract_video_cover",
            AsyncMock(return_value="cover.jpg"),
        ) as extract_video_cover,
        patch.object(
            dingtalk_adapter, "get_media_duration", AsyncMock(return_value=2500)
        ),
    ):
        await adapter._send_message_chain(
            target_type="user",
            target_id="staff-1",
            robot_code="robot-code",
            message_chain=MessageChain(chain=[video]),
        )

    convert_to_file_path.assert_awaited_once()
    convert_video_format.assert_awaited_once_with("clip.mov", "mp4")
    extract_video_cover.assert_awaited_once_with("clip.mp4")
    assert adapter.upload_media.await_args_list == [
        call("clip.mp4", "file"),
        call("cover.jpg", "image"),
    ]
    adapter._send_private_message.assert_awaited_once_with(
        staff_id="staff-1",
        robot_code="robot-code",
        msg_key="sampleVideo",
        msg_param={
            "duration": "2",
            "videoMediaId": "video-media",
            "videoType": "mp4",
            "picMediaId": "cover-media",
        },
    )
    assert adapter._safe_remove_file.call_args_list == [
        call("cover.jpg"),
        call("clip.mp4"),
    ]


@pytest.mark.asyncio
async def test_dingtalk_send_message_chain_sends_file_with_name_and_suffix():
    adapter = _build_adapter()
    adapter._send_group_message = AsyncMock()
    adapter.upload_media = AsyncMock(return_value="media-file")

    file_segment = File(name="report.pdf", file="report.pdf")

    with patch.object(
        File, "get_file", AsyncMock(return_value="C:/tmp/report.pdf")
    ) as get_file:
        await adapter._send_message_chain(
            target_type="group",
            target_id="group-1",
            robot_code="robot-code",
            message_chain=MessageChain(chain=[file_segment]),
        )

    get_file.assert_awaited_once()
    adapter.upload_media.assert_awaited_once_with("C:/tmp/report.pdf", "file")
    adapter._send_group_message.assert_awaited_once_with(
        open_conversation_id="group-1",
        robot_code="robot-code",
        msg_key="sampleFile",
        msg_param={
            "mediaId": "media-file",
            "fileName": "report.pdf",
            "fileType": "pdf",
        },
    )


@pytest.mark.asyncio
async def test_dingtalk_send_message_chain_skips_file_when_path_is_missing():
    adapter = _build_adapter()
    adapter._send_group_message = AsyncMock()
    adapter.upload_media = AsyncMock()

    file_segment = File(name="empty.txt", file="empty.txt")

    with patch.object(File, "get_file", AsyncMock(return_value="")) as get_file:
        await adapter._send_message_chain(
            target_type="group",
            target_id="group-1",
            robot_code="robot-code",
            message_chain=MessageChain(chain=[file_segment]),
        )

    get_file.assert_awaited_once()
    adapter.upload_media.assert_not_called()
    adapter._send_group_message.assert_not_called()


@pytest.mark.asyncio
async def test_dingtalk_event_send_streaming_buffers_plain_segments_once():
    event = DingtalkMessageEvent.__new__(DingtalkMessageEvent)
    event.platform_meta = _dingtalk_platform_meta()
    event.route_identity = _dingtalk_route_identity("user-1")
    event._has_send_oper = False
    event._background_tasks = set()
    event.send = AsyncMock()

    async def _generator():
        yield MessageChain().message("hello ")
        yield MessageChain().message("world")

    await event.send_streaming(_generator())

    event.send.assert_awaited_once()
    buffered_chain = event.send.await_args.args[0]
    assert buffered_chain.get_plain_text() == "hello world"


@pytest.mark.asyncio
async def test_dingtalk_event_send_without_adapter_logs_and_skips_parent_send(
    monkeypatch,
):
    event = DingtalkMessageEvent.__new__(DingtalkMessageEvent)
    event._adapter = None
    event.platform_meta = _dingtalk_platform_meta()
    event.route_identity = _dingtalk_route_identity("user-1")
    event.message_obj = SimpleNamespace(raw_message={})
    event._has_send_oper = False
    logger_error = MagicMock()

    monkeypatch.setattr(dingtalk_adapter.logger, "error", logger_error)
    with patch.object(
        DingtalkMessageEvent.__mro__[1],
        "send",
        AsyncMock(return_value=None),
    ) as parent_send:
        await event.send(MessageChain().message("hello"))

    logger_error.assert_called_once()
    parent_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_dingtalk_event_send_streaming_returns_none_for_empty_generator():
    event = DingtalkMessageEvent.__new__(DingtalkMessageEvent)
    event.platform_meta = _dingtalk_platform_meta()
    event.route_identity = _dingtalk_route_identity("user-1")
    event._has_send_oper = False
    event.send = AsyncMock()

    async def _generator():
        if False:
            yield MessageChain()

    result = await event.send_streaming(_generator())

    assert result is None
    event.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_dingtalk_event_send_streaming_merges_mixed_components_before_send():
    event = DingtalkMessageEvent.__new__(DingtalkMessageEvent)
    event.platform_meta = _dingtalk_platform_meta()
    event.route_identity = _dingtalk_route_identity("user-1")
    event._has_send_oper = False
    event._background_tasks = set()
    event.send = AsyncMock()

    async def _generator():
        yield MessageChain(chain=[Plain("hello "), At(qq="user-1")])
        yield MessageChain().message("world")

    await event.send_streaming(_generator())

    event.send.assert_awaited_once()
    buffered_chain = event.send.await_args.args[0]
    assert isinstance(buffered_chain.chain[0], Plain)
    assert buffered_chain.chain[0].text == "hello world"
    assert isinstance(buffered_chain.chain[1], At)
    assert buffered_chain.chain[1].qq == "user-1"


def test_dingtalk_create_event_does_not_promote_roles():
    from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember

    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.config = {"id": "dingtalk-test"}
    adapter.client = SimpleNamespace()
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.group_id = "conv-1"
    message.session_id = "conv-1"
    message.sender = MessageMember("staff-1", "tester")
    message.raw_message = SimpleNamespace(isAdmin=True, role="owner")
    message.message_str = "hello"
    message.message = []
    event = adapter.create_event(message)
    assert event.platform_member_role == "member"
    assert event.platform_role_source == "none"


@pytest.mark.asyncio
async def test_dingtalk_group_message_includes_available_group_details():
    adapter = _build_adapter()
    adapter.download_ding_file = AsyncMock()
    adapter._remember_sender_binding = AsyncMock()
    message = SimpleNamespace(
        create_at=1_700_000_000_123,
        conversation_type="2",
        sender_id="$:LWCP_v1:$user-1",
        sender_nick="Alice",
        chatbot_user_id="$:LWCP_v1:$bot-1",
        message_id="msg-group",
        at_users=[],
        conversation_id="conversation",
        conversation_title="AstrBot Group",
        message_type="text",
        robot_code="robot-code",
        extensions={"content": {}},
        text=SimpleNamespace(content="hello"),
        sender_staff_id="",
        isAdmin=True,
    )

    result = await adapter.convert_msg(message)

    assert result.group is not None
    assert result.group.group_id == "conversation"
    assert result.group.group_name == "AstrBot Group"
    assert result.group.group_admins is None

    event = DingtalkMessageEvent(
        result.message_str,
        result,
        PlatformMetadata(name="dingtalk", description="DingTalk", id="dingtalk"),
        result.session_id,
    )
    group = await event.get_group()
    assert group is not result.group
    assert group == result.group


@pytest.mark.asyncio
async def test_dingtalk_group_message_without_conversation_title_leaves_group_name_none():
    adapter = _build_adapter()
    adapter.download_ding_file = AsyncMock()
    adapter._remember_sender_binding = AsyncMock()
    message = SimpleNamespace(
        create_at=1_700_000_000_123,
        conversation_type="2",
        sender_id="$:LWCP_v1:$user-1",
        sender_nick="Alice",
        chatbot_user_id="$:LWCP_v1:$bot-1",
        message_id="msg-group",
        at_users=[],
        conversation_id="conversation",
        message_type="text",
        robot_code="robot-code",
        extensions={"content": {}},
        text=SimpleNamespace(content="hello"),
        sender_staff_id="",
        isAdmin=True,
    )

    result = await adapter.convert_msg(message)

    assert result.group is not None
    assert result.group.group_id == "conversation"
    assert result.group.group_name is None
