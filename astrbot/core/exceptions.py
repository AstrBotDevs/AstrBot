from __future__ import annotations


class AstrBotError(Exception):
    """Base exception for all AstrBot errors."""


class ProviderNotFoundError(AstrBotError):
    """Raised when a specified provider is not found."""
