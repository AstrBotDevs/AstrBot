import os
import sys


def is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_packaged_electron_runtime() -> bool:
    return os.environ.get("ASTRBOT_ELECTRON_CLIENT") == "1"
