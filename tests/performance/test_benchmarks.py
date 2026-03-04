"""Performance benchmark tests for core AstrBot execution paths.

Run with:
    uv run pytest tests/performance/test_benchmarks.py -q -s

Optional output:
    ASTRBOT_BENCHMARK_OUTPUT=/tmp/astrbot_benchmark.json
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import time
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Awaitable, Callable
from unittest.mock import MagicMock

import pytest
from aiohttp import web

from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.core.message.components import File, Image, Record
from astrbot.core.utils.io import download_file, file_to_base64


@dataclass(slots=True)
class BenchmarkResult:
    name: str
    iterations: int
    warmup: int
    min_ms: float
    max_ms: float
    mean_ms: float
    p50_ms: float
    p95_ms: float
    ops_per_sec: float


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * q
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return sorted_values[lower]
    weight = rank - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


async def run_async_benchmark(
    name: str,
    func: Callable[[], Awaitable[None]],
    *,
    iterations: int,
    warmup: int = 5,
) -> BenchmarkResult:
    for _ in range(warmup):
        await func()

    samples_ms: list[float] = []
    for _ in range(iterations):
        start_ns = time.perf_counter_ns()
        await func()
        elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        samples_ms.append(elapsed_ms)

    mean_ms = sum(samples_ms) / len(samples_ms)
    return BenchmarkResult(
        name=name,
        iterations=iterations,
        warmup=warmup,
        min_ms=min(samples_ms),
        max_ms=max(samples_ms),
        mean_ms=mean_ms,
        p50_ms=_percentile(samples_ms, 0.50),
        p95_ms=_percentile(samples_ms, 0.95),
        ops_per_sec=1000 / mean_ms if mean_ms > 0 else 0.0,
    )


def _print_report(results: list[BenchmarkResult]) -> None:
    print("\nAstrBot Benchmark Report")
    print("-" * 84)
    print(
        f"{'case':35} {'iters':>7} {'mean(ms)':>10} {'p50(ms)':>10} "
        f"{'p95(ms)':>10} {'ops/s':>10}"
    )
    print("-" * 84)
    for result in results:
        print(
            f"{result.name:35} {result.iterations:7d} "
            f"{result.mean_ms:10.4f} {result.p50_ms:10.4f} "
            f"{result.p95_ms:10.4f} {result.ops_per_sec:10.1f}"
        )


def _scaled_iterations(value: int) -> int:
    scale = int(os.environ.get("ASTRBOT_BENCHMARK_SCALE", "1"))
    return max(1, value * scale)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_core_performance_benchmarks(tmp_path: Path) -> None:
    """Measure representative performance paths across core modules."""
    data = os.urandom(256 * 1024)

    payload_path = tmp_path / "payload.bin"
    payload_path.write_bytes(data)

    image = Image.fromFileSystem(str(payload_path))
    record = Record.fromFileSystem(str(payload_path))
    file_component = File(name="payload.bin", file=str(payload_path))
    exists_path = tmp_path / "exists_target.txt"
    exists_path.write_text("ok", encoding="utf-8")

    attachments_dir = tmp_path / "attachments"
    attachments_dir.mkdir()
    attachments: list[dict[str, str]] = []
    attachments_with_missing: list[dict[str, str]] = []
    for i in range(64):
        file_path = attachments_dir / f"attachment_{i}.bin"
        file_path.write_bytes(data[:2048])
        attachments.append({"attachment_id": f"att_{i}", "path": str(file_path)})
        if i % 4 == 0:
            missing_path = attachments_dir / f"missing_{i}.bin"
            attachments_with_missing.append(
                {"attachment_id": f"att_missing_{i}", "path": str(missing_path)}
            )
        attachments_with_missing.append(
            {"attachment_id": f"att_existing_{i}", "path": str(file_path)}
        )

    exporter = AstrBotExporter(main_db=MagicMock())
    zip_path = tmp_path / "attachments_bench.zip"
    micro_batch = 32
    download_target = tmp_path / "download_target.bin"
    download_payload = os.urandom(512 * 1024)

    async def handle_download(_request):
        return web.Response(body=download_payload)

    app = web.Application()
    app.router.add_get("/download.bin", handle_download)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = site._server.sockets  # noqa: SLF001
    assert sockets
    port = sockets[0].getsockname()[1]
    download_url = f"http://127.0.0.1:{port}/download.bin"

    async def bench_file_to_base64() -> None:
        await file_to_base64(str(payload_path))

    async def bench_image_convert_to_base64() -> None:
        await image.convert_to_base64()

    async def bench_record_convert_to_base64() -> None:
        await record.convert_to_base64()

    async def bench_image_convert_to_file_path() -> None:
        for _ in range(micro_batch):
            await image.convert_to_file_path()

    async def bench_file_component_get_file() -> None:
        await file_component.get_file()

    async def bench_to_thread_exists() -> None:
        await asyncio.to_thread(Path.exists, exists_path)

    async def bench_export_attachments_existing() -> None:
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            await exporter._export_attachments(zf, attachments)
        zip_path.unlink(missing_ok=True)

    async def bench_export_attachments_with_missing() -> None:
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            await exporter._export_attachments(zf, attachments_with_missing)
        zip_path.unlink(missing_ok=True)

    async def bench_download_file_local_http() -> None:
        await download_file(download_url, str(download_target))
        download_target.unlink(missing_ok=True)

    try:
        results = [
            await run_async_benchmark(
                "utils.io.file_to_base64(256KB)",
                bench_file_to_base64,
                iterations=_scaled_iterations(120),
            ),
            await run_async_benchmark(
                "components.Image.convert_to_base64",
                bench_image_convert_to_base64,
                iterations=_scaled_iterations(120),
            ),
            await run_async_benchmark(
                "components.Record.convert_to_base64",
                bench_record_convert_to_base64,
                iterations=_scaled_iterations(120),
            ),
            await run_async_benchmark(
                f"components.Image.convert_to_file_path(x{micro_batch})",
                bench_image_convert_to_file_path,
                iterations=_scaled_iterations(140),
            ),
            await run_async_benchmark(
                "components.File.get_file(local)",
                bench_file_component_get_file,
                iterations=_scaled_iterations(140),
            ),
            await run_async_benchmark(
                "asyncio.to_thread(Path.exists)",
                bench_to_thread_exists,
                iterations=_scaled_iterations(240),
            ),
            await run_async_benchmark(
                "backup.exporter._export_attachments(existing)",
                bench_export_attachments_existing,
                iterations=_scaled_iterations(20),
                warmup=2,
            ),
            await run_async_benchmark(
                "backup.exporter._export_attachments(mixed)",
                bench_export_attachments_with_missing,
                iterations=_scaled_iterations(20),
                warmup=2,
            ),
            await run_async_benchmark(
                "utils.io.download_file(local_http_512KB)",
                bench_download_file_local_http,
                iterations=_scaled_iterations(12),
                warmup=2,
            ),
        ]
    finally:
        await runner.cleanup()

    _print_report(results)

    output_path = os.environ.get("ASTRBOT_BENCHMARK_OUTPUT")
    if output_path:
        Path(output_path).write_text(
            json.dumps([asdict(result) for result in results], indent=2),
            encoding="utf-8",
        )

    # Keep assertions broad: benchmarks are for measurement, not strict gating.
    assert len(results) == 9
    for result in results:
        assert result.iterations > 0
        assert result.mean_ms > 0
        assert result.max_ms >= result.min_ms
        assert result.p95_ms >= result.p50_ms
