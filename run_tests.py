#!/usr/bin/env python
"""
Test runner script for astrbot-sdk.

Usage:
    python run_tests.py                    # Run all tests
    python run_tests.py -v                 # Verbose output
    python run_tests.py -k "test_peer"     # Run tests matching pattern
    python run_tests.py --cov              # Run with coverage
    python run_tests.py -m "not slow"      # Skip slow tests
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Run tests with pytest."""
    project_root = Path(__file__).parent
    tests_dir = project_root / "tests_v4"

    # Build pytest command
    cmd = [sys.executable, "-m", "pytest", str(tests_dir)]

    # Parse arguments
    args = sys.argv[1:]

    # Handle --cov flag
    if "--cov" in args:
        args.remove("--cov")
        cmd.extend([
            "--cov=src-new/astrbot_sdk",
            "--cov-report=term-missing",
            "--cov-report=html:.htmlcov",
        ])

    # Default flags if no specific args
    if not args:
        cmd.extend(["-v", "--tb=short"])

    cmd.extend(args)

    print(f"Running: {' '.join(cmd)}")
    print("-" * 60)

    result = subprocess.run(cmd, cwd=project_root)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
