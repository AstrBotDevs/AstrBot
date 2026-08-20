import json
from io import BytesIO
from pathlib import Path

import pytest
from starlette.datastructures import UploadFile

from astrbot.dashboard.services.data_file_service import (
    DataFileService,
    DataFileServiceError,
)


def service(tmp_path: Path, *, demo_mode: bool = False) -> DataFileService:
    root = tmp_path / "data"
    root.mkdir(parents=True)
    return DataFileService(data_root=root, demo_mode=demo_mode)


def test_paths_hidden_unicode_and_traversal(tmp_path: Path):
    svc = service(tmp_path)
    (svc.root / ".hidden目录.txt").write_text("ok", encoding="utf-8")
    names = {item["name"] for item in svc.tree("", can_read=True)["entries"]}
    assert ".hidden目录.txt" in names
    for value in ("../x", "a/../../x", "/etc/passwd", r"..\x", "a//b", "a/./b"):
        with pytest.raises(DataFileServiceError):
            svc.normalize_relative_path(value)


def test_symlink_is_metadata_only(tmp_path: Path):
    svc = service(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (svc.root / "link.txt").symlink_to(outside)
    entry = svc.metadata("link.txt", can_read=True)
    assert entry["type"] == "symlink"
    assert entry["readable"] is True
    with pytest.raises(DataFileServiceError):
        svc.read_text("link.txt", is_root=True, can_read=True)


def test_etag_conflict_and_atomic_write(tmp_path: Path):
    svc = service(tmp_path)
    (svc.root / "note.txt").write_text("old", encoding="utf-8")
    loaded = svc.read_text("note.txt", is_root=False, can_read=True, can_write=True)
    with pytest.raises(DataFileServiceError) as exc:
        svc.write_text(
            "note.txt",
            "new",
            expected_etag="sha256:stale",
            is_root=False,
            can_write=True,
            can_manage=False,
        )
    assert exc.value.status_code == 409
    svc.write_text(
        "note.txt",
        "new",
        expected_etag=loaded["etag"],
        is_root=False,
        can_write=True,
        can_manage=False,
    )
    assert (svc.root / "note.txt").read_text(encoding="utf-8") == "new"
    assert not any(
        path.name.startswith(".astrbot-data-tmp-") for path in svc.root.iterdir()
    )


def test_write_requires_etag_and_rejects_directories(tmp_path: Path):
    svc = service(tmp_path)
    (svc.root / "folder").mkdir()
    with pytest.raises(DataFileServiceError) as directory_error:
        svc.write_text(
            "folder",
            "nope",
            expected_etag="stat:0:0",
            is_root=True,
            can_write=True,
            can_manage=True,
        )
    assert directory_error.value.status_code == 400

    (svc.root / "note.txt").write_text("old", encoding="utf-8")
    with pytest.raises(DataFileServiceError) as etag_error:
        svc.write_text(
            "note.txt",
            "new",
            expected_etag=None,
            is_root=True,
            can_write=True,
            can_manage=True,
        )
    assert etag_error.value.status_code == 428


def test_mutations_accept_shared_authorization_rights(tmp_path: Path):
    svc = service(tmp_path)
    rights = {
        "can_read": True,
        "is_root": True,
        "can_write": True,
        "can_manage": False,
    }
    created = svc.create("created.txt", "file", **rights)
    assert created["path"] == "created.txt"
    svc.write_text(
        "created.txt",
        "updated",
        expected_etag=created["etag"],
        **rights,
    )
    moved = svc.move("created.txt", "moved.txt", **rights)
    assert moved["path"] == "moved.txt"
    svc.delete("moved.txt", recursive=False, **rights)
    assert not (svc.root / "moved.txt").exists()


def test_classification_prefix_wins_and_demo_is_read_only(tmp_path: Path):
    svc = service(tmp_path)
    (svc.root / "plugins").mkdir()
    (svc.root / "plugins" / "x.py").write_text("x", encoding="utf-8")
    (svc.root / "plugin_data").mkdir()
    (svc.root / "plugin_data" / "x.json").write_text("{}", encoding="utf-8")
    plugin = svc.metadata(
        "plugins/x.py", can_read=True, can_write=True, can_manage=False
    )
    data = svc.metadata(
        "plugin_data/x.json", can_read=True, can_write=True, can_manage=False
    )
    assert plugin["category"] == "system" and not plugin["writable"]
    assert data["category"] == "text" and data["writable"]
    demo = service(tmp_path / "demo", demo_mode=True)
    with pytest.raises(DataFileServiceError):
        demo.create("x.txt", "file", is_root=False, can_write=True, can_manage=False)


def test_search_is_filename_only_and_truncated(tmp_path: Path):
    svc = service(tmp_path)
    (svc.root / "nested").mkdir()
    (svc.root / "nested" / "needle.txt").write_text("not in filename", encoding="utf-8")
    result = __import__("asyncio").run(
        svc.search("needle", "", is_root=False, can_read=True)
    )
    assert [item["path"] for item in result["results"]] == ["nested/needle.txt"]


def test_core_config_uses_managed_save_path(tmp_path: Path):
    calls: list[dict] = []

    async def save_config(_path: str, value: dict):
        calls.append(value)
        (tmp_path / "data" / "cmd_config.json").write_text(
            json.dumps(value), encoding="utf-8"
        )

    root = tmp_path / "data"
    root.mkdir()
    (root / "cmd_config.json").write_text("{}", encoding="utf-8")
    svc = DataFileService(data_root=root, managed_config_saver=save_config)
    etag = svc.read_text(
        "cmd_config.json", is_root=True, can_read=True, can_manage=True
    )["etag"]
    result = __import__("asyncio").run(
        svc.write_managed_text(
            "cmd_config.json",
            '{"dashboard": {}}',
            expected_etag=etag,
            is_root=True,
            can_write=True,
            can_manage=True,
        )
    )
    assert calls == [{"dashboard": {}}]
    assert result["runtime_reload"] == "reloaded"


def test_managed_config_accepts_utf8_bom(tmp_path: Path):
    root = tmp_path / "data"
    root.mkdir(parents=True)
    (root / "cmd_config.json").write_text('\ufeff{"dashboard": {}}', encoding="utf-8")
    saved: list[dict] = []

    async def save_config(_path: str, value: dict):
        saved.append(value)
        (root / "cmd_config.json").write_text(json.dumps(value), encoding="utf-8")

    svc = DataFileService(data_root=root, managed_config_saver=save_config)
    etag = svc.read_text(
        "cmd_config.json", is_root=True, can_read=True, can_manage=True
    )["etag"]
    __import__("asyncio").run(
        svc.write_managed_text(
            "cmd_config.json",
            '\ufeff{"dashboard": {"host": "127.0.0.1"}}',
            expected_etag=etag,
            is_root=True,
            can_write=True,
            can_manage=True,
        )
    )
    assert saved == [{"dashboard": {"host": "127.0.0.1"}}]


def test_hard_readonly_and_move_cannot_wash_restricted_files(tmp_path: Path):
    svc = service(tmp_path)
    (svc.root / "dist").mkdir()
    (svc.root / "dist" / "index.html").write_text("<p>x</p>", encoding="utf-8")
    entry = svc.metadata(
        "dist/index.html", can_read=True, can_write=True, can_manage=True, is_root=True
    )
    assert entry["protected"] is True
    assert entry["writable"] is False
    with pytest.raises(DataFileServiceError):
        svc.move(
            "dist/index.html",
            "moved.html",
            is_root=True,
            can_write=True,
            can_manage=True,
        )
    assert (svc.root / "dist" / "index.html").exists()


def test_recursive_delete_preflights_restricted_descendants(tmp_path: Path):
    svc = service(tmp_path)
    workspace = svc.root / "workspace"
    workspace.mkdir()
    (workspace / "ok.txt").write_text("ok", encoding="utf-8")
    (workspace / "nested.db").write_bytes(b"sqlite")
    with pytest.raises(DataFileServiceError) as exc:
        svc.delete(
            "workspace",
            recursive=True,
            is_root=True,
            can_write=True,
            can_manage=True,
        )
    assert exc.value.status_code == 403
    assert workspace.exists()
    assert (workspace / "nested.db").exists()


def test_sensitive_database_content_is_root_only_and_index_is_hard_readonly(
    tmp_path: Path,
):
    svc = service(tmp_path)
    (svc.root / "data.db").write_bytes(b"SQLite\x00")
    (svc.root / "knowledge_base").mkdir()
    (svc.root / "knowledge_base" / "vectors.faiss").write_bytes(b"index")
    operator = svc.metadata("data.db", can_read=True, can_write=False, is_root=False)
    root = svc.metadata("data.db", can_read=True, can_write=False, is_root=True)
    assert not operator["readable"] and root["readable"]
    assert svc.path_is_hard_restricted("knowledge_base/vectors.faiss")
    with pytest.raises(DataFileServiceError):
        svc.create(
            "knowledge_base/new.index",
            "file",
            is_root=True,
            can_write=True,
            can_manage=True,
        )


@pytest.mark.asyncio
async def test_upload_size_limit_cleans_reserved_temporary_file(tmp_path: Path):
    svc = service(tmp_path)
    upload = UploadFile(
        file=BytesIO(b"x" * (32 * 1024 * 1024 + 1)),
        filename="large.bin",
    )
    with pytest.raises(DataFileServiceError) as exc:
        await svc.upload(
            "large.bin",
            upload,
            is_root=False,
            can_write=True,
            can_manage=False,
        )
    assert exc.value.status_code == 413
    assert not (svc.root / "large.bin").exists()
    assert not any(
        path.name.startswith(".astrbot-data-tmp-") for path in svc.root.iterdir()
    )


@pytest.mark.asyncio
async def test_search_rejects_symlink_root(tmp_path: Path):
    svc = service(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    (svc.root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(DataFileServiceError):
        await svc.search("secret", "link", is_root=True, can_read=True)
