import json

import pytest

from astrbot.core.platform.sources.lark import bot_info
from astrbot.core.platform.sources.lark.bot_info import (
    BOT_INFO_PATH,
    TENANT_ACCESS_TOKEN_INTERNAL_PATH,
    LarkBotInfo,
    request_lark_bot_info,
)

OPEN_BASE = "https://open.example.test"
APP_SECRET = "super-secret-value"


class _FakeResponse:
    def __init__(self, data, *, status: int = 200, log_id: str | None = None):
        self.status = status
        self.headers = {"x-tt-logid": log_id} if log_id else {}
        self._data = data

    async def json(self, content_type=None):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse], calls: list[tuple]):
        self._responses = responses
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def request(self, method, endpoint, **kwargs):
        self._calls.append((method, endpoint, kwargs))
        return self._responses.pop(0)


def _patch_sessions(monkeypatch, responses: list[_FakeResponse]) -> list[tuple]:
    calls: list[tuple] = []
    monkeypatch.setattr(
        bot_info.aiohttp,
        "ClientSession",
        lambda **_kwargs: _FakeSession(responses, calls),
    )
    return calls


async def _request_bot_info() -> LarkBotInfo:
    return await request_lark_bot_info(
        domain=OPEN_BASE,
        app_id="cli_test",
        app_secret=APP_SECRET,
    )


@pytest.mark.asyncio
async def test_request_lark_bot_info_returns_bot_fields(monkeypatch):
    calls = _patch_sessions(
        monkeypatch,
        [
            _FakeResponse({"code": 0, "tenant_access_token": "t-token"}),
            _FakeResponse(
                {"code": 0, "bot": {"app_name": "AstrBot", "open_id": "ou_bot"}}
            ),
        ],
    )

    result = await _request_bot_info()

    assert result == LarkBotInfo(app_name="AstrBot", open_id="ou_bot")
    assert calls[0][:2] == ("POST", f"{OPEN_BASE}{TENANT_ACCESS_TOKEN_INTERNAL_PATH}")
    assert calls[0][2]["json"] == {"app_id": "cli_test", "app_secret": APP_SECRET}
    assert calls[1][:2] == ("GET", f"{OPEN_BASE}{BOT_INFO_PATH}")
    assert calls[1][2]["headers"] == {"Authorization": "Bearer t-token"}


@pytest.mark.asyncio
async def test_platform_policy_denial_keeps_diagnostics_without_secret(monkeypatch):
    calls = _patch_sessions(
        monkeypatch,
        [
            _FakeResponse(
                {
                    "code": 21001,
                    "msg": "Access denied due to platform policy.",
                },
                log_id="20261027-logid",
            )
        ],
    )

    with pytest.raises(RuntimeError) as exc_info:
        await _request_bot_info()

    message = str(exc_info.value)
    assert "code=21001" in message
    assert "Access denied due to platform policy." in message
    assert "HTTP 200" in message
    assert "log_id=20261027-logid" in message
    assert "retrying will not help" in message
    assert APP_SECRET not in message
    # The bot info endpoint is never called once token issuance is denied.
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_other_token_errors_have_no_policy_hint(monkeypatch):
    _patch_sessions(
        monkeypatch,
        [_FakeResponse({"code": 10014, "msg": "app secret invalid"}, status=400)],
    )

    with pytest.raises(RuntimeError) as exc_info:
        await _request_bot_info()

    message = str(exc_info.value)
    assert "obtain Lark tenant access token" in message
    assert "code=10014" in message
    assert "app secret invalid" in message
    assert "HTTP 400" in message
    assert "log_id=n/a" in message
    assert "platform policy" not in message


@pytest.mark.asyncio
async def test_bot_info_error_names_the_failed_call(monkeypatch):
    _patch_sessions(
        monkeypatch,
        [
            _FakeResponse({"code": 0, "tenant_access_token": "t-token"}),
            _FakeResponse(
                {"code": 99991663, "msg": "token invalid"}, log_id="bot-logid"
            ),
        ],
    )

    with pytest.raises(RuntimeError) as exc_info:
        await _request_bot_info()

    message = str(exc_info.value)
    assert "fetch Lark bot info" in message
    assert "code=99991663" in message
    assert "log_id=bot-logid" in message
    assert "t-token" not in message


@pytest.mark.asyncio
async def test_non_json_response_keeps_status_and_log_id(monkeypatch):
    decode_error = json.JSONDecodeError("Expecting value", "<html>502</html>", 0)
    _patch_sessions(
        monkeypatch,
        [_FakeResponse(decode_error, status=502, log_id="proxy-logid")],
    )

    with pytest.raises(RuntimeError) as exc_info:
        await _request_bot_info()

    message = str(exc_info.value)
    assert "obtain Lark tenant access token" in message
    assert "not valid JSON" in message
    assert "HTTP 502" in message
    assert "log_id=proxy-logid" in message
    assert exc_info.value.__cause__ is decode_error
