from __future__ import annotations


class AstrBotError(Exception):
    """Base exception for all AstrBot errors."""


class ProviderNotFoundError(AstrBotError):
    """Raised when a specified provider is not found."""


class LLMEmptyResponseError(AstrBotError):
    """Raised when LLM returns an empty assistant message with no tool calls."""
