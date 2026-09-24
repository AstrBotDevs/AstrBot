"""Black-box checks for the stopped-application image maintenance command."""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pytest_asyncio
from PIL import Image

from astrbot.core.db.sqlite import SQLiteDatabase

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLI = PROJECT_ROOT / "scripts" / "migrate_image_history.py"
DB_RELATIVE = Path("data") / "data_v4.db"
CONVERSATION_ID = "m7-cli-conversation"


@pytest_asyncio.fixture
async def cli_root(tmp_path: Path):
    """Create and close an isolated AstrBot database before CLI subprocesses."""
    root = tmp_path / "astrbot-root"
    (root / "data").mkdir(parents=True)
    (root / "data" / "temp").mkdir()
    database = root / DB_RELATIVE
    db = SQLiteDatabase(str(database))
    await db.initialize()
    db.inited = True
    await db.create_conversation(
        "m7-owner", "m7-platform", cid=CONVERSATION_ID, title="M7 fixture"
    )
    await db.engine.dispose()
    yield root


def _seed_history(root: Path, history: list[dict]) -> bytes:
    """Seed old-format JSON directly, bypassing the online history size guard."""
    content = json.dumps(history, ensure_ascii=False, separators=(",", ":"))
    with sqlite3.connect(root / DB_RELATIVE) as connection:
        connection.execute(
            "UPDATE conversations SET content=? WHERE conversation_id=?",
            (content, CONVERSATION_ID),
        )
    return content.encode("utf-8")


def _history_bytes(root: Path) -> bytes:
    with sqlite3.connect(root / DB_RELATIVE) as connection:
        return connection.execute(
            "SELECT CAST(content AS BLOB) FROM conversations WHERE conversation_id=?",
            (CONVERSATION_ID,),
        ).fetchone()[0]


def _run_cli(root: Path, *arguments: str, guard_dir: Path | None = None):
    """Run the real maintenance entry point with optional child network guards."""
    environment = os.environ.copy()
    environment.pop("ASTRBOT_ROOT", None)
    if guard_dir is not None:
        existing = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = os.pathsep.join(
            item for item in (str(guard_dir), existing) if item
        )
        environment["M7_NETWORK_ATTEMPT_FILE"] = str(guard_dir / "attempts.txt")
    return subprocess.run(
        [sys.executable, str(CLI), "--root", str(root), *arguments],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def _install_network_guard(path: Path) -> Path:
    """Reject outbound TCP and urllib requests inside a real CLI subprocess."""
    guard_dir = path / "network_guard"
    guard_dir.mkdir()
    (guard_dir / "sitecustomize.py").write_text(
        """import os
import socket
import urllib.request

def blocked(*args, **kwargs):
    with open(os.environ['M7_NETWORK_ATTEMPT_FILE'], 'a') as out:
        out.write('network API called\\n')
    raise AssertionError('network access is forbidden in this test')

socket.create_connection = blocked
_connect = socket.socket.connect
def guarded_connect(self, address):
    if isinstance(address, tuple):
        blocked(address)
    return _connect(self, address)
socket.socket.connect = guarded_connect
urllib.request.urlopen = blocked
""",
        encoding="utf-8",
    )
    return guard_dir


def test_list_is_read_only_and_reports_only_oversized_metadata(cli_root: Path):
    secret = "PRIVATE-LEGACY-BODY-DO-NOT-PRINT"
    original = _seed_history(
        cli_root,
        [
            {"role": "user", "content": secret + "x" * (16 * 1024 * 1024)},
        ],
    )
    before = _history_bytes(cli_root)

    result = _run_cli(cli_root, "--list")

    assert result.returncode == 0, result.stderr
    listing = json.loads(result.stdout)
    assert listing == [
        {
            "conversation_id": CONVERSATION_ID,
            "title": "M7 fixture",
            "history_bytes": len(original),
        }
    ]
    assert secret not in result.stdout
    assert _history_bytes(cli_root) == before
    assert not (cli_root / "data" / "image_history_migrations").exists()


def test_cli_requires_explicit_stop_ack_before_importing_maintenance_services(
    cli_root: Path,
):
    original = _seed_history(cli_root, [{"role": "user", "content": "keep me"}])
    before = _history_bytes(cli_root)

    result = _run_cli(cli_root, "--conversation", CONVERSATION_ID)

    assert result.returncode == 2
    assert "--stopped" in result.stderr
    assert "does not stop running processes" in result.stderr
    assert "image_history_migrations" not in result.stderr
    assert _history_bytes(cli_root) == before == original


def test_real_cli_preflight_apply_and_resume_preserve_legacy_json(
    cli_root: Path, tmp_path: Path
):
    with BytesIO() as image_buffer:
        Image.new("RGB", (1, 1), "red").save(image_buffer, format="PNG")
        image_bytes = image_buffer.getvalue()
    image_uri = "data:image/png;base64," + base64.b64encode(image_bytes).decode()
    original_history = [
        {
            "role": "user",
            "vendor_extension": {"unicode": "表情🙂", "escaped": 'a\\"b'},
            "content": [
                {"type": "text", "text": "先前说明"},
                {
                    "type": "image_url",
                    "image_url": {"url": image_uri, "detail": "high"},
                    "legacy_extension": [1, True, None],
                },
            ],
        },
        {"role": "assistant", "content": "已收到"},
    ]
    before = _seed_history(cli_root, original_history)
    guard_dir = _install_network_guard(tmp_path)
    common = ("--conversation", CONVERSATION_ID, "--stopped")

    preflight = _run_cli(cli_root, *common, guard_dir=guard_dir)
    assert preflight.returncode == 0, preflight.stderr
    prepared = json.loads(preflight.stdout)
    assert prepared["status"] == "prepared"
    assert prepared["model_calls"] == 0
    assert _history_bytes(cli_root) == before
    assert not list((cli_root / "data" / "image_assets").glob("*.img"))

    applied = _run_cli(cli_root, *common, "--apply", guard_dir=guard_dir)
    assert applied.returncode == 0, applied.stderr
    committed = json.loads(applied.stdout)
    assert committed["status"] == "committed"
    assert committed["model_calls"] == 0
    assert committed["image_count"] == 1
    with sqlite3.connect(cli_root / DB_RELATIVE) as connection:
        content = connection.execute(
            "SELECT content FROM conversations WHERE conversation_id=?",
            (CONVERSATION_ID,),
        ).fetchone()[0]
        assets = connection.execute("SELECT count(*) FROM image_assets").fetchone()[0]
        references = connection.execute(
            "SELECT count(*) FROM conversation_image_refs"
        ).fetchone()[0]
        tasks = connection.execute(
            "SELECT state FROM image_history_migration_tasks"
        ).fetchall()
    migrated = json.loads(content)
    assert migrated[0]["vendor_extension"] == original_history[0]["vendor_extension"]
    assert migrated[0]["content"][0] == original_history[0]["content"][0]
    assert migrated[0]["content"][1]["type"] == "image_ref"
    assert migrated[1] == original_history[1]
    assert (assets, references, tasks) == (1, 1, [("committed",)])

    resumed = _run_cli(cli_root, *common, "--apply", guard_dir=guard_dir)
    assert resumed.returncode == 0, resumed.stderr
    assert json.loads(resumed.stdout)["status"] == "already_committed"
    assert not (guard_dir / "attempts.txt").exists()
    assert len(list((cli_root / "data" / "image_assets").glob("*.img"))) == 1


def test_cli_failure_keeps_corrupt_legacy_source_and_hides_payload(
    cli_root: Path, tmp_path: Path
):
    secret = "SECRET_BASE64_PAYLOAD_SHOULD_NEVER_BE_ECHOED"
    bad_uri = "data:image/png;base64," + secret + "!"
    original = _seed_history(
        cli_root,
        [
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": bad_uri}}],
            }
        ],
    )
    guard_dir = _install_network_guard(tmp_path)

    result = _run_cli(
        cli_root,
        "--conversation",
        CONVERSATION_ID,
        "--stopped",
        "--apply",
        guard_dir=guard_dir,
    )

    assert result.returncode == 1
    assert secret not in result.stdout + result.stderr
    assert "Maintenance stopped" in result.stderr
    assert _history_bytes(cli_root) == original
    with sqlite3.connect(cli_root / DB_RELATIVE) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM conversation_image_refs"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute("SELECT count(*) FROM image_assets").fetchone()[0] == 0
        )
        assert connection.execute(
            "SELECT state FROM image_history_migration_tasks"
        ).fetchall() == [("prepared",)]
    assert not (guard_dir / "attempts.txt").exists()


def test_cli_output_over_limit_fails_closed_without_partial_history(
    cli_root: Path, tmp_path: Path
):
    # The input contains no images, so a safe rewrite would remain above 16 MiB.
    huge_unknown_value = "x" * (16 * 1024 * 1024)
    original = _seed_history(
        cli_root,
        [
            {
                "role": "user",
                "content": "short",
                "unknown_legacy_extension": huge_unknown_value,
            }
        ],
    )
    guard_dir = _install_network_guard(tmp_path)

    result = _run_cli(
        cli_root,
        "--conversation",
        CONVERSATION_ID,
        "--stopped",
        "--apply",
        guard_dir=guard_dir,
    )

    assert result.returncode == 1
    assert _history_bytes(cli_root) == original
    assert "16 MiB" in result.stderr
    assert "x" * 100 not in result.stderr
    assert not (guard_dir / "attempts.txt").exists()
    with sqlite3.connect(cli_root / DB_RELATIVE) as connection:
        assert (
            connection.execute("SELECT count(*) FROM image_assets").fetchone()[0] == 0
        )
        assert connection.execute(
            "SELECT state FROM image_history_migration_tasks"
        ).fetchall() == [("prepared",)]
