from __future__ import annotations

from abc import ABC
from ..transport import JSONRPCTransport


class JSONRPCClient(JSONRPCTransport, ABC):
    """Base class for JSON-RPC clients.

    Handles pure communication (reading/writing JSON-RPC messages).
    """

    def __init__(self) -> None:
        super().__init__()
