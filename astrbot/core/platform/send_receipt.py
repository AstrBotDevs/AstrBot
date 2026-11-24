from dataclasses import dataclass


@dataclass(frozen=True)
class MessageSendReceipt:
    """Confirm API acceptance of all message content passed to one send.

    A receipt does not confirm delivery or that the recipient read the message.
    Adapters return None when they cannot confirm acceptance of the whole chain.

    Attributes:
        message_ids: Message IDs returned by the platform, when available.
        tracking_keys: Request tracking keys, which are not message IDs.
    """

    message_ids: tuple[str, ...] = ()
    tracking_keys: tuple[str, ...] = ()
