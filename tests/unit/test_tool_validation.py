import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.agent import tool_validation


@pytest.mark.asyncio
async def test_tool_validation_offloads_regex_schemas(monkeypatch):
    spawn = AsyncMock(wraps=asyncio.create_subprocess_exec)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    await tool_validation.validate_tool_arguments({"type": "object"}, {})
    spawn.assert_not_awaited()

    schema = {
        "type": "object",
        "patternProperties": {"^label$": {"type": "string", "pattern": "^[a-z]+$"}},
    }
    await tool_validation.validate_tool_arguments(schema, {"label": "example"})
    with pytest.raises(ValueError, match="input schema"):
        await tool_validation.validate_tool_arguments(schema, {"label": "123"})
    assert spawn.await_count == 2


@pytest.mark.asyncio
async def test_tool_validation_terminates_timed_out_worker(monkeypatch):
    process = SimpleNamespace(
        communicate=AsyncMock(side_effect=TimeoutError),
        returncode=None,
        kill=Mock(),
        wait=AsyncMock(),
    )
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )

    with pytest.raises(ValueError, match="validation timed out"):
        await tool_validation.validate_tool_arguments({"patternProperties": {}}, {})

    process.kill.assert_called_once()
    process.wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_tool_validation_checks_regex_payload_size_before_spawning(monkeypatch):
    spawn = AsyncMock()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(tool_validation, "_MAX_WORKER_INPUT_BYTES", 20)

    with pytest.raises(ValueError, match="validation size limit"):
        await tool_validation.validate_tool_arguments({"patternProperties": {}}, {})

    spawn.assert_not_awaited()
