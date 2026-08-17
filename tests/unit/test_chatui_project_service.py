from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.workspace import resolve_project_workspace_root
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


def test_custom_workspace_relative_path_uses_astrbot_workspaces(tmp_path, monkeypatch):
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


@pytest.mark.asyncio
async def test_api_key_project_rejects_custom_workspace(tmp_path):
    """API key projects must not accept caller-selected workspace roots."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    db = SimpleNamespace(create_chatui_project=AsyncMock())
    service = ChatUIProjectService(db)

    with pytest.raises(
        ChatUIProjectServiceError,
        match="API key projects cannot use custom workspaces",
    ):
        await service.create_project(
            "api_key:key-id",
            {
                "title": "Unsafe project",
                "workspace_type": "custom",
                "workspace_path": str(workspace),
            },
        )

    db.create_chatui_project.assert_not_awaited()


@pytest.mark.asyncio
async def test_api_key_project_rejects_workspace_path_without_custom_type():
    """API key projects must reject workspace paths for every workspace type."""
    db = SimpleNamespace(create_chatui_project=AsyncMock())
    service = ChatUIProjectService(db)

    with pytest.raises(
        ChatUIProjectServiceError,
        match="API key projects cannot use custom workspaces",
    ):
        await service.create_project(
            "api_key:key-id",
            {
                "title": "Unsafe project",
                "workspace_type": "project",
                "workspace_path": "/etc",
            },
        )

    db.create_chatui_project.assert_not_awaited()


@pytest.mark.asyncio
async def test_api_key_project_defaults_to_managed_project_workspace():
    """API key projects should default to a managed per-project workspace."""
    now = datetime.now(timezone.utc)
    project = SimpleNamespace(
        project_id="project-1",
        title="Managed project",
        emoji="📁",
        description=None,
        creator="api_key:key-id",
        workspace_type="project",
        workspace_path=None,
        created_at=now,
        updated_at=now,
    )
    db = SimpleNamespace(create_chatui_project=AsyncMock(return_value=project))
    service = ChatUIProjectService(db)

    result = await service.create_project(
        "api_key:key-id",
        {"title": "Managed project"},
    )

    assert result["workspace_type"] == "project"
    db.create_chatui_project.assert_awaited_once_with(
        creator="api_key:key-id",
        title="Managed project",
        emoji="📁",
        description=None,
        workspace_type="project",
        workspace_path=None,
    )


@pytest.mark.asyncio
async def test_api_key_project_update_rejects_custom_workspace():
    """API key project updates must not accept a custom workspace path."""
    project = SimpleNamespace(
        project_id="project-1",
        creator="api_key:key-id",
        workspace_type="project",
        workspace_path=None,
    )
    db = SimpleNamespace(
        get_chatui_project_by_id=AsyncMock(return_value=project),
        update_chatui_project=AsyncMock(),
    )
    service = ChatUIProjectService(db)

    with pytest.raises(
        ChatUIProjectServiceError,
        match="API key projects cannot use custom workspaces",
    ):
        await service.update_project(
            "api_key:key-id",
            {
                "project_id": "project-1",
                "workspace_type": "custom",
                "workspace_path": "/etc",
            },
        )

    db.update_chatui_project.assert_not_awaited()


def test_dashboard_project_resolves_absolute_custom_workspace(tmp_path, monkeypatch):
    """Dashboard projects should preserve administrator-selected workspaces."""
    workspaces_root = tmp_path / "workspaces"
    custom_root = tmp_path / "custom"
    workspaces_root.mkdir()
    custom_root.mkdir()
    monkeypatch.setattr(
        "astrbot.core.workspace.get_astrbot_workspaces_path",
        lambda: str(workspaces_root),
    )
    project = SimpleNamespace(
        project_id="project-1",
        creator="alice",
        workspace_type="custom",
        workspace_path=str(custom_root),
    )

    resolved = resolve_project_workspace_root(
        project,
        fallback_umo="webchat:FriendMessage:webchat!alice!default",
    )

    assert resolved == custom_root


def test_api_key_project_runtime_rejects_root_outside_workspaces(
    tmp_path,
    monkeypatch,
):
    """Runtime resolution must keep every API key project under workspaces."""
    workspaces_root = tmp_path / "workspaces"
    external_root = tmp_path / "external"
    workspaces_root.mkdir()
    external_root.mkdir()
    monkeypatch.setattr(
        "astrbot.core.workspace.get_astrbot_workspaces_path",
        lambda: str(workspaces_root),
    )
    monkeypatch.setattr(
        "astrbot.core.workspace.project_workspace_root",
        lambda _project_id: external_root,
    )
    project = SimpleNamespace(
        project_id="project-1",
        creator="api_key:key-id",
        workspace_type="project",
        workspace_path=None,
    )

    with pytest.raises(ValueError, match="must stay within AstrBot workspaces"):
        resolve_project_workspace_root(
            project,
            fallback_umo="webchat:FriendMessage:webchat!api-key!default",
        )


@pytest.mark.asyncio
async def test_api_key_custom_workspace_cannot_expose_external_files(
    tmp_path,
    monkeypatch,
):
    """Legacy API key projects must resolve to managed project workspaces."""
    workspaces_root = tmp_path / "workspaces"
    external_root = tmp_path / "external"
    workspaces_root.mkdir()
    external_root.mkdir()
    (external_root / "secret.txt").write_text("secret", encoding="utf-8")
    monkeypatch.setattr(
        "astrbot.core.workspace.get_astrbot_workspaces_path",
        lambda: str(workspaces_root),
    )
    project = SimpleNamespace(
        project_id="project-1",
        creator="api_key:key-id",
        workspace_type="custom",
        workspace_path=str(external_root),
    )
    db = SimpleNamespace(get_chatui_project_by_id=AsyncMock(return_value=project))
    service = ChatUIProjectService(db)

    result = await service.list_workspace_files(
        "api_key:key-id",
        "project-1",
    )

    assert result == {"path": "", "entries": []}


@pytest.mark.asyncio
async def test_database_migrates_api_key_custom_workspaces(tmp_path):
    """Database startup should downgrade existing API key custom workspaces."""
    db = SQLiteDatabase(str(tmp_path / "workspace-migration.db"))
    try:
        await db.initialize()
        project = await db.create_chatui_project(
            creator="api_key:key-id",
            title="Legacy API project",
            workspace_type="custom",
            workspace_path="/external/workspace",
        )

        await db.initialize()
        migrated = await db.get_chatui_project_by_id(project.project_id)

        assert migrated is not None
        assert migrated.workspace_type == "project"
        assert migrated.workspace_path is None
    finally:
        await db.engine.dispose()


@pytest.fixture
def workspace_service(tmp_path, monkeypatch):
    """Create a project service backed by a temporary workspace.

    Args:
        tmp_path: Temporary workspace root.
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        Project service configured with an owned project.
    """
    project = SimpleNamespace(
        project_id="project-1",
        creator="alice",
        workspace_type="custom",
        workspace_path=str(tmp_path),
    )
    db = SimpleNamespace(get_chatui_project_by_id=AsyncMock(return_value=project))
    monkeypatch.setattr(
        "astrbot.dashboard.services.chatui_project_service.resolve_project_workspace_root",
        lambda _project, *, fallback_umo: tmp_path,
    )
    return ChatUIProjectService(db)


@pytest.mark.asyncio
async def test_list_workspace_files_is_sorted_and_idempotent(
    tmp_path,
    workspace_service,
):
    """Workspace listing should be stable, read-only, and directory-first."""
    (tmp_path / "z-dir").mkdir()
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "b.txt").write_text("beta", encoding="utf-8")

    first = await workspace_service.list_workspace_files("alice", "project-1")
    second = await workspace_service.list_workspace_files("alice", "project-1")

    assert first == second
    assert [entry["name"] for entry in first["entries"]] == [
        "z-dir",
        "a.txt",
        "b.txt",
    ]
    assert first["entries"][1]["readable"] is True
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "alpha"


@pytest.mark.asyncio
async def test_get_workspace_file_reads_utf8_text(tmp_path, workspace_service):
    """Workspace file reads should return content without changing the file."""
    target = tmp_path / "notes.md"
    target.write_text("你好，workspace", encoding="utf-8")

    result = await workspace_service.get_workspace_file(
        "alice",
        "project-1",
        "notes.md",
    )

    assert result == {
        "path": "notes.md",
        "content": "你好，workspace",
        "size": len("你好，workspace".encode()),
    }
    assert target.read_text(encoding="utf-8") == "你好，workspace"


@pytest.mark.asyncio
async def test_get_workspace_file_allows_nested_path(tmp_path, workspace_service):
    """Workspace reads should preserve legitimate nested file access."""
    nested_dir = tmp_path / "docs"
    nested_dir.mkdir()
    target = nested_dir / "notes.md"
    target.write_text("nested", encoding="utf-8")

    result = await workspace_service.get_workspace_file(
        "alice",
        "project-1",
        "docs/notes.md",
    )

    assert result["path"] == "docs/notes.md"
    assert result["content"] == "nested"


@pytest.mark.asyncio
async def test_get_workspace_file_location_supports_binary_download(
    tmp_path,
    workspace_service,
):
    """Workspace downloads should resolve binary files without changing them."""
    target = tmp_path / "archive.bin"
    target.write_bytes(b"\xff\xfe\x00")

    workspace_root, result = await workspace_service.get_workspace_file_location(
        "alice",
        "project-1",
        "archive.bin",
    )

    assert workspace_root == tmp_path
    assert result == target
    assert result.read_bytes() == b"\xff\xfe\x00"


@pytest.mark.asyncio
async def test_workspace_paths_reject_traversal(workspace_service):
    """Workspace APIs should reject relative paths that escape the project."""
    with pytest.raises(ChatUIProjectServiceError, match="Invalid workspace path"):
        await workspace_service.list_workspace_files(
            "alice",
            "project-1",
            "../outside",
        )

    with pytest.raises(ChatUIProjectServiceError, match="Invalid workspace path"):
        await workspace_service.get_workspace_file(
            "alice",
            "project-1",
            "../outside.txt",
        )


@pytest.mark.asyncio
async def test_get_workspace_file_rejects_binary_text(tmp_path, workspace_service):
    """Workspace preview should reject files that are not valid UTF-8."""
    (tmp_path / "binary.dat").write_bytes(b"\xff\xfe\x00")

    with pytest.raises(ChatUIProjectServiceError, match="not valid UTF-8"):
        await workspace_service.get_workspace_file(
            "alice",
            "project-1",
            "binary.dat",
        )


@pytest.mark.asyncio
async def test_workspace_file_rejects_symlink_escape(
    tmp_path,
    workspace_service,
):
    """Workspace reads should not follow a symlink outside the project root."""
    outside_file = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside_file.write_text("outside", encoding="utf-8")
    (tmp_path / "outside-link.txt").symlink_to(outside_file)

    with pytest.raises(
        ChatUIProjectServiceError,
        match="escapes project directory",
    ):
        await workspace_service.get_workspace_file(
            "alice",
            "project-1",
            "outside-link.txt",
        )


@pytest.mark.asyncio
async def test_workspace_file_rejects_symlink_directory_escape(
    tmp_path,
    workspace_service,
):
    """Workspace reads should reject an escaping symlink in any path segment."""
    outside_dir = tmp_path.parent / f"{tmp_path.name}-outside-dir"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("outside", encoding="utf-8")
    (tmp_path / "outside-link").symlink_to(outside_dir, target_is_directory=True)

    with pytest.raises(
        ChatUIProjectServiceError,
        match="escapes project directory",
    ):
        await workspace_service.get_workspace_file(
            "alice",
            "project-1",
            "outside-link/secret.txt",
        )
