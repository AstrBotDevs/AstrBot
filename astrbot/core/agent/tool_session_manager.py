"""
ToolSessionManager - Session-level state management for stateful tools.

Provides per-(UMO, tool_name) session state that persists across conversation
turns within the same session, with optional persistence via SharedPreferences.
"""

from collections.abc import MutableMapping
from dataclasses import dataclass, field
from typing import Any

from astrbot.core.utils.shared_preferences import SharedPreferences


@dataclass
class ToolSessionState(MutableMapping[str, Any]):
    """
    Represents the session state for a single tool within a session.
    Acts like a dict but supports persistence markers.

    Use `set_persistent(key)` to mark keys that survive session clear.
    """

    umo: str
    tool_name: str
    _data: dict[str, Any] = field(default_factory=dict)
    _persistent_keys: set[str] = field(default_factory=set)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def set_persistent(self, key: str) -> None:
        """Mark a key as persistent (survives session clear)."""
        self._persistent_keys.add(key)

    def is_persistent(self, key: str) -> bool:
        """Check if a key is marked as persistent."""
        return key in self._persistent_keys


class ToolSessionManager:
    """
    Central manager for all tool session states.

    Maintains in-memory state per (umo, tool_name) combination.
    Optional SharedPreferences integration for persistence across sessions.

    Example:
        mgr = ToolSessionManager()
        state = mgr.get_state(umo, "shell")
        state["cwd"] = "/tmp"
        state.set_persistent("env")  # env survives session clear
    """

    def __init__(self, sp: SharedPreferences | None = None) -> None:
        self._states: dict[tuple[str, str], ToolSessionState] = {}
        self._sp = sp

    def get_state(self, umo: str, tool_name: str) -> ToolSessionState:
        """Get or create session state for a tool in a session."""
        key = (umo, tool_name)
        if key not in self._states:
            self._states[key] = ToolSessionState(umo=umo, tool_name=tool_name)
        return self._states[key]

    async def persist_state(self, umo: str, tool_name: str) -> None:
        """Persist marked keys to SharedPreferences."""
        if not self._sp:
            return
        state = self.get_state(umo, tool_name)
        for key, value in state._data.items():
            if key in state._persistent_keys:
                storage_key = f"tool_state:{tool_name}:{key}"
                await self._sp.session_put(umo, storage_key, value)

    async def load_persistent_state(self, umo: str, tool_name: str) -> None:
        """Load persistent state from SharedPreferences into the session state."""
        if not self._sp:
            return
        state = self.get_state(umo, tool_name)
        storage_prefix = f"tool_state:{tool_name}:"
        # session_get(umo, None) returns list[Preference] for all prefs in this UMO
        prefs: list = await self._sp.session_get(umo, None)
        for pref in prefs:
            key = getattr(pref, "key", None) or ""
            if key.startswith(storage_prefix):
                actual_key = key[len(storage_prefix) :]
                val = getattr(pref, "value", None)
                state._data[actual_key] = (
                    val.get("val") if isinstance(val, dict) else val
                )
                state.set_persistent(actual_key)

    def clear_session(self, umo: str) -> None:
        """
        Clear non-persistent state for all tools in a session.

        Persistent keys (marked via `set_persistent`) are preserved.
        """
        keys_to_clear = [k for k in self._states if k[0] == umo]
        for key in keys_to_clear:
            state = self._states[key]
            # Keep only persistent keys
            state._data = {
                k: v for k, v in state._data.items() if k in state._persistent_keys
            }
