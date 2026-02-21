"""Runtime coverage for scenarios previously represented by skipped adapter tests.

These tests run in isolated Python subprocesses and install lightweight SDK stubs
so we can execute critical adapter paths without changing existing skipped tests.
"""

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


def _assert_ok(code: str) -> None:
    proc = _run_python(code)
    assert proc.returncode == 0, (
        f"Subprocess test failed.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}\n"
    )


def test_platform_manager_cycle_and_helpers_work() -> None:
    _assert_ok(
        """
        import asyncio

        from astrbot.core.platform.manager import PlatformManager


        class DummyConfig(dict):
            def save_config(self):
                self["_saved"] = True


        cfg = DummyConfig({"platform": [], "platform_settings": {}})
        manager = PlatformManager(cfg, asyncio.Queue())
        assert manager._is_valid_platform_id("platform_1")
        assert not manager._is_valid_platform_id("bad:id")
        assert manager._sanitize_platform_id("bad:id!x") == ("bad_id_x", True)
        assert manager._sanitize_platform_id("ok") == ("ok", False)
        stats = manager.get_all_stats()
        assert stats["summary"]["total"] == 0
        """
    )


def test_slack_adapter_smoke_without_external_sdk() -> None:
    _assert_ok(
        """
        import asyncio
        import types
        import sys

        quart = types.ModuleType("quart")

        class Quart:
            def __init__(self, *args, **kwargs):
                pass

            def route(self, *args, **kwargs):
                def deco(fn):
                    return fn
                return deco

            async def run_task(self, *args, **kwargs):
                return None

        class Response:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        quart.Quart = Quart
        quart.Response = Response
        quart.request = types.SimpleNamespace()
        sys.modules["quart"] = quart

        slack_sdk = types.ModuleType("slack_sdk")
        sys.modules["slack_sdk"] = slack_sdk
        sys.modules["slack_sdk.socket_mode"] = types.ModuleType("slack_sdk.socket_mode")

        req_mod = types.ModuleType("slack_sdk.socket_mode.request")
        class SocketModeRequest:
            def __init__(self):
                self.type = "events_api"
                self.payload = {}
                self.envelope_id = "env"
        req_mod.SocketModeRequest = SocketModeRequest
        sys.modules["slack_sdk.socket_mode.request"] = req_mod

        aiohttp_mod = types.ModuleType("slack_sdk.socket_mode.aiohttp")
        class SocketModeClient:
            def __init__(self, *args, **kwargs):
                self.socket_mode_request_listeners = []
            async def connect(self):
                return None
            async def disconnect(self):
                return None
            async def close(self):
                return None
            async def send_socket_mode_response(self, response):
                return None
        aiohttp_mod.SocketModeClient = SocketModeClient
        sys.modules["slack_sdk.socket_mode.aiohttp"] = aiohttp_mod

        async_client_mod = types.ModuleType("slack_sdk.socket_mode.async_client")
        async_client_mod.AsyncBaseSocketModeClient = object
        sys.modules["slack_sdk.socket_mode.async_client"] = async_client_mod

        resp_mod = types.ModuleType("slack_sdk.socket_mode.response")
        class SocketModeResponse:
            def __init__(self, envelope_id):
                self.envelope_id = envelope_id
        resp_mod.SocketModeResponse = SocketModeResponse
        sys.modules["slack_sdk.socket_mode.response"] = resp_mod

        sys.modules["slack_sdk.web"] = types.ModuleType("slack_sdk.web")
        web_async_mod = types.ModuleType("slack_sdk.web.async_client")
        class AsyncWebClient:
            def __init__(self, *args, **kwargs):
                pass
            async def auth_test(self):
                return {"user_id": "U1"}
            async def users_info(self, user):
                return {"user": {"name": "user", "real_name": "User"}}
            async def conversations_info(self, channel):
                return {"channel": {"is_im": False, "name": "general"}}
            async def chat_postMessage(self, **kwargs):
                return {"ok": True}
        web_async_mod.AsyncWebClient = AsyncWebClient
        sys.modules["slack_sdk.web.async_client"] = web_async_mod

        from astrbot.core.platform.sources.slack.slack_adapter import SlackAdapter

        adapter = SlackAdapter(
            {
                "id": "slack_test",
                "bot_token": "xoxb-test",
                "app_token": "xapp-test",
                "slack_connection_mode": "socket",
            },
            {},
            asyncio.Queue(),
        )
        assert adapter.meta().name == "slack"

        try:
            SlackAdapter({"id": "bad"}, {}, asyncio.Queue())
            raise AssertionError("Expected ValueError for missing bot_token")
        except ValueError:
            pass
        """
    )


def test_wecom_adapter_smoke_without_external_sdk() -> None:
    _assert_ok(
        """
        import asyncio
        import types
        import sys

        optionaldict_mod = types.ModuleType("optionaldict")
        class optionaldict(dict):
            pass
        optionaldict_mod.optionaldict = optionaldict
        sys.modules["optionaldict"] = optionaldict_mod

        quart = types.ModuleType("quart")
        class Quart:
            def __init__(self, *args, **kwargs):
                pass
            def add_url_rule(self, *args, **kwargs):
                return None
            async def run_task(self, *args, **kwargs):
                return None
            async def shutdown(self):
                return None
        quart.Quart = Quart
        quart.request = types.SimpleNamespace()
        sys.modules["quart"] = quart

        wechatpy = types.ModuleType("wechatpy")
        enterprise = types.ModuleType("wechatpy.enterprise")
        crypto_mod = types.ModuleType("wechatpy.enterprise.crypto")
        enterprise_messages = types.ModuleType("wechatpy.enterprise.messages")
        exceptions_mod = types.ModuleType("wechatpy.exceptions")
        messages_mod = types.ModuleType("wechatpy.messages")
        client_mod = types.ModuleType("wechatpy.client")
        client_api_mod = types.ModuleType("wechatpy.client.api")
        client_base_mod = types.ModuleType("wechatpy.client.api.base")

        class BaseWeChatAPI:
            def _post(self, *args, **kwargs):
                return {}
            def _get(self, *args, **kwargs):
                return {}
        client_base_mod.BaseWeChatAPI = BaseWeChatAPI

        class InvalidSignatureException(Exception):
            pass
        exceptions_mod.InvalidSignatureException = InvalidSignatureException

        class BaseMessage:
            type = "text"
        messages_mod.BaseMessage = BaseMessage

        class TextMessage(BaseMessage):
            def __init__(self, content="hello"):
                self.type = "text"
                self.content = content
                self.agent = "agent_1"
                self.source = "user_1"
                self.id = "msg_1"
                self.time = 1700000000

        class ImageMessage(BaseMessage):
            def __init__(self):
                self.type = "image"
                self.image = "https://example.com/a.jpg"
                self.agent = "agent_1"
                self.source = "user_1"
                self.id = "msg_2"
                self.time = 1700000000

        class VoiceMessage(BaseMessage):
            def __init__(self):
                self.type = "voice"
                self.media_id = "media_1"
                self.agent = "agent_1"
                self.source = "user_1"
                self.id = "msg_3"
                self.time = 1700000000

        enterprise_messages.TextMessage = TextMessage
        enterprise_messages.ImageMessage = ImageMessage
        enterprise_messages.VoiceMessage = VoiceMessage

        class WeChatCrypto:
            def __init__(self, *args, **kwargs):
                pass
            def check_signature(self, *args, **kwargs):
                return "ok"
            def decrypt_message(self, *args, **kwargs):
                return "<xml></xml>"
        crypto_mod.WeChatCrypto = WeChatCrypto

        class WeChatClient:
            def __init__(self, *args, **kwargs):
                self.message = types.SimpleNamespace(
                    send_text=lambda *a, **k: {"errcode": 0},
                    send_image=lambda *a, **k: {"errcode": 0},
                    send_voice=lambda *a, **k: {"errcode": 0},
                    send_file=lambda *a, **k: {"errcode": 0},
                )
                self.media = types.SimpleNamespace(
                    download=lambda media_id: types.SimpleNamespace(content=b"voice"),
                    upload=lambda *a, **k: {"media_id": "m1"},
                )
        enterprise.WeChatClient = WeChatClient
        enterprise.parse_message = lambda xml: TextMessage("xml")

        wechatpy.enterprise = enterprise
        wechatpy.exceptions = exceptions_mod
        wechatpy.messages = messages_mod
        wechatpy.client = client_mod
        client_mod.api = client_api_mod
        client_api_mod.base = client_base_mod

        sys.modules["wechatpy"] = wechatpy
        sys.modules["wechatpy.enterprise"] = enterprise
        sys.modules["wechatpy.enterprise.crypto"] = crypto_mod
        sys.modules["wechatpy.enterprise.messages"] = enterprise_messages
        sys.modules["wechatpy.exceptions"] = exceptions_mod
        sys.modules["wechatpy.messages"] = messages_mod
        sys.modules["wechatpy.client"] = client_mod
        sys.modules["wechatpy.client.api"] = client_api_mod
        sys.modules["wechatpy.client.api.base"] = client_base_mod

        from astrbot.core.platform.sources.wecom.wecom_adapter import WecomPlatformAdapter

        queue = asyncio.Queue()
        adapter = WecomPlatformAdapter(
            {
                "id": "wecom_test",
                "corpid": "corp",
                "secret": "sec",
                "token": "token",
                "encoding_aes_key": "x" * 43,
                "port": "8080",
                "callback_server_host": "0.0.0.0",
            },
            {},
            queue,
        )
        assert adapter.meta().name == "wecom"
        asyncio.run(adapter.convert_message(TextMessage("hello")))
        assert queue.qsize() == 1
        """
    )


def test_lark_adapter_smoke_without_external_sdk() -> None:
    _assert_ok(
        """
        import asyncio
        import types
        import sys

        lark = types.ModuleType("lark_oapi")
        lark.FEISHU_DOMAIN = "https://open.feishu.cn"
        lark.LogLevel = types.SimpleNamespace(ERROR="ERROR")

        class DispatcherBuilder:
            def register_p2_im_message_receive_v1(self, callback):
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
                pass
            async def _connect(self):
                return None
            async def _disconnect(self):
                return None
        lark.ws = types.SimpleNamespace(Client=WSClient)

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
                return types.SimpleNamespace(im=types.SimpleNamespace(v1=types.SimpleNamespace()))

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

        class BuilderObj:
            def __getattr__(self, name):
                def method(*args, **kwargs):
                    return self
                return method
            def build(self):
                return object()

        class Req:
            @staticmethod
            def builder():
                return BuilderObj()

        v1_mod.GetMessageRequest = Req
        v1_mod.GetMessageResourceRequest = Req
        v1_mod.CreateFileRequest = Req
        v1_mod.CreateFileRequestBody = Req
        v1_mod.CreateImageRequest = Req
        v1_mod.CreateImageRequestBody = Req
        v1_mod.CreateMessageReactionRequest = Req
        v1_mod.CreateMessageReactionRequestBody = Req
        v1_mod.ReplyMessageRequest = Req
        v1_mod.ReplyMessageRequestBody = Req
        v1_mod.CreateMessageRequest = Req
        v1_mod.CreateMessageRequestBody = Req
        v1_mod.Emoji = object
        sys.modules["lark_oapi.api.im.v1"] = v1_mod

        proc_mod = types.ModuleType("lark_oapi.api.im.v1.processor")
        class P2ImMessageReceiveV1Processor:
            def __init__(self, cb):
                self.cb = cb
            def type(self):
                return lambda data: data
            def do(self, data):
                return None
        proc_mod.P2ImMessageReceiveV1Processor = P2ImMessageReceiveV1Processor
        sys.modules["lark_oapi.api.im.v1.processor"] = proc_mod

        from astrbot.api.message_components import Plain
        from astrbot.core.platform.sources.lark.lark_adapter import LarkPlatformAdapter

        adapter = LarkPlatformAdapter(
            {
                "id": "lark_test",
                "app_id": "appid",
                "app_secret": "secret",
                "lark_connection_mode": "socket",
                "lark_bot_name": "astrbot",
            },
            {},
            asyncio.Queue(),
        )
        assert adapter.meta().name == "lark"
        assert adapter._build_message_str_from_components([Plain("hello")]) == "hello"
        assert adapter._is_duplicate_event("event_1") is False
        assert adapter._is_duplicate_event("event_1") is True
        """
    )


def test_dingtalk_adapter_smoke_without_external_sdk() -> None:
    _assert_ok(
        """
        import asyncio
        import types
        import sys

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

        class DingTalkStreamClient:
            def __init__(self, *args, **kwargs):
                self.websocket = None
            def register_all_event_handler(self, *args, **kwargs):
                return None
            def register_callback_handler(self, *args, **kwargs):
                return None
            async def start(self):
                return None
            def get_access_token(self):
                return "token"

        class ChatbotHandler:
            pass

        class CallbackMessage:
            pass

        class ChatbotMessage:
            TOPIC = "/v1.0/chatbot/messages"
            @staticmethod
            def from_dict(data):
                return types.SimpleNamespace(
                    create_at=0,
                    conversation_type="1",
                    sender_id="sender",
                    sender_nick="nick",
                    chatbot_user_id="bot",
                    message_id="msg",
                    at_users=[],
                    conversation_id="conv",
                    message_type="text",
                    text=types.SimpleNamespace(content="hello"),
                    sender_staff_id="staff",
                    robot_code="robot",
                )

        dingtalk.EventHandler = EventHandler
        dingtalk.EventMessage = EventMessage
        dingtalk.AckMessage = AckMessage
        dingtalk.Credential = Credential
        dingtalk.DingTalkStreamClient = DingTalkStreamClient
        dingtalk.ChatbotHandler = ChatbotHandler
        dingtalk.CallbackMessage = CallbackMessage
        dingtalk.ChatbotMessage = ChatbotMessage
        dingtalk.RichTextContent = object

        sys.modules["dingtalk_stream"] = dingtalk

        from astrbot.api.message_components import Plain
        from astrbot.api.platform import MessageType
        from astrbot.core.message.message_event_result import MessageChain
        from astrbot.core.platform.astr_message_event import MessageSesion
        from astrbot.core.platform.sources.dingtalk.dingtalk_adapter import (
            DingtalkPlatformAdapter,
        )

        adapter = DingtalkPlatformAdapter(
            {
                "id": "ding_test",
                "client_id": "client",
                "client_secret": "secret",
            },
            {},
            asyncio.Queue(),
        )
        assert adapter._id_to_sid("$:LWCP_v1:$abc") == "abc"

        called = {"ok": False}

        async def fake_send_by_session(session, chain):
            called["ok"] = True

        adapter.send_by_session = fake_send_by_session
        session = MessageSesion(
            platform_name="dingtalk",
            message_type=MessageType.FRIEND_MESSAGE,
            session_id="user_1",
        )
        asyncio.run(adapter.send_with_sesison(session, MessageChain([Plain("ping")])))
        assert called["ok"] is True
        """
    )


def test_other_adapters_runtime_imports() -> None:
    _assert_ok(
        """
        from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_server import (
            QQOfficialWebhook,
        )
        from astrbot.core.platform.sources.wecom_ai_bot.wecomai_webhook import (
            WecomAIBotWebhookClient,
        )
        from astrbot.core.platform.sources.line.line_adapter import LinePlatformAdapter
        from astrbot.core.platform.sources.satori.satori_adapter import (
            SatoriPlatformAdapter,
        )
        from astrbot.core.platform.sources.misskey.misskey_adapter import (
            MisskeyPlatformAdapter,
        )

        assert QQOfficialWebhook is not None
        assert WecomAIBotWebhookClient is not None
        assert LinePlatformAdapter is not None
        assert SatoriPlatformAdapter is not None
        assert MisskeyPlatformAdapter is not None
        """
    )


def test_line_satori_misskey_adapter_basic_init() -> None:
    _assert_ok(
        """
        import asyncio

        from astrbot.core.platform.sources.line.line_adapter import LinePlatformAdapter
        from astrbot.core.platform.sources.misskey.misskey_adapter import (
            MisskeyPlatformAdapter,
        )
        from astrbot.core.platform.sources.satori.satori_adapter import (
            SatoriPlatformAdapter,
        )

        queue = asyncio.Queue()

        line_adapter = LinePlatformAdapter(
            {
                "id": "line_test",
                "channel_access_token": "token",
                "channel_secret": "secret",
            },
            {},
            queue,
        )
        assert line_adapter.meta().name == "line"

        satori_adapter = SatoriPlatformAdapter(
            {"id": "satori_test"},
            {},
            queue,
        )
        assert satori_adapter.meta().name == "satori"

        misskey_adapter = MisskeyPlatformAdapter(
            {"id": "misskey_test"},
            {},
            queue,
        )
        assert misskey_adapter.meta().name == "misskey"
        """
    )


def test_wecom_ai_bot_webhook_client_basic() -> None:
    _assert_ok(
        """
        from astrbot.core.platform.sources.wecom_ai_bot.wecomai_webhook import (
            WecomAIBotWebhookClient,
        )

        client = WecomAIBotWebhookClient(
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test_key"
        )
        assert client._build_upload_url("file").startswith(
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?"
        )
        """
    )


def test_weixin_official_account_adapter_with_stubbed_wechatpy() -> None:
    _assert_ok(
        """
        import asyncio
        import types
        import sys

        quart = types.ModuleType("quart")
        class Quart:
            def __init__(self, *args, **kwargs):
                pass
            def add_url_rule(self, *args, **kwargs):
                return None
            async def run_task(self, *args, **kwargs):
                return None
            async def shutdown(self):
                return None
        quart.Quart = Quart
        quart.request = types.SimpleNamespace()
        sys.modules["quart"] = quart

        wechatpy = types.ModuleType("wechatpy")
        wechatpy.__path__ = []
        crypto_mod = types.ModuleType("wechatpy.crypto")
        exceptions_mod = types.ModuleType("wechatpy.exceptions")
        messages_mod = types.ModuleType("wechatpy.messages")
        replies_mod = types.ModuleType("wechatpy.replies")
        utils_mod = types.ModuleType("wechatpy.utils")

        class InvalidSignatureException(Exception):
            pass
        exceptions_mod.InvalidSignatureException = InvalidSignatureException

        class WeChatCrypto:
            def __init__(self, *args, **kwargs):
                pass
            def check_signature(self, *args, **kwargs):
                return "ok"
            def decrypt_message(self, *args, **kwargs):
                return "<xml></xml>"
            def encrypt_message(self, xml, nonce, ts):
                return xml
        crypto_mod.WeChatCrypto = WeChatCrypto

        class BaseMessage:
            type = "text"
            source = "user_1"
            id = "msg_1"
            time = 1700000000

        class TextMessage(BaseMessage):
            def __init__(self, content="hello"):
                self.type = "text"
                self.content = content
                self.source = "user_1"
                self.id = "msg_1"
                self.time = 1700000000
                self.target = "bot_1"

        class ImageMessage(BaseMessage):
            def __init__(self):
                self.type = "image"
                self.image = "https://example.com/a.jpg"
                self.source = "user_1"
                self.id = "msg_2"
                self.time = 1700000000
                self.target = "bot_1"

        class VoiceMessage(BaseMessage):
            def __init__(self):
                self.type = "voice"
                self.media_id = "media_1"
                self.source = "user_1"
                self.id = "msg_3"
                self.time = 1700000000
                self.target = "bot_1"

        messages_mod.BaseMessage = BaseMessage
        messages_mod.TextMessage = TextMessage
        messages_mod.ImageMessage = ImageMessage
        messages_mod.VoiceMessage = VoiceMessage

        class ImageReply:
            def __init__(self, *args, **kwargs):
                pass
            def render(self):
                return "<xml>image</xml>"

        class VoiceReply:
            def __init__(self, *args, **kwargs):
                pass
            def render(self):
                return "<xml>voice</xml>"

        replies_mod.ImageReply = ImageReply
        replies_mod.VoiceReply = VoiceReply

        class WeChatClient:
            def __init__(self, *args, **kwargs):
                self.message = types.SimpleNamespace(
                    send_text=lambda *a, **k: {"errcode": 0},
                    send_image=lambda *a, **k: {"errcode": 0},
                    send_voice=lambda *a, **k: {"errcode": 0},
                    send_file=lambda *a, **k: {"errcode": 0},
                )
                self.media = types.SimpleNamespace(
                    download=lambda media_id: types.SimpleNamespace(content=b"voice"),
                    upload=lambda *a, **k: {"media_id": "m1"},
                )
        wechatpy.WeChatClient = WeChatClient
        wechatpy.create_reply = lambda text, msg: text
        wechatpy.parse_message = lambda xml: TextMessage("xml")

        utils_mod.check_signature = lambda *args, **kwargs: True

        wechatpy.crypto = crypto_mod
        wechatpy.exceptions = exceptions_mod
        wechatpy.messages = messages_mod
        wechatpy.replies = replies_mod
        wechatpy.utils = utils_mod
        sys.modules["wechatpy"] = wechatpy
        sys.modules["wechatpy.crypto"] = crypto_mod
        sys.modules["wechatpy.exceptions"] = exceptions_mod
        sys.modules["wechatpy.messages"] = messages_mod
        sys.modules["wechatpy.replies"] = replies_mod
        sys.modules["wechatpy.utils"] = utils_mod

        from astrbot.core.platform.sources.weixin_official_account.weixin_offacc_adapter import (
            WeixinOfficialAccountPlatformAdapter,
        )

        queue = asyncio.Queue()
        adapter = WeixinOfficialAccountPlatformAdapter(
            {
                "id": "wxoa_test",
                "appid": "appid",
                "secret": "secret",
                "token": "token",
                "encoding_aes_key": "x" * 43,
                "port": "8081",
                "callback_server_host": "0.0.0.0",
            },
            {},
            queue,
        )
        assert adapter.meta().name == "weixin_official_account"
        """
    )
