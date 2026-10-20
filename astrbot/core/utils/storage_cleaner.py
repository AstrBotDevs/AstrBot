from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_temp_path


@dataclass(frozen=True)
class LogFileConfig:
    path: Path
    enabled: bool


class StorageCleaner:
    TARGET_LOGS = "logs"
    TARGET_CACHE = "cache"
    TARGET_TRACES = "traces"
    VALID_TARGETS = {TARGET_LOGS, TARGET_CACHE, TARGET_TRACES, "all"}

    def __init__(
        self,
        config: Mapping[str, object],
        *,
        data_dir: Path | None = None,
        temp_dir: Path | None = None,
    ) -> None:
        self._config = config
        self._data_dir = data_dir or Path(get_astrbot_data_path())
        self._temp_dir = temp_dir or Path(get_astrbot_temp_path())

    def get_status(self) -> dict:
        logs = self._build_status(self.TARGET_LOGS)
        cache = self._build_status(self.TARGET_CACHE)
        traces = self._build_status(self.TARGET_TRACES)
        return {
            self.TARGET_LOGS: logs,
            self.TARGET_CACHE: cache,
            self.TARGET_TRACES: traces,
            "total_bytes": logs["size_bytes"]
            + cache["size_bytes"]
            + traces["size_bytes"],
        }

    def cleanup(self, target: str = "all") -> dict:
        normalized_target = (target or "all").strip().lower()
        if normalized_target not in self.VALID_TARGETS:
            raise ValueError(f"Unsupported cleanup target: {target}")

        targets = (
            [self.TARGET_TRACES, self.TARGET_LOGS, self.TARGET_CACHE]
            if normalized_target == "all"
            else [normalized_target]
        )
        results: dict[str, dict] = {}
        aggregates = {
            "removed_bytes": 0,
            "processed_files": 0,
            "deleted_files": 0,
            "truncated_files": 0,
            "failed_files": 0,
            "removed_traces": 0,
        }

        for target_name in targets:
            result = self._cleanup_target(target_name)
            results[target_name] = result
            for key in aggregates:
                aggregates[key] += result[key]

        status = self.get_status()

        return {
            "target": normalized_target,
            "results": results,
            **aggregates,
            "status": status,
        }

    def _build_status(self, target: str) -> dict:
        if target == self.TARGET_LOGS:
            files = self.collect_log_files()
            primary_path = self._data_dir / "logs"
        elif target == self.TARGET_CACHE:
            files = self._collect_cache_files()
            primary_path = self._temp_dir
        elif target == self.TARGET_TRACES:
            primary_path = self._resolve_log_path(
                self._get_optional_str("trace_db_path"),
                default_relative_path="logs/traces.db",
            )
            files = {
                Path(str(primary_path) + suffix)
                for suffix in ("", "-wal", "-shm", "-journal")
            }
        else:
            raise ValueError(f"Unsupported cleanup target: {target}")

        size_bytes, file_count = self._summarize_files(files)
        return {
            "size_bytes": size_bytes,
            "file_count": file_count,
            "path": str(primary_path),
            "exists": primary_path.exists(),
        }

    def _cleanup_target(self, target: str) -> dict:
        if target == self.TARGET_TRACES:
            from astrbot.core.utils.trace_store import get_trace_store

            before = self._build_status(target)
            removed_traces = 0
            if before["size_bytes"]:
                store = get_trace_store(self._config)
                if store.path.resolve() != Path(before["path"]).resolve():
                    raise ValueError(
                        "Restart AstrBot after changing the trace database path before cleaning history."
                    )
                removed_traces = store.clear_history()["removed_traces"]
            after = self._build_status(target)
            return {
                "removed_bytes": max(0, before["size_bytes"] - after["size_bytes"]),
                "removed_traces": removed_traces,
                "processed_files": 0,
                "deleted_files": 0,
                "truncated_files": 0,
                "failed_files": 0,
            }
        if target == self.TARGET_LOGS:
            files = self.collect_log_files()
            active_log_files = self._active_log_files()
        elif target == self.TARGET_CACHE:
            files = self._collect_cache_files()
            active_log_files = set()
        else:
            raise ValueError(f"Unsupported cleanup target: {target}")

        removed_bytes = 0
        deleted_files = 0
        truncated_files = 0
        failed_files = 0

        for file_path in sorted(files):
            if not file_path.exists():
                continue

            try:
                size = file_path.stat().st_size
            except OSError as exc:
                logger.warning("Failed to stat %s before cleanup: %s", file_path, exc)
                failed_files += 1
                continue

            try:
                if file_path in active_log_files:
                    file_path.write_bytes(b"")
                    truncated_files += 1
                else:
                    file_path.unlink()
                    deleted_files += 1
                removed_bytes += size
            except OSError as exc:
                logger.warning("Failed to clean %s: %s", file_path, exc)
                failed_files += 1

        if target == self.TARGET_CACHE:
            self._cleanup_empty_dirs(self._temp_dir)
            self._temp_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Storage cleanup finished: target=%s removed_bytes=%s deleted_files=%s truncated_files=%s failed_files=%s",
            target,
            removed_bytes,
            deleted_files,
            truncated_files,
            failed_files,
        )

        return {
            "removed_bytes": removed_bytes,
            "removed_traces": 0,
            "processed_files": deleted_files + truncated_files,
            "deleted_files": deleted_files,
            "truncated_files": truncated_files,
            "failed_files": failed_files,
        }

    def collect_log_files(self) -> set[Path]:
        """Collect files under data/logs plus the configured log files.

        Returns:
            The log files, including rotated ones of the configured log and
            trace log paths, even when those are outside data/logs.
        """
        files = set(self._iter_files(self._data_dir / "logs"))
        for log_path in self._configured_log_paths():
            files.update(self._iter_log_family_files(log_path))
        trace_path = self._resolve_log_path(
            self._get_optional_str("trace_db_path"),
            default_relative_path="logs/traces.db",
        ).resolve()
        protected = {
            Path(str(trace_path) + suffix)
            for suffix in ("", "-wal", "-shm", "-journal")
        }
        candidates = set()
        for path in files:
            if (
                path.resolve() in protected
                or path.suffix in {".db", ".sqlite", ".sqlite3"}
                or path.name.endswith(("-wal", "-shm", "-journal"))
            ):
                continue
            try:
                # Protect custom database names, including an old active path
                # after a configuration edit that has not restarted the core.
                with path.open("rb") as stream:
                    if stream.read(16) == b"SQLite format 3\x00":
                        continue
            except OSError:
                continue
            candidates.add(path)
        return candidates

    def _collect_cache_files(self) -> set[Path]:
        files = set(self._iter_files(self._temp_dir))
        files.update(self._data_dir.glob("plugins_custom_*.json"))

        for extra_file in (
            self._data_dir / "plugins.json",
            self._data_dir / "sandbox_skills_cache.json",
        ):
            if extra_file.is_file():
                files.add(extra_file)

        trace_path = self._resolve_log_path(
            self._get_optional_str("trace_db_path"),
            default_relative_path="logs/traces.db",
        )
        protected = {
            Path(str(trace_path) + suffix).resolve()
            for suffix in ("", "-wal", "-shm", "-journal")
        }
        return {path for path in files if path.resolve() not in protected}

    def _log_file_configs(self) -> list[LogFileConfig]:
        return [
            LogFileConfig(
                path=self._resolve_log_path(
                    self._get_optional_str("log_file_path"),
                    default_relative_path="logs/astrbot.log",
                ),
                enabled=self._get_bool("log_file_enable", False),
            ),
            LogFileConfig(
                path=self._resolve_log_path(
                    self._get_optional_str("trace_log_path"),
                    default_relative_path="logs/astrbot.trace.log",
                ),
                enabled=self._get_bool("trace_log_enable", False),
            ),
        ]

    def _get_optional_str(self, key: str) -> str | None:
        value = self._config.get(key)
        return value if isinstance(value, str) else None

    def _get_bool(self, key: str, default: bool = False) -> bool:
        value = self._config.get(key, default)
        return value if isinstance(value, bool) else default

    def _configured_log_paths(self) -> set[Path]:
        return {config.path for config in self._log_file_configs()}

    def _active_log_files(self) -> set[Path]:
        return {config.path for config in self._log_file_configs() if config.enabled}

    def _resolve_log_path(
        self,
        configured_path: str | None,
        *,
        default_relative_path: str,
    ) -> Path:
        path_value = configured_path or default_relative_path
        path = Path(path_value)
        if path.is_absolute():
            return path.resolve()
        return (self._data_dir / path).resolve()

    def _iter_log_family_files(self, log_path: Path) -> set[Path]:
        files: set[Path] = set()
        parent_dir = log_path.parent
        if log_path.is_file():
            files.add(log_path)
        if not parent_dir.exists():
            return files

        suffix = log_path.suffix
        stem = log_path.stem if suffix else log_path.name
        pattern = f"{stem}.*{suffix}" if suffix else f"{stem}.*"

        for candidate in parent_dir.glob(pattern):
            if candidate.is_file() and candidate != log_path:
                files.add(candidate)

        return files

    @staticmethod
    def _iter_files(path: Path) -> Iterable[Path]:
        if path.is_file():
            yield path
            return
        if not path.exists():
            return
        for child in path.rglob("*"):
            if child.is_file():
                yield child

    @staticmethod
    def _summarize_files(files: Iterable[Path]) -> tuple[int, int]:
        total_size = 0
        file_count = 0
        for file_path in files:
            if not file_path.exists() or not file_path.is_file():
                continue
            try:
                total_size += file_path.stat().st_size
                file_count += 1
            except OSError as exc:
                logger.debug("Skip %s during storage scan: %s", file_path, exc)
        return total_size, file_count

    @staticmethod
    def _cleanup_empty_dirs(root_dir: Path) -> None:
        if not root_dir.exists():
            return
        for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
            path = Path(dirpath)
            if path == root_dir:
                continue
            try:
                path.rmdir()
            except OSError:
                continue
