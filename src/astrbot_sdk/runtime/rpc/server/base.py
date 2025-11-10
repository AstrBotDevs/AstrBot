from __future__ import annotations

from abc import ABC
from ..transport import JSONRPCTransport


class JSONRPCServer(JSONRPCTransport, ABC):
    """Base class for JSON-RPC servers.

    Handles pure communication (reading/writing JSON-RPC messages).
    Server runs in plugin process and receives messages from AstrBot.
    """

    def __init__(self) -> None:
        super().__init__()
