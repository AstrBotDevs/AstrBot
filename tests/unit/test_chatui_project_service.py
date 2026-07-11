import pytest

from astrbot.dashboard.services.chatui_project_service import (
    ChatUIProjectService,
    ChatUIProjectServiceError,
)


def test_custom_workspace_accepts_existing_directory(tmp_path, monkeypatch):
    """Custom workspace paths should accept existing usable directories."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(
        "astrbot.core.workspace.get_astrbot_workspaces_path",
        lambda: str(tmp_path),
    )

    workspace_type, workspace_path = ChatUIProjectService._normalize_workspace_config(
        {
            "workspace_type": "custom",
            "workspace_path": str(workspace),
        }
    )

    assert workspace_type == "custom"
    assert workspace_path == str(workspace)


def test_custom_workspace_rejects_missing_path(tmp_path, monkeypatch):
    """Custom workspace paths should reject missing directories."""
    monkeypatch.setattr(
        "astrbot.core.workspace.get_astrbot_workspaces_path",
        lambda: str(tmp_path),
    )

    with pytest.raises(ChatUIProjectServiceError, match="does not exist"):
        ChatUIProjectService._normalize_workspace_config(
            {
                "workspace_type": "custom",
                "workspace_path": "missing",
            }
        )


def test_custom_workspace_rejects_file_path(tmp_path, monkeypatch):
    """Custom workspace paths should reject regular files."""
    monkeypatch.setattr(
        "astrbot.core.workspace.get_astrbot_workspaces_path",
        lambda: str(tmp_path),
    )
    file_path = tmp_path / "workspace.txt"
    file_path.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ChatUIProjectServiceError, match="must be a directory"):
        ChatUIProjectService._normalize_workspace_config(
            {
                "workspace_type": "custom",
                "workspace_path": "workspace.txt",
            }
        )


def test_custom_workspace_relative_path_uses_astrbot_workspaces(
    tmp_path, monkeypatch
):
    """Relative custom workspace paths should resolve under AstrBot workspaces."""
    relative_workspace = tmp_path / "relative-workspace"
    relative_workspace.mkdir()
    monkeypatch.setattr(
        "astrbot.core.workspace.get_astrbot_workspaces_path",
        lambda: str(tmp_path),
    )

    workspace_type, workspace_path = ChatUIProjectService._normalize_workspace_config(
        {
            "workspace_type": "custom",
            "workspace_path": "relative-workspace",
        }
    )

    assert workspace_type == "custom"
    assert workspace_path == "relative-workspace"


def test_custom_workspace_rejects_relative_path_traversal(tmp_path, monkeypatch):
    """Relative custom workspace paths must not escape AstrBot workspaces."""
    outside_workspace = tmp_path / "outside"
    workspaces_root = tmp_path / "workspaces"
    outside_workspace.mkdir()
    workspaces_root.mkdir()
    monkeypatch.setattr(
        "astrbot.core.workspace.get_astrbot_workspaces_path",
        lambda: str(workspaces_root),
    )

    with pytest.raises(ChatUIProjectServiceError, match="must stay within"):
        ChatUIProjectService._normalize_workspace_config(
            {
                "workspace_type": "custom",
                "workspace_path": "../outside",
            }
        )


def test_custom_workspace_rejects_workspaces_root(tmp_path, monkeypatch):
    """Custom workspace paths must not expose the entire workspaces root."""
    monkeypatch.setattr(
        "astrbot.core.workspace.get_astrbot_workspaces_path",
        lambda: str(tmp_path),
    )

    with pytest.raises(ChatUIProjectServiceError, match="must stay within"):
        ChatUIProjectService._normalize_workspace_config(
            {
                "workspace_type": "custom",
                "workspace_path": ".",
            }
        )


def test_custom_workspace_accepts_absolute_path_outside_workspaces(
    tmp_path, monkeypatch
):
    """Absolute custom workspace paths may point outside AstrBot workspaces."""
    outside_workspace = tmp_path / "outside"
    workspaces_root = tmp_path / "workspaces"
    outside_workspace.mkdir()
    workspaces_root.mkdir()
    monkeypatch.setattr(
        "astrbot.core.workspace.get_astrbot_workspaces_path",
        lambda: str(workspaces_root),
    )

    workspace_type, workspace_path = ChatUIProjectService._normalize_workspace_config(
        {
            "workspace_type": "custom",
            "workspace_path": str(outside_workspace),
        }
    )

    assert workspace_type == "custom"
    assert workspace_path == str(outside_workspace)
