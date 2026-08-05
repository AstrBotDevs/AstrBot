"""Platform acceptance results and delivery receipts.

These values describe acceptance by a platform API.  They deliberately do not
claim that a recipient device received or read a message.
"""

from dataclasses import dataclass, field
from typing import Literal

from astrbot.core.utils.error_redaction import redact_sensitive_text

DeliveryStatus = Literal["accepted", "partial", "failed", "unknown", "skipped"]


def _safe_summary(value: str | None) -> str | None:
    """Return a bounded, redacted transport error summary."""
    if not value:
        return None
    return redact_sensitive_text(value)[:240]


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    """One immutable platform submission attempt.

    ``semantic_text`` is the local normalized text submitted with this
    attempt.  It is kept separate from transport headers and is only used for
    conversation-history projection after acceptance.
    """

    status: DeliveryStatus
    message_count: int = 0
    message_ids: tuple[str, ...] = ()
    semantic_text: str = ""
    error_summary: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "error_summary", _safe_summary(self.error_summary))
        object.__setattr__(self, "message_ids", tuple(self.message_ids))

    @property
    def accepted(self) -> bool:
        """Whether the platform explicitly accepted this attempt."""
        return self.status == "accepted"


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    """Aggregate platform acceptance for one logical response.

    The receipt only captures the platform's response to submission.  It is
    not an end-user delivery or read receipt.
    """

    status: DeliveryStatus
    attempts: tuple[DeliveryAttempt, ...] = ()
    platform_id: str = ""
    target: str = ""
    error_summary: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "error_summary", _safe_summary(self.error_summary))

    @property
    def accepted_attempts(self) -> tuple[DeliveryAttempt, ...]:
        """Accepted attempts in local submission order."""
        return tuple(attempt for attempt in self.attempts if attempt.accepted)

    @property
    def message_ids(self) -> tuple[str, ...]:
        """Platform message identifiers returned for accepted attempts."""
        return tuple(
            message_id
            for attempt in self.accepted_attempts
            for message_id in attempt.message_ids
        )

    @property
    def history_text(self) -> str:
        """Accepted local semantic text, excluding rejected fragments."""
        return "".join(
            attempt.semantic_text
            for attempt in self.accepted_attempts
            if attempt.semantic_text
        )

    @classmethod
    def skipped(
        cls,
        *,
        platform_id: str = "",
        target: str = "",
    ) -> DeliveryReceipt:
        """Create a receipt for an intentionally unsent response."""
        return cls(status="skipped", platform_id=platform_id, target=target)

    @classmethod
    def aggregate(
        cls,
        attempts: list[DeliveryAttempt] | tuple[DeliveryAttempt, ...],
        *,
        platform_id: str = "",
        target: str = "",
    ) -> DeliveryReceipt:
        """Aggregate attempts without converting uncertainty into success."""
        immutable_attempts = tuple(attempts)
        if not immutable_attempts:
            return cls.skipped(platform_id=platform_id, target=target)

        accepted = tuple(
            attempt for attempt in immutable_attempts if attempt.status == "accepted"
        )
        non_accepted = tuple(
            attempt for attempt in immutable_attempts if attempt.status != "accepted"
        )
        if accepted:
            status: DeliveryStatus = "accepted" if not non_accepted else "partial"
        elif any(attempt.status == "partial" for attempt in immutable_attempts):
            status = "partial"
        elif any(attempt.status == "unknown" for attempt in immutable_attempts):
            status = "unknown"
        elif any(attempt.status == "failed" for attempt in immutable_attempts):
            status = "failed"
        else:
            status = "skipped"

        error_summary = next(
            (
                attempt.error_summary
                for attempt in reversed(immutable_attempts)
                if attempt.error_summary
            ),
            None,
        )
        return cls(
            status=status,
            attempts=immutable_attempts,
            platform_id=platform_id,
            target=target,
            error_summary=error_summary,
        )


@dataclass(slots=True)
class PlatformSendResult:
    """Standardized outcome for a single platform submission.

    ``success`` remains the compatibility field for adapters.  A successful
    result means the platform accepted the request; it never means the user
    received or read it.
    """

    platform_id: str
    success: bool
    target: str
    message_count: int = 0
    error_message: str | None = None
    message_id: str | None = None
    message_ids: tuple[str, ...] = ()
    status: DeliveryStatus | None = None
    delivery_attempts: tuple[DeliveryAttempt, ...] = field(
        default_factory=tuple,
        repr=False,
        compare=False,
    )
    """Optional immutable detail for a logical send composed of several requests."""

    def __post_init__(self) -> None:
        self.error_message = _safe_summary(self.error_message)
        self.message_ids = tuple(self.message_ids)
        self.delivery_attempts = tuple(self.delivery_attempts)
        if self.message_id and self.message_id not in self.message_ids:
            self.message_ids = (self.message_id, *self.message_ids)

    def to_delivery_attempt(self, *, semantic_text: str = "") -> DeliveryAttempt:
        """Map this single platform result into an immutable delivery attempt."""
        if self.status is not None:
            status = self.status
        elif self.success:
            status = "accepted"
        else:
            status = "failed"
        return DeliveryAttempt(
            status=status,
            message_count=self.message_count,
            message_ids=tuple(self.message_ids),
            semantic_text=semantic_text,
            error_summary=self.error_message,
        )

    def to_delivery_attempts(
        self,
        *,
        semantic_text: str = "",
    ) -> tuple[DeliveryAttempt, ...]:
        """Return detailed attempts when an adapter submitted multiple parts."""
        if self.delivery_attempts:
            return self.delivery_attempts
        return (self.to_delivery_attempt(semantic_text=semantic_text),)

    @classmethod
    def from_delivery_attempts(
        cls,
        attempts: list[DeliveryAttempt] | tuple[DeliveryAttempt, ...],
        *,
        platform_id: str,
        target: str,
    ) -> PlatformSendResult:
        """Create a compatibility result while retaining per-submission detail."""
        receipt = DeliveryReceipt.aggregate(
            attempts,
            platform_id=platform_id,
            target=target,
        )
        return cls(
            platform_id=platform_id,
            success=receipt.status == "accepted",
            target=target,
            message_count=sum(
                attempt.message_count for attempt in receipt.accepted_attempts
            ),
            error_message=receipt.error_summary,
            message_ids=receipt.message_ids,
            status=receipt.status,
            delivery_attempts=receipt.attempts,
        )
