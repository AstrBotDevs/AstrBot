from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core.agent.message import Message


class AstrBotError(Exception):
    """Base exception for all AstrBot errors."""


class ProviderNotFoundError(AstrBotError):
    """Raised when a specified provider is not found."""


class EmptyModelOutputError(AstrBotError):
    """Raised when the model response contains no usable assistant output."""


class ContextCompressionError(AstrBotError):
    """A compression failure with the context and count used to trigger it."""

    def __init__(
        self, message: str, *, messages: list[Message], token_count: int
    ) -> None:
        """Preserve the request context for the runner's context-limit check.

        Args:
            message: Description of the compression failure.
            messages: Request messages before the failed compression attempt.
            token_count: Token count that triggered compression, including any
                provider-reported usage.
        """
        super().__init__(message)
        self.messages = messages
        self.token_count = token_count


class KnowledgeBaseUploadError(AstrBotError):
    """Raised when knowledge base upload fails with a user-facing message."""

    def __init__(
        self,
        *,
        stage: str,
        user_message: str,
        details: dict | None = None,
    ) -> None:
        super().__init__(user_message)
        self.stage = stage
        self.user_message = user_message
        self.details = details or {}

    def __str__(self) -> str:
        return self.user_message
