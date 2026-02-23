"""Isolated tests for Slack platform adapter using subprocess + stubbed dependencies."""

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


def _assert_slack_case(case: str) -> None:
    code = f"""
    import asyncio
    import sys
    import types

    case = {case!r}

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
        def __init__(self, body="", status=200):
            self.body = body
            self.status = status

    quart.Quart = Quart
    quart.Response = Response
    quart.request = types.SimpleNamespace()
    sys.modules["quart"] = quart

    slack_sdk = types.ModuleType("slack_sdk")
    sys.modules["slack_sdk"] = slack_sdk

    socket_mode_mod = types.ModuleType("slack_sdk.socket_mode")
    sys.modules["slack_sdk.socket_mode"] = socket_mode_mod

    request_mod = types.ModuleType("slack_sdk.socket_mode.request")

    class SocketModeRequest:
        def __init__(self, req_type="events_api", payload=None, envelope_id="env"):
            self.type = req_type
            self.payload = payload or {{}}
            self.envelope_id = envelope_id

    request_mod.SocketModeRequest = SocketModeRequest
    sys.modules["slack_sdk.socket_mode.request"] = request_mod

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

    class AsyncBaseSocketModeClient:
        pass

    async_client_mod.AsyncBaseSocketModeClient = AsyncBaseSocketModeClient
    sys.modules["slack_sdk.socket_mode.async_client"] = async_client_mod

    response_mod = types.ModuleType("slack_sdk.socket_mode.response")

    class SocketModeResponse:
        def __init__(self, envelope_id):
            self.envelope_id = envelope_id

    response_mod.SocketModeResponse = SocketModeResponse
    sys.modules["slack_sdk.socket_mode.response"] = response_mod

    web_mod = types.ModuleType("slack_sdk.web")
    sys.modules["slack_sdk.web"] = web_mod
    web_async_mod = types.ModuleType("slack_sdk.web.async_client")

    class AsyncWebClient:
        def __init__(self, *args, **kwargs):
            pass

        async def auth_test(self):
            return {{"user_id": "UBOT"}}

        async def users_info(self, user):
            return {{"user": {{"id": user, "name": "user", "real_name": "User"}}}}

        async def conversations_info(self, channel):
            return {{"channel": {{"id": channel, "is_im": False, "name": "general"}}}}

        async def chat_postMessage(self, **kwargs):
            return {{"ok": True, "ts": "1"}}

    web_async_mod.AsyncWebClient = AsyncWebClient
    sys.modules["slack_sdk.web.async_client"] = web_async_mod

    errors_mod = types.ModuleType("slack_sdk.errors")

    class SlackApiError(Exception):
        pass

    errors_mod.SlackApiError = SlackApiError
    sys.modules["slack_sdk.errors"] = errors_mod

    from astrbot.api.platform import MessageType
    from astrbot.core.platform.sources.slack.slack_adapter import SlackAdapter

    def _cfg(mode="socket"):
        data = {{"id": "slack_test", "bot_token": "xoxb-token", "slack_connection_mode": mode}}
        if mode == "socket":
            data["app_token"] = "xapp-token"
        if mode == "webhook":
            data["signing_secret"] = "sign-secret"
        return data

    async def _run_async_case():
        if case in {{"convert_text", "convert_dm", "convert_group"}}:
            adapter = SlackAdapter(_cfg("socket"), {{}}, asyncio.Queue())
            adapter.bot_self_id = "UBOT"

            async def users_info(user):
                return {{"user": {{"id": user, "name": "tester", "real_name": "Test User"}}}}

            async def conv_info(channel):
                if case == "convert_dm":
                    return {{"channel": {{"id": channel, "is_im": True, "name": "dm"}}}}
                return {{"channel": {{"id": channel, "is_im": False, "name": "general"}}}}

            adapter.web_client.users_info = users_info
            adapter.web_client.conversations_info = conv_info

            event = {{
                "type": "message",
                "user": "U123",
                "channel": "C123",
                "text": "Hello World",
                "ts": "123.45",
                "client_msg_id": "mid-1",
            }}

            abm = await adapter.convert_message(event)
            assert abm.message_str == "Hello World"
            if case == "convert_dm":
                assert abm.type == MessageType.FRIEND_MESSAGE
                assert abm.session_id == "U123"
            else:
                assert abm.type == MessageType.GROUP_MESSAGE
                assert abm.session_id == "C123"
                assert abm.group_id == "C123"
            return

        if case in {{"handle_ignore_bot", "handle_ignore_changed"}}:
            adapter = SlackAdapter(_cfg("socket"), {{}}, asyncio.Queue())
            called = {{"ok": False}}

            async def _handle_msg(abm):
                called["ok"] = True

            adapter.handle_msg = _handle_msg

            event = {{
                "type": "message",
                "user": "U1",
                "channel": "C1",
                "text": "x",
                "ts": "1",
            }}
            if case == "handle_ignore_bot":
                event["bot_id"] = "B1"
            else:
                event["subtype"] = "message_changed"

            req = types.SimpleNamespace(type="events_api", payload={{"event": event}})
            await adapter._handle_socket_event(req)
            assert called["ok"] is False
            return

        if case == "get_bot_user_id":
            adapter = SlackAdapter(_cfg("socket"), {{}}, asyncio.Queue())

            async def auth_test():
                return {{"user_id": "UBOT-XYZ"}}

            adapter.web_client.auth_test = auth_test
            result = await adapter.get_bot_user_id()
            assert result == "UBOT-XYZ"
            return

        raise AssertionError(f"Unknown async case: {{case}}")

    if case == "init_socket_basic":
        adapter = SlackAdapter(_cfg("socket"), {{}}, asyncio.Queue())
        assert adapter.connection_mode == "socket"
        assert adapter.meta().name == "slack"

    elif case == "init_webhook_basic":
        adapter = SlackAdapter(_cfg("webhook"), {{}}, asyncio.Queue())
        assert adapter.connection_mode == "webhook"
        assert adapter.meta().id == "slack_test"

    elif case == "init_missing_bot_token":
        try:
            SlackAdapter({{"id": "x", "slack_connection_mode": "socket", "app_token": "a"}}, {{}}, asyncio.Queue())
            raise AssertionError("Expected ValueError")
        except ValueError:
            pass

    elif case == "init_socket_missing_app_token":
        try:
            SlackAdapter({{"id": "x", "bot_token": "b", "slack_connection_mode": "socket"}}, {{}}, asyncio.Queue())
            raise AssertionError("Expected ValueError")
        except ValueError:
            pass

    elif case == "init_webhook_missing_signing_secret":
        try:
            SlackAdapter({{"id": "x", "bot_token": "b", "slack_connection_mode": "webhook"}}, {{}}, asyncio.Queue())
            raise AssertionError("Expected ValueError")
        except ValueError:
            pass

    elif case == "meta":
        adapter = SlackAdapter(_cfg("socket"), {{}}, asyncio.Queue())
        meta = adapter.meta()
        assert meta.name == "slack"
        assert meta.id == "slack_test"

    elif case == "parse_rich_text_block":
        adapter = SlackAdapter(_cfg("socket"), {{}}, asyncio.Queue())
        blocks = [
            {{
                "type": "rich_text",
                "elements": [
                    {{
                        "type": "rich_text_section",
                        "elements": [
                            {{"type": "text", "text": "hello "}},
                            {{"type": "user", "user_id": "U1"}},
                            {{"type": "text", "text": " world"}},
                        ],
                    }}
                ],
            }}
        ]
        comps = adapter._parse_blocks(blocks)
        assert len(comps) >= 2

    elif case == "parse_section_block":
        adapter = SlackAdapter(_cfg("socket"), {{}}, asyncio.Queue())
        blocks = [{{"type": "section", "text": {{"type": "mrkdwn", "text": "*hello*"}}}}]
        comps = adapter._parse_blocks(blocks)
        assert len(comps) == 1

    elif case == "unified_webhook_false":
        adapter = SlackAdapter(_cfg("socket"), {{}}, asyncio.Queue())
        assert adapter.unified_webhook() is False

    elif case in {{
        "convert_text",
        "convert_dm",
        "convert_group",
        "handle_ignore_bot",
        "handle_ignore_changed",
        "get_bot_user_id",
    }}:
        asyncio.run(_run_async_case())

    else:
        raise AssertionError(f"Unknown case: {{case}}")
    """
    proc = _run_python(code)
    assert proc.returncode == 0, (
        "Slack subprocess test failed.\n"
        f"case={case}\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}\n"
    )


class TestSlackAdapterInit:
    def test_init_socket_mode_basic(self):
        _assert_slack_case("init_socket_basic")

    def test_init_webhook_mode_basic(self):
        _assert_slack_case("init_webhook_basic")

    def test_init_missing_bot_token_raises_error(self):
        _assert_slack_case("init_missing_bot_token")

    def test_init_socket_mode_missing_app_token_raises_error(self):
        _assert_slack_case("init_socket_missing_app_token")

    def test_init_webhook_mode_missing_signing_secret_raises_error(self):
        _assert_slack_case("init_webhook_missing_signing_secret")


class TestSlackAdapterMetadata:
    def test_meta_returns_correct_metadata(self):
        _assert_slack_case("meta")


class TestSlackAdapterConvertMessage:
    def test_convert_text_message(self):
        _assert_slack_case("convert_text")

    def test_convert_dm_message(self):
        _assert_slack_case("convert_dm")

    def test_convert_group_message(self):
        _assert_slack_case("convert_group")


class TestSlackAdapterBlockParsing:
    def test_parse_rich_text_block(self):
        _assert_slack_case("parse_rich_text_block")

    def test_parse_section_block(self):
        _assert_slack_case("parse_section_block")


class TestSlackAdapterEventHandling:
    def test_handle_socket_event_ignores_bot_message(self):
        _assert_slack_case("handle_ignore_bot")

    def test_handle_socket_event_ignores_message_changed(self):
        _assert_slack_case("handle_ignore_changed")


class TestSlackAdapterUtilityMethods:
    def test_get_bot_user_id(self):
        _assert_slack_case("get_bot_user_id")

    def test_unified_webhook_returns_false_by_default(self):
        _assert_slack_case("unified_webhook_false")
