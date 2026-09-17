"""Measure real image preparation and SDK requests in isolated processes."""

from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import tracemalloc
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psutil


def _base64_payload_metrics(encoded: str) -> tuple[int, str]:
    """Hash an encoded payload in chunks without retaining decoded image bytes.

    Args:
        encoded: Base64 payload without the data-URI prefix.

    Returns:
        The decoded byte count and SHA-256 digest.
    """
    digest = hashlib.sha256()
    decoded_bytes = 0
    remainder = ""
    chunk_size = 4 * 1024 * 1024
    for start in range(0, len(encoded), chunk_size):
        chunk = remainder + encoded[start : start + chunk_size]
        usable = len(chunk) - len(chunk) % 4
        if usable:
            decoded = base64.b64decode(chunk[:usable])
            digest.update(decoded)
            decoded_bytes += len(decoded)
        remainder = chunk[usable:]
    if remainder:
        decoded = base64.b64decode(remainder)
        digest.update(decoded)
        decoded_bytes += len(decoded)
    return decoded_bytes, digest.hexdigest()


async def run_child(args: argparse.Namespace) -> dict:
    """Execute production preparation and request assembly in the chosen checkout.

    Args:
        args: Explicit source, checkout, local server and diagnostic options.

    Returns:
        Sizes, phase durations and resource counters without image content.
    """
    sys.path.insert(0, str(args.repo.resolve()))
    from openai import AsyncOpenAI

    from astrbot.core.provider.entities import ProviderRequest

    if args.trace_python:
        tracemalloc.start()
    process = psutil.Process()
    baseline_rss = process.memory_info().rss
    phases: dict[str, float] = {}
    stage = "startup"
    phase_marks = [(time.monotonic(), stage)]
    failure: dict[str, str] | None = None
    source_bytes = args.image.stat().st_size
    source_digest = hashlib.sha256()
    with args.image.open("rb") as source_stream:
        for chunk in iter(lambda: source_stream.read(1024 * 1024), b""):
            source_digest.update(chunk)
    source_sha256 = source_digest.hexdigest()
    prepared_bytes: int | None = None
    prepared_sha256: str | None = None
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="astrbot-image-runtime-") as runtime:
        os.environ["ASTRBOT_ROOT"] = runtime
        before_files = set(Path(runtime).rglob("*"))
        try:
            stage = "provider_prepare_and_assemble"
            phase_marks.append((time.monotonic(), stage))
            tick = time.perf_counter()
            request = ProviderRequest(
                prompt="Describe this image.",
                image_urls=[str(args.image.resolve())],
            )
            context = await request.assemble_context()
            phases["provider_prepare_and_assemble_ms"] = (
                time.perf_counter() - tick
            ) * 1000
            image_part = next(
                part
                for part in context.get("content", [])
                if part.get("type") == "image_url"
            )
            data_url = image_part["image_url"]["url"]
            stage = "benchmark_payload_verification"
            phase_marks.append((time.monotonic(), stage))
            prepared_bytes, prepared_sha256 = _base64_payload_metrics(
                data_url.split(",", 1)[1]
            )
            stage = "sdk_send"
            phase_marks.append((time.monotonic(), stage))
            async with AsyncOpenAI(
                api_key="local-experiment-only",
                base_url=args.endpoint,
                max_retries=0,
            ) as client:
                for _ in range(args.warmup):
                    await client.chat.completions.create(
                        model="local", messages=[context]
                    )
                tick = time.perf_counter()
                for _ in range(args.repeat):
                    await client.chat.completions.create(
                        model="local", messages=[context]
                    )
            phases["sdk_send_ms"] = (time.perf_counter() - tick) * 1000
            del context, request
        except Exception as exc:
            failure = {"stage": stage, "error_type": type(exc).__name__}
        finally:
            residual = [
                path
                for path in Path(runtime).rglob("*")
                if path.is_file() and path not in before_files
            ]
            result = {
                "source_bytes": source_bytes,
                "prepared_bytes": prepared_bytes,
                "source_sha256": source_sha256,
                "prepared_sha256": prepared_sha256,
                "preserved_source_bytes": (
                    prepared_sha256 == source_sha256
                    if prepared_sha256 is not None
                    else None
                ),
                "base64_bytes": (
                    4 * ((prepared_bytes + 2) // 3)
                    if prepared_bytes is not None
                    else None
                ),
                "phase_ms": phases,
                "phase_marks": phase_marks,
                "last_stage": stage,
                "failure": failure,
                "baseline_rss": baseline_rss,
                "post_request_rss": process.memory_info().rss,
                "temporary_files_remaining": len(residual),
                "temporary_bytes_remaining": sum(
                    path.stat().st_size for path in residual
                ),
                "elapsed_ms": (time.perf_counter() - started) * 1000,
            }
        if args.trace_python:
            result["python_current_bytes"], result["python_peak_bytes"] = (
                tracemalloc.get_traced_memory()
            )
            tracemalloc.stop()
        if sys.platform != "win32":
            import resource

            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            result["os_peak_rss_bytes"] = (
                peak if sys.platform == "darwin" else peak * 1024
            )
        return result


def main() -> int:
    """Run an isolated request and record measurements or a bounded failure."""
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument("--trace-python", action="store_true")
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--endpoint")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=0)
    parser.add_argument("--csv")
    parser.add_argument("--workload", default="single-image")
    args = parser.parse_args()
    if args.child:
        try:
            result = asyncio.run(run_child(args))
            result["status"] = "error" if result.get("failure") else "ok"
        except Exception as error:
            result = {"status": "error", "error_type": type(error).__name__}
        args.output.write_text(json.dumps(result), encoding="utf-8")
        return 0 if result["status"] == "ok" else 1

    # The server measures actual SDK bytes without storing the request body.
    request_sizes = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            remaining = length
            while remaining:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
            request_sizes.append(length - remaining)
            body = b'{"id":"local","object":"chat.completion","created":0,"model":"local","choices":[{"index":0,"message":{"role":"assistant","content":"fixture response"},"finish_reason":"stop"}],"usage":{"prompt_tokens":100,"completion_tokens":2,"total_tokens":102}}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    limit = min(2 * 1024**3, psutil.virtual_memory().available // 4)
    started = time.monotonic()
    samples = []
    stop_reason = None
    try:
        with tempfile.TemporaryDirectory(prefix="astrbot-image-measure-") as run_dir:
            child_result = Path(run_dir) / "child.json"
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                str(args.image.resolve()),
                str(child_result),
                "--child",
                "--repo",
                str(args.repo.resolve()),
                "--endpoint",
                f"http://127.0.0.1:{server.server_port}/v1",
            ]
            if args.repeat != 1:
                command.extend(["--repeat", str(args.repeat)])
            if args.warmup:
                command.extend(["--warmup", str(args.warmup)])
            command.extend(["--workload", args.workload])
            if args.trace_python:
                command.append("--trace-python")
            env = os.environ.copy()
            env["ASTRBOT_ROOT"] = str(Path(run_dir) / "runtime")
            with (
                (Path(run_dir) / "stdout").open("wb") as out,
                (Path(run_dir) / "stderr").open("wb") as err,
            ):
                proc = subprocess.Popen(
                    command, cwd=args.repo, env=env, stdout=out, stderr=err
                )
                process = psutil.Process(proc.pid)
                try:
                    while proc.poll() is None:
                        try:
                            children = process.children(recursive=True)
                            rss = process.memory_info().rss
                            descendants_rss = sum(
                                p.memory_info().rss for p in children if p.is_running()
                            )
                            info = process.memory_info()
                            samples.append(
                                {
                                    "seconds": time.monotonic() - started,
                                    "rss": rss,
                                    "descendants_rss": descendants_rss,
                                    "private_bytes": getattr(info, "private", None),
                                }
                            )
                            if rss + descendants_rss > limit:
                                stop_reason = "memory_limit"
                            elif time.monotonic() - started > 120:
                                stop_reason = "timeout"
                            if stop_reason:
                                for child in children:
                                    child.kill()
                                proc.kill()
                                break
                        except psutil.NoSuchProcess:
                            break
                        time.sleep(0.01)
                finally:
                    if proc.poll() is None:
                        proc.kill()
                    proc.wait()
            result = (
                json.loads(child_result.read_text())
                if child_result.exists()
                else {"status": "error"}
            )
            phase_peaks = {}
            for sample in samples:
                phase = "process_startup"
                for timestamp, name in result.get("phase_marks", []):
                    if timestamp > started + sample["seconds"]:
                        break
                    phase = name
                sample["phase"] = phase
                phase_peaks[phase] = max(phase_peaks.get(phase, 0), sample["rss"])
            result.update(
                {
                    "status": stop_reason or result["status"],
                    "workload": args.workload,
                    "phase_rss_high_water_bytes": phase_peaks,
                    "returncode": proc.returncode,
                    "rss_high_water_bytes": max(
                        (s["rss"] for s in samples), default=None
                    ),
                    "private_high_water_bytes": max(
                        (
                            s["private_bytes"]
                            for s in samples
                            if s["private_bytes"] is not None
                        ),
                        default=None,
                    ),
                    "descendants_high_water_bytes": max(
                        (s["descendants_rss"] for s in samples), default=None
                    ),
                    "request_json_bytes": request_sizes,
                    "samples": samples,
                    "trace_python": args.trace_python,
                    "code_commit": subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=args.repo, text=True
                    ).strip(),
                    "working_tree_diff_sha256": hashlib.sha256(
                        subprocess.check_output(
                            ["git", "diff", "--binary"], cwd=args.repo
                        )
                    ).hexdigest(),
                    "benchmark_source_sha256": hashlib.sha256(
                        Path(__file__).read_bytes()
                    ).hexdigest(),
                    "monitor_sample_count": len(samples),
                }
            )
            with args.output.open("a", encoding="utf-8") as output:
                output.write(json.dumps(result) + "\n")
            if args.csv:
                fields = [
                    "status",
                    "workload",
                    "repeat",
                    "warmup",
                    "rss_high_water_bytes",
                    "private_high_water_bytes",
                    "post_request_rss",
                    "temporary_files_remaining",
                    "temporary_bytes_remaining",
                    "request_json_bytes",
                ]
                csv_path = Path(args.csv)
                write_header = not csv_path.exists()
                with csv_path.open("a", newline="", encoding="utf-8") as csv_file:
                    writer = csv.DictWriter(csv_file, fieldnames=fields)
                    if write_header:
                        writer.writeheader()
                    writer.writerow(
                        {
                            "status": result.get("status"),
                            "workload": args.workload,
                            "repeat": args.repeat,
                            "warmup": args.warmup,
                            "rss_high_water_bytes": result.get("rss_high_water_bytes"),
                            "private_high_water_bytes": result.get(
                                "private_high_water_bytes"
                            ),
                            "post_request_rss": result.get("post_request_rss"),
                            "temporary_files_remaining": result.get(
                                "temporary_files_remaining"
                            ),
                            "temporary_bytes_remaining": result.get(
                                "temporary_bytes_remaining"
                            ),
                            "request_json_bytes": json.dumps(
                                result.get("request_json_bytes", [])
                            ),
                        }
                    )
            print(json.dumps({k: v for k, v in result.items() if k != "samples"}))
            return 0 if result["status"] == "ok" else 1
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join()


if __name__ == "__main__":
    raise SystemExit(main())
