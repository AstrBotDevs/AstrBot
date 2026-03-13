"""Tests for cron tool metadata."""

from astrbot.core.tools.cron_tools import CreateActiveCronTool


def test_create_future_task_cron_description_prefers_named_weekdays():
    """The cron tool should steer users toward unambiguous named weekdays."""
    tool = CreateActiveCronTool()

    description = tool.parameters["properties"]["cron_expression"]["description"]

    assert "mon-fri" in description
    assert "sat,sun" in description
    assert "1-5" in description
    assert "avoid ambiguity" in description
