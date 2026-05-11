from __future__ import annotations

from pathlib import Path

from astrbot.core.utils.astrbot_path import AstrbotPaths


def test_astrbot_paths_root_tracks_environment_updates(monkeypatch, tmp_path: Path):
    first_root = tmp_path / "first-root"
    second_root = tmp_path / "second-root"

    monkeypatch.setenv("ASTRBOT_ROOT", str(first_root))
    paths = AstrbotPaths()

    assert paths.root == first_root
    assert paths.skills == first_root / "data" / "skills"

    monkeypatch.setenv("ASTRBOT_ROOT", str(second_root))

    assert paths.root == second_root
    assert paths.skills == second_root / "data" / "skills"


def test_astrbot_paths_root_override_remains_explicit(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("ASTRBOT_ROOT", raising=False)
    paths = AstrbotPaths()
    override_root = tmp_path / "override-root"

    paths.root = override_root
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path / "env-root"))

    assert paths.root == override_root
    assert paths.skills == override_root / "data" / "skills"
