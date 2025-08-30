"""
Misskey Platform Adapter for AstrBot

Provides integration with Misskey instances, a decentralized social networking platform.
Supports listening to mentions, replies, and timeline events.
"""

from .misskey_adapter import MisskeyPlatformAdapter
from .misskey_event import MisskeyPlatformEvent

__all__ = ["MisskeyPlatformAdapter", "MisskeyPlatformEvent"]
