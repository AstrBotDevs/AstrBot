import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import File, Record, Video
from astrbot.api.platform import MessageType
from astrbot.core.agent.stop_policy import AgentOutputStopped
from astrbot.core.platform.sources.dingtalk import dingtalk_adapter
from astrbot.core.platform.sources.dingtalk.dingtalk_adapter import (
    DINGTALK_RECONNECT_INITIAL_DELAY,
    DINGTALK_RECONNECT_MAX_DELAY,
    DingtalkPlatformAdapter,
    _dingtalk_reconnect_delay,
)
from astrbot.core.platform.sources.dingtalk.dingtalk_event import (
    DingtalkMessageEvent,
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


@pytest.mark.asyncio
async def test_dingtalk_stop_after_staff_lookup_blocks_message_write():
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.client_id = "bot"
    adapter._id_to_sid = lambda value: value
    adapter.meta = lambda: SimpleNamespace(id="dingtalk")
    lookup_started = asyncio.Event()
    release_lookup = asyncio.Event()

    async def get_staff_id(_session):
        lookup_started.set()
        await release_lookup.wait()
        return "staff"

    adapter._get_sender_staff_id = get_staff_id
    adapter.send_message_chain_to_user = AsyncMock()
    extras = {}
    stop_event = SimpleNamespace(
        is_stopped=lambda: False,
        get_extra=lambda key, default=None: extras.get(key, default),
        set_extra=lambda key, value: extras.__setitem__(key, value),
    )
    incoming = SimpleNamespace(
        sender_id="user",
        sender_staff_id="",
        conversation_type="1",
    )

    task = asyncio.create_task(
        adapter.send_message_chain_with_incoming(
            incoming,
            MessageChain().message("answer"),
            stop_event=stop_event,
        )
    )
    await asyncio.wait_for(lookup_started.wait(), timeout=1)
    stop_event.set_extra("agent_stop_requested", True)
    release_lookup.set()

    with pytest.raises(AgentOutputStopped):
        await task
    adapter.send_message_chain_to_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_dingtalk_private_session_requires_staff_id_mapping():
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.client_id = "bot"
    adapter._get_sender_staff_id = AsyncMock(return_value="")
    adapter.send_message_chain_to_user = AsyncMock()
    session = SimpleNamespace(
        message_type=MessageType.FRIEND_MESSAGE,
        session_id="opaque-session",
    )

    with pytest.raises(RuntimeError, match="missing a staff_id mapping"):
        await adapter.send_by_session(session, MessageChain().message("answer"))

    adapter.send_message_chain_to_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_dingtalk_empty_chain_is_not_reported_as_delivered():
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)

    with pytest.raises(RuntimeError, match="no platform delivery"):
        await adapter._send_message_chain(
            "group",
            "conversation",
            "robot",
            MessageChain(),
        )


@pytest.mark.asyncio
async def test_dingtalk_empty_stream_is_not_reported_as_delivered():
    event = object.__new__(DingtalkMessageEvent)
    event._extras = {}
    event._force_stopped = False
    event._result = None

    async def empty_source():
        if False:
            yield MessageChain().message("never")

    with pytest.raises(RuntimeError, match="produced no delivery"):
        await event.send_streaming(empty_source())


@pytest.mark.asyncio
async def test_dingtalk_stop_during_token_lookup_blocks_http_write(monkeypatch):
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    token_started = asyncio.Event()
    release_token = asyncio.Event()
    post_calls = 0
    extras = {}
    stop_event = SimpleNamespace(
        is_stopped=lambda: False,
        get_extra=lambda key, default=None: extras.get(key, default),
    )

    async def get_access_token(_stop_event=None):
        token_started.set()
        await release_token.wait()
        return "token"

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def post(self, *_args, **_kwargs):
            nonlocal post_calls
            post_calls += 1
            raise AssertionError("DingTalk POST must not start after stop")

    adapter.get_access_token = get_access_token
    monkeypatch.setattr(dingtalk_adapter.aiohttp, "ClientSession", Session)
    task = asyncio.create_task(
        adapter._send_message_chain(
            "group",
            "conversation",
            "robot",
            MessageChain().message("late"),
            stop_event=stop_event,
        )
    )
    await asyncio.wait_for(token_started.wait(), timeout=1)
    extras["agent_stop_requested"] = True
    release_token.set()

    with pytest.raises(AgentOutputStopped):
        await task
    assert post_calls == 0


@pytest.mark.parametrize(
    ("status", "response_text"),
    [
        (500, "rejected"),
        (200, '{"errcode": 123, "errmsg": "rejected"}'),
    ],
)
@pytest.mark.asyncio
async def test_dingtalk_rejected_message_raises_delivery_error(
    monkeypatch,
    status,
    response_text,
):
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.get_access_token = AsyncMock(return_value="token")

    class Response:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def text(self):
            return response_text

    Response.status = status

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(dingtalk_adapter.aiohttp, "ClientSession", Session)

    with pytest.raises(RuntimeError, match="delivery failed"):
        await adapter._send_message_chain(
            "group",
            "conversation",
            "robot",
            MessageChain().message("required"),
        )


@pytest.mark.asyncio
async def test_dingtalk_successful_message_is_still_accepted(monkeypatch):
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.get_access_token = AsyncMock(return_value="token")

    class Response:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def text(self):
            return '{"processQueryKey": "query"}'

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(dingtalk_adapter.aiohttp, "ClientSession", Session)

    await adapter._send_message_chain(
        "group",
        "conversation",
        "robot",
        MessageChain().message("delivered"),
    )


@pytest.mark.parametrize("component_type", ["record", "video", "file"])
@pytest.mark.asyncio
async def test_dingtalk_required_media_failure_is_not_swallowed(
    monkeypatch,
    component_type,
):
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.upload_media = AsyncMock(side_effect=RuntimeError("upload failed"))
    adapter._safe_remove_file = lambda _path: None

    if component_type == "record":
        component = Record(file="source.wav")
        monkeypatch.setattr(
            Record,
            "convert_to_file_path",
            AsyncMock(return_value="/tmp/source.wav"),
        )
        adapter._prepare_voice_for_dingtalk = AsyncMock(
            return_value=("/tmp/source.ogg", False)
        )
    elif component_type == "video":
        component = Video(file="source.mp4")
        monkeypatch.setattr(
            Video,
            "convert_to_file_path",
            AsyncMock(return_value="/tmp/source.mp4"),
        )
        monkeypatch.setattr(
            dingtalk_adapter,
            "extract_video_cover",
            AsyncMock(return_value="/tmp/cover.jpg"),
        )
    else:
        component = File(name="source.txt", file="source.txt")
        monkeypatch.setattr(
            File,
            "get_file",
            AsyncMock(return_value="/tmp/source.txt"),
        )

    with pytest.raises(RuntimeError, match="upload failed"):
        await adapter._send_message_chain(
            "group",
            "conversation",
            "robot",
            MessageChain([component]),
        )


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
