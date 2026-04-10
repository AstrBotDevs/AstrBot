"""Tests for cron tool metadata."""

from astrbot.core.tools.cron_tools import FutureTaskTool


def test_future_task_schema_has_action_and_create_cron_guidance():
    """The merged tool should expose action routing and unambiguous cron guidance."""
    tool = FutureTaskTool()

    assert tool.name == "future_task"
    assert tool.parameters["required"] == ["action"]
    assert tool.parameters["properties"]["action"]["enum"] == [
        "create",
        "delete",
        "list",
    ]

    description = tool.parameters["properties"]["cron_expression"]["description"]

    assert "mon-fri" in description
    assert "sat,sun" in description
    assert "1-5" in description
    assert "avoid ambiguity" in description


def test_future_task_schema_has_no_job_type_and_delete_job_id():
    """The merged tool should remove job_type and document delete requirements."""
    tool = FutureTaskTool()

    assert "job_type" not in tool.parameters["properties"]
    job_id_description = tool.parameters["properties"]["job_id"]["description"]

    assert "action='delete'" in job_id_description
