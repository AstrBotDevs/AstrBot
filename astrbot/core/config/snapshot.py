"""Independent runtime configuration snapshots with optional session overrides."""

from astrbot.core.session_overrides import apply_overrides

from .astrbot_config import AstrBotConfig


class AstrBotConfigSnapshot(AstrBotConfig):
    """An independent configuration whose changes cannot be saved to a profile."""

    def __init__(self, base: AstrBotConfig, overrides: dict) -> None:
        """Copy configuration values and apply session overrides without file I/O.

        Args:
            base: Shared profile providing inherited configuration values.
            overrides: Explicit dotted paths and their replacement values.
        """
        # The runtime object owns values only, not file paths or persistence locks.
        dict.__init__(self, apply_overrides(base, overrides))

    def save_config(
        self, replace_config: dict | None = None, *, indent: int = 2
    ) -> None:
        """Reject saving effective configuration as a shared profile.

        Args:
            replace_config: Unused values; no changes are applied.
            indent: Unused serialization indentation.

        Raises:
            ValueError: Always; session changes must use the override API.
        """
        raise ValueError("Save session changes through the session override API")

    async def save_config_async(
        self, replace_config: dict | None = None, *, indent: int = 2
    ) -> bool:
        """Reject asynchronously saving effective configuration as a profile.

        Args:
            replace_config: Unused values; no changes are applied.
            indent: Unused serialization indentation.

        Raises:
            ValueError: Always; session changes must use the override API.
        """
        raise ValueError("Save session changes through the session override API")
