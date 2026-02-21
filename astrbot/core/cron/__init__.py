"""Cron package exports.

Keep `CronJobManager` import-compatible while avoiding hard import failure when
`apscheduler` is partially mocked in test environments.
"""

try:
    from .manager import CronJobManager
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("apscheduler")):
        raise

    _IMPORT_ERROR = exc

    class CronJobManager:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise ModuleNotFoundError(
                "CronJobManager requires a complete `apscheduler` installation."
            ) from _IMPORT_ERROR


__all__ = ["CronJobManager"]
