from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_DEFAULT_MAX_COMPONENT_CHAIN_DEPTH = 4
_DEFAULT_MAX_FORWARD_NODE_DEPTH = 6
_DEFAULT_MAX_FORWARD_FETCH = 32


def _read_int_mapping(
    mapping: Mapping[str, Any],
    key: str,
    default: int,
) -> int:
    raw = mapping.get(key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    return value


def _read_bool_mapping(
    mapping: Mapping[str, Any],
    key: str,
    default: bool,
) -> bool:
    raw = mapping.get(key)
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


@dataclass(frozen=True)
class QuotedMessageParserSettings:
    max_component_chain_depth: int = _DEFAULT_MAX_COMPONENT_CHAIN_DEPTH
    max_forward_node_depth: int = _DEFAULT_MAX_FORWARD_NODE_DEPTH
    max_forward_fetch: int = _DEFAULT_MAX_FORWARD_FETCH
    warn_on_action_failure: bool = False

    def with_overrides(
        self,
        overrides: Mapping[str, Any] | None = None,
    ) -> QuotedMessageParserSettings:
        if not overrides:
            return self
        return QuotedMessageParserSettings(
            max_component_chain_depth=_read_int_mapping(
                overrides,
                "max_component_chain_depth",
                self.max_component_chain_depth,
            ),
            max_forward_node_depth=_read_int_mapping(
                overrides,
                "max_forward_node_depth",
                self.max_forward_node_depth,
            ),
            max_forward_fetch=_read_int_mapping(
                overrides,
                "max_forward_fetch",
                self.max_forward_fetch,
            ),
            warn_on_action_failure=_read_bool_mapping(
                overrides,
                "warn_on_action_failure",
                self.warn_on_action_failure,
            ),
        )


SETTINGS = QuotedMessageParserSettings()
