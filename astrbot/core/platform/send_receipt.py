from dataclasses import dataclass


@dataclass(frozen=True)
class MessageSendReceipt:
    """Confirm API acceptance of all message content passed to one send.

    A receipt does not confirm delivery or that the recipient read the message.
    Adapters return None when they cannot confirm acceptance of the whole chain.

    Attributes:
        message_ids: Message IDs returned by the platform, when available.
        tracking_keys: Request tracking keys, which are not message IDs.
        reference_ids: Platform message references available for quoting.
    """

    message_ids: tuple[str, ...] = ()
    tracking_keys: tuple[str, ...] = ()
    reference_ids: tuple[str, ...] = ()


class MessageSendRejected(RuntimeError):
    """A platform or adapter definitively refused this operation before acceptance.

    Attributes:
        reason: A machine-readable reason such as `permission_denied`,
            `reply_window_expired`, `rate_limited`, `invalid_target` or `rejected`.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
