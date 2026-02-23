"""Runtime smoke tests for Wecom adapter without external SDK dependency."""

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
        "Subprocess test failed.\n"
        f"Code:\n{code}\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}\n"
    )


def test_wecom_adapter_init_and_convert_text_smoke() -> None:
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
            pass

        class VoiceMessage(BaseMessage):
            pass

        enterprise_messages.TextMessage = TextMessage
        enterprise_messages.ImageMessage = ImageMessage
        enterprise_messages.VoiceMessage = VoiceMessage

        class WeChatCrypto:
            def __init__(self, *args, **kwargs):
                pass
            def check_signature(self, *args, **kwargs):
                return "ok"
        crypto_mod.WeChatCrypto = WeChatCrypto

        class WeChatClient:
            def __init__(self, *args, **kwargs):
                self.message = types.SimpleNamespace(
                    send_text=lambda *a, **k: {"errcode": 0},
                    send_image=lambda *a, **k: {"errcode": 0},
                    send_voice=lambda *a, **k: {"errcode": 0},
                    send_file=lambda *a, **k: {"errcode": 0},
                    send_video=lambda *a, **k: {"errcode": 0},
                )
                self.media = types.SimpleNamespace(
                    upload=lambda *a, **k: {"media_id": "m"},
                    download=lambda *a, **k: types.SimpleNamespace(content=b""),
                )
        enterprise.WeChatClient = WeChatClient
        enterprise.parse_message = lambda xml: TextMessage("parsed")

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

        async def main():
            adapter = WecomPlatformAdapter(
                {
                    "id": "wecom_test",
                    "corpid": "corp",
                    "secret": "secret",
                    "token": "token",
                    "encoding_aes_key": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
                    "port": "8080",
                    "callback_server_host": "127.0.0.1",
                },
                {},
                asyncio.Queue(),
            )
            assert adapter.meta().name == "wecom"
            assert adapter.meta().id == "wecom_test"

            called = {"ok": False}
            async def _fake_handle_msg(message):
                called["ok"] = True
                assert message.message_str == "hello"
                assert message.session_id == "user_1"
            adapter.handle_msg = _fake_handle_msg

            await adapter.convert_message(TextMessage("hello"))
            assert called["ok"] is True
            assert adapter.agent_id == "agent_1"

        asyncio.run(main())
        """
    )


def test_wecom_server_verify_smoke() -> None:
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
            pass
        client_base_mod.BaseWeChatAPI = BaseWeChatAPI

        class InvalidSignatureException(Exception):
            pass
        exceptions_mod.InvalidSignatureException = InvalidSignatureException

        class BaseMessage:
            type = "text"
        messages_mod.BaseMessage = BaseMessage

        class TextMessage(BaseMessage):
            pass
        class ImageMessage(BaseMessage):
            pass
        class VoiceMessage(BaseMessage):
            pass
        enterprise_messages.TextMessage = TextMessage
        enterprise_messages.ImageMessage = ImageMessage
        enterprise_messages.VoiceMessage = VoiceMessage

        class WeChatCrypto:
            def __init__(self, *args, **kwargs):
                pass
            def check_signature(self, msg_signature, timestamp, nonce, echostr):
                return echostr
        crypto_mod.WeChatCrypto = WeChatCrypto

        class WeChatClient:
            def __init__(self, *args, **kwargs):
                pass
        enterprise.WeChatClient = WeChatClient
        enterprise.parse_message = lambda xml: TextMessage()

        sys.modules["wechatpy"] = wechatpy
        sys.modules["wechatpy.enterprise"] = enterprise
        sys.modules["wechatpy.enterprise.crypto"] = crypto_mod
        sys.modules["wechatpy.enterprise.messages"] = enterprise_messages
        sys.modules["wechatpy.exceptions"] = exceptions_mod
        sys.modules["wechatpy.messages"] = messages_mod
        sys.modules["wechatpy.client"] = client_mod
        sys.modules["wechatpy.client.api"] = client_api_mod
        sys.modules["wechatpy.client.api.base"] = client_base_mod

        from astrbot.core.platform.sources.wecom.wecom_adapter import WecomServer

        async def main():
            server = WecomServer(
                asyncio.Queue(),
                {
                    "corpid": "corp",
                    "token": "token",
                    "encoding_aes_key": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
                    "port": "8080",
                    "callback_server_host": "127.0.0.1",
                },
            )
            req = types.SimpleNamespace(
                args={
                    "msg_signature": "sig",
                    "timestamp": "1",
                    "nonce": "2",
                    "echostr": "echo",
                }
            )
            resp = await server.handle_verify(req)
            assert resp == "echo"

        asyncio.run(main())
        """
    )
