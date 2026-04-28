from __future__ import annotations

from time import time
from typing import Any

from .platform_metadata import PlatformMetadata


class RawPlatformEvent:
    def __init__(
        self,
        payload: Any,
        platform_meta: PlatformMetadata,
        meta: dict[str, Any] | None = None,
        plugins_name: list[str] | None = None,
    ) -> None:
        self.payload = payload
        self.platform_meta = platform_meta
        self.meta = meta or {}
        self.created_at = time()
        self.plugins_name = plugins_name

        self._extras: dict[str, Any] = {}
        self._stopped = False

        # back compatibility with existing event access patterns
        self.platform = platform_meta

    @property
    def platform_name(self) -> str:
        return self.platform_meta.name

    @property
    def platform_id(self) -> str:
        return self.platform_meta.id

    @property
    def adapter_display_name(self) -> str:
        return self.platform_meta.adapter_display_name or self.platform_meta.name

    @property
    def event_type(self) -> str | None:
        event_type = self.meta.get("event_type")
        if event_type is None:
            return None
        return str(event_type)

    def get_platform_name(self) -> str:
        return self.platform_name

    def get_platform_id(self) -> str:
        return self.platform_id

    def stop_event(self) -> None:
        self._stopped = True

    def continue_event(self) -> None:
        self._stopped = False

    def is_stopped(self) -> bool:
        return self._stopped

    def set_extra(self, key: str, value: Any) -> None:
        self._extras[key] = value

    def get_extra(self, key: str | None = None, default=None) -> Any:
        if key is None:
            return self._extras
        return self._extras.get(key, default)

    def clear_extra(self) -> None:
        self._extras.clear()
