from __future__ import annotations

import asyncio
import inspect
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

try:
    from astrbot.core.config.default import VERSION as _ASTRBOT_VERSION
except Exception:  # noqa: BLE001
    _ASTRBOT_VERSION = ""

__all__ = ["PluginLogEntry", "PluginLogger"]


@dataclass(slots=True)
class PluginLogEntry:
    level: str
    time: float
    message: str
    plugin_id: str
    context: dict[str, Any] = field(default_factory=dict)


class _PluginLogBroker:
    def __init__(self, plugin_id: str) -> None:
        self.plugin_id = plugin_id
        self._subscribers: set[asyncio.Queue[PluginLogEntry]] = set()

    def publish(self, entry: PluginLogEntry) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(entry)
            except asyncio.QueueFull:
                continue

    async def watch(self) -> AsyncIterator[PluginLogEntry]:
        queue: asyncio.Queue[PluginLogEntry] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)


_BROKERS: dict[str, _PluginLogBroker] = {}

_SHORT_LEVEL_NAMES = {
    "DEBUG": "DBUG",
    "INFO": "INFO",
    "WARNING": "WARN",
    "ERROR": "ERRO",
    "CRITICAL": "CRIT",
}

_ANSI_RESET = "\u001b[0m"
_ANSI_GREEN = "\u001b[32m"
_ANSI_LEVEL_COLORS = {
    "DEBUG": "\u001b[1;34m",
    "INFO": "\u001b[1;36m",
    "WARNING": "\u001b[1;33m",
    "ERROR": "\u001b[31m",
    "CRITICAL": "\u001b[1;31m",
}


def _get_short_level_name(level_name: str) -> str:
    return _SHORT_LEVEL_NAMES.get(level_name.upper(), level_name[:4].upper())


def _build_source_file(pathname: str | None) -> str:
    if not pathname:
        return "unknown"
    dirname = os.path.dirname(pathname)
    return (
        os.path.basename(dirname) + "." + os.path.basename(pathname).replace(".py", "")
    )


def _plugin_tag_from_path(pathname: str | None) -> str:
    if not pathname:
        return "[Plug]"
    norm_path = os.path.normpath(pathname)
    if any(
        marker in norm_path
        for marker in (
            os.path.normpath("data/plugins"),
            os.path.normpath("data/sdk_plugins"),
            os.path.normpath("astrbot/builtin_stars"),
        )
    ):
        return "[Plug]"
    return "[Core]"


def _level_color(level: str) -> str:
    return _ANSI_LEVEL_COLORS.get(level.upper(), _ANSI_RESET)


def _get_broker(plugin_id: str) -> _PluginLogBroker:
    broker = _BROKERS.get(plugin_id)
    if broker is None:
        broker = _PluginLogBroker(plugin_id)
        _BROKERS[plugin_id] = broker
    return broker


class PluginLogger:
    def __init__(
        self,
        *,
        plugin_id: str,
        logger: Any,
        bound_context: dict[str, Any] | None = None,
    ) -> None:
        self._plugin_id = plugin_id
        self._logger = logger
        self._broker = _get_broker(plugin_id)
        self._bound_context = dict(bound_context or {})

    @property
    def plugin_id(self) -> str:
        return self._plugin_id

    def bind(self, **kwargs: Any) -> PluginLogger:
        bind = getattr(self._logger, "bind", None)
        next_logger = self._logger
        if callable(bind):
            try:
                next_logger = bind(**kwargs)
            except Exception:
                next_logger = self._logger
        return PluginLogger(
            plugin_id=self._plugin_id,
            logger=next_logger,
            bound_context={**self._bound_context, **kwargs},
        )

    def opt(self, *args: Any, **kwargs: Any) -> PluginLogger:
        opt = getattr(self._logger, "opt", None)
        next_logger = self._logger
        if callable(opt):
            try:
                next_logger = opt(*args, **kwargs)
            except Exception:
                next_logger = self._logger
        return PluginLogger(
            plugin_id=self._plugin_id,
            logger=next_logger,
            bound_context=self._bound_context,
        )

    async def watch(self) -> AsyncIterator[PluginLogEntry]:
        async for entry in self._broker.watch():
            yield entry

    def log(self, level: str, message: Any, *args: Any, **kwargs: Any) -> None:
        normalized_level = str(level).upper()
        self._emit_console(normalized_level, message, *args, **kwargs)
        self._publish(normalized_level, message, *args, **kwargs)

    def debug(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self._emit_console("DEBUG", message, *args, **kwargs)
        self._publish("DEBUG", message, *args, **kwargs)

    def info(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self._emit_console("INFO", message, *args, **kwargs)
        self._publish("INFO", message, *args, **kwargs)

    def warning(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self._emit_console("WARNING", message, *args, **kwargs)
        self._publish("WARNING", message, *args, **kwargs)

    def error(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self._emit_console("ERROR", message, *args, **kwargs)
        self._publish("ERROR", message, *args, **kwargs)

    def exception(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self._emit_console("ERROR", message, *args, exception=True, **kwargs)
        self._publish("ERROR", message, *args, **kwargs)

    def _emit_console(
        self,
        level: str,
        message: Any,
        *args: Any,
        exception: bool = False,
        **kwargs: Any,
    ) -> None:
        if self._emit_console_with_opt(
            level,
            message,
            *args,
            exception=exception,
            **kwargs,
        ):
            return
        self._emit_console_fallback(
            level,
            message,
            *args,
            exception=exception,
            **kwargs,
        )

    def _emit_console_with_opt(
        self,
        level: str,
        message: Any,
        *args: Any,
        exception: bool = False,
        **kwargs: Any,
    ) -> bool:
        opt = getattr(self._logger, "opt", None)
        if not callable(opt):
            return False
        formatted_message = self._format_message(message, *args, **kwargs)
        pathname, source_line = self._caller_info()
        plugin_tag = _plugin_tag_from_path(pathname)
        source_file = _build_source_file(pathname)
        version_tag = (
            f" [v{_ASTRBOT_VERSION}]"
            if _ASTRBOT_VERSION and level in {"WARNING", "ERROR", "CRITICAL"}
            else ""
        )
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        level_text = _get_short_level_name(level)
        level_color = _level_color(level)
        line = (
            f"{_ANSI_GREEN}[{timestamp}]{_ANSI_RESET} {plugin_tag} "
            f"{level_color}[{level_text}]{_ANSI_RESET}{version_tag} "
            f"[{source_file}:{source_line}]: {level_color}{formatted_message}{_ANSI_RESET}"
        )
        try:
            emitter = opt(raw=True, exception=True) if exception else opt(raw=True)
            log = getattr(emitter, "log", None)
            if not callable(log):
                return False
            log(level, line + "\n")
            return True
        except Exception:
            return False

    def _emit_console_fallback(
        self,
        level: str,
        message: Any,
        *args: Any,
        exception: bool = False,
        **kwargs: Any,
    ) -> None:
        method_names = []
        if exception:
            method_names.append("exception")
        method_names.append(str(level).lower())
        if exception:
            method_names.append("error")
        for method_name in method_names:
            method = getattr(self._logger, method_name, None)
            if not callable(method):
                continue
            try:
                method(message, *args, **kwargs)
            except Exception:
                continue
            return
        log = getattr(self._logger, "log", None)
        if callable(log):
            try:
                log(level, self._format_message(message, *args, **kwargs))
            except Exception:
                return

    def _caller_info(self) -> tuple[str | None, int]:
        frame = inspect.currentframe()
        if frame is None:
            return None, 0
        frame = frame.f_back
        while frame is not None and frame.f_globals.get("__name__") == __name__:
            frame = frame.f_back
        if frame is None:
            return None, 0
        return str(frame.f_code.co_filename), int(frame.f_lineno)

    def _publish(self, level: str, message: Any, *args: Any, **kwargs: Any) -> None:
        entry = PluginLogEntry(
            level=level,
            time=time.time(),
            message=self._format_message(message, *args, **kwargs),
            plugin_id=self._plugin_id,
            context=dict(self._bound_context),
        )
        self._broker.publish(entry)

    @staticmethod
    def _format_message(message: Any, *args: Any, **kwargs: Any) -> str:
        if not isinstance(message, str):
            return str(message)
        text = message
        if not args and not kwargs:
            return text
        try:
            return text.format(*args, **kwargs)
        except Exception:
            return text

    def __getattr__(self, name: str) -> Any:
        return getattr(self._logger, name)
