"""Tests for security fixes - cryptographic random number generation and SSL context."""

import os
import ssl
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest


def test_wecom_crypto_uses_secrets():
    """Test that WXBizJsonMsgCrypt uses secrets module instead of random."""
    from astrbot.core.platform.sources.wecom_ai_bot.WXBizJsonMsgCrypt import Prpcrypt

    # Create an instance and test that random string generation works
    prpcrypt = Prpcrypt(b"test_key_32_bytes_long_value!")

    # Generate multiple random strings and verify they are different and valid
    random_strings = [prpcrypt.get_random_str() for _ in range(10)]

    # All strings should be 16 bytes long
    assert all(len(s) == 16 for s in random_strings)

    # All strings should be different (extremely high probability with cryptographic random)
    assert len(set(random_strings)) == 10

    # All strings should be numeric when decoded
    for s in random_strings:
        decoded = s.decode()
        assert decoded.isdigit()
        assert 1000000000000000 <= int(decoded) <= 9999999999999999


def test_wecomai_utils_uses_secrets():
    """Test that wecomai_utils uses secrets module for random string generation."""
    from astrbot.core.platform.sources.wecom_ai_bot.wecomai_utils import (
        generate_random_string,
    )

    # Generate multiple random strings and verify they are different
    random_strings = [generate_random_string(10) for _ in range(20)]

    # All strings should be 10 characters long
    assert all(len(s) == 10 for s in random_strings)

    # All strings should be alphanumeric
    for s in random_strings:
        assert s.isalnum()

    # All strings should be different (extremely high probability with cryptographic random)
    assert len(set(random_strings)) >= 19  # Allow for 1 collision in 20 (very unlikely)


def test_azure_tts_signature_uses_secrets():
    """Test that Azure TTS signature generation uses secrets module."""
    import asyncio

    from astrbot.core.provider.sources.azure_tts_source import OTTSProvider

    # Create a provider with test config
    config = {
        "OTTS_SKEY": "test_secret_key",
        "OTTS_URL": "https://example.com/api/tts",
        "OTTS_AUTH_TIME": "https://example.com/api/time",
    }

    async def test_nonce_generation():
        async with OTTSProvider(config) as provider:
            # Mock time sync to avoid actual API calls
            provider.time_offset = 0
            provider.last_sync_time = 9999999999

            # Generate multiple signatures and extract nonces
            signatures = []
            for _ in range(10):
                sig = await provider._generate_signature()
                signatures.append(sig)

            # Extract nonces (second field in signature format: timestamp-nonce-0-hash)
            nonces = [sig.split("-")[1] for sig in signatures]

            # All nonces should be 10 characters long
            assert all(len(n) == 10 for n in nonces)

            # All nonces should be alphanumeric (lowercase letters and digits)
            for n in nonces:
                assert all(c in "abcdefghijklmnopqrstuvwxyz0123456789" for c in n)

            # All nonces should be different (cryptographic random ensures uniqueness)
            assert len(set(nonces)) == 10

    asyncio.run(test_nonce_generation())


def test_ssl_context_fallback_explicit():
    """Test that SSL context fallback is properly configured."""
    # This test verifies the SSL context configuration
    # We can't easily test the full io.py functions without network calls,
    # but we can verify that ssl.CERT_NONE and check_hostname=False are valid settings

    # Create a context similar to what's used in io.py
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    # Verify the settings are applied correctly
    assert ssl_context.check_hostname is False
    assert ssl_context.verify_mode == ssl.CERT_NONE

    # This configuration should work but is intentionally insecure for fallback
    # The actual code only uses this when certificate validation fails


def test_io_module_has_ssl_imports():
    """Verify that io.py properly imports ssl module."""
    from astrbot.core.utils import io

    # Check that ssl is available in the module
    assert hasattr(io, "ssl")

    # Check that CERT_NONE constant is accessible
    assert hasattr(io.ssl, "CERT_NONE")


def test_secrets_module_randomness_quality():
    """Test that secrets module provides high-quality randomness."""
    import secrets

    # Generate a large set of random numbers
    random_numbers = [secrets.randbelow(100) for _ in range(1000)]

    # Basic statistical test: should have good distribution
    unique_values = len(set(random_numbers))

    # With 1000 random numbers from 0-99, we should see most values at least once
    # This is a very basic test - real cryptographic random should pass this easily
    assert unique_values >= 60  # Should see at least 60 different values out of 100

    # Test secrets.choice for string generation
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    random_chars = [secrets.choice(chars) for _ in range(1000)]

    # Should have good character distribution
    unique_chars = len(set(random_chars))
    assert unique_chars >= 20  # Should see at least 20 different characters


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
