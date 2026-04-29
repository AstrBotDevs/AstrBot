"""Mock-based unit tests for astrbot.core.utils.file_extract.

All external calls (httpx.AsyncClient and anyio.Path) are mocked so that
the tests never touch the network or the filesystem.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from astrbot.core.utils.file_extract import extract_file_moonshotai


def _make_http_status_error(status_code: int = 400) -> httpx.HTTPStatusError:
    """Return a realistic HTTPStatusError for use as a side_effect."""
    request = httpx.Request("POST", "https://api.moonshot.cn/v1/files")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=request,
        response=response,
    )


# ---------------------------------------------------------------------------
# mocks
# ---------------------------------------------------------------------------


def _mock_client() -> tuple[MagicMock, AsyncMock]:
    """Create a pre-configured AsyncMock httpx client.

    Returns (mock_client, mock_httpx_cls) where:
      - mock_httpx_cls.return_value = mock_client
      - mock_client.__aenter__.return_value = mock_client
    """
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    return mock_client


def _mock_path(file_bytes: bytes = b"dummy file content") -> MagicMock:
    """Create a pre-configured MagicMock anyio.Path.

    Returns mock_path where:
      - mock_path.read_bytes is an AsyncMock returning *file_bytes*
    """
    mock_path = MagicMock(spec=Path)  # anyio.Path implements Path-like interface
    mock_path.name = "test-file.pdf"  # used for the upload filename
    mock_path.read_bytes = AsyncMock(return_value=file_bytes)
    return mock_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExtractFileMoonshotaiSuccess:

    FAKE_CONTENT = b"%PDF-1.4 fake binary content..."
    EXTRACTED_TEXT = "Extracted text from Moonshot AI API"

    @pytest.mark.asyncio
    @patch("astrbot.core.utils.file_extract.httpx.AsyncClient")
    @patch("astrbot.core.utils.file_extract.anyio.Path")
    async def test_successful_extraction(
        self,
        mock_path_cls: MagicMock,
        mock_httpx_cls: MagicMock,
    ):
        """Happy path: file is uploaded, file-id returned, content fetched."""
        mock_path = _mock_path(self.FAKE_CONTENT)
        mock_path_cls.return_value = mock_path

        mock_client = _mock_client()
        mock_httpx_cls.return_value = mock_client

        upload_resp = MagicMock()
        upload_resp.json.return_value = {"id": "file-mock-001"}
        mock_client.post.return_value = upload_resp

        content_resp = MagicMock()
        content_resp.text = self.EXTRACTED_TEXT
        mock_client.get.return_value = content_resp

        result = await extract_file_moonshotai("/fake/path/report.pdf", "sk-test-key")

        assert result == self.EXTRACTED_TEXT
        mock_path_cls.assert_called_once()
        mock_path.read_bytes.assert_called_once()
        mock_httpx_cls.assert_called_once()
        mock_client.post.assert_called_once()
        mock_client.get.assert_called_once_with("/files/file-mock-001/content")

    @pytest.mark.asyncio
    @patch("astrbot.core.utils.file_extract.httpx.AsyncClient")
    @patch("astrbot.core.utils.file_extract.anyio.Path")
    async def test_client_created_with_authorization_header(
        self,
        mock_path_cls: MagicMock,
        mock_httpx_cls: MagicMock,
    ):
        """The Bearer token should match the api_key passed."""
        mock_path_cls.return_value = _mock_path(b"data")
        mock_client = _mock_client()
        mock_httpx_cls.return_value = mock_client
        mock_client.post.return_value = MagicMock(json=lambda: {"id": "f1"})
        mock_client.get.return_value = MagicMock(text="ok")

        await extract_file_moonshotai("/f.pdf", "sk-secret-42")

        call_headers = mock_httpx_cls.call_args[1].get("headers", {})
        assert call_headers.get("Authorization") == "Bearer sk-secret-42"

    @pytest.mark.asyncio
    @patch("astrbot.core.utils.file_extract.httpx.AsyncClient")
    @patch("astrbot.core.utils.file_extract.anyio.Path")
    async def test_passes_file_path_to_anyio_path(
        self,
        mock_path_cls: MagicMock,
        mock_httpx_cls: MagicMock,
    ):
        """The file_path argument should be forwarded to anyio.Path()."""
        mock_path_cls.return_value = _mock_path(b"data")
        mock_client = _mock_client()
        mock_httpx_cls.return_value = mock_client
        mock_client.post.return_value = MagicMock(json=lambda: {"id": "f1"})
        mock_client.get.return_value = MagicMock(text="ok")

        await extract_file_moonshotai("/my/custom/document.txt", "key")

        args, _ = mock_path_cls.call_args
        assert str(args[0]) == "/my/custom/document.txt"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestExtractFileMoonshotaiErrors:

    FAKE_CONTENT = b"fake bytes"

    @pytest.mark.asyncio
    @patch("astrbot.core.utils.file_extract.httpx.AsyncClient")
    @patch("astrbot.core.utils.file_extract.anyio.Path")
    async def test_missing_file_id_raises_value_error(
        self,
        mock_path_cls: MagicMock,
        mock_httpx_cls: MagicMock,
    ):
        """Upload response without an 'id' key should raise ValueError."""
        mock_path_cls.return_value = _mock_path(self.FAKE_CONTENT)
        mock_client = _mock_client()
        mock_httpx_cls.return_value = mock_client

        resp = MagicMock()
        resp.json.return_value = {}  # no "id"
        mock_client.post.return_value = resp

        with pytest.raises(ValueError, match="valid file id"):
            await extract_file_moonshotai("/f.pdf", "key")

    @pytest.mark.asyncio
    @patch("astrbot.core.utils.file_extract.httpx.AsyncClient")
    @patch("astrbot.core.utils.file_extract.anyio.Path")
    async def test_null_file_id_raises_value_error(
        self,
        mock_path_cls: MagicMock,
        mock_httpx_cls: MagicMock,
    ):
        """Upload response with 'id': None should raise ValueError."""
        mock_path_cls.return_value = _mock_path(self.FAKE_CONTENT)
        mock_client = _mock_client()
        mock_httpx_cls.return_value = mock_client

        resp = MagicMock()
        resp.json.return_value = {"id": None}
        mock_client.post.return_value = resp

        with pytest.raises(ValueError, match="valid file id"):
            await extract_file_moonshotai("/f.pdf", "key")

    @pytest.mark.asyncio
    @patch("astrbot.core.utils.file_extract.httpx.AsyncClient")
    @patch("astrbot.core.utils.file_extract.anyio.Path")
    async def test_upload_http_error_propagates(
        self,
        mock_path_cls: MagicMock,
        mock_httpx_cls: MagicMock,
    ):
        """Non-2xx status from upload POST should propagate as HTTPStatusError."""
        mock_path_cls.return_value = _mock_path(self.FAKE_CONTENT)
        mock_client = _mock_client()
        mock_httpx_cls.return_value = mock_client

        resp = MagicMock()
        resp.raise_for_status.side_effect = _make_http_status_error(400)
        mock_client.post.return_value = resp

        with pytest.raises(httpx.HTTPStatusError):
            await extract_file_moonshotai("/f.pdf", "key")

    @pytest.mark.asyncio
    @patch("astrbot.core.utils.file_extract.httpx.AsyncClient")
    @patch("astrbot.core.utils.file_extract.anyio.Path")
    async def test_content_fetch_http_error_propagates(
        self,
        mock_path_cls: MagicMock,
        mock_httpx_cls: MagicMock,
    ):
        """Non-2xx status from content GET should propagate as HTTPStatusError."""
        mock_path_cls.return_value = _mock_path(self.FAKE_CONTENT)
        mock_client = _mock_client()
        mock_httpx_cls.return_value = mock_client

        upload_resp = MagicMock()
        upload_resp.json.return_value = {"id": "file-001"}
        mock_client.post.return_value = upload_resp

        content_resp = MagicMock()
        content_resp.raise_for_status.side_effect = _make_http_status_error(500)
        mock_client.get.return_value = content_resp

        with pytest.raises(httpx.HTTPStatusError):
            await extract_file_moonshotai("/f.pdf", "key")

    @pytest.mark.asyncio
    @patch("astrbot.core.utils.file_extract.httpx.AsyncClient")
    @patch("astrbot.core.utils.file_extract.anyio.Path")
    async def test_connection_error_during_upload_propagates(
        self,
        mock_path_cls: MagicMock,
        mock_httpx_cls: MagicMock,
    ):
        """A network-level error on POST should propagate as ConnectError."""
        mock_path_cls.return_value = _mock_path(self.FAKE_CONTENT)
        mock_client = _mock_client()
        mock_httpx_cls.return_value = mock_client

        mock_client.post.side_effect = httpx.ConnectError("connection refused")

        with pytest.raises(httpx.ConnectError):
            await extract_file_moonshotai("/f.pdf", "key")

    @pytest.mark.asyncio
    @patch("astrbot.core.utils.file_extract.httpx.AsyncClient")
    @patch("astrbot.core.utils.file_extract.anyio.Path")
    async def test_file_read_error_prevents_http_call(
        self,
        mock_path_cls: MagicMock,
        mock_httpx_cls: MagicMock,
    ):
        """If anyio.Path.read_bytes raises, the function should raise and
        httpx.AsyncClient should never be constructed."""
        mock_path = _mock_path(b"ignored")
        mock_path.read_bytes = AsyncMock(side_effect=OSError(2, "No such file"))
        mock_path_cls.return_value = mock_path

        with pytest.raises(OSError):
            await extract_file_moonshotai("/missing/file.txt", "key")

        mock_httpx_cls.assert_not_called()
