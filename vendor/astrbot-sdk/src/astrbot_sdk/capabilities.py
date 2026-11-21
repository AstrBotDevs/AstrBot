from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

_CAPABILITY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)+$")

# Capabilities that are always granted without user authorization. They only
# expose plugin-scoped resources, so the Host grants them implicitly.
DEFAULT_CAPABILITY_IDS = frozenset({"storage.kv", "assets.transfer"})


@dataclass(frozen=True, slots=True)
class CapabilityGrant:
    id: str
    scope: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _CAPABILITY_ID_PATTERN.fullmatch(self.id):
            raise ValueError(f"invalid capability id: {self.id!r}")
        object.__setattr__(self, "scope", MappingProxyType(dict(self.scope)))


class CapabilitySet(Mapping[str, CapabilityGrant]):
    __slots__ = ("_grants",)

    def __init__(
        self,
        grants: Mapping[str, CapabilityGrant] | Iterable[CapabilityGrant] = (),
    ) -> None:
        if isinstance(grants, Mapping):
            values = grants.values()
        else:
            values = grants

        normalized: dict[str, CapabilityGrant] = {}
        for grant in values:
            if grant.id in normalized:
                raise ValueError(f"duplicate capability grant: {grant.id}")
            normalized[grant.id] = grant
        self._grants = MappingProxyType(normalized)

    @classmethod
    def from_ids(cls, *capability_ids: str) -> CapabilitySet:
        return cls(
            CapabilityGrant(id=capability_id) for capability_id in capability_ids
        )

    def has(self, capability_id: str) -> bool:
        return capability_id in self._grants

    def get(
        self,
        capability_id: str,
        default: CapabilityGrant | None = None,
    ) -> CapabilityGrant | None:
        return self._grants.get(capability_id, default)

    def __getitem__(self, capability_id: str) -> CapabilityGrant:
        return self._grants[capability_id]

    def __iter__(self) -> Iterator[str]:
        return iter(self._grants)

    def __len__(self) -> int:
        return len(self._grants)
