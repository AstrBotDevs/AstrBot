from __future__ import annotations

from pathlib import Path

import pytest

from astrbot_sdk.runtime.environment_groups import GroupEnvironmentManager


@pytest.mark.unit
def test_matches_python_version_accepts_uv_version_info_format(tmp_path: Path) -> None:
    venv_path = tmp_path / "venv"
    venv_path.mkdir()
    (venv_path / "pyvenv.cfg").write_text(
        "\n".join(
            [
                "home = C:\\Users\\tester\\AppData\\Local\\Programs\\Python\\Python313",
                "implementation = CPython",
                "uv = 0.9.17",
                "version_info = 3.13.12",
                "include-system-site-packages = true",
            ]
        ),
        encoding="utf-8",
    )

    assert GroupEnvironmentManager._matches_python_version(venv_path, "3.13") is True
    assert GroupEnvironmentManager._matches_python_version(venv_path, "3.11") is False
