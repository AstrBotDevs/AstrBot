from __future__ import annotations

import subprocess
import sys
import unittest


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
