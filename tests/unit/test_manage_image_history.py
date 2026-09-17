from __future__ import annotations

import base64
import importlib.util
import json
import sqlite3
import subprocess
import sys

import pytest
from PIL import Image


def _image() -> bytes:
    import io

    output = io.BytesIO()
    Image.new("RGB", (3, 2), "red").save(output, "PNG")
    return output.getvalue()


def _db(path, content):
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE conversations (inner_conversation_id INTEGER PRIMARY KEY, conversation_id TEXT, content JSON)"
    )
    connection.execute(
        "INSERT INTO conversations VALUES (1, 'one', ?)", (json.dumps(content),)
    )
    connection.commit()
    connection.close()


def _run(db, media, *args):
    return subprocess.run(
        [
            sys.executable,
            "scripts/manage_image_history.py",
            str(db),
            "--media",
            str(media),
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_migration_defaults_to_dry_run(tmp_path):
    data = _image()
    history = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,"
                        + base64.b64encode(data).decode()
                    },
                }
            ],
        }
    ]
    db = tmp_path / "db.sqlite"
    media = tmp_path / "media"
    _db(db, history)
    result = _run(db, media)
    assert result.returncode == 0
    assert not media.exists()
    assert (
        json.loads(
            sqlite3.connect(db)
            .execute("SELECT content FROM conversations")
            .fetchone()[0]
        )
        == history
    )


def test_apply_creates_backup_and_references(tmp_path):
    data = _image()
    history = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,"
                        + base64.b64encode(data).decode(),
                        "id": "keep",
                    },
                }
            ],
        }
    ]
    db = tmp_path / "db.sqlite"
    media = tmp_path / "media"
    backup = tmp_path / "backup"
    _db(db, history)
    result = _run(db, media, "--apply", "--offline", "--backup", str(backup))
    assert result.returncode == 0, result.stderr
    content = json.loads(
        sqlite3.connect(db).execute("SELECT content FROM conversations").fetchone()[0]
    )
    ref = content[0]["content"][0]
    assert ref["type"] == "image_media_ref" and ref["image_id"] == "keep"
    assert (backup / "db.sqlite").exists() and (backup / "manifest.json").exists()


def test_apply_requires_offline_and_cleanup_dry_run_is_read_only(tmp_path):
    db = tmp_path / "db.sqlite"
    media = tmp_path / "media"
    _db(db, [])
    media.mkdir()
    (media / "dead.bin").write_bytes(b"x")
    result = _run(db, media, "--apply")
    assert result.returncode != 0
    result = _run(db, media, "--cleanup")
    assert result.returncode == 0
    assert (media / "dead.bin").exists()


def test_cleanup_aborts_on_malformed_history(tmp_path):
    db = tmp_path / "db.sqlite"
    media = tmp_path / "media"
    _db(db, {"not": "a history"})
    media.mkdir()
    (media / ("a" * 64 + ".bin")).write_bytes(b"orphan")
    result = _run(db, media, "--cleanup", "--apply", "--offline")
    assert result.returncode != 0
    assert (media / ("a" * 64 + ".bin")).exists()


def test_cleanup_preserves_references_nested_in_retained_messages(tmp_path):
    from astrbot.core.utils.image_media_store import ImageMediaStore

    media = tmp_path / "media"
    store = ImageMediaStore(media)
    ref = store.put(_image())
    db = tmp_path / "db.sqlite"
    _db(db, [{"role": "tool", "content": [{"resource": ref.model_dump()}]}])
    result = _run(db, media, "--cleanup", "--apply", "--offline")
    assert result.returncode == 0, result.stderr
    assert store.read(ref, {ref.media_id}) == _image()


def test_cleanup_keeps_shared_media_until_last_history_reference_is_removed(tmp_path):
    from astrbot.core.utils.image_media_store import ImageMediaStore

    media = tmp_path / "media"
    store = ImageMediaStore(media)
    ref = store.put(_image())
    first_history = [{"role": "user", "content": [ref.model_dump()]}]
    second_history = [{"role": "user", "content": [ref.model_dump()]}]
    db = tmp_path / "db.sqlite"
    _db(db, first_history)
    connection = sqlite3.connect(db)
    connection.execute(
        "INSERT INTO conversations VALUES (2, 'two', ?)",
        (json.dumps(second_history),),
    )
    connection.commit()
    connection.close()

    first_delete = _run(db, media, "--cleanup", "--apply", "--offline")
    assert first_delete.returncode == 0, first_delete.stderr
    assert (media / f"{ref.media_id}.bin").exists()

    connection = sqlite3.connect(db)
    connection.execute("DELETE FROM conversations WHERE inner_conversation_id=1")
    connection.commit()
    connection.close()
    second_delete = _run(db, media, "--cleanup", "--apply", "--offline")
    assert second_delete.returncode == 0, second_delete.stderr
    assert (media / f"{ref.media_id}.bin").exists()

    connection = sqlite3.connect(db)
    connection.execute("DELETE FROM conversations WHERE inner_conversation_id=2")
    connection.commit()
    connection.close()
    last_delete = _run(db, media, "--cleanup", "--apply", "--offline")
    assert last_delete.returncode == 0, last_delete.stderr
    assert not (media / f"{ref.media_id}.bin").exists()
    quarantine = media.parent / "media.quarantine"
    assert (quarantine / f"{ref.media_id}.bin").exists()


def test_cleanup_leaves_unpaired_and_symlink_objects(tmp_path):
    db = tmp_path / "db.sqlite"
    media = tmp_path / "media"
    _db(db, [])
    media.mkdir()
    media_id = "b" * 64
    (media / f"{media_id}.bin").write_bytes(b"bad")
    (media / f"{media_id}.json").write_text("{}")
    (media / ("c" * 64 + ".bin")).write_bytes(b"bad")
    result = _run(db, media, "--cleanup", "--apply", "--offline")
    assert result.returncode == 0
    assert (media / f"{media_id}.bin").exists()


def test_restore_refuses_newer_history_and_wal_is_not_left_stale(tmp_path):
    data = _image()
    history = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,"
                        + base64.b64encode(data).decode()
                    },
                }
            ],
        }
    ]
    db = tmp_path / "db.sqlite"
    media = tmp_path / "media"
    backup = tmp_path / "backup"
    _db(db, history)
    assert (
        _run(db, media, "--apply", "--offline", "--backup", str(backup)).returncode == 0
    )
    connection = sqlite3.connect(db)
    connection.execute("UPDATE conversations SET content='[]'")
    connection.execute("CREATE TABLE unrelated (value TEXT)")
    connection.execute("INSERT INTO unrelated VALUES ('changed')")
    connection.commit()
    connection.close()
    (db.with_name(db.name + "-wal")).write_bytes(b"stale")
    result = _run(db, media, "--restore", str(backup), "--offline")
    assert result.returncode != 0
    assert not (db.with_name(db.name + ".before-restore")).exists()


def test_restore_validates_backup_and_conflicting_media_before_database_write(tmp_path):
    db = tmp_path / "db.sqlite"
    media = tmp_path / "media"
    backup = tmp_path / "backup"
    _db(db, [])
    assert (
        _run(db, media, "--apply", "--offline", "--backup", str(backup)).returncode == 0
    )
    manifest = backup / "manifest.json"
    manifest.write_text(
        manifest.read_text().replace(
            '"database":', '"database": "tampered", "ignored":'
        )
    )
    before = db.read_bytes()
    result = _run(db, media, "--restore", str(backup), "--offline")
    assert result.returncode != 0
    assert db.read_bytes() == before


def test_successful_restore_preserves_inline_history_and_detail(tmp_path):
    data = _image()
    history = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,"
                        + base64.b64encode(data).decode(),
                        "detail": "high",
                    },
                }
            ],
        }
    ]
    db = tmp_path / "db.sqlite"
    media = tmp_path / "media"
    backup = tmp_path / "backup"
    _db(db, history)
    assert (
        _run(db, media, "--apply", "--offline", "--backup", str(backup)).returncode == 0
    )
    result = _run(db, media, "--restore", str(backup), "--offline")
    assert result.returncode == 0, result.stderr
    restored = json.loads(
        sqlite3.connect(db).execute("SELECT content FROM conversations").fetchone()[0]
    )
    assert restored == history


def test_backup_reads_consistent_open_wal_database(tmp_path):
    db = tmp_path / "db.sqlite"
    media = tmp_path / "media"
    backup = tmp_path / "backup"
    connection = sqlite3.connect(db)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        "CREATE TABLE conversations (inner_conversation_id INTEGER PRIMARY KEY, conversation_id TEXT, content JSON)"
    )
    connection.execute("INSERT INTO conversations VALUES (1, 'wal', '[]')")
    connection.commit()
    assert (db.with_name(db.name + "-wal")).exists()
    connection.close()
    result = _run(db, media, "--apply", "--offline", "--backup", str(backup))
    assert result.returncode == 0, result.stderr
    assert (
        sqlite3.connect(backup / "db.sqlite")
        .execute("SELECT conversation_id FROM conversations")
        .fetchone()[0]
        == "wal"
    )


def test_restore_replace_failure_leaves_database_and_cleans_stage(
    tmp_path, monkeypatch
):
    db = tmp_path / "db.sqlite"
    media = tmp_path / "media"
    backup = tmp_path / "backup"
    _db(db, [])
    from astrbot.core.utils.image_media_store import ImageMediaStore

    ImageMediaStore(media).put(_image(), detail="high")
    assert (
        _run(db, media, "--apply", "--offline", "--backup", str(backup)).returncode == 0
    )
    for path in media.iterdir():
        path.unlink()
    module_spec = importlib.util.spec_from_file_location(
        "manage_image_history", "scripts/manage_image_history.py"
    )
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)

    def fail_replace(self, target):
        raise OSError("injected replace failure")

    monkeypatch.setattr(module.Path, "replace", fail_replace)
    args = type(
        "Args",
        (),
        {
            "offline": True,
            "restore": str(backup),
            "database": str(db),
            "media": str(media),
        },
    )
    before = db.read_bytes()
    with pytest.raises(OSError, match="injected replace failure"):
        module._restore(args)
    assert db.read_bytes() == before
    assert not list(tmp_path.glob("astrbot-restore-media-*"))
