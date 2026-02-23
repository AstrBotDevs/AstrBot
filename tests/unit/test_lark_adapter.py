"""Isolated tests for Lark adapter using subprocess + stubbed lark_oapi."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path


def _run_python(code: str) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


def _assert_lark_case(case: str) -> None:
    code = f"""
    import asyncio
    import json
    import sys
    import types

    case = {case!r}

    lark = types.ModuleType("lark_oapi")
    lark.FEISHU_DOMAIN = "https://open.feishu.cn"
    lark.LogLevel = types.SimpleNamespace(ERROR="ERROR")

    class DispatcherBuilder:
        def register_p2_im_message_receive_v1(self, callback):
            self.callback = callback
            return self

        def build(self):
            return object()

    class EventDispatcherHandler:
        @staticmethod
        def builder(*args, **kwargs):
            return DispatcherBuilder()

    lark.EventDispatcherHandler = EventDispatcherHandler

    class WSClient:
        def __init__(self, *args, **kwargs):
            self.connected = False
            self.disconnected = False

        async def _connect(self):
            self.connected = True

        async def _disconnect(self):
            self.disconnected = True

    lark.ws = types.SimpleNamespace(Client=WSClient)

    class BuilderObj:
        def message_id(self, *args, **kwargs):
            return self

        def file_key(self, *args, **kwargs):
            return self

        def type(self, *args, **kwargs):
            return self

        def request_body(self, *args, **kwargs):
            return self

        def content(self, *args, **kwargs):
            return self

        def msg_type(self, *args, **kwargs):
            return self

        def uuid(self, *args, **kwargs):
            return self

        def reply_in_thread(self, *args, **kwargs):
            return self

        def receive_id_type(self, *args, **kwargs):
            return self

        def receive_id(self, *args, **kwargs):
            return self

        def file_type(self, *args, **kwargs):
            return self

        def file_name(self, *args, **kwargs):
            return self

        def file(self, *args, **kwargs):
            return self

        def duration(self, *args, **kwargs):
            return self

        def image_type(self, *args, **kwargs):
            return self

        def image(self, *args, **kwargs):
            return self

        def build(self):
            return object()

    class GetMessageRequest:
        @staticmethod
        def builder():
            return BuilderObj()

    class GetMessageResourceRequest:
        @staticmethod
        def builder():
            return BuilderObj()

    class DummyResponse:
        code = 0
        msg = ""
        file = None

        def success(self):
            return False

    class MessageAPI:
        async def aget(self, request):
            return DummyResponse()

    class MessageResourceAPI:
        async def aget(self, request):
            return DummyResponse()

    class APIBuilder:
        def app_id(self, *args, **kwargs):
            return self

        def app_secret(self, *args, **kwargs):
            return self

        def log_level(self, *args, **kwargs):
            return self

        def domain(self, *args, **kwargs):
            return self

        def build(self):
            return types.SimpleNamespace(
                im=types.SimpleNamespace(
                    v1=types.SimpleNamespace(
                        message=MessageAPI(),
                        message_resource=MessageResourceAPI(),
                    )
                )
            )

    class Client:
        @staticmethod
        def builder():
            return APIBuilder()

    lark.Client = Client
    lark.im = types.SimpleNamespace(v1=types.SimpleNamespace(P2ImMessageReceiveV1=object))

    sys.modules["lark_oapi"] = lark
    sys.modules["lark_oapi.api"] = types.ModuleType("lark_oapi.api")
    sys.modules["lark_oapi.api.im"] = types.ModuleType("lark_oapi.api.im")

    v1_mod = types.ModuleType("lark_oapi.api.im.v1")
    v1_mod.GetMessageRequest = GetMessageRequest
    v1_mod.GetMessageResourceRequest = GetMessageResourceRequest
    v1_mod.CreateFileRequest = GetMessageRequest
    v1_mod.CreateFileRequestBody = GetMessageRequest
    v1_mod.CreateImageRequest = GetMessageRequest
    v1_mod.CreateImageRequestBody = GetMessageRequest
    v1_mod.CreateMessageReactionRequest = GetMessageRequest
    v1_mod.CreateMessageReactionRequestBody = GetMessageRequest
    v1_mod.ReplyMessageRequest = GetMessageRequest
    v1_mod.ReplyMessageRequestBody = GetMessageRequest
    v1_mod.CreateMessageRequest = GetMessageRequest
    v1_mod.CreateMessageRequestBody = GetMessageRequest
    v1_mod.Emoji = object
    sys.modules["lark_oapi.api.im.v1"] = v1_mod

    processor_mod = types.ModuleType("lark_oapi.api.im.v1.processor")

    class P2ImMessageReceiveV1Processor:
        def __init__(self, callback):
            self.callback = callback

        def type(self):
            return lambda x: x

        def do(self, data):
            return None

    processor_mod.P2ImMessageReceiveV1Processor = P2ImMessageReceiveV1Processor
    sys.modules["lark_oapi.api.im.v1.processor"] = processor_mod

    from astrbot.api.message_components import At, Image, Plain
    from astrbot.api.platform import MessageType
    from astrbot.core.platform.sources.lark.lark_adapter import LarkPlatformAdapter

    def _cfg(mode="socket", bot_name="astrbot"):
        data = {{
            "id": "lark_test",
            "app_id": "appid",
            "app_secret": "secret",
            "lark_connection_mode": mode,
            "lark_bot_name": bot_name,
        }}
        return data

    def _build_event(chat_type="group", text="Hello World", sender_id="ou_user", chat_id="oc_chat"):
        message = types.SimpleNamespace(
            create_time=1700000000000,
            message=[],
            chat_type=chat_type,
            chat_id=chat_id,
            content=json.dumps({{"text": text}}),
            message_type="text",
            parent_id=None,
            mentions=[],
            message_id="om_message_1",
        )
        sender = types.SimpleNamespace(sender_id=types.SimpleNamespace(open_id=sender_id))
        return types.SimpleNamespace(event=types.SimpleNamespace(message=message, sender=sender))

    async def _run_async_case():
        if case in {{"convert_text", "convert_group", "convert_private"}}:
            adapter = LarkPlatformAdapter(_cfg("socket"), {{}}, asyncio.Queue())
            capture = {{"abm": None}}

            async def _handle_msg(abm):
                capture["abm"] = abm

            adapter.handle_msg = _handle_msg

            if case == "convert_private":
                event = _build_event(chat_type="p2p", sender_id="ou_private", chat_id="")
            else:
                event = _build_event(chat_type="group", sender_id="ou_group", chat_id="oc_group")

            await adapter.convert_msg(event)
            abm = capture["abm"]
            assert abm is not None
            assert abm.message_str == "Hello World"
            if case == "convert_private":
                assert abm.type == MessageType.FRIEND_MESSAGE
                assert abm.session_id == "ou_private"
            else:
                assert abm.type == MessageType.GROUP_MESSAGE
                assert abm.group_id == "oc_group"
                assert abm.session_id == "oc_group"
            return

        if case == "terminate_socket":
            adapter = LarkPlatformAdapter(_cfg("socket"), {{}}, asyncio.Queue())
            assert adapter.client.disconnected is False
            await adapter.terminate()
            assert adapter.client.disconnected is True
            return

        if case == "terminate_webhook":
            adapter = LarkPlatformAdapter(_cfg("webhook"), {{}}, asyncio.Queue())
            assert adapter.client.disconnected is False
            await adapter.terminate()
            assert adapter.client.disconnected is False
            return

        raise AssertionError(f"Unknown async case: {{case}}")

    if case == "init_socket_basic":
        adapter = LarkPlatformAdapter(_cfg("socket"), {{}}, asyncio.Queue())
        assert adapter.connection_mode == "socket"
        assert adapter.webhook_server is None

    elif case == "init_webhook_basic":
        adapter = LarkPlatformAdapter(_cfg("webhook"), {{}}, asyncio.Queue())
        assert adapter.connection_mode == "webhook"
        assert adapter.webhook_server is not None

    elif case == "init_without_bot_name_warning":
        adapter = LarkPlatformAdapter(_cfg("socket", bot_name=""), {{}}, asyncio.Queue())
        assert adapter.bot_name == ""

    elif case == "meta":
        adapter = LarkPlatformAdapter(_cfg("socket"), {{}}, asyncio.Queue())
        meta = adapter.meta()
        assert meta.name == "lark"
        assert meta.id == "lark_test"

    elif case == "build_message_str":
        message = LarkPlatformAdapter._build_message_str_from_components([Plain("hello"), Plain("world")])
        assert message == "hello world"

    elif case == "build_message_str_with_at":
        message = LarkPlatformAdapter._build_message_str_from_components([At(qq="ou1", name="tester")])
        assert message == "@tester"

    elif case == "build_message_str_with_image":
        message = LarkPlatformAdapter._build_message_str_from_components([Image.fromBase64("aGVsbG8=")])
        assert message == "[image]"

    elif case == "event_id_tracking":
        adapter = LarkPlatformAdapter(_cfg("socket"), {{}}, asyncio.Queue())
        assert adapter._is_duplicate_event("event-1") is False
        assert adapter._is_duplicate_event("event-1") is True

    elif case in {{
        "convert_text",
        "convert_group",
        "convert_private",
        "terminate_socket",
        "terminate_webhook",
    }}:
        asyncio.run(_run_async_case())

    else:
        raise AssertionError(f"Unknown case: {{case}}")
    """
    proc = _run_python(code)
    assert proc.returncode == 0, (
        "Lark subprocess test failed.\n"
        f"case={case}\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}\n"
    )


class TestLarkAdapterInit:
    def test_init_socket_mode_basic(self):
        _assert_lark_case("init_socket_basic")

    def test_init_webhook_mode_basic(self):
        _assert_lark_case("init_webhook_basic")

    def test_init_without_bot_name_warning(self):
        _assert_lark_case("init_without_bot_name_warning")


class TestLarkAdapterMetadata:
    def test_meta_returns_correct_metadata(self):
        _assert_lark_case("meta")


class TestLarkAdapterConvertMessage:
    def test_convert_text_message(self):
        _assert_lark_case("convert_text")

    def test_convert_group_message(self):
        _assert_lark_case("convert_group")

    def test_convert_private_message(self):
        _assert_lark_case("convert_private")


class TestLarkAdapterUtilityMethods:
    def test_build_message_str_from_components(self):
        _assert_lark_case("build_message_str")

    def test_build_message_str_with_at(self):
        _assert_lark_case("build_message_str_with_at")

    def test_build_message_str_with_image(self):
        _assert_lark_case("build_message_str_with_image")


class TestLarkAdapterEventDeduplication:
    def test_event_id_tracking(self):
        _assert_lark_case("event_id_tracking")


class TestLarkAdapterTerminate:
    def test_terminate_socket_mode(self):
        _assert_lark_case("terminate_socket")

    def test_terminate_webhook_mode(self):
        _assert_lark_case("terminate_webhook")
