from pathlib import Path

from astrbot.core.tools.computer_tools import util as computer_util


def test_normalize_umo_for_workspace_preserves_normal_session_names() -> None:
    assert (
        computer_util.normalize_umo_for_workspace("qq:GroupMessage:1000")
        == "qq_GroupMessage_1000"
    )
    assert (
        computer_util.normalize_umo_for_workspace("platform.user-1")
        == "platform.user-1"
    )


def test_normalize_umo_for_workspace_rejects_dot_only_values() -> None:
    assert computer_util.normalize_umo_for_workspace(".") == "unknown"
    assert computer_util.normalize_umo_for_workspace("..") == "unknown"
    assert computer_util.normalize_umo_for_workspace("...") == "unknown"
    assert computer_util.normalize_umo_for_workspace(" _._ ") == "unknown"


def test_workspace_root_for_dot_only_umo_stays_under_workspaces(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspaces_root = tmp_path / "workspaces"
    monkeypatch.setattr(
        computer_util,
        "get_astrbot_workspaces_path",
        lambda: str(workspaces_root),
    )

    root = computer_util.workspace_root("..")

    assert root == (workspaces_root / "unknown").resolve(strict=False)
    assert root.is_relative_to(workspaces_root.resolve(strict=False))
