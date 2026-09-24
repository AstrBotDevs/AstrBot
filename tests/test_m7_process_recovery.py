"""Recovery after a child exits without running Python cleanup handlers."""

import base64
import json
import os
import sqlite3
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pytest
import pytest_asyncio
from PIL import Image

from astrbot.core.db.sqlite import SQLiteDatabase


@pytest_asyncio.fixture
async def abrupt_root(tmp_path):
    root = tmp_path / "astrbot"
    (root / "data").mkdir(parents=True)
    db = SQLiteDatabase(str(root / "data" / "data_v4.db"))
    try:
        await db.initialize()
        db.inited = True
        await db.create_conversation("owner", "platform", cid="abrupt")
    finally:
        await db.engine.dispose()
    return root


@pytest.mark.parametrize("boundary", ["asset", "commit"])
def test_abrupt_process_exit_resumes_without_duplicate_assets(abrupt_root, boundary):
    image = BytesIO()
    Image.new("RGB", (4, 4), "red").save(image, format="PNG")
    original = json.dumps(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": "data:image/png;base64,"
                        + base64.b64encode(image.getvalue()).decode("ascii"),
                    }
                ],
            }
        ]
    )
    database = abrupt_root / "data" / "data_v4.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE conversations SET content=? WHERE conversation_id='abrupt'",
            (original,),
        )
    child = r"""
import asyncio
import os
import sys
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core import image_history_maintenance as maintenance

boundary = sys.argv[1]
if boundary == "asset":
    original = maintenance.ImageAssetStore.import_file
    async def terminated(self, *args, **kwargs):
        await original(self, *args, **kwargs)
        os._exit(73)
    maintenance.ImageAssetStore.import_file = terminated
else:
    original = maintenance.commit_migrated_history
    async def terminated(*args, **kwargs):
        await original(*args, **kwargs)
        os._exit(73)
    maintenance.commit_migrated_history = terminated

async def run():
    db = SQLiteDatabase(sys.argv[2])
    await db.initialize()
    db.inited = True
    await maintenance.run_image_history_maintenance(db, "abrupt", apply=True)
asyncio.run(run())
"""
    environment = dict(os.environ, ASTRBOT_ROOT=str(abrupt_root))
    project = Path(__file__).resolve().parents[1]
    killed = subprocess.run(
        [sys.executable, "-c", child, boundary, str(database)],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert killed.returncode == 73, killed.stderr
    with sqlite3.connect(database) as connection:
        before_resume = connection.execute(
            "SELECT content FROM conversations WHERE conversation_id='abrupt'"
        ).fetchone()[0]
        assert (before_resume == original) == (boundary == "asset")
    resumed = subprocess.run(
        [
            sys.executable,
            str(project / "scripts" / "migrate_image_history.py"),
            "--root",
            str(abrupt_root),
            "--conversation",
            "abrupt",
            "--stopped",
            "--apply",
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert resumed.returncode == 0, resumed.stderr
    assert '"status": "committed"' in resumed.stdout or (
        '"status": "already_committed"' in resumed.stdout
    )
    with sqlite3.connect(database) as connection:
        stored = json.loads(
            connection.execute(
                "SELECT content FROM conversations WHERE conversation_id='abrupt'"
            ).fetchone()[0]
        )
        assert stored[0]["content"][0]["type"] == "image_ref"
        # Table names are static schema identifiers, not user input.
        for table in ("image_assets", "conversation_image_refs"):
            assert (
                connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1
            )
        assert (
            connection.execute(
                "SELECT state FROM image_history_migration_tasks"
            ).fetchone()[0]
            == "committed"
        )
    assert len(list((abrupt_root / "data" / "image_assets").glob("*.img"))) == 1
