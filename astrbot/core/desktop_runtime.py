import os

DESKTOP_MANAGED_RESTART_MESSAGE = (
    "AstrBot Desktop manages this backend process. Please restart or update from "
    "the desktop app instead of the core WebUI."
)


def is_desktop_managed_backend() -> bool:
    return os.environ.get("ASTRBOT_DESKTOP_MANAGED") == "1"
