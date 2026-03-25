from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot._internal.protocols.lsp.client import AstrbotLspClient


@pytest.mark.asyncio
async def test_lsp_reader_task_failure_marks_client_disconnected_and_logs():
    """Test reader task failures update connection state and are logged."""
    client = AstrbotLspClient()
    fake_process = SimpleNamespace(stdout=MagicMock(), stdin=MagicMock())

    with (
        patch(
            "astrbot._internal.protocols.lsp.client.anyio.open_process",
            AsyncMock(return_value=fake_process),
        ),
        patch.object(
            client,
            "_read_responses",
            AsyncMock(side_effect=RuntimeError("reader crashed")),
        ),
        patch.object(client, "send_request", AsyncMock(return_value={})),
        patch.object(client, "send_notification", AsyncMock()),
        patch("astrbot._internal.protocols.lsp.client.log") as mock_log,
    ):
        await client.connect_to_server(["python", "fake_lsp.py"], "file:///tmp")
        await asyncio.sleep(0)

        reader_task = client._reader_task
        assert reader_task is not None
        _ = reader_task.exception()
        await asyncio.sleep(0)

        assert client.connected is False
        mock_log.error.assert_called_once()
