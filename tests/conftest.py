from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

while str(SRC) in sys.path:
    sys.path.remove(str(SRC))

sys.path.insert(0, str(SRC))
