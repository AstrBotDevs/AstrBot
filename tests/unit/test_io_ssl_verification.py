"""Tests for SSL verification in download functions.

This test suite ensures that SSL certificate verification is properly enforced
and that the application does not silently downgrade to insecure connections
when SSL errors occur, which would expose users to MITM attacks.

Related to Issue #9446 - SSL verification downgrade vulnerability.

IMPORTANT: These tests are designed to FAIL on the current vulnerable code
and PASS after the vulnerability is fixed. The failing tests demonstrate that:
1. SSL errors trigger insecure fallback (CERT_NONE) - VULNERABLE BEHAVIOR
2. After the fix, SSL errors should raise exceptions immediately - SECURE BEHAVIOR

Expected test results:
- BEFORE FIX: Some tests will fail, showing the vulnerability exists
- AFTER FIX: All tests should pass, confirming SSL errors raise exceptions
"""

import ssl
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from astrbot.core.utils.io import download_file, download_image_by_url


class TestDownloadImageSSLVerification:
    """Test SSL verification behavior in download_image_by_url function."""

    @pytest.mark.asyncio
    async def test_download_image_https_success(self):
        """Test that HTTPS downloads work correctly with valid certificates."""
        mock_response = AsyncMock()
        mock_response.read = AsyncMock(return_value=b"fake_image_data")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await download_image_by_url("https://example.com/image.jpg")

            assert result is not None
            assert Path(result).exists()
            # Verify that SSL context was created properly
            mock_session.get.assert_called_once_with("https://example.com/image.jpg")
            # Clean up temp file
            Path(result).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_download_image_ssl_error_should_raise(self):
        """Test that SSL errors raise exceptions instead of silently downgrading.

        This is the critical test for the vulnerability fix. The function should
        NOT catch SSL errors and retry with CERT_NONE. It should let the exception
        propagate to the caller.
        """
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            side_effect=aiohttp.ClientConnectorSSLError(
                connection_key=None,
                os_error=ssl.SSLError("certificate verify failed"),
            )
        )
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            # After the fix, this should raise the SSL error instead of downgrading
            with pytest.raises(
                (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError)
            ):
                await download_image_by_url("https://invalid-cert.example.com/image.jpg")

    @pytest.mark.asyncio
    async def test_download_image_certificate_error_should_raise(self):
        """Test that certificate errors raise exceptions instead of downgrading."""
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            side_effect=aiohttp.ClientConnectorCertificateError(
                connection_key=None,
                certificate_error=Exception("cert verification failed"),
            )
        )
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(
                (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError)
            ):
                await download_image_by_url("https://expired-cert.example.com/image.jpg")

    @pytest.mark.asyncio
    async def test_download_image_http_url_still_works(self):
        """Test that HTTP (non-HTTPS) URLs continue to work normally."""
        mock_response = AsyncMock()
        mock_response.read = AsyncMock(return_value=b"fake_image_data")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await download_image_by_url("http://example.com/image.jpg")

            assert result is not None
            assert Path(result).exists()
            mock_session.get.assert_called_once_with("http://example.com/image.jpg")
            # Clean up temp file
            Path(result).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_download_image_post_ssl_error_should_raise(self):
        """Test that SSL errors in POST requests also raise exceptions."""
        mock_session = MagicMock()
        mock_session.post = MagicMock(
            side_effect=aiohttp.ClientConnectorSSLError(
                connection_key=None,
                os_error=ssl.SSLError("certificate verify failed"),
            )
        )
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(
                (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError)
            ):
                await download_image_by_url(
                    "https://invalid-cert.example.com/api/image",
                    post=True,
                    post_data={"key": "value"},
                )

    @pytest.mark.asyncio
    async def test_download_image_with_path_ssl_error_should_raise(self):
        """Test that SSL errors raise when downloading to a specific path."""
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            side_effect=aiohttp.ClientConnectorSSLError(
                connection_key=None,
                os_error=ssl.SSLError("certificate verify failed"),
            )
        )
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with patch("aiohttp.ClientSession", return_value=mock_session):
                with pytest.raises(
                    (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError)
                ):
                    await download_image_by_url(
                        "https://invalid-cert.example.com/image.jpg",
                        path=tmp_path,
                    )
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class TestDownloadFileSSLVerification:
    """Test SSL verification behavior in download_file function."""

    @pytest.mark.asyncio
    async def test_download_file_https_success(self):
        """Test that HTTPS file downloads work correctly with valid certificates."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"content-length": "1024"}
        mock_response.content = AsyncMock()
        mock_response.content.read = AsyncMock(side_effect=[b"data", b""])
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with patch("aiohttp.ClientSession", return_value=mock_session):
                await download_file("https://example.com/file.zip", tmp_path)

            assert Path(tmp_path).exists()
            mock_session.get.assert_called()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_download_file_ssl_error_with_fallback_disabled_should_raise(self):
        """Test that SSL errors raise when allow_insecure_ssl_fallback=False.

        This is the secure behavior - when the fallback is disabled, SSL errors
        should propagate immediately without any retry attempts.
        """
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            side_effect=aiohttp.ClientConnectorSSLError(
                connection_key=None,
                os_error=ssl.SSLError("certificate verify failed"),
            )
        )
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with patch("aiohttp.ClientSession", return_value=mock_session):
                with pytest.raises(
                    (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError)
                ):
                    await download_file(
                        "https://invalid-cert.example.com/file.zip",
                        tmp_path,
                        allow_insecure_ssl_fallback=False,
                    )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_download_file_certificate_error_should_raise(self):
        """Test that certificate errors raise when fallback is disabled."""
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            side_effect=aiohttp.ClientConnectorCertificateError(
                connection_key=None,
                certificate_error=Exception("cert verification failed"),
            )
        )
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with patch("aiohttp.ClientSession", return_value=mock_session):
                with pytest.raises(
                    (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError)
                ):
                    await download_file(
                        "https://expired-cert.example.com/file.zip",
                        tmp_path,
                        allow_insecure_ssl_fallback=False,
                    )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_download_file_http_url_still_works(self):
        """Test that HTTP (non-HTTPS) file downloads continue to work."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"content-length": "1024"}
        mock_response.content = AsyncMock()
        mock_response.content.read = AsyncMock(side_effect=[b"data", b""])
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with patch("aiohttp.ClientSession", return_value=mock_session):
                await download_file("http://example.com/file.zip", tmp_path)

            assert Path(tmp_path).exists()
            mock_session.get.assert_called()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_download_file_non_ssl_errors_still_propagate(self):
        """Test that non-SSL errors (like network errors) still propagate correctly."""
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            side_effect=aiohttp.ClientConnectorError(
                connection_key=None,
                os_error=OSError("Connection refused"),
            )
        )
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with patch("aiohttp.ClientSession", return_value=mock_session):
                with pytest.raises(aiohttp.ClientConnectorError):
                    await download_file(
                        "https://example.com/file.zip",
                        tmp_path,
                        allow_insecure_ssl_fallback=False,
                    )
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class TestSSLContextSecurity:
    """Test that secure SSL contexts are used and insecure patterns are avoided."""

    @pytest.mark.asyncio
    async def test_ssl_context_uses_cert_verification(self):
        """Verify that SSL context is created with proper certificate verification.

        This test ensures that when SSL context is created, it uses the default
        secure settings and does not disable verification.
        """
        mock_context = ssl.create_default_context()

        with patch("ssl.create_default_context", return_value=mock_context) as mock_ssl_context:
            mock_response = AsyncMock()
            mock_response.read = AsyncMock(return_value=b"data")
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await download_image_by_url("https://example.com/image.jpg")
                Path(result).unlink(missing_ok=True)

            # Verify SSL context was created (certification verification enabled)
            mock_ssl_context.assert_called()
            # Verify that check_hostname and verify_mode retain secure defaults
            assert mock_context.check_hostname is True
            assert mock_context.verify_mode == ssl.CERT_REQUIRED

    @pytest.mark.asyncio
    async def test_no_insecure_ssl_context_created_on_error(self):
        """Verify that insecure SSL contexts (CERT_NONE) are not created on SSL errors.

        After the fix, when an SSL error occurs, the function should raise the error
        immediately rather than creating a new SSL context with verify_mode=CERT_NONE.
        """
        call_count = 0
        original_create_default_context = ssl.create_default_context

        def mock_ssl_context(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Call the original function to avoid recursion
            return original_create_default_context(*args, **kwargs)

        with patch("ssl.create_default_context", side_effect=mock_ssl_context):
            mock_session = MagicMock()
            mock_session.get = MagicMock(
                side_effect=aiohttp.ClientConnectorSSLError(
                    connection_key=None,
                    os_error=ssl.SSLError("certificate verify failed"),
                )
            )
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            with patch("aiohttp.ClientSession", return_value=mock_session):
                with pytest.raises(
                    (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError)
                ):
                    await download_image_by_url("https://invalid-cert.example.com/image.jpg")

            # After the fix, SSL context should only be created once (for the initial attempt)
            # There should be no second context creation with CERT_NONE
            assert call_count == 1, "SSL context should only be created once, not for a fallback retry"
