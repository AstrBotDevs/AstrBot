from __future__ import annotations

from pathlib import Path

import pytest

from astrbot.cli.commands.cmd_init import initialize_astrbot


@pytest.mark.asyncio
async def test_initialize_astrbot_creates_skills_dir(tmp_path: Path) -> None:
    await initialize_astrbot(
        tmp_path,
        yes=True,
        backend_only=True,
        admin_username=None,
        admin_password=None,
    )

    assert (tmp_path / ".astrbot").exists()
    assert (tmp_path / "data" / "skills").is_dir()
