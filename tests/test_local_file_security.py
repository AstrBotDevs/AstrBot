import os
import subprocess

import pytest

from astrbot.core.computer.local_file_security import open_file_in_allowed_roots


@pytest.mark.parametrize("access", ["read", "write", "edit"])
def test_workspace_file_descriptors_support_each_access_mode(tmp_path, access):
    """Use one checked descriptor for ordinary Unicode file access on every OS."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "中文😀.txt"
    target.write_text("original", encoding="utf-8")

    descriptor = open_file_in_allowed_roots(str(target), (workspace,), access=access)
    with os.fdopen(
        descriptor, {"read": "r", "write": "w", "edit": "r+"}[access], encoding="utf-8"
    ) as file_obj:
        assert not os.get_inheritable(file_obj.fileno())
        if access != "write":
            assert file_obj.read() == "original"
        if access != "read":
            file_obj.seek(0)
            file_obj.truncate()
            file_obj.write("updated")
    assert target.read_text(encoding="utf-8") == (
        "original" if access == "read" else "updated"
    )


def test_workspace_file_creation_is_relative_to_checked_directories(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "new" / "nested" / "file.txt"

    descriptor = open_file_in_allowed_roots(
        str(target), (workspace,), access="write", create_parents=True
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as file_obj:
        file_obj.write("created")
    assert target.read_text(encoding="utf-8") == "created"


@pytest.mark.parametrize("access", ["read", "write", "edit"])
def test_workspace_open_rejects_hardlinks_without_truncating(tmp_path, access):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    target = workspace / "alias.txt"
    target.hardlink_to(secret)

    with pytest.raises(PermissionError, match="multiple hard links"):
        open_file_in_allowed_roots(str(target), (workspace,), access=access)
    assert secret.read_text(encoding="utf-8") == "secret"


@pytest.mark.parametrize("directory", [False, True])
def test_workspace_open_rejects_links_in_any_component(tmp_path, directory):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    link = workspace / "link"
    try:
        link.symlink_to(outside if directory else secret, target_is_directory=directory)
    except OSError as exc:
        pytest.skip(f"Symbolic links are unavailable: {exc}")
    target = link / "secret.txt" if directory else link

    with pytest.raises(PermissionError):
        open_file_in_allowed_roots(str(target), (workspace,), access="write")
    assert secret.read_text(encoding="utf-8") == "secret"


def test_checked_descriptor_survives_parent_directory_replacement(tmp_path):
    workspace = tmp_path / "workspace"
    checked = workspace / "checked"
    checked.mkdir(parents=True)
    target = checked / "file.txt"
    target.write_text("checked file", encoding="utf-8")
    descriptor = open_file_in_allowed_roots(str(target), (workspace,), access="edit")
    with os.fdopen(descriptor, "r+", encoding="utf-8") as file_obj:
        try:
            checked.rename(workspace / "moved")
        except PermissionError:
            # Windows may pin the directory while a child is open.
            assert os.name == "nt"
        else:
            checked.mkdir()
            target.write_text("replacement", encoding="utf-8")
        assert file_obj.read() == "checked file"
        file_obj.seek(0)
        file_obj.write("updated file")
    if (workspace / "moved").exists():
        assert target.read_text(encoding="utf-8") == "replacement"
        assert (workspace / "moved" / "file.txt").read_text(
            encoding="utf-8"
        ) == "updated file"


@pytest.mark.skipif(os.name != "nt", reason="Requires Windows directory junctions.")
@pytest.mark.parametrize("create", [False, True])
def test_windows_workspace_open_rejects_directory_junctions(tmp_path, create):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    junction = workspace / "junction"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        check=True,
        capture_output=True,
    )
    try:
        with pytest.raises(PermissionError):
            open_file_in_allowed_roots(
                str(junction / ("new.txt" if create else "secret.txt")),
                (workspace,),
                access="write",
                create_parents=create,
            )
        assert secret.read_text(encoding="utf-8") == "secret"
        assert not (outside / "new.txt").exists()
    finally:
        junction.rmdir()


@pytest.mark.skipif(os.name != "nt", reason="Requires Windows native paths.")
@pytest.mark.parametrize("ancestor", [False, True])
def test_windows_workspace_open_rejects_junctions_at_or_above_root(tmp_path, ancestor):
    outside = tmp_path / "outside"
    outside.mkdir()
    directory = outside / "nested" if ancestor else outside
    directory.mkdir(exist_ok=True)
    secret = directory / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    junction = tmp_path / "junction"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        check=True,
        capture_output=True,
    )
    workspace = junction / "nested" if ancestor else junction
    try:
        with pytest.raises(PermissionError, match="reparse point"):
            open_file_in_allowed_roots(
                str(workspace / "secret.txt"), (workspace,), access="write"
            )
        assert secret.read_text(encoding="utf-8") == "secret"
    finally:
        junction.rmdir()


def test_workspace_file_creation_does_not_create_missing_trusted_root(tmp_path):
    workspace = tmp_path / "missing" / "workspace"
    with pytest.raises(FileNotFoundError):
        open_file_in_allowed_roots(
            str(workspace / "file.txt"),
            (workspace,),
            access="write",
            create_parents=True,
        )
    assert not workspace.parent.exists()


@pytest.mark.skipif(os.name != "nt", reason="Requires Windows native paths.")
@pytest.mark.parametrize("name", ["file.txt:stream", "file.txt.", "file.txt "])
def test_windows_workspace_open_rejects_alternate_streams_and_ambiguous_names(
    tmp_path, name
):
    with pytest.raises(PermissionError, match="unsafe restricted Windows path"):
        open_file_in_allowed_roots(
            str(tmp_path / name), (tmp_path,), access="write", create_parents=True
        )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("access", ["read", "write", "edit"])
def test_workspace_open_rejects_paths_outside_root(tmp_path, access):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(PermissionError, match="outside restricted roots"):
        open_file_in_allowed_roots(
            str(tmp_path / "outside.txt"), (workspace,), access=access
        )


def test_workspace_open_rejects_directory_as_file(tmp_path):
    with pytest.raises(IsADirectoryError):
        open_file_in_allowed_roots(str(tmp_path), (tmp_path,), access="read")
