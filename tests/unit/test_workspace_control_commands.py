"""Tests for deterministic administrator workspace-control commands."""

import hashlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from astrbot.builtin_stars.builtin_commands.commands.workspace_control import (
    WorkspaceControlCommands,
)


def _result_text(event) -> str:
    """Return the plain text assigned by a command handler.

    Args:
        event: Test event carrying the command result.

    Returns:
        Plain text in the first message component.
    """
    return event.set_result.call_args.args[0].chain[0].text


@pytest.mark.asyncio
async def test_workspace_control_command_lists_and_approves_artifact(
    tmp_path,
    monkeypatch,
) -> None:
    """List a pending artifact and approve it only with its displayed digest."""
    artifact = tmp_path / "EXTRA_PROMPT.md"
    artifact.write_text("trusted", encoding="utf-8")
    event = SimpleNamespace(
        unified_msg_origin="qq:friend:admin-1",
        get_sender_id=lambda: "admin-1",
        set_result=Mock(),
    )
    context = SimpleNamespace(get_db=lambda: object())
    command = WorkspaceControlCommands(context)

    async def resolve_workspace(*_args, **_kwargs):
        return tmp_path

    # Some plugin lifecycle tests deliberately reload command modules. Patch
    # the exact globals dictionary used by the class collected for this test so
    # full-suite ordering cannot redirect the patch to a newer module object.
    monkeypatch.setitem(
        WorkspaceControlCommands.workspace_control.__globals__,
        "resolve_workspace_root_for_umo",
        resolve_workspace,
    )

    await command.workspace_control(event, "list")
    assert "EXTRA_PROMPT.md | status=pending" in _result_text(event)

    digest = hashlib.sha256(b"trusted").hexdigest()
    await command.workspace_control(event, "approve", "EXTRA_PROMPT.md", digest)
    assert "Approved EXTRA_PROMPT.md" in _result_text(event)

    await command.workspace_control(event, "revoke", "EXTRA_PROMPT.md")
    assert "Revoked approval for EXTRA_PROMPT.md" in _result_text(event)
