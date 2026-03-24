import mcp
import pytest

from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor


@pytest.mark.parametrize(
    ("value", "expected_bool", "expect_error"),
    [
        (True, True, False),
        ("true", True, False),
        ("1", True, False),
        ("yes", True, False),
        ("on", True, False),
        (" TRUE ", True, False),
        (False, False, False),
        ("false", False, False),
        ("0", False, False),
        ("no", False, False),
        ("off", False, False),
        ("", False, False),
        (" FALSE ", False, False),
        (None, False, False),
        ("not-a-bool", False, True),
        ("y", False, True),
        ("t", False, True),
        (123, False, True),
        ({}, False, True),
    ],
)
def test_parse_background_task_arg(value, expected_bool, expect_error):
    is_bg, error = FunctionToolExecutor._parse_background_task_arg(
        "transfer_to_subagent",
        value,
    )

    assert is_bg is expected_bool
    if expect_error:
        assert error is not None
        assert isinstance(error, mcp.types.CallToolResult)
        text_content = error.content[0]
        assert isinstance(text_content, mcp.types.TextContent)
        assert "invalid_background_task" in text_content.text
    else:
        assert error is None
