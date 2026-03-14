from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_NEW = REPO_ROOT / "src-new"

if str(SRC_NEW) not in sys.path:
    sys.path.insert(0, str(SRC_NEW))
