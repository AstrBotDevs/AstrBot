from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import tracemalloc
from pathlib import Path

import pytest

from astrbot.core.astr_agent_runtime.computer.booters._search_stream import run_search


def search(code, **options):
    defaults = {
        "max_results": None,
        "max_output_bytes": 1024 * 1024,
        "timeout": 5,
        "has_context": False,
    }
    defaults.update(options)
    code = "import sys; sys.stdout.reconfigure(newline='\\n'); " + code
    return run_search([sys.executable, "-u", "-c", code], **defaults)


def test_search_stream_terminates_after_global_result_limit():
    result = search(
        "import sys,time; print('1:first\\n2:second\\n3:third',flush=True); time.sleep(10)",
        max_results=2,
    )

    assert result == {
        "success": True,
        "content": "1:first\n2:second\n",
        "truncated": True,
        "truncation_reason": "max_results",
    }


def test_search_stream_preserves_last_complete_context_group():
    result = search(
        "print('1:first\\n2-after\\n--\\n8:second\\n9-after\\n--\\n15:third')",
        max_results=2,
        has_context=True,
    )

    assert result["content"] == "1:first\n2-after\n--\n8:second\n9-after\n"
    assert result["truncation_reason"] == "max_results"


def test_search_stream_does_not_mark_exact_group_count_truncated():
    assert search("print('1:first\\n2:second')", max_results=2) == {
        "success": True,
        "content": "1:first\n2:second\n",
    }


def test_search_stream_drains_flooded_stderr_with_a_bound():
    result = search(
        "import sys; sys.stderr.write('e'*2000000); sys.stderr.flush(); print('1:needle')"
    )
    assert result == {"success": True, "content": "1:needle\n"}
    error = search("import sys; sys.stderr.write('e'*2000000); sys.exit(2)")
    assert error["success"] is False
    assert len(error["error"]) == 65536
    assert error["exit_code"] == 2


@pytest.mark.parametrize(
    "code",
    [
        "import time; time.sleep(10)",
        'import sys; exec("while True: sys.stdout.buffer.write(bytes([10])*4096); sys.stdout.flush()")',
    ],
)
def test_search_stream_wall_timeout_reaps_child_and_readers(code):
    started = time.monotonic()
    result = search(code, timeout=0.25)

    assert result["success"] is False
    assert result["error"] == "File search timed out after 0.25 seconds."
    assert time.monotonic() - started < 3
    assert not [
        thread
        for thread in threading.enumerate()
        if thread.name in ("search-stdout", "search-stderr")
    ]


def test_search_stream_discards_giant_line_without_large_python_allocation():
    tracemalloc.start()
    try:
        result = search("print('1:'+'x'*2000000)")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert result == {"success": True, "content": "1:" + "x" * 998 + "\n"}
    assert peak < 2 * 1024 * 1024


def test_search_stream_utf8_byte_bound_does_not_split_character():
    result = search(
        "import sys; sys.stdout.buffer.write(('1:'+chr(0x1f642)*1200+'\\n').encode())",
        max_output_bytes=19,
    )

    assert result["content"] == "1:" + "🙂" * 4
    assert len(result["content"].encode()) <= 19
    assert result["truncation_reason"] == "max_output_bytes"


def test_search_stream_exact_byte_count_is_not_marked_truncated():
    assert search("print('1:first')", max_output_bytes=8) == {
        "success": True,
        "content": "1:first\n",
    }


def test_search_stream_uses_native_decoder_and_preserves_line_ending():
    result = search(
        "import sys; sys.stdout.buffer.write(b'1:\\xd6\\xd0\\xce\\xc4\\r\\n')",
        decode=lambda value: value.decode("gbk"),
    )
    assert result == {"success": True, "content": "1:中文\r\n"}


def test_search_stream_long_utf8_prefix_is_complete_before_fallback_decode():
    def decode(value):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return "wrong encoding"

    result = search(
        "import sys; sys.stdout.buffer.write(('1:'+chr(0x1f642)*3000+'\\n').encode())",
        decode=decode,
    )
    assert result == {"success": True, "content": "1:" + "🙂" * 998 + "\n"}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signal escalation")
def test_search_stream_escalates_to_kill_after_ignored_sigterm():
    result = search(
        "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "print('1:first\\n2:second',flush=True); time.sleep(10)",
        max_results=1,
    )
    assert result["success"] is True
    assert result["content"] == "1:first\n"
    assert result["truncation_reason"] == "max_results"


@pytest.mark.parametrize("code", ["pass", "import sys; sys.exit(1)"])
def test_search_stream_handles_no_matches(code):
    assert search(code) == {"success": True, "content": ""}


def test_search_stream_standalone_sandbox_cli():
    module = (
        Path(__file__).parents[1]
        / "astrbot/core/astr_agent_runtime/computer/booters/_search_stream.py"
    )
    options = {
        "command": [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(b'1:one\\n2:two\\n')",
        ],
        "max_results": 1,
        "max_output_bytes": 1024,
        "timeout": 5,
        "has_context": False,
    }
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", module.read_text(), json.dumps(options)],
        capture_output=True,
        timeout=10,
    )

    assert result.returncode == 3
    assert result.stdout == b"1:one\n"
    assert json.loads(result.stderr) == {
        "truncated": True,
        "truncation_reason": "max_results",
    }


def test_search_stream_accepts_only_opted_in_helper_truncation():
    code = (
        "import sys; print('1:needle'); "
        'sys.stderr.write(\'{"truncation_reason":"max_results"}\'); sys.exit(3)'
    )
    assert search(code)["success"] is False
    result = search(code, allow_truncated_exit=True)
    assert result == {
        "success": True,
        "content": "1:needle\n",
        "truncated": True,
        "truncation_reason": "max_results",
    }
