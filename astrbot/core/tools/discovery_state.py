"""Session-scoped append-only tracker of discovered tool names."""

from __future__ import annotations


class DiscoveryState:
    """Tracks which deferred tools have been discovered during a session.

    Maintains an ordered, deduplicated list of tool names. Names are appended
    via :meth:`add` and can never be removed -- the list only grows
    (monotonic append). This guarantees that the tools parameter sent to the
    LLM never shrinks across conversation turns.

    The state lives outside message history so it survives context window
    compression (truncation, summarization).
    """

    def __init__(self) -> None:
        self._names: list[str] = []
        self._seen: set[str] = set()

    def add(self, tool_name: str) -> bool:
        """Append *tool_name* if not already discovered.

        Returns:
            ``True`` if the name was newly added, ``False`` if it was
            already present (duplicate add is a no-op).
        """
        if tool_name in self._seen:
            return False
        self._seen.add(tool_name)
        self._names.append(tool_name)
        return True

    def get_discovered_names(self) -> tuple[str, ...]:
        """Return discovered tool names in discovery order (immutable snapshot)."""
        return tuple(self._names)

    def __len__(self) -> int:
        return len(self._names)

    def __contains__(self, tool_name: str) -> bool:  # type: ignore[override]
        return tool_name in self._seen
