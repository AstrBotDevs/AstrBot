from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_lifecycle_workload_defines_bounded_matrix_and_no_payload_dump():
    source = Path("scripts/image_memory_bench/lifecycle_workloads.py").read_text(
        encoding="utf-8"
    )
    assert "REQUESTS = 200" in source
    assert "SESSIONS = 4" in source
    assert "--request-count" in source
    assert "--window-turns" in source
    assert "time.sleep(0.01)" in source
    assert "120" in source
    assert "b64encode" not in source
    assert "print(" not in source


def test_lifecycle_child_requires_real_database_and_reports_wire_metadata(tmp_path):
    output = tmp_path / "result.jsonl"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/image_memory_bench/lifecycle_workloads.py",
            str(output),
            "--child",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not output.exists()
