import os
import tempfile
from pathlib import Path

from astrbot.core.utils.astrbot_path import get_astrbot_system_tmp_path


def test_system_tmp_path_lives_in_the_system_temp_dir(monkeypatch, tmp_path):
    system_temp = tmp_path / "system_temp"
    system_temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(system_temp))

    assert get_astrbot_system_tmp_path() == os.path.realpath(
        str(system_temp / ".astrbot")
    )


def test_system_tmp_path_keeps_an_existing_directory(monkeypatch, tmp_path):
    system_temp = tmp_path / "system_temp"
    (system_temp / ".astrbot").mkdir(parents=True)
    monkeypatch.setattr(tempfile, "tempdir", str(system_temp))

    assert get_astrbot_system_tmp_path() == os.path.realpath(
        str(system_temp / ".astrbot")
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
