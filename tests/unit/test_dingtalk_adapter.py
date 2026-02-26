"""Isolated tests for DingTalk adapter using subprocess + stubbed dingtalk_stream."""

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


def _assert_dingtalk_case(case: str) -> None:
    code = f"""
    import asyncio
    import sys
    import threading
    import types

    case = {case!r}

    dingtalk = types.ModuleType("dingtalk_stream")

    class EventHandler:
        pass

    class EventMessage:
        pass

    class AckMessage:
        STATUS_OK = "OK"

    class Credential:
        def __init__(self, *args, **kwargs):
            pass

    class ChatbotHandler:
        pass

    class CallbackMessage:
        pass

    class ChatbotMessage:
        TOPIC = "/v1.0/chatbot/messages"

        @staticmethod
        def from_dict(data):
            return types.SimpleNamespace(
                create_at=1700000000000,
                conversation_type="1",
                sender_id=data.get("sender_id", "user_1"),
                sender_nick="Nick",
                chatbot_user_id="bot_1",
                message_id="msg_1",
                at_users=[],
                conversation_id=data.get("conversation_id", "conv_1"),
                message_type="text",
                text=types.SimpleNamespace(content=data.get("text", "hello")),
                sender_staff_id=data.get("sender_staff_id", "staff_1"),
                robot_code="robot_1",
            )

    class DummyWS:
        def __init__(self):
            self.closed = False

        async def close(self, code=1000, reason=""):
            self.closed = True

    class DingTalkStreamClient:
        def __init__(self, *args, **kwargs):
            self.websocket = None
            self.handlers = []
            self.callback_handlers = []
            self.open_connection = None

        def register_all_event_handler(self, handler):
            self.handlers.append(handler)

        def register_callback_handler(self, topic, handler):
            self.callback_handlers.append((topic, handler))

        async def start(self):
            return None

        def get_access_token(self):
            return "token"

    class RichTextContent:
        pass

    dingtalk.EventHandler = EventHandler
    dingtalk.EventMessage = EventMessage
    dingtalk.AckMessage = AckMessage
    dingtalk.Credential = Credential
    dingtalk.ChatbotHandler = ChatbotHandler
    dingtalk.CallbackMessage = CallbackMessage
    dingtalk.ChatbotMessage = ChatbotMessage
    dingtalk.DingTalkStreamClient = DingTalkStreamClient
    dingtalk.RichTextContent = RichTextContent

    sys.modules["dingtalk_stream"] = dingtalk

    from astrbot.api.message_components import Plain
    from astrbot.core.message.message_event_result import MessageChain
    from astrbot.core.platform.astr_message_event import MessageSesion
    from astrbot.api.platform import MessageType
    from astrbot.core.platform.sources.dingtalk.dingtalk_adapter import DingtalkPlatformAdapter

    def _cfg():
        return {{
            "id": "dingtalk_test",
            "client_id": "client_id",
            "client_secret": "client_secret",
        }}

    async def _run_async_case():
        if case == "send_group":
            adapter = DingtalkPlatformAdapter(_cfg(), {{}}, asyncio.Queue())
            called = {{"ok": False}}

            async def _send_group(open_conversation_id, robot_code, message_chain):
                called["ok"] = True
                assert open_conversation_id == "group_1"
                assert robot_code == "client_id"

            adapter.send_message_chain_to_group = _send_group
            session = MessageSesion(
                platform_name="dingtalk",
                message_type=MessageType.GROUP_MESSAGE,
                session_id="group_1",
            )
            await adapter.send_by_session(session, MessageChain([Plain("hello")]))
            assert called["ok"] is True
            return

        if case == "send_private":
            adapter = DingtalkPlatformAdapter(_cfg(), {{}}, asyncio.Queue())
            called = {{"ok": False}}

            async def _get_staff(session):
                return "staff_99"

            async def _send_user(staff_id, robot_code, message_chain):
                called["ok"] = True
                assert staff_id == "staff_99"
                assert robot_code == "client_id"

            adapter._get_sender_staff_id = _get_staff
            adapter.send_message_chain_to_user = _send_user
            session = MessageSesion(
                platform_name="dingtalk",
                message_type=MessageType.FRIEND_MESSAGE,
                session_id="user_1",
            )
            await adapter.send_by_session(session, MessageChain([Plain("hello")]))
            assert called["ok"] is True
            return

        if case == "send_with_sesison_typo":
            adapter = DingtalkPlatformAdapter(_cfg(), {{}}, asyncio.Queue())
            called = {{"ok": False}}

            async def _send_by_session(session, message_chain):
                called["ok"] = True

            adapter.send_by_session = _send_by_session
            session = MessageSesion(
                platform_name="dingtalk",
                message_type=MessageType.FRIEND_MESSAGE,
                session_id="user_1",
            )
            await adapter.send_with_sesison(session, MessageChain([Plain("hello")]))
            assert called["ok"] is True
            return

        if case == "terminate":
            adapter = DingtalkPlatformAdapter(_cfg(), {{}}, asyncio.Queue())
            ws = DummyWS()
            adapter.client_.websocket = ws
            adapter._shutdown_event = threading.Event()
            await adapter.terminate()
            assert ws.closed is True
            assert adapter._shutdown_event.is_set() is True
            return

        raise AssertionError(f"Unknown async case: {{case}}")

    if case == "init_basic":
        adapter = DingtalkPlatformAdapter(_cfg(), {{}}, asyncio.Queue())
        assert adapter.client_id == "client_id"
        assert adapter.client_secret == "client_secret"

    elif case == "init_creates_client":
        adapter = DingtalkPlatformAdapter(_cfg(), {{}}, asyncio.Queue())
        assert adapter.client is not None
        assert adapter.client_ is not None

    elif case == "meta":
        adapter = DingtalkPlatformAdapter(_cfg(), {{}}, asyncio.Queue())
        meta = adapter.meta()
        assert meta.name == "dingtalk"
        assert meta.id == "dingtalk_test"

    elif case == "id_with_prefix":
        adapter = DingtalkPlatformAdapter(_cfg(), {{}}, asyncio.Queue())
        assert adapter._id_to_sid("$:LWCP_v1:$abc") == "abc"

    elif case == "id_without_prefix":
        adapter = DingtalkPlatformAdapter(_cfg(), {{}}, asyncio.Queue())
        assert adapter._id_to_sid("abc") == "abc"

    elif case == "id_none":
        adapter = DingtalkPlatformAdapter(_cfg(), {{}}, asyncio.Queue())
        assert adapter._id_to_sid(None) == "unknown"

    elif case == "id_empty":
        adapter = DingtalkPlatformAdapter(_cfg(), {{}}, asyncio.Queue())
        assert adapter._id_to_sid("") == "unknown"

    elif case in {{"send_group", "send_private", "send_with_sesison_typo", "terminate"}}:
        asyncio.run(_run_async_case())

    else:
        raise AssertionError(f"Unknown case: {{case}}")
    """
    proc = _run_python(code)
    assert proc.returncode == 0, (
        "DingTalk subprocess test failed.\n"
        f"case={case}\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}\n"
    )


class TestDingtalkAdapterInit:
    def test_init_basic(self):
        _assert_dingtalk_case("init_basic")

    def test_init_creates_client(self):
        _assert_dingtalk_case("init_creates_client")


class TestDingtalkAdapterMetadata:
    def test_meta_returns_correct_metadata(self):
        _assert_dingtalk_case("meta")


class TestDingtalkAdapterIdConversion:
    def test_id_to_sid_with_prefix(self):
        _assert_dingtalk_case("id_with_prefix")

    def test_id_to_sid_without_prefix(self):
        _assert_dingtalk_case("id_without_prefix")

    def test_id_to_sid_with_none(self):
        _assert_dingtalk_case("id_none")

    def test_id_to_sid_with_empty_string(self):
        _assert_dingtalk_case("id_empty")


class TestDingtalkAdapterSendMessage:
    def test_send_by_session_group_message(self):
        _assert_dingtalk_case("send_group")

    def test_send_by_session_private_message(self):
        _assert_dingtalk_case("send_private")


class TestDingtalkAdapterTypoCompatibility:
    def test_send_with_sesison_typo(self):
        _assert_dingtalk_case("send_with_sesison_typo")


class TestDingtalkAdapterTerminate:
    def test_terminate(self):
        _assert_dingtalk_case("terminate")
