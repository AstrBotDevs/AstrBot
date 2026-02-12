from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_MAX_COMPONENT_CHAIN_DEPTH = 4
_DEFAULT_MAX_FORWARD_NODE_DEPTH = 6
_DEFAULT_MAX_FORWARD_FETCH = 32


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value <= 0:
        return default
    return value


@dataclass(frozen=True)
class QuotedMessageParserSettings:
    max_component_chain_depth: int = _DEFAULT_MAX_COMPONENT_CHAIN_DEPTH
    max_forward_node_depth: int = _DEFAULT_MAX_FORWARD_NODE_DEPTH
    max_forward_fetch: int = _DEFAULT_MAX_FORWARD_FETCH
    warn_on_action_failure: bool = False

    @classmethod
    def from_env(cls) -> QuotedMessageParserSettings:
        return cls(
            max_component_chain_depth=_read_int_env(
                "ASTRBOT_QUOTED_MAX_COMPONENT_CHAIN_DEPTH",
                _DEFAULT_MAX_COMPONENT_CHAIN_DEPTH,
            ),
            max_forward_node_depth=_read_int_env(
                "ASTRBOT_QUOTED_MAX_FORWARD_NODE_DEPTH",
                _DEFAULT_MAX_FORWARD_NODE_DEPTH,
            ),
            max_forward_fetch=_read_int_env(
                "ASTRBOT_QUOTED_MAX_FORWARD_FETCH",
                _DEFAULT_MAX_FORWARD_FETCH,
            ),
            warn_on_action_failure=os.getenv(
                "ASTRBOT_QUOTED_ACTION_WARN",
                "",
            )
            .strip()
            .lower()
            in {"1", "true", "yes", "on"},
        )


SETTINGS = QuotedMessageParserSettings.from_env()
