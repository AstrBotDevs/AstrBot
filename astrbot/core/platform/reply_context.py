from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class MessageReplyContext:
    """Persist an original message's reply destination without credentials.

    Capture this value from a received event through its Platform. A caller
    owns authorization and storage integrity; this value is not a permission.
    Reconstruct it from JSON and pass it to the same Platform.create_event().

    Attributes:
        platform_id: Configured platform instance that received the message.
        platform_type: Adapter type that interprets the native identifiers.
        account_id: Application identity, excluding credentials.
        scene: Native conversation kind, such as group or c2c.
        conversation_id: Original native group or direct conversation.
        message_id: Platform ID of the incoming message to reply to.
        sender_id: Original native sender identity.
        session_id: Original framework session identity.
        timestamp: Original message timestamp in seconds since the Unix epoch.
        reference_id: Native reference for displaying a quote of this message.
        thread_id: Optional native thread containing the message.
        root_id: Optional original topic root.
        parent_id: Original parent message or QQ quoted message reference index.
        reply_sequence: Optional QQ send sequence for this reply.
        mode: Original-message reply by default. QQ also supports an explicit
            proactive send to the same conversation when the caller permits it.
    """

    platform_id: str
    platform_type: str
    account_id: str
    scene: str
    conversation_id: str
    message_id: str
    sender_id: str
    session_id: str
    timestamp: int
    reference_id: str | None = None
    thread_id: str | None = None
    root_id: str | None = None
    parent_id: str | None = None
    reply_sequence: int | None = None
    mode: Literal["reply", "proactive"] = "reply"

    def __post_init__(self) -> None:
        optional = ("reference_id", "thread_id", "root_id", "parent_id")
        for field in (
            "platform_id",
            "platform_type",
            "account_id",
            "scene",
            "conversation_id",
            "message_id",
            "sender_id",
            "session_id",
            *optional,
        ):
            value = getattr(self, field)
            if value is None and field in optional:
                continue
            if (
                not isinstance(value, str)
                or not value.strip()
                or any(ord(c) < 32 for c in value)
            ):
                raise ValueError(f"Invalid reply context {field}")
        if type(self.timestamp) is not int or self.timestamp < 0:
            raise ValueError("Invalid reply context timestamp")
        if self.mode not in ("reply", "proactive"):
            raise ValueError("Invalid reply context mode")
        if self.reply_sequence is not None and (
            type(self.reply_sequence) is not int or self.reply_sequence < 1
        ):
            raise ValueError("Invalid reply sequence")
