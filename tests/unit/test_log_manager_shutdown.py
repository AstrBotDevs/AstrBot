from unittest.mock import AsyncMock, MagicMock, call

import pytest

import astrbot.core.log as log_module
from astrbot.core.log import LogManager


@pytest.mark.asyncio
async def test_shutdown_completes_and_removes_all_registered_sinks(monkeypatch):
    fake_loguru = MagicMock()
    fake_loguru.complete = AsyncMock(return_value=None)
    fake_loguru.remove = MagicMock()
    monkeypatch.setattr(log_module, "_loguru", fake_loguru)

    original_state = (
        LogManager._trace_sink_id,
        LogManager._file_sink_id,
        LogManager._console_sink_id,
        LogManager._configured,
    )
    LogManager._trace_sink_id = 22
    LogManager._file_sink_id = 11
    LogManager._console_sink_id = 33
    LogManager._configured = True

    try:
        await LogManager.shutdown()

        fake_loguru.complete.assert_awaited_once()
        assert fake_loguru.remove.call_args_list == [call(22), call(11), call(33)]
        assert LogManager._trace_sink_id is None
        assert LogManager._file_sink_id is None
        assert LogManager._console_sink_id is None
        assert LogManager._configured is False
    finally:
        (
            LogManager._trace_sink_id,
            LogManager._file_sink_id,
            LogManager._console_sink_id,
            LogManager._configured,
        ) = original_state
