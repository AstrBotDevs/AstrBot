"""Helpers for transporting portable button callback payloads."""

import hashlib
import json
import sqlite3
import threading
from copy import deepcopy
from pathlib import Path

from astrbot.core.message.components import JSONValue

BUTTON_CALLBACK_PREFIX = "astrbot:"


class _ButtonCallbackRegistry:
    """Store callback data behind compact, platform-safe tokens."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[str, JSONValue | None]] = {}
        self._db_path: Path | None = None
        self._lock = threading.RLock()

    def configure(self, db_path: str | Path) -> None:
        """Enable persistent callback lookup using AstrBot's SQLite database.

        Args:
            db_path: Path to the initialized AstrBot SQLite database.
        """
        resolved_path = Path(db_path)
        with self._lock, sqlite3.connect(resolved_path, timeout=30) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS button_callbacks ("
                "token TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )
            connection.commit()
            self._db_path = resolved_path

    def register(self, action_id: str, data: JSONValue | None) -> str:
        """Register one callback payload and return its compact token.

        Args:
            action_id: Stable identifier used to route the click.
            data: Optional JSON-compatible callback context.

        Returns:
            A deterministic URL-safe token.

        Raises:
            ValueError: If the payload is not JSON-compatible.
        """
        try:
            payload = json.dumps(
                {"i": action_id, "d": data},
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Button callback data must be JSON-compatible.") from exc

        token = hashlib.blake2s(payload.encode("utf-8"), digest_size=16).hexdigest()
        with self._lock:
            self._cache[token] = (action_id, deepcopy(data))
            if self._db_path is not None:
                with sqlite3.connect(self._db_path, timeout=30) as connection:
                    connection.execute(
                        "INSERT INTO button_callbacks(token, payload) VALUES (?, ?) "
                        "ON CONFLICT(token) DO UPDATE SET payload = excluded.payload",
                        (token, payload),
                    )
                    connection.commit()
        return token

    def resolve(self, token: str) -> tuple[str, JSONValue | None]:
        """Resolve a callback token from memory or persistent storage.

        Args:
            token: Compact callback token returned by register().

        Returns:
            The registered action identifier and callback data.

        Raises:
            ValueError: If the token is unknown or its stored payload is invalid.
        """
        with self._lock:
            cached = self._cache.get(token)
            if cached is not None:
                return cached[0], deepcopy(cached[1])

            payload = None
            if self._db_path is not None:
                with sqlite3.connect(self._db_path, timeout=30) as connection:
                    row = connection.execute(
                        "SELECT payload FROM button_callbacks WHERE token = ?",
                        (token,),
                    ).fetchone()
                    if row is not None:
                        payload = row[0]

            if payload is None:
                raise ValueError("Unknown AstrBot button callback token.")
            try:
                decoded = json.loads(payload)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError("Invalid stored button callback payload.") from exc
            if not isinstance(decoded, dict) or not isinstance(decoded.get("i"), str):
                raise ValueError("Invalid stored button callback payload.")
            resolved = (decoded["i"], decoded.get("d"))
            self._cache[token] = resolved
            return resolved[0], deepcopy(resolved[1])


_button_callback_registry = _ButtonCallbackRegistry()


def configure_button_callback_registry(db_path: str | Path) -> None:
    """Enable persistent callback tokens after the core database is initialized.

    Args:
        db_path: Path to AstrBot's SQLite database.
    """
    _button_callback_registry.configure(db_path)


def encode_button_callback(
    action_id: str,
    data: JSONValue | None = None,
) -> str:
    """Encode a callback action as a compact opaque token.

    Args:
        action_id: Stable identifier used by plugin code to route the click.
        data: Optional JSON-compatible context returned with the click.

    Returns:
        A compact token that does not expose callback data to the IM platform.

    Raises:
        ValueError: If action_id is empty or data cannot be serialized as JSON.
    """
    if not action_id:
        raise ValueError("Button action_id cannot be empty.")
    token = _button_callback_registry.register(action_id, data)
    return f"{BUTTON_CALLBACK_PREFIX}{token}"


def decode_button_callback(payload: str) -> tuple[str, JSONValue | None]:
    """Resolve an AstrBot button callback token.

    Args:
        payload: The exact callback value returned by the IM platform.

    Returns:
        The action identifier and its optional JSON data.

    Raises:
        ValueError: If the payload is not a known AstrBot button callback.
    """
    if not payload.startswith(BUTTON_CALLBACK_PREFIX):
        raise ValueError("Not an AstrBot button callback payload.")
    token = payload.removeprefix(BUTTON_CALLBACK_PREFIX)
    if len(token) != 32 or any(char not in "0123456789abcdef" for char in token):
        raise ValueError("Invalid AstrBot button callback token.")
    return _button_callback_registry.resolve(token)
