import os
import sys
import pytest
from unittest import mock
from main import check_env, check_dashboard_files


class _version_info:
    def __init__(self, major, minor):
        self.major = major
        self.minor = minor


def test_check_env(monkeypatch):
    version_info_correct = _version_info(3, 10)
    version_info_wrong = _version_info(3, 9)
    monkeypatch.setattr(sys, "version_info", version_info_correct)
    with mock.patch("os.makedirs") as mock_makedirs:
        check_env()
        mock_makedirs.assert_any_call("data/config", exist_ok=True)
        mock_makedirs.assert_any_call("data/plugins", exist_ok=True)
        mock_makedirs.assert_any_call("data/temp", exist_ok=True)

    monkeypatch.setattr(sys, "version_info", version_info_wrong)
    with pytest.raises(SystemExit):
        check_env()


@pytest.mark.asyncio
async def test_check_dashboard_files(monkeypatch):
    monkeypatch.setattr(os.path, "exists", lambda x: False)

    async def mock_get(*args, **kwargs):
        class MockResponse:
            status = 200

            async def read(self):
                return b"content"

        return MockResponse()

    with mock.patch("aiohttp.ClientSession.get", new=mock_get):
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            with mock.patch("zipfile.ZipFile.extractall") as mock_extractall:

                async def mock_aenter(_):
                    await check_dashboard_files()
                    mock_file.assert_called_once_with("data/dashboard.zip", "wb")
                    mock_extractall.assert_called_once()

                async def mock_aexit(obj, exc_type, exc, tb):
                    return

                mock_extractall.__aenter__ = mock_aenter
                mock_extractall.__aexit__ = mock_aexit
