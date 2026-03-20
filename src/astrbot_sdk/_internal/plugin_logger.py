from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

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
        return PluginLogger(
            plugin_id=self._plugin_id,
            logger=self._logger.bind(**kwargs),
            bound_context={**self._bound_context, **kwargs},
        )

    def opt(self, *args: Any, **kwargs: Any) -> PluginLogger:
        return PluginLogger(
            plugin_id=self._plugin_id,
            logger=self._logger.opt(*args, **kwargs),
            bound_context=self._bound_context,
        )

    async def watch(self) -> AsyncIterator[PluginLogEntry]:
        async for entry in self._broker.watch():
            yield entry

    def log(self, level: str, message: Any, *args: Any, **kwargs: Any) -> None:
        self._logger.log(level, message, *args, **kwargs)
        self._publish(str(level).upper(), message, *args, **kwargs)

    def debug(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self._logger.debug(message, *args, **kwargs)
        self._publish("DEBUG", message, *args, **kwargs)

    def info(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self._logger.info(message, *args, **kwargs)
        self._publish("INFO", message, *args, **kwargs)

    def warning(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self._logger.warning(message, *args, **kwargs)
        self._publish("WARNING", message, *args, **kwargs)

    def error(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self._logger.error(message, *args, **kwargs)
        self._publish("ERROR", message, *args, **kwargs)

    def exception(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self._logger.exception(message, *args, **kwargs)
        self._publish("ERROR", message, *args, **kwargs)

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
