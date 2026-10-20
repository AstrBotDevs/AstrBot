import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path


def parse_size_to_bytes(value: str | int | float | None) -> int:
    """Parse size in MB to bytes."""
    if value is None:
        return 0

    try:
        size_mb = float(str(value).strip())
    except (TypeError, ValueError):
        return 0

    if size_mb <= 0:
        return 0

    return int(size_mb * 1024**2)


@dataclass
class TempFileInfo:
    path: Path
    size: int
    mtime: float


class TempDirCleaner:
    CONFIG_KEY = "temp_dir_max_size"
    DEFAULT_MAX_SIZE = 1024
    CHECK_INTERVAL_SECONDS = 10 * 60
    CLEANUP_RATIO = 0.30

    def __init__(
        self,
        max_size_getter: Callable[[], str | int | float | None],
        temp_dir: Path | None = None,
    ) -> None:
        self._max_size_getter = max_size_getter
        self._temp_dir = temp_dir or Path(get_astrbot_temp_path())
        self._stop_event = asyncio.Event()

    def _limit_bytes(self) -> int:
        configured = self._max_size_getter()
        parsed = parse_size_to_bytes(configured)
        if parsed <= 0:
            fallback = parse_size_to_bytes(self.DEFAULT_MAX_SIZE)
            logger.warning(
                f"Invalid {self.CONFIG_KEY}={configured!r}, fallback to {self.DEFAULT_MAX_SIZE}MB.",
            )
            return fallback
        return parsed

    def _scan_temp_files(self) -> tuple[int, list[TempFileInfo]]:
        if not self._temp_dir.exists():
            return 0, []

        total_size = 0
        files: list[TempFileInfo] = []
        for path in self._temp_dir.rglob("*"):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except OSError as e:
                logger.debug(f"Skip temp file {path} due to stat error: {e}")
                continue
            total_size += stat.st_size
            files.append(
                TempFileInfo(path=path, size=stat.st_size, mtime=stat.st_mtime)
            )

        return total_size, files

    def _cleanup_empty_dirs(self) -> None:
        if not self._temp_dir.exists():
            return
        for path in sorted(
            self._temp_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True
        ):
            if not path.is_dir():
                continue
            try:
                path.rmdir()
            except OSError:
                continue

    def cleanup_once(self) -> None:
        limit = self._limit_bytes()
        if limit <= 0:
            return

        total_size, files = self._scan_temp_files()
        if total_size <= limit:
            return

        target_release = max(int(total_size * self.CLEANUP_RATIO), 1)
        released = 0
        removed_files = 0

        for file_info in sorted(files, key=lambda item: item.mtime):
            try:
                file_info.path.unlink()
            except OSError as e:
                logger.warning(f"Failed to delete temp file {file_info.path}: {e}")
                continue

            released += file_info.size
            removed_files += 1
            if released >= target_release:
                break

        self._cleanup_empty_dirs()

        logger.warning(
            f"Temp dir exceeded limit ({total_size} > {limit}). "
            f"Removed {removed_files} files, released {released} bytes "
            f"(target {target_release} bytes).",
        )

    async def run(self) -> None:
        logger.info(
            f"TempDirCleaner started. interval={self.CHECK_INTERVAL_SECONDS}s "
            f"cleanup_ratio={self.CLEANUP_RATIO}",
        )
        while not self._stop_event.is_set():
            try:
                # File-system traversal and deletion are blocking operations.
                # Run cleanup in a worker thread to avoid blocking the event loop.
                await asyncio.to_thread(self.cleanup_once)
            except Exception as e:
                logger.error(f"TempDirCleaner run failed: {e}", exc_info=True)

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.CHECK_INTERVAL_SECONDS,
                )
            except asyncio.TimeoutError:
                continue

        logger.info("TempDirCleaner stopped.")

    async def stop(self) -> None:
        self._stop_event.set()
