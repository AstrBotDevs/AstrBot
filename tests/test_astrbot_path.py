import os
import tempfile
from pathlib import Path

import pytest

from astrbot.core.utils.astrbot_path import get_astrbot_system_tmp_path


def test_system_tmp_path_lives_in_the_system_temp_dir(monkeypatch, tmp_path):
    system_temp = tmp_path / "system_temp"
    system_temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(system_temp))

    assert get_astrbot_system_tmp_path() == os.path.realpath(
        str(system_temp / ".astrbot-tmp")
    )


@pytest.mark.parametrize("directory_name", [".astrbot", ".astrbot-tmp"])
def test_system_tmp_path_uses_dedicated_directory(
    monkeypatch, tmp_path, directory_name
):
    system_temp = tmp_path / "system_temp"
    (system_temp / directory_name).mkdir(parents=True)
    monkeypatch.setattr(tempfile, "tempdir", str(system_temp))

    assert get_astrbot_system_tmp_path() == os.path.realpath(
        str(system_temp / ".astrbot-tmp")
    )


def test_system_tmp_path_never_shadows_the_init_marker_file(monkeypatch, tmp_path):
    """The system temp dir can fall back to the AstrBot root.

    There ".astrbot" is the marker file created by "astrbot init", so the
    shared temporary directory must not be created on top of it.
    """
    system_temp = tmp_path / "system_temp"
    system_temp.mkdir()
    marker = system_temp / ".astrbot"
    marker.write_text("", encoding="utf-8")
    monkeypatch.setattr(tempfile, "tempdir", str(system_temp))

    resolved = get_astrbot_system_tmp_path()

    assert resolved != os.path.realpath(str(marker))
    Path(resolved).mkdir(parents=True, exist_ok=True)
    assert Path(resolved).is_dir()
    assert marker.is_file()


def test_system_temp_dir_is_ignored_by_git_and_docker():
    """The system temp dir must not leak into git history or images.

    The temp dir can be created inside the repository root, so both ignore
    files have to exclude it.
    """
    repo_root = Path(__file__).resolve().parents[1]

    for ignore_file in (".gitignore", ".dockerignore"):
        entries = {
            line.strip()
            for line in (repo_root / ignore_file)
            .read_text(encoding="utf-8")
            .splitlines()
        }
        assert ".astrbot-tmp" in entries, f"{ignore_file} must ignore .astrbot-tmp"
