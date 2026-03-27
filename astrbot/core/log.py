"""AstrBot logging pipeline with structured console events."""

import asyncio
import logging
import sys
import time
from asyncio import Queue
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from loguru import logger as _raw_loguru_logger

from astrbot.core.config.default import VERSION
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

CACHED_SIZE = 500
_LOG_CONTEXT: ContextVar[dict[str, Any]] = ContextVar(
    "_astrbot_log_context",
    default={},
)

if TYPE_CHECKING:
    from loguru import Record


def _normalize_path(pathname: str | None) -> str:
    if not pathname:
        return ""
    return str(PurePosixPath(pathname.replace("\\", "/")))


def _extract_path_segment(pathname: str | None, marker: str) -> str | None:
    normalized = _normalize_path(pathname)
    if marker not in normalized:
        return None

    suffix = normalized.split(marker, 1)[1]
    segment = PurePosixPath(suffix).parts
    if not segment:
        return None
    return segment[0] or None


def _extract_plugin_name(pathname: str | None) -> str | None:
    return _extract_path_segment(
        pathname, "astrbot/builtin_stars/"
    ) or _extract_path_segment(
        pathname,
        "data/plugins/",
    )


def _extract_platform_id(pathname: str | None) -> str | None:
    return _extract_path_segment(pathname, "astrbot/core/platform/sources/")


def _get_short_level_name(level_name: str) -> str:
    level_map = {
        "DEBUG": "DBUG",
        "INFO": "INFO",
        "WARNING": "WARN",
        "ERROR": "ERRO",
        "CRITICAL": "CRIT",
    }
    return level_map.get(level_name, level_name[:4].upper())


def _build_source_file(pathname: str | None) -> str:
    if not pathname:
        return "unknown"

    path = Path(pathname)
    stem = path.stem or "unknown"
    parent = path.parent.name
    return f"{parent}.{stem}" if parent else stem


def _build_primary_tag(
    *,
    pathname: str | None,
    logger_name: str,
    plugin_name: str | None,
    platform_id: str | None,
    source_file: str,
) -> str:
    if plugin_name:
        return f"plugin:{plugin_name}"
    if platform_id:
        return f"platform:{platform_id}"
    if logger_name and logger_name not in {"root", "astrbot"}:
        return f"core:{logger_name}"
    if source_file and source_file != "unknown":
        return f"core:{source_file}"
    return "core:astrbot"


def _build_tag_list(
    *,
    tag: str,
    logger_name: str,
    plugin_name: str | None,
    platform_id: str | None,
    umo: str | None,
    extra_tags: Any,
) -> list[str]:
    ordered: list[str] = [tag]

    if plugin_name:
        ordered.extend([f"plugin:{plugin_name}", plugin_name, "plugin"])
    if platform_id:
        ordered.extend([f"platform:{platform_id}", platform_id, "platform"])
    if umo:
        ordered.extend([f"umo:{umo}", umo, "umo"])
    if logger_name:
        ordered.append(f"logger:{logger_name}")

    if isinstance(extra_tags, (list, tuple, set)):
        ordered.extend(str(item) for item in extra_tags if item)
    elif extra_tags:
        ordered.append(str(extra_tags))

    seen: set[str] = set()
    result: list[str] = []
    for value in ordered:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _build_display_tag(tag: str) -> str:
    return f"[{tag}]"


def _get_context_value(
    name: str,
    overrides: dict[str, Any],
    fallback: Any = None,
) -> Any:
    if name in overrides and overrides[name] is not None:
        return overrides[name]

    context = _LOG_CONTEXT.get()
    if name in context and context[name] is not None:
        return context[name]

    return fallback


def _build_record_metadata(
    *,
    pathname: str | None,
    logger_name: str,
    level_name: str,
    level_no: int,
    source_line: int,
    is_trace: bool,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    overrides = overrides or {}
    source_file = str(
        _get_context_value("source_file", overrides, _build_source_file(pathname))
    )
    plugin_name = _get_context_value(
        "plugin_name",
        overrides,
        _extract_plugin_name(pathname),
    )
    platform_id = _get_context_value(
        "platform_id",
        overrides,
        _extract_platform_id(pathname),
    )
    plugin_display_name = _get_context_value(
        "plugin_display_name",
        overrides,
        plugin_name,
    )
    umo = _get_context_value("umo", overrides, None)
    tag = _get_context_value(
        "tag",
        overrides,
        _build_primary_tag(
            pathname=pathname,
            logger_name=logger_name,
            plugin_name=plugin_name,
            platform_id=platform_id,
            source_file=source_file,
        ),
    )
    tags = _build_tag_list(
        tag=tag,
        logger_name=logger_name,
        plugin_name=plugin_name,
        platform_id=platform_id,
        umo=umo,
        extra_tags=_get_context_value("tags", overrides, None),
    )

    return {
        "plugin_tag": "[Plug]" if plugin_name else "[Core]",
        "display_tag": _build_display_tag(tag),
        "short_levelname": _get_short_level_name(level_name),
        "astrbot_version_tag": f" [v{VERSION}]" if level_no >= logging.WARNING else "",
        "source_file": source_file,
        "source_line": source_line,
        "is_trace": is_trace,
        "tag": tag,
        "tags": tags,
        "platform_id": platform_id,
        "plugin_name": plugin_name,
        "plugin_display_name": plugin_display_name,
        "umo": umo,
        "logger_name": logger_name,
    }


def _ensure_record_metadata(record: logging.LogRecord) -> dict[str, Any]:
    overrides = {
        "tag": getattr(record, "tag", None),
        "tags": getattr(record, "tags", None),
        "platform_id": getattr(record, "platform_id", None),
        "plugin_name": getattr(record, "plugin_name", None),
        "plugin_display_name": getattr(record, "plugin_display_name", None),
        "umo": getattr(record, "umo", None),
        "source_file": getattr(record, "source_file", None),
    }
    metadata = _build_record_metadata(
        pathname=getattr(record, "pathname", None),
        logger_name=record.name,
        level_name=record.levelname,
        level_no=record.levelno,
        source_line=getattr(record, "lineno", 0),
        is_trace=record.name == "astrbot.trace",
        overrides=overrides,
    )
    for key, value in metadata.items():
        setattr(record, key, value)
    return metadata


def _patch_record(record: "Record") -> None:
    extra = record["extra"]
    metadata = _build_record_metadata(
        pathname=record["file"].path,
        logger_name=record["name"],
        level_name=record["level"].name,
        level_no=record["level"].no,
        source_line=record["line"],
        is_trace=bool(extra.get("is_trace", False)),
        overrides=extra,
    )
    extra.update(metadata)


_loguru = _raw_loguru_logger.patch(_patch_record)


class _RecordEnricherFilter(logging.Filter):
    """Inject AstrBot log metadata into stdlib records."""

    def filter(self, record: logging.LogRecord) -> bool:
        _ensure_record_metadata(record)
        return True


class _QueueAnsiColorFilter(logging.Filter):
    """Attach ANSI color prefix for WebUI console rendering."""

    _LEVEL_COLOR = {
        "DEBUG": "\u001b[1;34m",
        "INFO": "\u001b[1;36m",
        "WARNING": "\u001b[1;33m",
        "ERROR": "\u001b[31m",
        "CRITICAL": "\u001b[1;31m",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        record.ansi_prefix = self._LEVEL_COLOR.get(record.levelname, "\u001b[0m")
        record.ansi_reset = "\u001b[0m"
        return True


class _LoguruInterceptHandler(logging.Handler):
    """Bridge stdlib logging records to loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        metadata = _ensure_record_metadata(record)
        try:
            level: str | int = _loguru.level(record.levelname).name
        except ValueError:
            level = record.levelno

        payload = {
            "plugin_tag": metadata["plugin_tag"],
            "display_tag": metadata["display_tag"],
            "short_levelname": metadata["short_levelname"],
            "astrbot_version_tag": metadata["astrbot_version_tag"],
            "source_file": metadata["source_file"],
            "source_line": metadata["source_line"],
            "is_trace": metadata["is_trace"],
            "tag": metadata["tag"],
            "tags": metadata["tags"],
            "platform_id": metadata["platform_id"],
            "plugin_name": metadata["plugin_name"],
            "plugin_display_name": metadata["plugin_display_name"],
            "umo": metadata["umo"],
            "logger_name": metadata["logger_name"],
        }

        _loguru.bind(**payload).opt(exception=record.exc_info).log(
            level,
            record.getMessage(),
        )


class LogBroker:
    """Cache and fan out live console events."""

    def __init__(self) -> None:
        self.log_cache = deque(maxlen=CACHED_SIZE)
        self.subscribers: list[Queue] = []

    def register(self) -> Queue:
        q = Queue(maxsize=CACHED_SIZE + 10)
        self.subscribers.append(q)
        return q

    def unregister(self, q: Queue) -> None:
        self.subscribers.remove(q)

    def publish(self, log_entry: dict[str, Any]) -> None:
        self.log_cache.append(log_entry)
        for q in self.subscribers:
            try:
                q.put_nowait(log_entry)
            except asyncio.QueueFull:
                pass


class LogQueueHandler(logging.Handler):
    """Publish structured log events to the live console broker."""

    def __init__(self, log_broker: LogBroker) -> None:
        super().__init__()
        self.log_broker = log_broker

    def emit(self, record: logging.LogRecord) -> None:
        metadata = _ensure_record_metadata(record)
        rendered = self.format(record)
        message = record.getMessage()
        timestamp = time.time()
        event = {
            "type": "log",
            "level": record.levelname,
            "time": timestamp,
            "message": message,
            "rendered": rendered,
            "data": rendered,
            "tag": metadata["tag"],
            "tags": metadata["tags"],
            "platform_id": metadata["platform_id"],
            "plugin_name": metadata["plugin_name"],
            "plugin_display_name": metadata["plugin_display_name"],
            "umo": metadata["umo"],
            "logger_name": metadata["logger_name"],
            "source_file": metadata["source_file"],
            "source_line": metadata["source_line"],
            "is_trace": False,
        }
        self.log_broker.publish(event)


class LogManager:
    _LOGGER_HANDLER_FLAG = "_astrbot_loguru_handler"
    _ENRICH_FILTER_FLAG = "_astrbot_enrich_filter"
    _QUEUE_HANDLER_FLAG = "_astrbot_log_queue_handler"

    _configured = False
    _console_sink_id: int | None = None
    _file_sink_id: int | None = None
    _trace_sink_id: int | None = None
    _queue_broker: LogBroker | None = None
    _NOISY_LOGGER_LEVELS: dict[str, int] = {
        "aiosqlite": logging.WARNING,
        "filelock": logging.WARNING,
        "asyncio": logging.WARNING,
        "tzlocal": logging.WARNING,
        "apscheduler": logging.WARNING,
    }

    @classmethod
    def _default_log_path(cls) -> str:
        return str(Path(get_astrbot_data_path()) / "logs" / "astrbot.log")

    @classmethod
    def _resolve_log_path(cls, configured_path: str | None) -> str:
        if not configured_path:
            return cls._default_log_path()

        path = Path(configured_path)
        if path.is_absolute():
            return str(path)
        return str(Path(get_astrbot_data_path()) / path)

    @classmethod
    def _setup_loguru(cls) -> None:
        if cls._configured:
            return

        _loguru.remove()
        cls._console_sink_id = _loguru.add(
            sys.stdout,
            level="DEBUG",
            colorize=True,
            filter=lambda record: not record["extra"].get("is_trace", False),
            format=(
                "<green>[{time:HH:mm:ss.SSS}]</green> {extra[display_tag]} "
                "<level>[{extra[short_levelname]}]</level>{extra[astrbot_version_tag]} "
                "[{extra[source_file]}:{extra[source_line]}]: <level>{message}</level>"
            ),
        )
        cls._configured = True

    @classmethod
    def _setup_root_bridge(cls) -> None:
        root_logger = logging.getLogger()

        has_handler = any(
            getattr(handler, cls._LOGGER_HANDLER_FLAG, False)
            for handler in root_logger.handlers
        )
        if not has_handler:
            handler = _LoguruInterceptHandler()
            setattr(handler, cls._LOGGER_HANDLER_FLAG, True)
            root_logger.addHandler(handler)
        root_logger.setLevel(logging.DEBUG)
        for name, level in cls._NOISY_LOGGER_LEVELS.items():
            logging.getLogger(name).setLevel(level)

    @classmethod
    def _ensure_logger_enricher_filter(cls, logger: logging.Logger) -> None:
        has_filter = any(
            getattr(existing_filter, cls._ENRICH_FILTER_FLAG, False)
            for existing_filter in logger.filters
        )
        if not has_filter:
            enrich_filter = _RecordEnricherFilter()
            setattr(enrich_filter, cls._ENRICH_FILTER_FLAG, True)
            logger.addFilter(enrich_filter)

    @classmethod
    def _ensure_logger_intercept_handler(cls, logger: logging.Logger) -> None:
        has_handler = any(
            getattr(handler, cls._LOGGER_HANDLER_FLAG, False)
            for handler in logger.handlers
        )
        if not has_handler:
            handler = _LoguruInterceptHandler()
            setattr(handler, cls._LOGGER_HANDLER_FLAG, True)
            logger.addHandler(handler)

    @classmethod
    def _attach_queue_handler(
        cls, logger: logging.Logger, log_broker: LogBroker
    ) -> None:
        has_handler = any(
            getattr(handler, cls._QUEUE_HANDLER_FLAG, False)
            for handler in logger.handlers
        )
        if has_handler:
            return

        handler = LogQueueHandler(log_broker)
        setattr(handler, cls._QUEUE_HANDLER_FLAG, True)
        handler.setLevel(logging.DEBUG)
        handler.addFilter(_QueueAnsiColorFilter())
        handler.setFormatter(
            logging.Formatter(
                "%(ansi_prefix)s[%(asctime)s.%(msecs)03d] %(display_tag)s [%(short_levelname)s]%(astrbot_version_tag)s "
                "[%(source_file)s:%(source_line)d]: %(message)s%(ansi_reset)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ),
        )
        logger.addHandler(handler)

    @classmethod
    def GetLogger(cls, log_name: str = "default") -> logging.Logger:
        cls._setup_loguru()
        cls._setup_root_bridge()

        logger = logging.getLogger(log_name)
        cls._ensure_logger_enricher_filter(logger)
        cls._ensure_logger_intercept_handler(logger)
        if cls._queue_broker is not None:
            cls._attach_queue_handler(logger, cls._queue_broker)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        return logger

    @classmethod
    @contextmanager
    def contextualize(cls, **fields: Any) -> Iterator[None]:
        current = dict(_LOG_CONTEXT.get())
        current.update(
            {key: value for key, value in fields.items() if value is not None}
        )
        token = _LOG_CONTEXT.set(current)
        try:
            yield
        finally:
            _LOG_CONTEXT.reset(token)

    @classmethod
    def set_queue_handler(cls, logger: logging.Logger, log_broker: LogBroker) -> None:
        cls._queue_broker = log_broker
        cls._ensure_logger_enricher_filter(logger)
        cls._attach_queue_handler(logger, log_broker)
        cls._attach_queue_handler(logging.getLogger(), log_broker)

    @classmethod
    def _remove_sink(cls, sink_id: int | None) -> None:
        if sink_id is None:
            return
        try:
            _loguru.remove(sink_id)
        except ValueError:
            pass

    @classmethod
    def _add_file_sink(
        cls,
        *,
        file_path: str,
        level: int,
        max_mb: int | None,
        backup_count: int,
        trace: bool,
    ) -> int:
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        rotation = f"{max_mb} MB" if max_mb and max_mb > 0 else None
        retention = (
            backup_count if rotation and backup_count and backup_count > 0 else None
        )
        if trace:
            return _loguru.add(
                file_path,
                level="INFO",
                format="[{time:YYYY-MM-DD HH:mm:ss.SSS}] {message}",
                encoding="utf-8",
                rotation=rotation,
                retention=retention,
                enqueue=True,
                filter=lambda record: record["extra"].get("is_trace", False),
            )

        logging_level_name = logging.getLevelName(level)
        if isinstance(logging_level_name, int):
            logging_level_name = "INFO"
        return _loguru.add(
            file_path,
            level=logging_level_name,
            format=(
                "[{time:YYYY-MM-DD HH:mm:ss.SSS}] {extra[display_tag]} "
                "[{extra[short_levelname]}]{extra[astrbot_version_tag]} "
                "[{extra[source_file]}:{extra[source_line]}]: {message}"
            ),
            encoding="utf-8",
            rotation=rotation,
            retention=retention,
            enqueue=True,
            filter=lambda record: not record["extra"].get("is_trace", False),
        )

    @classmethod
    def configure_logger(
        cls,
        logger: logging.Logger,
        config: dict | None,
        override_level: str | None = None,
    ) -> None:
        if not config:
            return

        level = override_level or config.get("log_level")
        if level:
            try:
                logger.setLevel(level)
            except Exception:
                logger.setLevel(logging.INFO)

        if "log_file" in config:
            file_conf = config.get("log_file") or {}
            enable_file = bool(file_conf.get("enable", False))
            file_path = file_conf.get("path")
            max_mb = file_conf.get("max_mb")
        else:
            enable_file = bool(config.get("log_file_enable", False))
            file_path = config.get("log_file_path")
            max_mb = config.get("log_file_max_mb")

        cls._remove_sink(cls._file_sink_id)
        cls._file_sink_id = None

        if not enable_file:
            return

        try:
            cls._file_sink_id = cls._add_file_sink(
                file_path=cls._resolve_log_path(file_path),
                level=logger.level,
                max_mb=max_mb,
                backup_count=3,
                trace=False,
            )
        except Exception as e:
            logger.error(f"Failed to add file sink: {e}")

    @classmethod
    def configure_trace_logger(cls, config: dict | None) -> None:
        if not config:
            return

        enable = bool(
            config.get("trace_log_enable")
            or (config.get("log_file", {}) or {}).get("trace_enable", False)
        )
        path = config.get("trace_log_path")
        max_mb = config.get("trace_log_max_mb")
        if "log_file" in config:
            legacy = config.get("log_file") or {}
            path = path or legacy.get("trace_path")
            max_mb = max_mb or legacy.get("trace_max_mb")

        trace_logger = logging.getLogger("astrbot.trace")
        cls._ensure_logger_enricher_filter(trace_logger)
        cls._ensure_logger_intercept_handler(trace_logger)
        trace_logger.setLevel(logging.INFO)
        trace_logger.propagate = False

        cls._remove_sink(cls._trace_sink_id)
        cls._trace_sink_id = None

        if not enable:
            return

        cls._trace_sink_id = cls._add_file_sink(
            file_path=cls._resolve_log_path(path or "logs/astrbot.trace.log"),
            level=logging.INFO,
            max_mb=max_mb,
            backup_count=3,
            trace=True,
        )
