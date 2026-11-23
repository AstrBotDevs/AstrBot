"""Exercise cryptographic nonce sources and the signed HTTP boundary."""

import string
from unittest.mock import Mock, call

import httpx
import pytest


@pytest.mark.parametrize(
    ("random_value", "expected"),
    [(0, b"1000000000000000"), (8_999_999_999_999_999, b"9999999999999999")],
)
def test_wecom_crypto_uses_secrets(monkeypatch, random_value, expected):
    import astrbot.core.platform.sources.wecom_ai_bot.WXBizJsonMsgCrypt as crypto

    random_number = Mock(return_value=random_value)
    monkeypatch.setattr(crypto.secrets, "randbelow", random_number)
    cipher = crypto.Prpcrypt(b"0123456789abcdef0123456789abcdef")

    assert cipher.get_random_str() == expected
    random_number.assert_called_once_with(9_000_000_000_000_000)


@pytest.mark.parametrize("length", [0, 1, 10])
def test_wecomai_utils_uses_secrets(monkeypatch, length):
    from astrbot.core.platform.sources.wecom_ai_bot import wecomai_utils

    expected = "aB0zY9cD2e"[:length]
    choose = Mock(side_effect=expected)
    monkeypatch.setattr(wecomai_utils.secrets, "choice", choose)

    assert wecomai_utils.generate_random_string(length) == expected
    assert (
        choose.call_args_list == [call(string.ascii_letters + string.digits)] * length
    )


@pytest.mark.asyncio
async def test_azure_tts_signature_uses_secrets_and_server_time(monkeypatch):
    from astrbot.core.provider.sources import azure_tts_source

    requests = []

    def time_response(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"timestamp": 1_700_000_012})

    def client_factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(time_response), **kwargs)

    choose = Mock(side_effect="ab09cd12ef")
    monkeypatch.setattr(azure_tts_source, "AsyncClient", client_factory)
    monkeypatch.setattr(azure_tts_source.time, "time", lambda: 1_700_000_000)
    monkeypatch.setattr(azure_tts_source.secrets, "choice", choose)
    provider = azure_tts_source.OTTSProvider(
        {
            "OTTS_SKEY": "test-secret-key",
            "OTTS_URL": "https://tts.example.test/api/tts",
            "OTTS_AUTH_TIME": "https://tts.example.test/api/time",
        }
    )

    async with provider:
        signature = await provider._generate_signature()

    assert signature == "1700000012-ab09cd12ef-0-7c5a712ea82224661d31368d283cda39"
    assert provider.time_offset == 12
    assert provider.last_sync_time == 1_700_000_000
    assert choose.call_args_list == [call(string.ascii_lowercase + string.digits)] * 10
    assert [(request.method, str(request.url)) for request in requests] == [
        ("GET", "https://tts.example.test/api/time")
    ]
    with pytest.raises(RuntimeError, match="not initialized"):
        _ = provider.client
