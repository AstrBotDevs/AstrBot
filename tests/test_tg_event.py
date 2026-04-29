"""Import smoke tests for astrbot.core.platform.sources.telegram.tg_event."""


def test_import_and_class_exists() -> None:
    """Verify the module imports and the main class is accessible."""
    from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent

    assert TelegramPlatformEvent is not None
