"""Import smoke tests for astrbot.core.platform.sources.discord.discord_platform_event."""


def test_import_and_class_exists() -> None:
    """Verify the module imports and the main class is accessible."""
    from astrbot.core.platform.sources.discord.discord_platform_event import (
        DiscordPlatformEvent,
    )

    assert DiscordPlatformEvent is not None
