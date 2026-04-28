"""Import smoke tests for astrbot.core.platform.sources.kook.kook_event."""


def test_import_and_class_exists() -> None:
    """Verify the module imports and the main class is accessible."""
    from astrbot.core.platform.sources.kook.kook_event import KookEvent

    assert KookEvent is not None
