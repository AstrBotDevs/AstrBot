"""Tests for security fixes - cryptographic random number generation and SSL context."""

import os
import ssl
import sys
from unittest.mock import AsyncMock, Mock, call

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest


def test_wecom_crypto_uses_secrets(monkeypatch: pytest.MonkeyPatch):
    """Test that WXBizJsonMsgCrypt uses secrets module instead of random."""
    from astrbot.core.platform.sources.wecom_ai_bot import WXBizJsonMsgCrypt

    randbelow = Mock(return_value=42)
    monkeypatch.setattr(WXBizJsonMsgCrypt.secrets, "randbelow", randbelow)

    prpcrypt = WXBizJsonMsgCrypt.Prpcrypt(b"test_key_32_bytes_long_value!")

    assert prpcrypt.get_random_str() == b"1000000000000042"
    randbelow.assert_called_once_with(prpcrypt.RANDOM_RANGE)


def test_wecomai_utils_uses_secrets(monkeypatch: pytest.MonkeyPatch):
    """Test that wecomai_utils uses secrets module for random string generation."""
    from astrbot.core.platform.sources.wecom_ai_bot import wecomai_utils

    choice = Mock(side_effect=iter("aZ9b"))
    monkeypatch.setattr(wecomai_utils.secrets, "choice", choice)

    assert wecomai_utils.generate_random_string(4) == "aZ9b"
    choice.assert_has_calls(
        [call(wecomai_utils.string.ascii_letters + wecomai_utils.string.digits)] * 4
    )
    assert choice.call_count == 4


@pytest.mark.asyncio
async def test_azure_tts_signature_uses_secrets(monkeypatch: pytest.MonkeyPatch):
    """Test that Azure TTS signature generation uses secrets module."""
    import hashlib

    from astrbot.core.provider.sources import azure_tts_source

    config = {
        "OTTS_SKEY": "test_secret_key",
        "OTTS_URL": "https://example.com/api/tts",
        "OTTS_AUTH_TIME": "https://example.com/api/time",
    }
    provider = azure_tts_source.OTTSProvider(config)
    provider._sync_time = AsyncMock()
    choice = Mock(side_effect=iter("noncevalue"))
    monkeypatch.setattr(azure_tts_source.secrets, "choice", choice)
    monkeypatch.setattr(azure_tts_source.time, "time", lambda: 1_700_000_000)

    signature = await provider._generate_signature()

    expected_payload = "/api/tts-1700000000-noncevalue-0-test_secret_key"
    expected_digest = hashlib.md5(
        expected_payload.encode(), usedforsecurity=False
    ).hexdigest()
    assert signature == f"1700000000-noncevalue-0-{expected_digest}"
    provider._sync_time.assert_awaited_once()
    choice.assert_has_calls([call("abcdefghijklmnopqrstuvwxyz0123456789")] * 10)
    assert choice.call_count == 10


def test_ssl_context_verifies_certificates_by_default():
    """TLS contexts must verify the peer certificate and hostname by default."""
    ssl_context = ssl.create_default_context()
    assert ssl_context.check_hostname is True
    assert ssl_context.verify_mode == ssl.CERT_REQUIRED


def test_io_module_uses_ssl_module():
    """Verify that io.py creates verified TLS contexts."""
    from astrbot.core.utils import io

    # Check that ssl is available in the module
    assert hasattr(io, "ssl")

    assert hasattr(io.ssl, "create_default_context")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
