import time

_RUNTIME_LOG_SAVE_RESTART_SKIP_SECONDS = 8
_runtime_log_save_restart_skip_until = 0.0


def mark_runtime_log_config_saved() -> None:
    global _runtime_log_save_restart_skip_until
    _runtime_log_save_restart_skip_until = (
        time.monotonic() + _RUNTIME_LOG_SAVE_RESTART_SKIP_SECONDS
    )


def should_skip_restart_after_runtime_log_config_save() -> bool:
    return time.monotonic() < _runtime_log_save_restart_skip_until
