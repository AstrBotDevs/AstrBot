"""Python adapters preserve output, error, and timeout semantics."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.astr_agent_runtime.computer.booters.cua import CuaPythonComponent
from astrbot.core.astr_agent_runtime.computer.olayer.python import PythonComponent


@pytest.mark.asyncio
@pytest.mark.parametrize("silent", [False, True])
async def test_native_python_transport_preserves_result(silent):
    transport = AsyncMock(return_value={"stdout": "42", "stderr": "", "exit_code": 0})
    component: PythonComponent = CuaPythonComponent(
        SimpleNamespace(python=SimpleNamespace(exec=transport))
    )
    result = await component.exec(
        "print(42)", kernel_id="existing", timeout=9, silent=silent
    )
    transport.assert_awaited_once_with("print(42)", timeout=9)
    expected = "" if silent else "42"
    assert result == {
        "success": True,
        "data": {"output": {"text": expected, "images": []}, "error": ""},
        "output": expected,
        "error": "",
    }


@pytest.mark.asyncio
async def test_python_failure_keeps_error_in_both_envelopes():
    transport = AsyncMock(
        return_value={"stdout": "", "stderr": "NameError", "exit_code": 1}
    )
    component: PythonComponent = CuaPythonComponent(
        SimpleNamespace(python=SimpleNamespace(exec=transport))
    )
    result = await component.exec("missing")
    assert result["success"] is False
    assert result["error"] == result["data"]["error"] == "NameError"
