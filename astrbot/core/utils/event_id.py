"""Compact identities for conversation events and their references."""

from base64 import urlsafe_b64encode
from uuid import uuid4


def new_event_id() -> str:
    """Encode a complete UUID without changing its random information.

    Returns:
        A 22-character, unpadded Base64URL identity.
    """
    return urlsafe_b64encode(uuid4().bytes).rstrip(b"=").decode("ascii")
