"""Comprehensive performance benchmark tests for AstrBot core modules.

This module provides performance benchmarks with scoring to track
performance regressions and improvements over time.
"""

import asyncio
import gc
import tracemalloc
from typing import Callable, Any
from dataclasses import dataclass

import pytest

from astrbot.core.star.filter.command import CommandFilter, GreedyStr


@dataclass
class BenchmarkResult:
    """Result of a benchmark test."""
    name: str
    operation_count: int
    total_time_ms: float
    avg_time_ms: float
    ops_per_second: float
    memory_delta_kb: float
    score: int  # 0-100, 100 is best

    def __str__(self) -> str:
        return (
            f"[{self.name}]\n"
            f"  Ops/sec: {self.ops_per_second:,.0f} | "
            f"Avg: {self.avg_time_ms:.4f}ms | "
            f"Memory: +{self.memory_delta_kb:.1f}KB | "
            f"Score: {self.score}/100"
        )


class PerformanceBenchmark:
    """Helper class to run benchmarks with memory tracking."""

    def __init__(self, name: str, operations: int = 1000):
        self.name = name
        self.operations = operations
        self.tracemalloc = tracemalloc

    def run(self, func: Callable, *args, **kwargs) -> BenchmarkResult:
        """Run a function multiple times and measure performance."""
        gc.collect()
        self.tracemalloc.start()
        snapshot_before = self.tracemalloc.take_snapshot()

        start = asyncio.get_event_loop().time()
        for _ in range(self.operations):
            func(*args, **kwargs)
        end = asyncio.get_event_loop().time()

        snapshot_after = self.tracemalloc.take_snapshot()
        self.tracemalloc.stop()

        total_time = (end - start) * 1000  # ms
        avg_time = total_time / self.operations
        ops_per_sec = self.operations / ((end - start) if (end - start) > 0 else 0.001)

        # Calculate memory delta
        top_stats = snapshot_after.compare_to(snapshot_before, 'lineno')
        memory_delta_kb = sum(stat.size_diff for stat in top_stats) / 1024

        # Calculate score (0-100)
        # Higher ops/sec = better, lower memory = better
        score = self._calculate_score(ops_per_sec, memory_delta_kb)

        return BenchmarkResult(
            name=self.name,
            operation_count=self.operations,
            total_time_ms=total_time,
            avg_time_ms=avg_time,
            ops_per_second=ops_per_sec,
            memory_delta_kb=memory_delta_kb,
            score=score,
        )

    def _calculate_score(self, ops_per_sec: float, memory_kb: float) -> int:
        """Calculate a score from 0-100 based on performance metrics."""
        # Score based on operations per second (log scale)
        # 10k ops/sec = 80 points, 100k = 95 points, 1M = 100 points
        if ops_per_sec >= 1_000_000:
            ops_score = 100
        elif ops_per_sec >= 100_000:
            ops_score = 95
        elif ops_per_sec >= 10_000:
            ops_score = 80
        elif ops_per_sec >= 1_000:
            ops_score = 60
        elif ops_per_sec >= 100:
            ops_score = 40
        else:
            ops_score = 20

        # Memory penalty (lower is better)
        # < 1KB per op = no penalty, > 100KB = max penalty
        memory_per_op = memory_kb / self.operations
        if memory_per_op < 0.001:
            mem_score = 0
        elif memory_per_op < 0.1:
            mem_score = 5
        elif memory_per_op < 1:
            mem_score = 10
        else:
            mem_score = min(15, int(memory_per_op / 10))

        return max(0, min(100, ops_score - mem_score))


class TestCommandFilterBenchmarks:
    """Performance benchmarks for CommandFilter operations."""

    def test_complete_command_names_performance(self):
        """Benchmark get_complete_command_names with caching."""
        bench = PerformanceBenchmark("CommandFilter.get_complete_command_names", operations=10000)

        # Setup: create 100 filters
        filters: list[CommandFilter] = []
        for i in range(100):
            cf = CommandFilter(command_name=f"test_cmd_{i}")
            cf.alias = {f"t{i}", f"alias{i}"}
            cf.parent_command_names = [f"parent{i}"]
            filters.append(cf)

        result = bench.run(lambda: [cf.get_complete_command_names() for cf in filters])

        print(f"\n{'='*60}")
        print(f"Benchmark: {result.name}")
        print(f"  Operations: {result.operation_count:,}")
        print(f"  Total time: {result.total_time_ms:.2f}ms")
        print(f"  Avg per call: {result.avg_time_ms:.6f}ms")
        print(f"  Ops/sec: {result.ops_per_second:,.0f}")
        print(f"  Memory delta: +{result.memory_delta_kb:.2f}KB")
        print(f"  SCORE: {result.score}/100")
        print(f"{'='*60}\n")

        assert result.score >= 60, f"Performance score {result.score} is below threshold 60"

    def test_validate_bool_params_performance(self):
        """Benchmark boolean parameter validation."""
        bench = PerformanceBenchmark("CommandFilter.validate_bool", operations=50000)

        cf = CommandFilter(command_name="test")
        cf.handler_params = {"enabled": bool}

        result = bench.run(
            lambda: cf.validate_and_convert_params(["true"], cf.handler_params)
        )

        print(f"\n{'='*60}")
        print(f"Benchmark: {result.name}")
        print(f"  Operations: {result.operation_count:,}")
        print(f"  Total time: {result.total_time_ms:.2f}ms")
        print(f"  Avg per call: {result.avg_time_ms:.6f}ms")
        print(f"  Ops/sec: {result.ops_per_second:,.0f}")
        print(f"  Memory delta: +{result.memory_delta_kb:.2f}KB")
        print(f"  SCORE: {result.score}/100")
        print(f"{'='*60}\n")

        assert result.score >= 70, f"Performance score {result.score} is below threshold 70"

    def test_validate_int_params_performance(self):
        """Benchmark integer parameter validation."""
        bench = PerformanceBenchmark("CommandFilter.validate_int", operations=50000)

        cf = CommandFilter(command_name="test")
        cf.handler_params = {"count": int}

        result = bench.run(
            lambda: cf.validate_and_convert_params(["42"], cf.handler_params)
        )

        print(f"\n{'='*60}")
        print(f"Benchmark: {result.name}")
        print(f"  Operations: {result.operation_count:,}")
        print(f"  Total time: {result.total_time_ms:.2f}ms")
        print(f"  Avg per call: {result.avg_time_ms:.6f}ms")
        print(f"  Ops/sec: {result.ops_per_second:,.0f}")
        print(f"  Memory delta: +{result.memory_delta_kb:.2f}KB")
        print(f"  SCORE: {result.score}/100")
        print(f"{'='*60}\n")

        assert result.score >= 70, f"Performance score {result.score} is below threshold 70"


class TestMemoryBenchmarks:
    """Memory usage benchmarks."""

    def test_filter_creation_memory(self):
        """Benchmark memory usage when creating many filters."""
        bench = PerformanceBenchmark("Filter creation (1000x)", operations=10)

        def create_filters():
            filters = []
            for i in range(1000):
                cf = CommandFilter(command_name=f"cmd_{i}")
                cf.alias = {f"a{i}", f"b{i}"}
                filters.append(cf)
            return filters

        result = bench.run(create_filters)

        print(f"\n{'='*60}")
        print(f"Benchmark: {result.name}")
        print(f"  Creating 1000 filters")
        print(f"  Total memory: +{result.memory_delta_kb:.2f}KB")
        print(f"  Per filter: {result.memory_delta_kb:.4f}KB")
        print(f"  SCORE: {result.score}/100")
        print(f"{'='*60}\n")

        # Each filter should use < 10KB of memory
        per_filter_kb = result.memory_delta_kb / 1000
        assert per_filter_kb < 10, f"Filter memory usage {per_filter_kb:.2f}KB is too high"

    def test_greedy_str_memory(self):
        """Benchmark GreedyStr memory usage."""
        bench = PerformanceBenchmark("GreedyStr creation", operations=10000)

        def create_greedy():
            return GreedyStr(" ".join([f"arg{i}" for i in range(100)]))

        result = bench.run(create_greedy)

        print(f"\n{'='*60}")
        print(f"Benchmark: {result.name}")
        print(f"  Operations: {result.operation_count:,}")
        print(f"  Memory delta: +{result.memory_delta_kb:.2f}KB")
        print(f"  Per operation: {result.memory_delta_kb / result.operation_count:.4f}KB")
        print(f"  SCORE: {result.score}/100")
        print(f"{'='*60}\n")

        assert result.score >= 50, f"Memory score {result.score} is below threshold 50"


class TestThroughputBenchmarks:
    """High-throughput benchmarks."""

    @pytest.mark.asyncio
    async def test_high_throughput_bool_validation(self):
        """Test boolean validation at high throughput."""
        bench = PerformanceBenchmark("High-throughput bool validation", operations=100000)

        cf = CommandFilter(command_name="test")
        cf.handler_params = {"enabled": bool}
        values = ["true", "false", "yes", "no", "1", "0"]

        def validate_many():
            for v in values:
                cf.validate_and_convert_params([v], cf.handler_params)

        # Run 100k validations across 6 values
        result = bench.run(validate_many)

        print(f"\n{'='*60}")
        print(f"Benchmark: {result.name}")
        print(f"  Total operations: {result.operation_count * 6:,}")
        print(f"  Effective ops/sec: {result.ops_per_second * 6:,.0f}")
        print(f"  Total time: {result.total_time_ms:.2f}ms")
        print(f"  SCORE: {result.score}/100")
        print(f"{'='*60}\n")

        # Should handle > 100k validations per second
        effective_ops = result.ops_per_second * 6
        assert effective_ops > 100_000, f"Throughput {effective_ops:,.0f} is too low"

    @pytest.mark.asyncio
    async def test_command_name_resolution_throughput(self):
        """Test command name resolution at high throughput."""
        bench = PerformanceBenchmark("Command name resolution", operations=50000)

        filters = []
        for i in range(50):
            cf = CommandFilter(command_name=f"cmd_{i}")
            cf.alias = {f"c{i}", f"d{i}"}
            filters.append(cf)

        def resolve_all():
            for cf in filters:
                cf.get_complete_command_names()

        result = bench.run(resolve_all)

        print(f"\n{'='*60}")
        print(f"Benchmark: {result.name}")
        print(f"  Operations: {result.operation_count:,}")
        print(f"  Ops/sec: {result.ops_per_second:,.0f}")
        print(f"  SCORE: {result.score}/100")
        print(f"{'='*60}\n")

        assert result.ops_per_second > 100_000, f"Throughput {result.ops_per_second:,.0f} is too low"


class TestScoringSummary:
    """Summary test that reports overall score."""

    @pytest.mark.asyncio
    async def test_overall_performance_score(self):
        """Calculate overall performance score across all benchmarks."""
        scores = []

        # Test 1: CommandFilter operations
        bench1 = PerformanceBenchmark("CommandFilter ops", operations=10000)
        filters = [CommandFilter(command_name=f"c{i}") for i in range(50)]
        result1 = bench1.run(lambda: [f.get_complete_command_names() for f in filters])
        scores.append(result1.score)

        # Test 2: Bool validation
        bench2 = PerformanceBenchmark("Bool validation", operations=50000)
        cf = CommandFilter(command_name="test")
        cf.handler_params = {"enabled": bool}
        result2 = bench2.run(lambda: cf.validate_and_convert_params(["true"], cf.handler_params))
        scores.append(result2.score)

        # Test 3: Int validation
        bench3 = PerformanceBenchmark("Int validation", operations=50000)
        cf2 = CommandFilter(command_name="test2")
        cf2.handler_params = {"count": int}
        result3 = bench3.run(lambda: cf2.validate_and_convert_params(["42"], cf2.handler_params))
        scores.append(result3.score)

        overall_score = sum(scores) // len(scores)

        print(f"\n{'='*60}")
        print(f"PERFORMANCE BENCHMARK SUMMARY")
        print(f"{'='*60}")
        print(f"  CommandFilter operations:  {scores[0]}/100")
        print(f"  Bool validation:         {scores[1]}/100")
        print(f"  Int validation:         {scores[2]}/100")
        print(f"  {'-'*40}")
        print(f"  OVERALL SCORE:          {overall_score}/100")
        print(f"{'='*60}\n")

        assert overall_score >= 60, f"Overall score {overall_score} is below threshold 60"
