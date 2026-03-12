from __future__ import annotations

import subprocess
import sys
import unittest

import pytest


def _is_astrbot_sdk_installed_in_site_packages() -> bool:
    """Check if astrbot_sdk is installed via pip (not just in PYTHONPATH)."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import astrbot_sdk; print(astrbot_sdk.__file__)"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return False
        # Check if installed in site-packages, not just in local path
        location = result.stdout.strip()
        return "site-packages" in location or "dist-packages" in location
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.skipif(
    not _is_astrbot_sdk_installed_in_site_packages(),
    reason="astrbot_sdk not installed in site-packages (run: pip install -e .)",
)
class EntryPointTest(unittest.TestCase):
    def test_import_package(self) -> None:
        process = subprocess.run(
            [sys.executable, "-c", "import astrbot_sdk; print(astrbot_sdk.__name__)"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("astrbot_sdk", process.stdout)

    def test_module_help(self) -> None:
        process = subprocess.run(
            [sys.executable, "-m", "astrbot_sdk", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("Usage", process.stdout)

    def test_run_help(self) -> None:
        process = subprocess.run(
            [sys.executable, "-m", "astrbot_sdk", "run", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("--plugins-dir", process.stdout)
