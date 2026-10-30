from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.workspace import (
    default_workspace_root,
    resolve_project_workspace_root,
    resolve_workspace_root_for_umo,
)
from astrbot.dashboard.api import chat_projects
from astrbot.dashboard.api.auth import AuthContext
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


@pytest_asyncio.fixture
async def session_workspace_service(tmp_path, monkeypatch):
    """Create owned and unrelated sessions with real project associations.

    Args:
        tmp_path: Temporary database and workspace directory.
        monkeypatch: Pytest monkeypatch fixture.

    Yields:
        Project service and the project whose session files are being browsed.
    """
    monkeypatch.setattr(
        "astrbot.core.workspace.get_astrbot_workspaces_path", lambda: str(tmp_path)
    )
    db = SQLiteDatabase(str(tmp_path / "sessions.db"))
    try:
        await db.initialize()
        project = await db.create_chatui_project(
            creator="alice", title="Session files", workspace_type="session"
        )
        other_project = await db.create_chatui_project(
            creator="alice", title="Other project", workspace_type="session"
        )
        for session_id, creator, project_id in (
            ("session-a", "alice", project.project_id),
            ("session-b", "alice", project.project_id),
            ("other-project-session", "alice", other_project.project_id),
            ("unassigned-session", "alice", None),
            ("bob-session", "bob", None),
        ):
            await db.create_platform_session(creator=creator, session_id=session_id)
            if project_id:
                await db.add_session_to_project(session_id, project_id)
        yield ChatUIProjectService(db), project
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_session_workspace_files_follow_session_context(session_workspace_service):
    """Listing, preview and download must use the same root as session tools.

    Args:
        session_workspace_service: Service with two sessions in the same project.
    """
    service, project = session_workspace_service
    default_root = default_workspace_root("webchat:FriendMessage:webchat!alice!default")
    default_root.mkdir()
    (default_root / "default-only.txt").write_text("default", encoding="utf-8")
    (default_root / "output.txt").write_text("wrong content", encoding="utf-8")

    for session_id in ("session-a", "session-b"):
        root = await resolve_workspace_root_for_umo(
            f"webchat:FriendMessage:webchat!alice!{session_id}", service.db
        )
        root.mkdir()
        (root / "output.txt").write_text(session_id, encoding="utf-8")

    for session_id in ("session-a", "session-b"):
        listing = await service.list_workspace_files(
            "alice", project.project_id, session_id=session_id
        )
        assert [entry["name"] for entry in listing["entries"]] == ["output.txt"]
        preview = await service.get_workspace_file(
            "alice", project.project_id, "output.txt", session_id=session_id
        )
        assert preview["content"] == session_id
        root, download = await service.get_workspace_file_location(
            "alice", project.project_id, "output.txt", session_id=session_id
        )
        assert download.parent == root
        assert download.read_text(encoding="utf-8") == session_id


@pytest.mark.asyncio
async def test_workspace_routes_use_session_query(session_workspace_service):
    """Exercise session selection through the real list, preview and download routes.

    Args:
        session_workspace_service: Service backed by actual session associations.
    """
    service, project = session_workspace_service
    app = FastAPI()
    app.include_router(chat_projects.router, prefix="/api/v1")
    app.dependency_overrides[chat_projects.get_service] = lambda: service
    app.dependency_overrides[chat_projects.require_chat_scope] = lambda: AuthContext(
        username="alice", scopes=["chat"]
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for session_id in ("session-a", "session-b"):
            root = await resolve_workspace_root_for_umo(
                f"webchat:FriendMessage:webchat!alice!{session_id}", service.db
            )
            root.mkdir()
            (root / "output.txt").write_text(session_id, encoding="utf-8")
            base = f"/api/v1/chat/projects/{project.project_id}/workspace"
            query = {"session_id": session_id, "path": "output.txt"}
            listing = await client.get(f"{base}/files", params={"session_id": session_id})
            assert listing.status_code == 200
            assert [entry["name"] for entry in listing.json()["data"]["entries"]] == [
                "output.txt"
            ]
            preview = await client.get(f"{base}/file", params=query)
            assert preview.status_code == 200
            assert preview.json()["data"]["content"] == session_id
            download = await client.get(f"{base}/file/download", params=query)
            assert download.status_code == 200
            assert download.text == session_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method",
    ["list_workspace_files", "get_workspace_file", "get_workspace_file_location"],
)
@pytest.mark.parametrize(
    ("session_id", "error"),
    [
        (None, "Missing key: session_id"),
        ("bob-session", "Permission denied"),
        ("other-project-session", "Session does not belong to this project"),
        ("unassigned-session", "Session does not belong to this project"),
        ("missing-session", "Session missing-session not found"),
    ],
)
async def test_session_workspace_requires_owned_project_session(
    session_workspace_service, method, session_id, error
):
    """File APIs must reject missing, foreign and unrelated session contexts.

    Args:
        session_workspace_service: Service with owned and unrelated sessions.
        method: Workspace operation to exercise.
        session_id: Missing or unauthorized session context.
        error: Expected validation message.
    """
    service, project = session_workspace_service
    with pytest.raises(ChatUIProjectServiceError, match=error):
        await getattr(service, method)(
            "alice", project.project_id, "output.txt", session_id=session_id
        )


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
    require_symlink,
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
    require_symlink,
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
