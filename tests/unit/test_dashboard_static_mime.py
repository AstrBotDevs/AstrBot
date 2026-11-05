"""Tests for dashboard static file MIME types."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(os.name != "nt", reason="Windows registry MIME mappings.")
def test_dashboard_serves_js_as_javascript_when_registry_says_text_plain():
    """Keep .js as JavaScript when the Windows registry maps it to text/plain.

    Browsers refuse module scripts served as text/plain, which leaves the
    WebUI blank. A fresh interpreter reads the simulated registry before the
    dashboard server module is imported, as on a real startup.
    """
    code = (
        "import mimetypes\n"
        "def read_registry(self, strict=True):\n"
        "    self.add_type('text/plain', '.js', strict)\n"
        "mimetypes.MimeTypes.read_windows_registry = read_registry\n"
        "mimetypes.init()\n"
        "assert mimetypes.guess_type('index.js')[0] == 'text/plain'\n"
        "import astrbot.dashboard.server\n"
        "js_type = mimetypes.guess_type('index.js')[0]\n"
        "assert js_type == 'text/javascript', js_type\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
