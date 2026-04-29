"""
GUI automation component.
"""

from typing import Any, Protocol


class GUIComponent(Protocol):
    """Desktop GUI operations component."""

    async def screenshot(self, path: str | None = None) -> dict[str, Any]:
        """Capture a screenshot, optionally saving it to path."""
        ...

    async def click(self, x: int, y: int, button: str = "left") -> dict[str, Any]:
        """Click at screen coordinates."""
        ...

    async def type_text(self, text: str) -> dict[str, Any]:
        """Type text into the active UI target."""
        ...

    async def press_key(self, key: str) -> dict[str, Any]:
        """Press a keyboard key or shortcut."""
        ...
