"""Safety checks for the standalone image benchmark utilities."""

import json
import subprocess
import sys


def test_baseline_manifest_records_fixture_fingerprints(tmp_path):
    fixture = tmp_path / "fixtures" / "7"
    fixture.mkdir(parents=True)
    (fixture / "sample.png").write_bytes(b"fixture")
    output = tmp_path / "manifest.json"
    subprocess.run(
        [
            sys.executable,
            "scripts/image_memory_bench/baseline_manifest.py",
            str(output),
            "--fixtures",
            str(tmp_path / "fixtures"),
        ],
        check=True,
    )
    manifest = json.loads(output.read_text())
    assert manifest["fixtures"][0]["sha256"]


def test_migration_dry_run_and_rollback_keep_input(tmp_path):
    source = tmp_path / "history.jsonl"
    source.write_text(
        json.dumps({"history": [{"role": "user", "content": "hello"}]}) + "\n"
    )
    output = tmp_path / "migrated.jsonl"
    media = tmp_path / "media"
    command = [
        sys.executable,
        "scripts/image_memory_bench/migrate_history.py",
        str(source),
        str(output),
        "--media-dir",
        str(media),
    ]
    subprocess.run(command, check=True)
    assert not output.exists()
    subprocess.run(command + ["--apply"], check=True)
    rollback = tmp_path / "rollback.jsonl"
    subprocess.run(
        [
            sys.executable,
            "scripts/image_memory_bench/migrate_history.py",
            str(output),
            str(rollback),
            "--media-dir",
            str(media),
            "--rollback",
            "--apply",
        ],
        check=True,
    )
    assert output.read_bytes() == rollback.read_bytes()
