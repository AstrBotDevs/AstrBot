from __future__ import annotations

_PROTOCOL_DATACLASSES: dict[str, type] = {}


def register_protocol_dataclass(cls: type) -> type:
    """Register one frozen dataclass for generic protocol serialization.

    The wire format uses the class name, so registered names are part of the
    protocol contract and must stay stable.
    """
    _PROTOCOL_DATACLASSES[cls.__name__] = cls
    return cls
