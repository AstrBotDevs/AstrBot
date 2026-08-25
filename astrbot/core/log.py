"""日志系统，统一将标准 logging 输出转发到 loguru。"""

import asyncio
import errno
import json
import logging
import os
import sys
import tempfile
import time
import uuid
from asyncio import Queue
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger as _raw_loguru_logger

from astrbot.core.config.default import VERSION
from astrbot.core.utils.astrbot_path import (
    get_astrbot_config_path,
    get_astrbot_data_path,
)
from astrbot.core.utils.error_redaction import redact_sensitive_text

CACHED_SIZE = 500
PLUGIN_LOGGER_PREFIX = "astrbot.plugin."
PLUGIN_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LOG_CATEGORIES = frozenset({"system", "user_chat", "platform_send", "security"})
LOG_PRIVACY = frozenset({"public", "internal", "private"})


def _new_event_id() -> str:
    value = uuid.uuid4()
    return str(getattr(value, "hex", value))


if TYPE_CHECKING:
    from loguru import Record


class _RecordEnricherFilter(logging.Filter):
    """为 logging.LogRecord 注入 AstrBot 日志字段。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith(PLUGIN_LOGGER_PREFIX):
            record.plugin_tag = f"[{record.name.removeprefix(PLUGIN_LOGGER_PREFIX)}]"
        else:
            record.plugin_tag = (
                "[Plug]" if _is_plugin_path(record.pathname) else "[Core]"
            )
        record.short_levelname = _get_short_level_name(record.levelname)
        record.astrbot_version_tag = (
            f" [v{VERSION}]" if record.levelno >= logging.WARNING else ""
        )
        record.source_file = _build_source_file(record.pathname)
        record.source_line = record.lineno
        record.is_trace = record.name == "astrbot.trace"
        category = str(getattr(record, "category", "system") or "system")
        record.category = category if category in LOG_CATEGORIES else "system"
        privacy = str(getattr(record, "privacy", "internal") or "internal")
        record.privacy = privacy if privacy in LOG_PRIVACY else "internal"
        record.event_id = str(getattr(record, "event_id", "") or _new_event_id())
        record.timestamp = float(getattr(record, "timestamp", record.created))
        record.platform = getattr(record, "platform", None)
        record.conversation_id = getattr(record, "conversation_id", None)
        record.sender_id = getattr(record, "sender_id", None)
        record.summary = redact_sensitive_text(
            str(getattr(record, "summary", record.getMessage()))[:512]
        )
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


def _is_plugin_path(pathname: str | None) -> bool:
    if not pathname:
        return False
    norm_path = os.path.normpath(pathname)
    return ("data/plugins" in norm_path) or ("astrbot/builtin_stars/" in norm_path)


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
    dirname = os.path.dirname(pathname)
    return (
        os.path.basename(dirname) + "." + os.path.basename(pathname).replace(".py", "")
    )


def _patch_record(record: Record) -> None:
    extra = record["extra"]
    extra.setdefault("plugin_tag", "[Core]")
    extra.setdefault("short_levelname", _get_short_level_name(record["level"].name))
    level_no = record["level"].no
    extra.setdefault("astrbot_version_tag", f" [v{VERSION}]" if level_no >= 30 else "")
    extra.setdefault("source_file", _build_source_file(record["file"].path))
    extra.setdefault("source_line", record["line"])
    extra.setdefault("is_trace", False)
    extra.setdefault("category", "system")
    extra.setdefault("privacy", "internal")
    extra.setdefault("event_id", _new_event_id())
    extra.setdefault("timestamp", time.time())
    extra.setdefault("platform", None)
    extra.setdefault("conversation_id", None)
    extra.setdefault("sender_id", None)
    extra.setdefault("summary", redact_sensitive_text(str(record["message"])[:512]))


_loguru = _raw_loguru_logger.patch(_patch_record)


class _SafeConsoleStream:
    """Write console logs without crashing on stream encoding mismatches."""

    def __init__(self, stream) -> None:
        self._stream = stream
        self._broken_pipe = False

    def write(self, message: str) -> None:
        if self._broken_pipe:
            return

        try:
            try:
                self._stream.write(message)
            except UnicodeEncodeError:
                encoding = getattr(self._stream, "encoding", None) or "utf-8"
                safe_bytes = message.encode(encoding, errors="backslashreplace")
                if hasattr(self._stream, "buffer"):
                    self._stream.buffer.write(safe_bytes)
                else:
                    self._stream.write(safe_bytes.decode(encoding, errors="ignore"))
        except BrokenPipeError:
            self._broken_pipe = True
        except OSError as exc:
            if exc.errno != errno.EPIPE:
                raise
            self._broken_pipe = True

    def flush(self) -> None:
        if self._broken_pipe:
            return

        if hasattr(self._stream, "flush"):
            try:
                self._stream.flush()
            except BrokenPipeError:
                self._broken_pipe = True
            except OSError as exc:
                if exc.errno != errno.EPIPE:
                    raise
                self._broken_pipe = True

    def isatty(self) -> bool:
        if hasattr(self._stream, "isatty"):
            return bool(self._stream.isatty())
        return False


class _LoguruInterceptHandler(logging.Handler):
    """将 logging 记录转发到 loguru。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = _loguru.level(record.levelname).name
        except ValueError:
            level = record.levelno

        payload = {
            "plugin_tag": getattr(record, "plugin_tag", "[Core]"),
            "short_levelname": getattr(
                record,
                "short_levelname",
                _get_short_level_name(record.levelname),
            ),
            "astrbot_version_tag": getattr(record, "astrbot_version_tag", ""),
            "source_file": getattr(
                record, "source_file", _build_source_file(record.pathname)
            ),
            "source_line": getattr(record, "source_line", record.lineno),
            "is_trace": getattr(record, "is_trace", record.name == "astrbot.trace"),
        }

        _loguru.bind(**payload).opt(exception=record.exc_info).log(
            level,
            record.getMessage(),
        )


class LogBroker:
    """日志代理类，用于缓存和分发日志消息。"""

    def __init__(self) -> None:
        self.log_cache = deque(maxlen=CACHED_SIZE)
        self.subscribers: list[Queue] = []

    def register(self) -> Queue:
        q = Queue(maxsize=CACHED_SIZE + 10)
        self.subscribers.append(q)
        return q

    def unregister(self, q: Queue) -> None:
        if q in self.subscribers:
            self.subscribers.remove(q)

    def publish(self, log_entry: dict) -> None:
        self.log_cache.append(log_entry)
        for q in self.subscribers:
            try:
                q.put_nowait(log_entry)
            except asyncio.QueueFull:
                pass


class LogQueueHandler(logging.Handler):
    """日志处理器，用于将日志消息发送到 LogBroker。"""

    def __init__(self, log_broker: LogBroker) -> None:
        super().__init__()
        self.log_broker = log_broker

    def emit(self, record: logging.LogRecord) -> None:
        timestamp = float(getattr(record, "timestamp", record.created))
        category = str(getattr(record, "category", "system") or "system")
        privacy = str(getattr(record, "privacy", "internal") or "internal")
        summary = redact_sensitive_text(
            str(getattr(record, "summary", record.getMessage()))[:512]
        )
        log_entry = redact_sensitive_text(self.format(record))
        self.log_broker.publish(
            {
                "level": record.levelname,
                "time": timestamp,
                "timestamp": timestamp,
                "data": log_entry,
                "category": category if category in LOG_CATEGORIES else "system",
                "privacy": privacy if privacy in LOG_PRIVACY else "internal",
                "event_id": str(getattr(record, "event_id", "") or _new_event_id()),
                "platform": getattr(record, "platform", None),
                "conversation_id": getattr(record, "conversation_id", None),
                "sender_id": getattr(record, "sender_id", None),
                "summary": summary,
            },
        )


class LogManager:
    _LOGGER_HANDLER_FLAG = "_astrbot_loguru_handler"
    _ENRICH_FILTER_FLAG = "_astrbot_enrich_filter"

    _configured = False
    _console_sink_id: int | None = None
    _file_sink_id: int | None = None
    _trace_sink_id: int | None = None
    _plugin_logger_names: set[str] = set()
    _plugin_level_overrides: dict[str, str] | None = None
    _log_broker: LogBroker | None = None
    _NOISY_LOGGER_LEVELS: dict[str, int] = {
        "aiosqlite": logging.WARNING,
        "filelock": logging.WARNING,
        "asyncio": logging.WARNING,
        "tzlocal": logging.WARNING,
        "apscheduler": logging.WARNING,
    }

    @classmethod
    def _default_log_path(cls) -> str:
        return os.path.join(get_astrbot_data_path(), "logs", "astrbot.log")

    @classmethod
    def _resolve_log_path(cls, configured_path: str | None) -> str:
        if not configured_path:
            return cls._default_log_path()
        if os.path.isabs(configured_path):
            return configured_path
        return os.path.join(get_astrbot_data_path(), configured_path)

    @classmethod
    def _setup_loguru(cls) -> None:
        if cls._configured:
            return

        _loguru.remove()
        cls._console_sink_id = _loguru.add(
            _SafeConsoleStream(sys.stdout),
            level="DEBUG",
            colorize=True,
            filter=lambda record: not record["extra"].get("is_trace", False),
            format=(
                "<green>[{time:HH:mm:ss.SSS}]</green> {extra[plugin_tag]} "
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
    def GetLogger(cls, log_name: str = "default") -> logging.Logger:
        cls._setup_loguru()
        cls._setup_root_bridge()

        logger = logging.getLogger(log_name)
        cls._ensure_logger_enricher_filter(logger)
        cls._ensure_logger_intercept_handler(logger)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        return logger

    @classmethod
    def _plugin_log_levels_path(cls) -> Path:
        return Path(get_astrbot_config_path()) / "plugin_log_levels.json"

    @classmethod
    def _load_plugin_level_overrides(cls) -> dict[str, str]:
        """Load valid persisted plugin log-level overrides once per process."""
        if cls._plugin_level_overrides is None:
            cls._plugin_level_overrides = {}
            try:
                with cls._plugin_log_levels_path().open(encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    cls._plugin_level_overrides = {
                        str(name): str(level).upper()
                        for name, level in data.items()
                        if str(level).upper() in PLUGIN_LOG_LEVELS
                    }
            except OSError, ValueError:
                pass
        return cls._plugin_level_overrides

    @classmethod
    def get_plugin_log_level(cls, plugin_name: str) -> str | None:
        """Return a plugin override, or None when it follows the core level."""
        return cls._load_plugin_level_overrides().get(plugin_name)

    @classmethod
    def _effective_plugin_log_level(cls, plugin_name: str) -> int:
        if override := cls.get_plugin_log_level(plugin_name):
            return int(logging.getLevelName(override))
        global_level = logging.getLogger("astrbot").level
        return global_level if global_level > logging.NOTSET else logging.INFO

    @classmethod
    def get_plugin_logger(cls, plugin_name: str) -> logging.Logger:
        """Return the dedicated logger for one catalog-published plugin."""
        logger = cls.GetLogger(f"{PLUGIN_LOGGER_PREFIX}{plugin_name}")
        cls._plugin_logger_names.add(plugin_name)
        logger.setLevel(cls._effective_plugin_log_level(plugin_name))
        if cls._log_broker is not None:
            cls.set_queue_handler(logger, cls._log_broker)
        return logger

    @classmethod
    def set_plugin_log_level(cls, plugin_name: str, level: str | None) -> None:
        """Atomically persist and apply one plugin's log-level override."""
        overrides = dict(cls._load_plugin_level_overrides())
        if level is None:
            overrides.pop(plugin_name, None)
        else:
            normalized = level.upper()
            if normalized not in PLUGIN_LOG_LEVELS:
                raise ValueError(f"Invalid plugin log level: {level}")
            overrides[plugin_name] = normalized

        config_path = cls._plugin_log_levels_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=config_path.parent,
                prefix=f".{config_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(overrides, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            temp_path.replace(config_path)
        except BaseException:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise

        cls._plugin_level_overrides = overrides
        if plugin_name in cls._plugin_logger_names:
            logging.getLogger(f"{PLUGIN_LOGGER_PREFIX}{plugin_name}").setLevel(
                cls._effective_plugin_log_level(plugin_name)
            )

    @classmethod
    def set_queue_handler(cls, logger: logging.Logger, log_broker: LogBroker) -> None:
        cls._log_broker = log_broker
        targets = [logger]
        if logger.name == "astrbot":
            targets.extend(
                logging.getLogger(f"{PLUGIN_LOGGER_PREFIX}{name}")
                for name in cls._plugin_logger_names
            )

        for target in targets:
            cls._ensure_logger_enricher_filter(target)
            if any(isinstance(handler, LogQueueHandler) for handler in target.handlers):
                continue
            handler = LogQueueHandler(log_broker)
            handler.setLevel(logging.DEBUG)
            handler.addFilter(_QueueAnsiColorFilter())
            handler.setFormatter(
                logging.Formatter(
                    "%(ansi_prefix)s[%(asctime)s.%(msecs)03d] %(plugin_tag)s [%(short_levelname)s]%(astrbot_version_tag)s "
                    "[%(source_file)s:%(source_line)d]: %(message)s%(ansi_reset)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                ),
            )
            target.addHandler(handler)

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
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
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
                "[{time:YYYY-MM-DD HH:mm:ss.SSS}] {extra[plugin_tag]} "
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

            configured_level = logging.getLevelName(logger.level)
            if cls._console_sink_id is not None and isinstance(configured_level, str):
                try:
                    new_sink_id = _loguru.add(
                        _SafeConsoleStream(sys.stdout),
                        level=configured_level,
                        colorize=True,
                        filter=lambda record: (
                            not record["extra"].get("is_trace", False)
                        ),
                        format=(
                            "<green>[{time:HH:mm:ss.SSS}]</green> {extra[plugin_tag]} "
                            "<level>[{extra[short_levelname]}]</level>"
                            "{extra[astrbot_version_tag]} "
                            "[{extra[source_file]}:{extra[source_line]}]: "
                            "<level>{message}</level>"
                        ),
                    )
                    cls._remove_sink(cls._console_sink_id)
                    cls._console_sink_id = new_sink_id
                except Exception as e:
                    logger.warning("Failed to replace console sink: %s", e)

            root_logger = logging.getLogger()
            root_logger.setLevel(logger.level)
            for name, noisy_level in cls._NOISY_LOGGER_LEVELS.items():
                logging.getLogger(name).setLevel(noisy_level)

            overrides = cls._load_plugin_level_overrides()
            for name in cls._plugin_logger_names:
                if name not in overrides:
                    logging.getLogger(f"{PLUGIN_LOGGER_PREFIX}{name}").setLevel(
                        logger.level
                    )

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

        enable = bool(config.get("trace_log_enable"))
        path = config.get("trace_log_path")
        max_mb = config.get("trace_log_max_mb")

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
