"""Bounded subprocess search capture, also runnable inside a process sandbox."""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable


def run_search(
    command: list[str],
    *,
    max_results: int | None,
    max_output_bytes: int,
    timeout: float,
    has_context: bool,
    decode: Callable[[bytes], str] | None = None,
    allow_truncated_exit: bool = False,
) -> dict:
    """Capture search output without buffering unbounded lines or streams.

    Args:
        command: Search executable and its arguments.
        max_results: Maximum lines or context groups, or no group limit.
        max_output_bytes: Maximum UTF-8 bytes returned in content.
        timeout: Wall clock timeout in seconds.
        has_context: Whether ``--`` separates result groups.
        decode: Optional decoder for native command output.
        allow_truncated_exit: Accept exit 3 and truncation JSON from a search helper.

    Returns:
        Search status and bounded content, with truncation metadata on early stop.
    """
    if max_results is not None and max_results < 1:
        return {
            "success": False,
            "content": "",
            "error": "max_results must be positive.",
        }
    if max_output_bytes < 1 or timeout <= 0:
        return {
            "success": False,
            "content": "",
            "error": "max_output_bytes and timeout must be positive.",
        }
    decode_output = decode or (lambda value: value.decode("utf-8", errors="replace"))
    deadline = time.monotonic() + timeout
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        return {"success": False, "content": "", "error": str(exc)}
    chunks: queue.Queue[bytes | None] = queue.Queue(maxsize=16)
    stop = threading.Event()
    stderr = bytearray()

    def read_stdout() -> None:
        try:
            while not stop.is_set():
                chunk = process.stdout.read1(4096)
                while not stop.is_set():
                    try:
                        chunks.put(chunk or None, timeout=0.05)
                        break
                    except queue.Full:
                        continue
                if not chunk:
                    break
        except (OSError, ValueError):
            pass

    def read_stderr() -> None:
        try:
            while chunk := process.stderr.read1(4096):
                stderr.extend(chunk[: max(0, 65536 - len(stderr))])
        except (OSError, ValueError):
            pass

    readers = [
        threading.Thread(target=read_stdout, name="search-stdout", daemon=True),
        threading.Thread(target=read_stderr, name="search-stderr", daemon=True),
    ]
    for reader in readers:
        reader.start()
    output = bytearray()
    output_bytes = 0
    groups = 0
    new_group = True
    separator = ""
    prefix = bytearray()
    clipped_line = False
    last_byte = b""
    reason = ""
    timed_out = False

    def consume_line(ending: str) -> None:
        nonlocal groups, new_group, separator, output_bytes, reason
        raw = bytes(prefix)
        if ending and last_byte == b"\r":
            ending = "\r\n"
            if raw.endswith(b"\r"):
                raw = raw[:-1]
        if clipped_line:
            # Avoid mistaking a UTF-8 prefix cut mid-character for a legacy
            # encoding when the caller supplies an encoding fallback decoder.
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                if exc.reason == "unexpected end of data":
                    raw = raw[: exc.start]
        line = decode_output(raw)[:1000]
        if not line.strip():
            return
        if has_context and line.strip() == "--":
            if groups:
                new_group = True
                separator = "--" + ending
            return
        if not has_context or new_group:
            if max_results is not None and groups >= max_results:
                reason = "max_results"
                return
            groups += 1
            new_group = False
        for text in (separator, line + ending):
            encoded = text.encode("utf-8")
            remaining = max_output_bytes - output_bytes
            if len(encoded) > remaining:
                retained = encoded[:remaining].decode("utf-8", errors="ignore").encode()
                output.extend(retained)
                output_bytes += len(retained)
                reason = "max_output_bytes"
                break
            output.extend(encoded)
            output_bytes += len(encoded)
        separator = ""

    try:
        finished = False
        while not reason and not finished:
            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0:
                timed_out = True
                break
            try:
                chunk = chunks.get(timeout=min(0.05, remaining_time))
            except queue.Empty:
                continue
            if chunk is None:
                if prefix or clipped_line:
                    consume_line("")
                finished = True
                break
            parts = chunk.split(b"\n")
            for index, part in enumerate(parts):
                if part:
                    last_byte = part[-1:]
                available = 4004 - len(prefix)
                prefix.extend(part[:available])
                clipped_line |= len(part) > available
                if index < len(parts) - 1:
                    consume_line("\n")
                    prefix.clear()
                    clipped_line = False
                    last_byte = b""
                    if reason:
                        break
            # Check the deadline even when stdout is continuously readable.
            if time.monotonic() >= deadline and not reason:
                timed_out = True
                break
        if not reason and not timed_out:
            try:
                process.wait(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True
    finally:
        stop.set()
        if process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for reader in readers:
            reader.join(timeout=1)
        process.stdout.close()
        process.stderr.close()
    if timed_out:
        return {
            "success": False,
            "content": "",
            "error": f"File search timed out after {timeout:g} seconds.",
        }
    content = output.decode("utf-8")
    if allow_truncated_exit and process.returncode == 3 and not reason:
        try:
            metadata = json.loads(stderr)
            if metadata.get("truncation_reason") in ("max_results", "max_output_bytes"):
                reason = metadata["truncation_reason"]
        except (ValueError, AttributeError):
            pass
    if reason:
        return {
            "success": True,
            "content": content,
            "truncated": True,
            "truncation_reason": reason,
        }
    if process.returncode in (0, 1):
        return {"success": True, "content": content if process.returncode == 0 else ""}
    return {
        "success": False,
        "content": "",
        "error": decode_output(bytes(stderr))
        or f"command exited with code {process.returncode}",
        "exit_code": process.returncode,
    }


if __name__ == "__main__":
    result = run_search(**json.loads(sys.argv[1]))
    sys.stdout.buffer.write(result["content"].encode("utf-8"))
    if not result["success"]:
        sys.stderr.write(result["error"])
        raise SystemExit(2)
    if result.get("truncated"):
        sys.stderr.write(
            json.dumps(
                {
                    "truncated": True,
                    "truncation_reason": result["truncation_reason"],
                }
            )
        )
        raise SystemExit(3)
    raise SystemExit(0 if result["content"] else 1)
