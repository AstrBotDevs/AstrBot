from collections.abc import Iterable

from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.filter.custom_filter import CustomFilter


class TelegramEventFilter(CustomFilter):
    """Custom filter for Telegram-specific structured events."""

    def __init__(
        self,
        event_types: str | Iterable[str] | None = None,
        *,
        callback_data_prefix: str | None = None,
        callback_data: str | None = None,
        raise_error: bool = True,
    ) -> None:
        super().__init__(raise_error=raise_error)
        if event_types is None:
            normalized_types = {"callback_query"}
        elif isinstance(event_types, str):
            normalized_types = {event_types}
        else:
            normalized_types = {str(item) for item in event_types}
        self.event_types = {
            item.strip().lower() for item in normalized_types if item and item.strip()
        }
        self.callback_data_prefix = callback_data_prefix
        self.callback_data = callback_data

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        if event.get_platform_name() != "telegram":
            return False

        event_type = str(event.get_extra("telegram_event_type", "") or "").lower()
        if not event_type:
            event_type = "callback_query" if _is_callback_event(event) else ""
        if not event_type or event_type not in self.event_types:
            return False

        if self.callback_data is None and self.callback_data_prefix is None:
            return True

        data = _get_callback_data(event)
        if self.callback_data is not None and data != self.callback_data:
            return False
        if self.callback_data_prefix is not None and not data.startswith(
            self.callback_data_prefix,
        ):
            return False
        return True


def telegram_event_filter(
    event_types: str | Iterable[str] | None = None,
    *,
    callback_data_prefix: str | None = None,
    callback_data: str | None = None,
):
    """Return a CustomFilter class usable by ``@filter.custom_filter``."""

    class _TelegramEventFilter(TelegramEventFilter):
        def __init__(self, raise_error: bool = True) -> None:
            super().__init__(
                event_types,
                callback_data_prefix=callback_data_prefix,
                callback_data=callback_data,
                raise_error=raise_error,
            )

    return _TelegramEventFilter


def _is_callback_event(event: AstrMessageEvent) -> bool:
    getter = getattr(event, "is_button_interaction", None)
    return bool(callable(getter) and getter())


def _get_callback_data(event: AstrMessageEvent) -> str:
    getter = getattr(event, "get_interaction_data", None)
    if callable(getter):
        return str(getter() or "")
    return ""
