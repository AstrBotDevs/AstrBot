import os


def is_packaged_electron_runtime() -> bool:
    return os.environ.get("ASTRBOT_ELECTRON_CLIENT") == "1"
