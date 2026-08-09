
import pytest

from astrbot.core.project_workspace import ProjectWorkspaceResolver
from astrbot.dashboard.services.chatui_project_service import ChatUIProjectService


@pytest.mark.asyncio
async def test_project_workspace_is_creator_and_uuid_derived_and_safe(temp_db, tmp_path):
    service = ChatUIProjectService(temp_db)
    service.workspace_resolver = ProjectWorkspaceResolver(tmp_path)
    project = await temp_db.create_chatui_project(creator="alice", title="Project")
    root = service.workspace_resolver.root_for("alice", project.project_id)
    root.mkdir(parents=True)
    (root / "hello.txt").write_text("hello", encoding="utf-8")
    (root / "image.bin").write_bytes(b"\xff\xfe")

    listing = await service.list_workspace_files("alice", project.project_id)
    assert {entry["name"] for entry in listing["entries"]} == {"hello.txt", "image.bin"}
    preview = await service.get_workspace_file(
        "alice", project.project_id, "hello.txt"
    )
    assert preview["content"] == "hello"
    binary = await service.get_workspace_file(
        "alice", project.project_id, "image.bin"
    )
    assert binary["binary"] is True

    with pytest.raises(Exception, match="Invalid workspace path"):
        await service.get_workspace_file("alice", project.project_id, "../secret")
    with pytest.raises(Exception, match="Invalid workspace path"):
        await service.get_workspace_file("alice", project.project_id, "%2e%2e/secret")


@pytest.mark.asyncio
async def test_project_workspace_rejects_symlink_and_hardlink(temp_db, tmp_path):
    service = ChatUIProjectService(temp_db)
    service.workspace_resolver = ProjectWorkspaceResolver(tmp_path)
    project = await temp_db.create_chatui_project(creator="alice", title="Project")
    root = service.workspace_resolver.root_for("alice", project.project_id)
    root.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (root / "link.txt").symlink_to(outside)
    with pytest.raises(Exception):
        await service.get_workspace_file("alice", project.project_id, "link.txt")

    hardlink = root / "hardlink.txt"
    hardlink.hardlink_to(outside)
    listing = await service.list_workspace_files("alice", project.project_id)
    assert all(entry["name"] != "hardlink.txt" for entry in listing["entries"])
