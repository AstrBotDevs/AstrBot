import os
import sys


def is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_packaged_desktop_runtime() -> bool:
    return is_frozen_runtime() and os.environ.get("ASTRBOT_DESKTOP_CLIENT") == "1"
