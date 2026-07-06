import asyncio
import faulthandler
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

LAG_MONITOR_ENABLED_ENV = "ASTRBOT_EVENT_LOOP_LAG_MONITOR"
LAG_MONITOR_INTERVAL_ENV = "ASTRBOT_EVENT_LOOP_LAG_INTERVAL"
LAG_MONITOR_THRESHOLD_ENV = "ASTRBOT_EVENT_LOOP_LAG_THRESHOLD"
WATCHDOG_ENABLED_ENV = "ASTRBOT_EVENT_LOOP_WATCHDOG"
WATCHDOG_INTERVAL_ENV = "ASTRBOT_EVENT_LOOP_WATCHDOG_INTERVAL"
WATCHDOG_TIMEOUT_ENV = "ASTRBOT_EVENT_LOOP_WATCHDOG_TIMEOUT"
WATCHDOG_LOG_PATH_ENV = "ASTRBOT_EVENT_LOOP_WATCHDOG_LOG_PATH"
WATCHDOG_LOG_MAX_BYTES_ENV = "ASTRBOT_EVENT_LOOP_WATCHDOG_LOG_MAX_BYTES"

DEFAULT_LAG_MONITOR_INTERVAL = 1.0
DEFAULT_LAG_MONITOR_THRESHOLD = 5.0
DEFAULT_WATCHDOG_INTERVAL = 1.0
DEFAULT_WATCHDOG_TIMEOUT = 15.0
DEFAULT_WATCHDOG_LOG_RELATIVE_PATH = Path("logs") / "event_loop_watchdog.log"
DEFAULT_WATCHDOG_LOG_MAX_BYTES = 1024 * 1024


@dataclass(frozen=True)
class EventLoopDiagnosticSettings:
    """Settings for event loop lag and blockage diagnostics.

    Args:
        lag_monitor_enabled: Whether to log event loop scheduling lag.
        lag_monitor_interval: Seconds between lag monitor wakeups.
        lag_monitor_threshold: Minimum lag seconds before logging a warning.
        watchdog_enabled: Whether to arm the faulthandler watchdog.
        watchdog_interval: Seconds between faulthandler watchdog refreshes.
        watchdog_timeout: Seconds without event loop progress before dumping stacks.
        watchdog_log_path: File that receives faulthandler watchdog output.
        watchdog_log_max_bytes: Maximum watchdog log bytes before rotation.
    """

    lag_monitor_enabled: bool
    lag_monitor_interval: float
    lag_monitor_threshold: float
    watchdog_enabled: bool
    watchdog_interval: float
    watchdog_timeout: float
    watchdog_log_path: Path
    watchdog_log_max_bytes: int


def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean flag from the environment.

    Args:
        name: Environment variable name.
        default: Value to use when the variable is unset or empty.

    Returns:
        Parsed boolean value.
    """
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, minimum: float) -> float:
    """Read a bounded float from the environment.

    Args:
        name: Environment variable name.
        default: Value to use when parsing fails or the value is too small.
        minimum: Smallest accepted value.

    Returns:
        Parsed float value or the default.
    """
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        parsed = float(value)
    except ValueError:
        logger.warning(
            "Invalid %s=%r, fallback to %.3fs.",
            name,
            value,
            default,
        )
        return default
    if parsed < minimum:
        logger.warning(
            "Invalid %s=%r, expected at least %.3fs; fallback to %.3fs.",
            name,
            value,
            minimum,
            default,
        )
        return default
    return parsed


def _env_int(name: str, default: int, minimum: int) -> int:
    """Read a bounded integer from the environment.

    Args:
        name: Environment variable name.
        default: Value to use when parsing fails or the value is too small.
        minimum: Smallest accepted value.

    Returns:
        Parsed integer value or the default.
    """
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        parsed = int(value)
    except ValueError:
        logger.warning(
            "Invalid %s=%r, fallback to %d.",
            name,
            value,
            default,
        )
        return default
    if parsed < minimum:
        logger.warning(
            "Invalid %s=%r, expected at least %d; fallback to %d.",
            name,
            value,
            minimum,
            default,
        )
        return default
    return parsed


def _watchdog_log_path() -> Path:
    """Resolve the watchdog stack dump log path.

    Returns:
        Absolute path for watchdog stack dump output.
    """
    configured = os.environ.get(WATCHDOG_LOG_PATH_ENV, "").strip()
    path = (
        Path(configured).expanduser()
        if configured
        else DEFAULT_WATCHDOG_LOG_RELATIVE_PATH
    )
    if not path.is_absolute():
        path = Path(get_astrbot_data_path()) / path
    return path


def load_event_loop_diagnostic_settings() -> EventLoopDiagnosticSettings:
    """Load event loop diagnostic settings from environment variables.

    Returns:
        Event loop diagnostic settings.
    """
    return EventLoopDiagnosticSettings(
        lag_monitor_enabled=_env_flag(LAG_MONITOR_ENABLED_ENV, True),
        lag_monitor_interval=_env_float(
            LAG_MONITOR_INTERVAL_ENV,
            DEFAULT_LAG_MONITOR_INTERVAL,
            0.1,
        ),
        lag_monitor_threshold=_env_float(
            LAG_MONITOR_THRESHOLD_ENV,
            DEFAULT_LAG_MONITOR_THRESHOLD,
            0.1,
        ),
        watchdog_enabled=_env_flag(WATCHDOG_ENABLED_ENV, False),
        watchdog_interval=_env_float(
            WATCHDOG_INTERVAL_ENV,
            DEFAULT_WATCHDOG_INTERVAL,
            0.1,
        ),
        watchdog_timeout=_env_float(
            WATCHDOG_TIMEOUT_ENV,
            DEFAULT_WATCHDOG_TIMEOUT,
            1.0,
        ),
        watchdog_log_path=_watchdog_log_path(),
        watchdog_log_max_bytes=_env_int(
            WATCHDOG_LOG_MAX_BYTES_ENV,
            DEFAULT_WATCHDOG_LOG_MAX_BYTES,
            1024,
        ),
    )


async def monitor_event_loop_lag(
    *,
    interval: float = DEFAULT_LAG_MONITOR_INTERVAL,
    warn_after: float = DEFAULT_LAG_MONITOR_THRESHOLD,
) -> None:
    """Log a warning when the event loop wakes significantly later than expected.

    Args:
        interval: Seconds between monitor wakeups.
        warn_after: Minimum lag seconds before logging a warning.
    """
    loop = asyncio.get_running_loop()
    expected = loop.time() + interval
    while True:
        await asyncio.sleep(interval)
        now = loop.time()
        lag = now - expected
        if lag > warn_after:
            logger.warning(
                "Event loop lag detected: %.3fs (threshold %.3fs).",
                lag,
                warn_after,
            )
        expected = now + interval


def _rotate_watchdog_log_file(log_path: Path, max_bytes: int) -> None:
    """Rotate the watchdog log when it reaches the configured size limit.

    Args:
        log_path: Current watchdog log path.
        max_bytes: Maximum current log size before rotation.
    """
    try:
        if not log_path.exists() or log_path.stat().st_size < max_bytes:
            return
        rotated_path = log_path.with_name(f"{log_path.name}.1")
        if rotated_path.exists():
            rotated_path.unlink()
        log_path.replace(rotated_path)
    except OSError as e:
        logger.warning("Failed to rotate event loop watchdog log %s: %s", log_path, e)


def _open_watchdog_log_file(log_path: Path, max_bytes: int) -> TextIO:
    """Open the watchdog log file after applying size-based rotation.

    Args:
        log_path: Current watchdog log path.
        max_bytes: Maximum current log size before rotation.

    Returns:
        Writable text file object for faulthandler output.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_watchdog_log_file(log_path, max_bytes)
    return log_path.open("a", encoding="utf-8")


async def faulthandler_event_loop_watchdog(
    *,
    timeout: float = DEFAULT_WATCHDOG_TIMEOUT,
    interval: float = DEFAULT_WATCHDOG_INTERVAL,
    dump_file: TextIO | None = None,
    dump_path: Path | None = None,
    max_bytes: int = DEFAULT_WATCHDOG_LOG_MAX_BYTES,
) -> None:
    """Dump all thread stacks if the event loop is blocked for too long.

    Args:
        timeout: Seconds without watchdog refresh before faulthandler dumps stacks.
        interval: Seconds between watchdog refreshes while the event loop is healthy.
        dump_file: File object that receives faulthandler output.
        dump_path: Path that receives faulthandler output when dump_file is unset.
        max_bytes: Maximum current log size before rotation.
    """
    log_path = dump_path or _watchdog_log_path()
    try:
        while True:
            faulthandler.cancel_dump_traceback_later()
            output = dump_file or _open_watchdog_log_file(log_path, max_bytes)
            should_close = dump_file is None
            try:
                faulthandler.dump_traceback_later(
                    timeout,
                    repeat=False,
                    file=output,
                )
                await asyncio.sleep(interval)
            finally:
                faulthandler.cancel_dump_traceback_later()
                if should_close:
                    output.close()
    finally:
        faulthandler.cancel_dump_traceback_later()


def create_event_loop_diagnostic_tasks() -> list[asyncio.Task]:
    """Create enabled event loop diagnostic tasks for the current loop.

    Returns:
        A list of created asyncio tasks.
    """
    settings = load_event_loop_diagnostic_settings()
    tasks: list[asyncio.Task] = []

    if settings.lag_monitor_enabled:
        tasks.append(
            asyncio.create_task(
                monitor_event_loop_lag(
                    interval=settings.lag_monitor_interval,
                    warn_after=settings.lag_monitor_threshold,
                ),
                name="event_loop_lag_monitor",
            )
        )

    if settings.watchdog_enabled:
        logger.warning(
            "Event loop faulthandler watchdog enabled: timeout=%.3fs interval=%.3fs. "
            "If the loop is blocked, Python thread stacks will be written to %s "
            "(rotates at %d bytes).",
            settings.watchdog_timeout,
            settings.watchdog_interval,
            settings.watchdog_log_path,
            settings.watchdog_log_max_bytes,
        )
        tasks.append(
            asyncio.create_task(
                faulthandler_event_loop_watchdog(
                    timeout=settings.watchdog_timeout,
                    interval=settings.watchdog_interval,
                    dump_path=settings.watchdog_log_path,
                    max_bytes=settings.watchdog_log_max_bytes,
                ),
                name="event_loop_faulthandler_watchdog",
            )
        )

    return tasks
