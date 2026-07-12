import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import File, Image, Record
from astrbot.core.agent.stop_policy import AgentOutputStopped
from astrbot.core.platform.sources.satori.satori_event import SatoriPlatformEvent
from astrbot.core.platform.sources.webchat import webchat_event
from astrbot.core.platform.sources.webchat.webchat_event import WebChatMessageEvent
from astrbot.core.platform.sources.wecom import wecom_event
from astrbot.core.platform.sources.wecom.wecom_event import WecomPlatformEvent
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_event import (
    WecomAIBotMessageEvent,
)
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_webhook import (
    WecomAIBotWebhookClient,
)
from astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter import WeixinOCAdapter
from astrbot.core.platform.sources.weixin_official_account.weixin_offacc_event import (
    WeixinOfficialAccountPlatformEvent,
)
from astrbot.core.utils import media_utils


class _StopEvent:
    def __init__(self):
        self.extras = {}

    def is_stopped(self):
        return False

    def get_extra(self, key, default=None):
        return self.extras.get(key, default)

    def set_extra(self, key, value):
        self.extras[key] = value


@pytest.mark.asyncio
async def test_wecom_webhook_stop_blocks_later_markdown_chunks():
    event = _StopEvent()
    webhook = object.__new__(WecomAIBotWebhookClient)
    writes = 0

    async def send_payload(_payload):
        nonlocal writes
        writes += 1
        event.set_extra("agent_stop_requested", True)

    webhook.send_payload = send_payload

    with pytest.raises(AgentOutputStopped):
        await webhook.send_message_chain(
            MessageChain().message("x" * 4097),
            stop_event=event,
        )
    assert writes == 1


@pytest.mark.asyncio
async def test_wecom_partial_webhook_stop_blocks_required_long_reply():
    event = object.__new__(WecomAIBotMessageEvent)
    event._extras = {}
    event._force_stopped = False
    event._result = None
    event.session = SimpleNamespace(session_id="stream")
    event.message_obj = SimpleNamespace(raw_message={"stream_id": "stream"})
    event.queue_mgr = SimpleNamespace(
        get_pending_response=lambda _stream_id: {
            "callback_params": {
                "connection_mode": "long_connection",
                "req_id": "request",
            }
        }
    )
    event.only_use_webhook_url_to_send = False
    event.long_connection_sender = AsyncMock(return_value=True)

    async def webhook_send(*_args, **_kwargs):
        event.set_extra("agent_stop_requested", True)

    event.webhook_client = SimpleNamespace(send_message_chain=webhook_send)

    with pytest.raises(AgentOutputStopped):
        await event.send(MessageChain().message("required reply"))
    event.long_connection_sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_satori_streaming_stop_is_not_swallowed():
    event = object.__new__(SatoriPlatformEvent)
    event._extras = {}
    event._force_stopped = False
    event._result = None
    event.send = AsyncMock(side_effect=AgentOutputStopped)

    async def source():
        yield MessageChain().message("late")

    with pytest.raises(AgentOutputStopped):
        await event.send_streaming(source())


@pytest.mark.asyncio
async def test_satori_rejected_message_is_reported_as_delivery_failure():
    event = object.__new__(SatoriPlatformEvent)
    event._extras = {}
    event._force_stopped = False
    event._result = None
    event.session = SimpleNamespace(session_id="channel")
    event.adapter = SimpleNamespace(
        logins=[{"platform": "test", "user": {"id": "bot"}}],
        send_http_request=AsyncMock(return_value=None),
    )

    with pytest.raises(RuntimeError, match="delivery failed"):
        await event.send(MessageChain().message("answer"))


@pytest.mark.asyncio
async def test_webchat_stop_after_conversion_is_not_reported_as_success(monkeypatch):
    event = _StopEvent()
    queue = asyncio.Queue()

    async def convert_to_base64(_image):
        event.set_extra("agent_stop_requested", True)
        return "aGVsbG8="

    monkeypatch.setattr(Image, "convert_to_base64", convert_to_base64)
    monkeypatch.setattr(
        "astrbot.core.platform.sources.webchat.webchat_event."
        "webchat_queue_mgr.get_or_create_back_queue",
        lambda *_args, **_kwargs: queue,
    )

    with pytest.raises(AgentOutputStopped):
        await WebChatMessageEvent._send(
            "message",
            MessageChain([Image(file="ignored")]),
            "webchat!user!conversation",
            stop_event=event,
        )
    assert queue.empty()


@pytest.mark.parametrize("component_type", ["image", "record", "file"])
@pytest.mark.parametrize("stop_after_write", [False, True])
@pytest.mark.asyncio
async def test_webchat_attachment_ownership_after_write(
    monkeypatch,
    tmp_path,
    component_type,
    stop_after_write,
):
    event = _StopEvent()
    queue = asyncio.Queue()
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    monkeypatch.setattr(webchat_event, "attachments_dir", str(attachments))
    monkeypatch.setattr(
        webchat_event.webchat_queue_mgr,
        "get_or_create_back_queue",
        lambda *_args, **_kwargs: queue,
    )

    if component_type == "image":
        component = Image(file="ignored")
        monkeypatch.setattr(
            Image,
            "convert_to_base64",
            AsyncMock(return_value="aGVsbG8="),
        )
    elif component_type == "record":
        component = Record(file="ignored")
        monkeypatch.setattr(
            Record,
            "convert_to_base64",
            AsyncMock(return_value="YXVkaW8="),
        )
    else:
        source = tmp_path / "source.txt"
        source.write_text("file", encoding="utf-8")
        component = File(file=str(source), name="source.txt")
        monkeypatch.setattr(
            File,
            "get_file",
            AsyncMock(return_value=str(source)),
        )

    if stop_after_write and component_type in {"image", "record"}:

        async def write_then_stop(func, *args, **kwargs):
            result = func(*args, **kwargs)
            event.set_extra("agent_stop_requested", True)
            return result

        monkeypatch.setattr(webchat_event.asyncio, "to_thread", write_then_stop)
    elif stop_after_write:
        original_copy = webchat_event.shutil.copy2

        def copy_then_stop(*args, **kwargs):
            result = original_copy(*args, **kwargs)
            event.set_extra("agent_stop_requested", True)
            return result

        monkeypatch.setattr(webchat_event.shutil, "copy2", copy_then_stop)

    send = WebChatMessageEvent._send(
        "message",
        MessageChain([component]),
        "webchat!user!conversation",
        stop_event=event,
    )
    if stop_after_write:
        with pytest.raises(AgentOutputStopped):
            await send
        assert queue.empty()
        assert list(attachments.iterdir()) == []
    else:
        await send
        assert queue.qsize() == 1
        assert len(list(attachments.iterdir())) == 1


@pytest.mark.parametrize("component_type", ["image", "record"])
@pytest.mark.asyncio
async def test_webchat_cancellation_waits_for_background_write_cleanup(
    monkeypatch,
    tmp_path,
    component_type,
):
    event = _StopEvent()
    queue = asyncio.Queue()
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    monkeypatch.setattr(webchat_event, "attachments_dir", str(attachments))
    monkeypatch.setattr(
        webchat_event.webchat_queue_mgr,
        "get_or_create_back_queue",
        lambda *_args, **_kwargs: queue,
    )

    if component_type == "image":
        component = Image(file="ignored")
        monkeypatch.setattr(
            Image,
            "convert_to_base64",
            AsyncMock(return_value="aGVsbG8="),
        )
    else:
        component = Record(file="ignored")
        monkeypatch.setattr(
            Record,
            "convert_to_base64",
            AsyncMock(return_value="YXVkaW8="),
        )

    write_started = threading.Event()
    release_write = threading.Event()

    async def delayed_to_thread(func, *args, **kwargs):
        def run():
            result = func(*args, **kwargs)
            write_started.set()
            release_write.wait()
            return result

        return await asyncio.get_running_loop().run_in_executor(None, run)

    monkeypatch.setattr(webchat_event.asyncio, "to_thread", delayed_to_thread)
    task = asyncio.create_task(
        WebChatMessageEvent._send(
            "message",
            MessageChain([component]),
            "webchat!user!conversation",
            stop_event=event,
        )
    )
    await asyncio.wait_for(
        asyncio.get_running_loop().run_in_executor(None, write_started.wait),
        timeout=1,
    )
    task.cancel()
    await asyncio.sleep(0)
    release_write.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert queue.empty()
    assert list(attachments.iterdir()) == []


@pytest.mark.parametrize("event_type", ["wecom_kf", "wecom_app", "weixin"])
@pytest.mark.asyncio
async def test_amr_conversion_stop_still_cleans_temporary_file(
    monkeypatch,
    tmp_path,
    event_type,
):
    converted_path = tmp_path / f"{event_type}.amr"
    converted_path.write_bytes(b"audio")

    async def convert_to_file_path(_record):
        return str(tmp_path / "source.wav")

    monkeypatch.setattr(Record, "convert_to_file_path", convert_to_file_path)

    if event_type.startswith("wecom"):
        event = object.__new__(WecomPlatformEvent)
        event._extras = {}
        event._force_stopped = False
        event._result = None
        event.message_obj = SimpleNamespace(self_id="bot", session_id="user")
        event.get_sender_id = lambda: "user"
        event.get_self_id = lambda: "bot"
        if event_type == "wecom_kf":

            class FakeKFMessage:
                pass

            monkeypatch.setattr(wecom_event, "WeChatKFMessage", FakeKFMessage)
            event.client = SimpleNamespace(
                kf_message=FakeKFMessage(),
                message=SimpleNamespace(),
                media=SimpleNamespace(),
            )
        else:
            event.client = SimpleNamespace(
                message=SimpleNamespace(),
                media=SimpleNamespace(),
            )
        module = wecom_event
    else:
        from astrbot.core.platform.sources.weixin_official_account import (
            weixin_offacc_event,
        )

        event = object.__new__(WeixinOfficialAccountPlatformEvent)
        event._extras = {}
        event._force_stopped = False
        event._result = None
        event.message_out = {}
        event.message_obj = SimpleNamespace(
            raw_message={"active_send_mode": True},
            sender=SimpleNamespace(user_id="user"),
        )
        event.client = SimpleNamespace(
            message=SimpleNamespace(),
            media=SimpleNamespace(),
        )
        module = weixin_offacc_event

    async def convert_audio(_path):
        event.set_extra("agent_stop_requested", True)
        return str(converted_path)

    monkeypatch.setattr(module, "convert_audio_to_amr", convert_audio)

    with pytest.raises(AgentOutputStopped):
        await event.send(MessageChain([Record(file="source.wav")]))

    assert not converted_path.exists()


@pytest.mark.parametrize("output_kind", ["new", "existing", "dangling_symlink"])
@pytest.mark.asyncio
async def test_cancelled_audio_conversion_reaps_process_and_preserves_ownership(
    monkeypatch,
    tmp_path,
    output_kind,
):
    output_path = tmp_path / "cancelled.amr"
    target_path = None
    if output_kind == "existing":
        output_path.write_bytes(b"original audio")
    elif output_kind == "dangling_symlink":
        target_path = tmp_path / "missing-target.amr"
        output_path.symlink_to(target_path.name)
    output_created = asyncio.Event()
    wait_started = asyncio.Event()
    release_wait = asyncio.Event()

    class Process:
        returncode = None
        killed = False
        waited = False
        output_path = None

        async def communicate(self):
            self.output_path.write_bytes(b"partial audio")
            output_created.set()
            await asyncio.Event().wait()

        def kill(self):
            self.killed = True

        async def wait(self):
            self.waited = True
            wait_started.set()
            await release_wait.wait()
            self.returncode = -9
            return self.returncode

    process = Process()

    async def create_subprocess_exec(*args, **_kwargs):
        process.output_path = Path(args[-1])
        return process

    monkeypatch.setattr(
        media_utils.asyncio,
        "create_subprocess_exec",
        create_subprocess_exec,
    )
    task = asyncio.create_task(
        media_utils.convert_audio_format(
            "source.wav",
            "amr",
            str(output_path),
        )
    )
    await asyncio.wait_for(output_created.wait(), timeout=1)
    task.cancel()
    await asyncio.wait_for(wait_started.wait(), timeout=1)
    task.cancel()
    await asyncio.sleep(0)
    release_wait.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert process.killed is True
    assert process.waited is True
    assert not process.output_path.exists()
    if output_kind == "existing":
        assert output_path.read_bytes() == b"original audio"
    elif output_kind == "dangling_symlink":
        assert output_path.is_symlink()
        assert not target_path.exists()
    else:
        assert not output_path.exists()


@pytest.mark.parametrize("failure", [FileNotFoundError("ffmpeg"), OSError("spawn")])
@pytest.mark.asyncio
async def test_audio_spawn_failure_preserves_preexisting_explicit_output(
    monkeypatch,
    tmp_path,
    failure,
):
    output_path = tmp_path / "existing.amr"
    output_path.write_bytes(b"original audio")

    async def create_subprocess_exec(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(
        media_utils.asyncio,
        "create_subprocess_exec",
        create_subprocess_exec,
    )

    with pytest.raises(Exception):
        await media_utils.convert_audio_format(
            "source.wav",
            "amr",
            str(output_path),
        )

    assert output_path.read_bytes() == b"original audio"


@pytest.mark.parametrize("output_kind", ["new", "existing", "symlink"])
@pytest.mark.asyncio
async def test_successful_audio_conversion_keeps_explicit_output(
    monkeypatch,
    tmp_path,
    output_kind,
):
    output_path = tmp_path / "converted.amr"
    target_path = None
    if output_kind == "existing":
        output_path.write_bytes(b"original audio")
    elif output_kind == "symlink":
        target_path = tmp_path / "converted-target.amr"
        target_path.write_bytes(b"original audio")
        output_path.symlink_to(target_path.name)

    class Process:
        returncode = 0

        def __init__(self, converter_output_path):
            self.output_path = converter_output_path

        async def communicate(self):
            self.output_path.write_bytes(b"converted audio")
            return b"", b""

    async def create_subprocess_exec(*args, **_kwargs):
        return Process(Path(args[-1]))

    monkeypatch.setattr(
        media_utils.asyncio,
        "create_subprocess_exec",
        create_subprocess_exec,
    )

    result = await media_utils.convert_audio_format(
        "source.wav",
        "amr",
        str(output_path),
    )

    assert result == str(output_path)
    assert output_path.read_bytes() == b"converted audio"
    if output_kind == "symlink":
        assert output_path.is_symlink()
        assert target_path.read_bytes() == b"converted audio"


@pytest.mark.asyncio
async def test_weixin_oc_text_failure_is_not_hidden_by_media_success():
    adapter = object.__new__(WeixinOCAdapter)
    adapter.token = "token"
    calls = []

    async def resolve_path(*_args, **_kwargs):
        return Path("/tmp/ignored.jpg")

    async def prepare_item(*_args, **_kwargs):
        return {"type": adapter.IMAGE_ITEM_TYPE, "image_item": {}}

    async def send_items(_user_id, item_list, **_kwargs):
        calls.append(item_list)
        return False

    adapter._resolve_media_file_path = resolve_path
    adapter._prepare_media_item = prepare_item
    adapter._send_items_to_session = send_items

    sent = await adapter._send_media_segment(
        "user",
        Image(file="ignored"),
        text="required text",
    )

    assert sent is False
    assert len(calls) == 1
    assert calls[0][0]["type"] == 1


@pytest.mark.asyncio
async def test_wecom_stop_between_plain_chunks_blocks_later_writes(monkeypatch):
    event = object.__new__(WecomPlatformEvent)
    event._extras = {}
    event._force_stopped = False
    event._result = None
    event.message_obj = SimpleNamespace(self_id="bot", session_id="user")
    writes = []

    def send_text(*_args):
        writes.append(_args[-1])
        event.set_extra("agent_stop_requested", True)

    event.client = SimpleNamespace(
        message=SimpleNamespace(send_text=send_text),
    )
    monkeypatch.setattr(wecom_event.asyncio, "sleep", AsyncMock())

    with pytest.raises(AgentOutputStopped):
        await event.send(MessageChain().message("x" * 2050))
    assert len(writes) == 1


@pytest.mark.asyncio
async def test_weixin_official_stop_after_conversion_blocks_platform_write(
    monkeypatch,
):
    event = object.__new__(WeixinOfficialAccountPlatformEvent)
    event._extras = {}
    event._force_stopped = False
    event._result = None
    event.message_out = {}
    event.message_obj = SimpleNamespace(
        raw_message={"active_send_mode": True},
        sender=SimpleNamespace(user_id="user"),
    )
    upload = MagicMock(return_value={"media_id": "media"})
    send_image = MagicMock()
    event.client = SimpleNamespace(
        media=SimpleNamespace(upload=upload),
        message=SimpleNamespace(send_image=send_image),
    )

    async def convert_to_file_path(_image):
        event.set_extra("agent_stop_requested", True)
        return "/tmp/ignored.jpg"

    monkeypatch.setattr(Image, "convert_to_file_path", convert_to_file_path)

    with pytest.raises(AgentOutputStopped):
        await event.send(MessageChain([Image(file="ignored")]))
    upload.assert_not_called()
    send_image.assert_not_called()
