"""Helpers for transporting portable button callback payloads."""

import asyncio
import hashlib
import json
import math
import sqlite3
import threading
import time
from contextlib import closing
from copy import deepcopy
from pathlib import Path

from astrbot.core.message.components import JSONValue

BUTTON_CALLBACK_PREFIX = "astrbot:"
BUTTON_ACTION_EXPIRED_MESSAGE = (
    "按钮已过期，请重新发起操作。 / This button has expired. Please start again."
)

# Keep recently registered or loaded callbacks in memory to avoid repeated reads.
_MAX_CACHED_CALLBACKS = 4096
# Retain expired tokens long enough to report their expiry to late clicks.
_EXPIRED_RETENTION_SECONDS = 86400


class ButtonActionExpiredError(ValueError):
    """Indicate an expired callback that should receive an expiry notice."""


class _ButtonCallbackRegistry:
    """Store callback data behind compact, platform-safe tokens."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[str, JSONValue | None, float | None]] = {}
        self._db_path: Path | None = None
        self._lock = threading.RLock()

    def configure(self, db_path: str | Path) -> None:
        """Enable persistent callback lookup using AstrBot's SQLite database.

        Args:
            db_path: Path to the initialized AstrBot SQLite database.
        """
        resolved_path = Path(db_path)
        with (
            self._lock,
            closing(sqlite3.connect(resolved_path, timeout=30)) as connection,
        ):
            connection.execute(
                "CREATE TABLE IF NOT EXISTS button_callbacks ("
                "token TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_button_callbacks_expiry "
                "ON button_callbacks (json_extract(payload, '$.e')) "
                "WHERE json_valid(payload) AND json_extract(payload, '$.e') IS NOT NULL"
            )
            connection.commit()
            self._db_path = resolved_path

    def register(
        self, action_id: str, data: JSONValue | None, expires_at: float | None = None
    ) -> str:
        """Register one callback payload and return its compact token.

        Args:
            action_id: Stable identifier used to route the click.
            data: Optional JSON-compatible callback context.
            expires_at: Absolute callback deadline, or None if unlimited.

        Returns:
            A URL-safe token including the deadline in its identity.

        Raises:
            ValueError: If the payload is not JSON-compatible or expiry is not finite.
            sqlite3.Error: If the callback cannot be persisted.
        """
        callback_payload = {"i": action_id, "d": data}
        if expires_at is not None:
            if not math.isfinite(expires_at):
                raise ValueError("Button callback expiry must be finite.")
            callback_payload["e"] = expires_at
        try:
            payload = json.dumps(
                callback_payload,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Button callback data must be JSON-compatible.") from exc

        token = hashlib.blake2s(payload.encode("utf-8"), digest_size=16).hexdigest()
        entry = (action_id, deepcopy(data), expires_at)
        with self._lock:
            db_path = self._db_path
        cutoff = None
        if db_path is not None:
            # Publish the token only after committing it. A locked database must
            # not hold the cache lock while other callbacks are being resolved.
            with closing(sqlite3.connect(db_path, timeout=30)) as connection:
                connection.execute(
                    "INSERT INTO button_callbacks(token, payload) VALUES (?, ?) "
                    "ON CONFLICT(token) DO UPDATE SET payload = excluded.payload",
                    (token, payload),
                )
                cutoff = time.time() - _EXPIRED_RETENTION_SECONDS
                connection.execute(
                    "DELETE FROM button_callbacks WHERE json_valid(payload) "
                    "AND json_extract(payload, '$.e') < ?",
                    (cutoff,),
                )
                connection.commit()
        with self._lock:
            self._cache[token] = entry
            if cutoff is not None:
                for old_token, (_, _, old_expiry) in list(self._cache.items()):
                    if old_expiry is not None and old_expiry < cutoff:
                        self._cache.pop(old_token)
            self._trim_cache()
        return token

    def _trim_cache(self) -> None:
        """Drop the oldest cached callbacks while holding the registry lock."""
        while len(self._cache) > _MAX_CACHED_CALLBACKS:
            self._cache.pop(next(iter(self._cache)))

    def resolve(
        self, token: str, *, allow_expired: bool = False
    ) -> tuple[str, JSONValue | None]:
        """Resolve a callback token from memory or persistent storage.

        Args:
            token: Compact callback token returned by register().
            allow_expired: Resolve routing metadata for sending an expiry notice.

        Returns:
            The registered action identifier and callback data.

        Raises:
            ValueError: If the token is unknown, expired, or has an invalid payload.
        """
        with self._lock:
            cached = self._cache.get(token)
            db_path = self._db_path
        if cached is None:
            row = None
            if db_path is not None:
                with closing(sqlite3.connect(db_path, timeout=30)) as connection:
                    row = connection.execute(
                        "SELECT payload FROM button_callbacks WHERE token = ?",
                        (token,),
                    ).fetchone()
            if row is None:
                raise ValueError("Unknown AstrBot button callback token.")
            try:
                decoded = json.loads(row[0])
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError("Invalid stored button callback payload.") from exc
            if not isinstance(decoded, dict) or not isinstance(decoded.get("i"), str):
                raise ValueError("Invalid stored button callback payload.")
            expires_at = decoded.get("e")
            if expires_at is not None and (
                not isinstance(expires_at, (int, float))
                or not math.isfinite(expires_at)
            ):
                raise ValueError("Invalid stored button callback expiry.")
            cached = (decoded["i"], decoded.get("d"), expires_at)
            with self._lock:
                self._cache[token] = cached
                self._trim_cache()

        if not allow_expired and cached[2] is not None and time.time() >= cached[2]:
            # Retain expiry metadata so repeated clicks also receive a notice.
            raise ButtonActionExpiredError("AstrBot button action has expired.")
        return cached[0], deepcopy(cached[1])


_button_callback_registry = _ButtonCallbackRegistry()


def configure_button_callback_registry(db_path: str | Path) -> None:
    """Persist callbacks separately from the asynchronous application database.

    Rendering buttons is synchronous. Sharing the main database can block its
    event loop while waiting for an asynchronous transaction to release a write
    lock. Existing tokens are copied so buttons remain valid across upgrades.

    Args:
        db_path: Path to AstrBot's SQLite database.
    """
    main_db_path = Path(db_path)
    callback_db_path = main_db_path.with_name(
        f"{main_db_path.stem}_button_callbacks.db"
    )
    _button_callback_registry.configure(callback_db_path)
    with closing(sqlite3.connect(callback_db_path, timeout=30)) as connection:
        connection.execute("ATTACH DATABASE ? AS legacy", (str(main_db_path),))
        legacy_table = connection.execute(
            "SELECT 1 FROM legacy.sqlite_master "
            "WHERE type = 'table' AND name = 'button_callbacks'"
        ).fetchone()
        if legacy_table is not None:
            connection.execute(
                "INSERT OR IGNORE INTO button_callbacks(token, payload) "
                "SELECT token, payload FROM legacy.button_callbacks"
            )
            connection.commit()


def encode_button_callback(
    action_id: str,
    data: JSONValue | None = None,
    *,
    expires_at: float | None = None,
) -> str:
    """Encode a callback action as a compact opaque token.

    Args:
        action_id: Stable identifier used by plugin code to route the click.
        data: Optional JSON-compatible context returned with the click.
        expires_at: Absolute callback deadline shared by the action row.

    Returns:
        A compact token that does not expose callback data to the IM platform.

    Raises:
        ValueError: If action_id is empty, data is invalid, or expiry is not finite.
    """
    if not action_id:
        raise ValueError("Button action_id cannot be empty.")
    token = _button_callback_registry.register(action_id, data, expires_at)
    return f"{BUTTON_CALLBACK_PREFIX}{token}"


def decode_button_callback(
    payload: str, *, allow_expired: bool = False
) -> tuple[str, JSONValue | None]:
    """Resolve an AstrBot button callback token.

    Args:
        payload: The exact callback value returned by the IM platform.
        allow_expired: Resolve metadata only to route an expiry notice. The inbound
            ButtonInteraction must retain callback_data for pipeline validation.

    Returns:
        The action identifier and its optional JSON data.

    Raises:
        ValueError: If the payload is unknown, invalid, or expired.
    """
    if not payload.startswith(BUTTON_CALLBACK_PREFIX):
        raise ValueError("Not an AstrBot button callback payload.")
    token = payload.removeprefix(BUTTON_CALLBACK_PREFIX)
    if len(token) != 32 or any(char not in "0123456789abcdef" for char in token):
        raise ValueError("Invalid AstrBot button callback token.")
    return _button_callback_registry.resolve(token, allow_expired=allow_expired)


async def encode_button_callback_async(
    action_id: str,
    data: JSONValue | None = None,
    *,
    expires_at: float | None = None,
) -> str:
    """Persist a callback on a worker thread before returning its token.

    Args:
        action_id: Stable identifier used by plugin code to route the click.
        data: Optional JSON-compatible context returned with the click.
        expires_at: Absolute callback deadline shared by the action row.

    Returns:
        The compact callback token.

    Raises:
        ValueError: If the callback data, action ID, or expiry is invalid.
        sqlite3.Error: If the callback cannot be persisted.
    """
    return await asyncio.to_thread(
        encode_button_callback, action_id, data, expires_at=expires_at
    )


async def decode_button_callback_async(
    payload: str, *, allow_expired: bool = False
) -> tuple[str, JSONValue | None]:
    """Resolve a callback on a worker thread, including database cache misses.

    Args:
        payload: The exact callback value returned by the IM platform.
        allow_expired: Resolve metadata only to route an expiry notice.

    Returns:
        The action identifier and its optional JSON data.

    Raises:
        ValueError: If the payload is unknown, invalid, or expired.
        sqlite3.Error: If the stored callback cannot be read.
    """
    return await asyncio.to_thread(
        decode_button_callback, payload, allow_expired=allow_expired
    )
