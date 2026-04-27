"""TTL-based key registry for deduplication.

This module provides a reusable TTL (time-to-live) key registry that can be used
for message/event deduplication across different components.
"""

import time
from collections.abc import Hashable, Sequence


class TTLKeyRegistry:
    """A TTL-based registry for tracking seen keys.

    This utility handles time-based expiration of keys, making it suitable for
    deduplication scenarios where old entries should be automatically cleaned up.
    Supports optional cleanup interval throttling to avoid per-access full scans.

    Concurrency note:
        This class is not thread-safe and does not provide internal locking.
        It is designed for single-consumer/single-thread usage patterns.
        If shared across concurrent tasks/threads, callers must provide
        external synchronization.

    Example:
        registry = TTLKeyRegistry(ttl_seconds=0.5)
        if registry.seen("some_key"):
            # Key was seen within TTL window
            pass
        else:
            # New key, register it
            pass
    """

    def __init__(
        self,
        ttl_seconds: float,
        cleanup_interval_seconds: float = 0.0,
    ) -> None:
        """Initialize the registry.

        Args:
            ttl_seconds: Time-to-live in seconds for each key. Keys older than
                        this will be considered expired and cleaned up on next access.
            cleanup_interval_seconds: Minimum interval between cleanup operations.
                                      If 0 (default), cleanup runs on every access.
                                      If > 0, cleanup is throttled to this interval.
        """
        self._ttl_seconds = ttl_seconds
        self._cleanup_interval_seconds = cleanup_interval_seconds
        self._last_cleanup_at: float = 0.0
        self._seen: dict[Hashable, float] = {}

    @property
    def ttl_seconds(self) -> float:
        """Return the TTL seconds value."""
        return self._ttl_seconds

    def _clean_expired(self) -> None:
        """Remove expired entries from the registry, with interval throttling."""
        # Short-circuit: if TTL is disabled (<=0), skip all cleanup logic
        if self._ttl_seconds <= 0:
            return

        now = time.monotonic()

        # Apply cleanup interval throttling if configured
        if self._cleanup_interval_seconds > 0:
            if self._last_cleanup_at > 0:
                if now - self._last_cleanup_at < self._cleanup_interval_seconds:
                    return
            self._last_cleanup_at = now

        expire_before = now - self._ttl_seconds
        for key, ts in list(self._seen.items()):
            if ts < expire_before:
                del self._seen[key]

    def contains(self, key: Hashable) -> bool:
        """Check if a key exists in the registry (without registering).

        Args:
            key: The key to check.

        Returns:
            True if the key exists and is not expired, False otherwise.
        """
        self._clean_expired()
        return key in self._seen

    def add(self, key: Hashable) -> None:
        """Register a key with current timestamp.

        Args:
            key: The key to add.
        """
        self._seen[key] = time.monotonic()

    def discard(self, key: Hashable) -> None:
        """Remove a key from the registry.

        Args:
            key: The key to remove.
        """
        self._seen.pop(key, None)

    def seen(self, key: Hashable) -> bool:
        """Check if a key has been seen within the TTL window.

        If not seen, registers the key with current timestamp.

        Args:
            key: The key to check.

        Returns:
            True if the key was already seen within TTL window, False otherwise.
        """
        self._clean_expired()
        if key in self._seen:
            return True
        self._seen[key] = time.monotonic()
        return False

    def seen_many(self, keys: Sequence[Hashable]) -> bool:
        """Check if any of the keys have been seen within the TTL window.

        If none are seen, registers all keys with current timestamp.

        Args:
            keys: The sequence of keys to check.

        Returns:
            True if any key was already seen within TTL window, False otherwise.
        """
        self._clean_expired()
        now = time.monotonic()
        if any(k in self._seen for k in keys):
            return True
        for k in keys:
            self._seen[k] = now
        return False
