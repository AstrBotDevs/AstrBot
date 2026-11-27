from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tracemalloc
from pathlib import Path

import pytest

MODULE = (
    Path(__file__).resolve().parents[1]
    / "astrbot/core/astr_agent_runtime/computer/booters/_bounded_search.py"
)
SPEC = importlib.util.spec_from_file_location("bounded_search_fallback", MODULE)
assert SPEC is not None and SPEC.loader is not None
fallback = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fallback)


def test_fallback_global_groups_stop_before_later_files(tmp_path, capsys):
    (tmp_path / "matches.txt").write_text("needle\n" * 100, encoding="utf-8")
    (tmp_path / "irrelevant.txt").write_text("unused", encoding="utf-8")
    output = io.BytesIO()

    status = fallback.run_search(
        {"path": str(tmp_path), "pattern": ".", "max_results": 10}, output
    )

    assert status == 3
    assert len(output.getvalue().splitlines()) == 10
    assert json.loads(capsys.readouterr().err) == {"truncation_reason": "max_results"}


def test_fallback_context_keeps_last_group_complete(tmp_path, capsys):
    target = tmp_path / "context.txt"
    target.write_text(
        "before\nneedle\nafter\ngap\ngap\nneedle\nafter\n", encoding="utf-8"
    )
    output = io.BytesIO()

    status = fallback.run_search(
        {
            "path": str(target),
            "pattern": "needle",
            "before_context": 1,
            "after_context": 1,
            "max_results": 1,
        },
        output,
    )

    assert status == 3
    assert output.getvalue() == b"1-before\n2:needle\n3-after\n"
    assert json.loads(capsys.readouterr().err)["truncation_reason"] == "max_results"


def test_fallback_separated_context_groups_only_include_requested_context(tmp_path):
    target = tmp_path / "context.txt"
    target.write_text(
        "before\nneedle\nafter\ngap\ngap\nneedle\nafter\n", encoding="utf-8"
    )
    output = io.BytesIO()

    assert (
        fallback.run_search(
            {
                "path": str(target),
                "pattern": "needle",
                "before_context": 1,
                "after_context": 1,
                "max_results": 2,
            },
            output,
        )
        == 0
    )
    assert (
        output.getvalue()
        == b"1-before\n2:needle\n3-after\n--\n5-gap\n6:needle\n7-after\n"
    )


@pytest.mark.parametrize("pattern", ["needle$", "^a.*needle$", "needle"])
def test_fallback_large_line_matches_suffix_without_copying(tmp_path, pattern):
    target = tmp_path / "large.txt"
    target.write_bytes(b"a" * (5 * 1024 * 1024) + b"needle\n")
    output = io.BytesIO()
    tracemalloc.start()
    try:
        status = fallback.run_search({"path": str(target), "pattern": pattern}, output)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert status == 0
    assert output.getvalue() == b"1:" + b"a" * 998 + b"\n"
    assert peak < 1024 * 1024


def test_fallback_large_unicode_literal_matches_suffix(tmp_path):
    target = tmp_path / "unicode.txt"
    target.write_text("字" * 50_000 + "目标\n", encoding="utf-8")
    output = io.BytesIO()

    status = fallback.run_search({"path": str(target), "pattern": "目标"}, output)

    assert status == 0
    assert output.getvalue().decode() == "1:" + "字" * 998 + "\n"


def test_fallback_unicode_classes_and_casefold_for_ordinary_lines(tmp_path):
    target = tmp_path / "unicode.txt"
    target.write_text("中文\nÜBER\n", encoding="utf-8")
    output = io.BytesIO()

    status = fallback.run_search(
        {"path": str(target), "pattern": r"(?i)\b(?:中文|über)\b"}, output
    )

    assert status == 0
    assert output.getvalue().decode() == "1:中文\n2:ÜBER\n"


def test_fallback_byte_budget_and_huge_context_stay_bounded(tmp_path, capsys):
    target = tmp_path / "context.txt"
    target.write_text("context\n" * 100 + "needle\n", encoding="utf-8")
    output = io.BytesIO()

    status = fallback.run_search(
        {
            "path": str(target),
            "pattern": "needle",
            "before_context": 1_000_000,
            "max_output_bytes": 32,
        },
        output,
    )

    assert status == 3
    assert len(output.getvalue()) <= 32
    assert (
        json.loads(capsys.readouterr().err)["truncation_reason"] == "max_output_bytes"
    )


def test_fallback_glob_ignore_binary_and_hidden_files(tmp_path):
    (tmp_path / ".gitignore").write_text("ignored.py\nignored_dir/\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("needle", encoding="utf-8")
    (tmp_path / ".hidden.py").write_text("needle", encoding="utf-8")
    (tmp_path / "binary.py").write_bytes(b"needle\0")
    (tmp_path / "other.txt").write_text("needle", encoding="utf-8")
    (tmp_path / "kept.py").write_text("needle", encoding="utf-8")
    ignored_dir = tmp_path / "ignored_dir"
    ignored_dir.mkdir()
    (ignored_dir / "ignored.py").write_text("needle", encoding="utf-8")
    output = io.BytesIO()

    assert (
        fallback.run_search(
            {"path": str(tmp_path), "pattern": "needle", "glob": "*.py"}, output
        )
        == 0
    )
    # Explicit positive globs match hidden files, as with rg -g.
    lines = output.getvalue().decode().splitlines()
    assert len(lines) == 3
    assert any(".hidden.py:1:needle" in line for line in lines)
    assert any("kept.py:1:needle" in line for line in lines)
    assert any("ignored.py:1:needle" in line for line in lines)


def test_fallback_brace_glob_and_ordinary_ignore_rules(tmp_path):
    (tmp_path / ".gitignore").write_text("ignored.ts\n", encoding="utf-8")
    for name in ("ignored.ts", "kept.ts", "kept.tsx", "other.txt"):
        (tmp_path / name).write_text("needle\n", encoding="utf-8")
    output = io.BytesIO()
    assert (
        fallback.run_search({"path": str(tmp_path), "pattern": "needle"}, output) == 0
    )
    assert "ignored.ts" not in output.getvalue().decode()
    output = io.BytesIO()
    assert (
        fallback.run_search(
            {"path": str(tmp_path), "pattern": "needle", "glob": "*.{ts,tsx}"}, output
        )
        == 0
    )
    lines = output.getvalue().decode().splitlines()
    assert len(lines) == 3
    assert not any("other.txt" in line for line in lines)


def test_fallback_nested_ignore_rules_have_a_cumulative_memory_budget(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    directory = root
    # These individual ignore files fit the per-file budget, but retaining
    # duplicated inherited rule lists at every level used to grow quadratically.
    ignore_rules = "".join(
        f"nonexistent-{index:04d}-xxxxxxxx\n" for index in range(1000)
    )
    for _ in range(30):
        (directory / ".gitignore").write_text(ignore_rules, encoding="utf-8")
        directory = directory / "d"
        directory.mkdir()
    (directory / "found.txt").write_text("needle\n", encoding="utf-8")
    tracemalloc.start()
    try:
        with pytest.raises(ValueError, match="accumulated ignore rules"):
            fallback.run_search({"path": str(root), "pattern": "needle"}, io.BytesIO())
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak < 10 * 1024 * 1024


def test_fallback_sibling_directory_ignore_rules_do_not_leak(tmp_path):
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    (first / ".gitignore").write_text("*.txt\n", encoding="utf-8")
    (first / "hidden.txt").write_text("needle\n", encoding="utf-8")
    (second / "found.txt").write_text("needle\n", encoding="utf-8")
    output = io.BytesIO()

    assert (
        fallback.run_search({"path": str(tmp_path), "pattern": "needle"}, output) == 0
    )
    assert len(output.getvalue().splitlines()) == 1
    assert "found.txt" in output.getvalue().decode()


def test_fallback_binary_no_matches_and_invalid_patterns(tmp_path):
    target = tmp_path / "binary.txt"
    target.write_bytes(b"needle\0")
    output = io.BytesIO()
    assert fallback.run_search({"path": str(target), "pattern": "."}, output) == 1
    assert output.getvalue() == b""
    with pytest.raises(ValueError, match="unsupported fallback"):
        fallback.run_search({"path": str(target), "pattern": "["}, output)
    with pytest.raises(ValueError, match="Rust-specific"):
        fallback.run_search({"path": str(target), "pattern": r"\p{Han}"}, output)


def test_fallback_stops_before_binary_tail_outside_probe(tmp_path, capsys):
    target = tmp_path / "large.txt"
    target.write_bytes(b"needle\n" * 10_000 + b"\0binary tail")
    output = io.BytesIO()

    assert (
        fallback.run_search(
            {"path": str(target), "pattern": "needle", "max_results": 2}, output
        )
        == 3
    )
    assert output.getvalue() == b"1:needle\n2:needle\n"
    assert json.loads(capsys.readouterr().err)["truncation_reason"] == "max_results"


def test_fallback_deadline_is_checked_without_output(tmp_path, monkeypatch):
    target = tmp_path / "plain.txt"
    target.write_text("nothing", encoding="utf-8")
    times = iter((0, 10))
    monkeypatch.setattr(fallback.time, "monotonic", lambda: next(times))
    with pytest.raises(TimeoutError, match="File search timed out"):
        fallback.run_search(
            {"path": str(target), "pattern": "needle", "timeout": 0.000000001},
            io.BytesIO(),
        )


def test_fallback_source_runs_in_isolated_stdlib_process(tmp_path):
    target = tmp_path / "plain.txt"
    target.write_text("needle\nneedle\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            MODULE.read_text(encoding="utf-8"),
            json.dumps({"path": str(target), "pattern": "needle", "max_results": 1}),
        ],
        capture_output=True,
        timeout=10,
    )

    assert result.returncode == 3
    assert result.stdout == b"1:needle\n"
    assert json.loads(result.stderr)["truncation_reason"] == "max_results"
