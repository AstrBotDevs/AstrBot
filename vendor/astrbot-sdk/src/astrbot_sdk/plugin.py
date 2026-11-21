from __future__ import annotations

import logging
from typing import Any, ClassVar, Generic, TypeVar

from .context import _ACTIVE_INVOCATION_CTX, PluginContext

ConfigT = TypeVar("ConfigT")


class Plugin(Generic[ConfigT]):
    config_model: ClassVar[type[Any] | None] = None

    def __init__(self, context: PluginContext[ConfigT]) -> None:
        self._ctx = context

    @property
    def ctx(self) -> PluginContext[ConfigT]:
        active = _ACTIVE_INVOCATION_CTX.get()
        if active is not None:
            return active
        return self._ctx

    @ctx.setter
    def ctx(self, value: PluginContext[ConfigT]) -> None:
        self._ctx = value

    @property
    def config(self) -> ConfigT:
        return self.ctx.config

    @property
    def logger(self) -> logging.Logger:
        return self.ctx.logger
