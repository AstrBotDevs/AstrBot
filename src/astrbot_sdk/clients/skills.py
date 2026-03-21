from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._proxy import CapabilityProxy


@dataclass(slots=True)
class SkillRegistration:
    name: str
    description: str
    path: str
    skill_dir: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillRegistration:
        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "") or ""),
            path=str(data.get("path", "")),
            skill_dir=str(data.get("skill_dir", "")),
        )


class SkillClient:
    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def register(
        self,
        *,
        name: str,
        path: str,
        description: str = "",
    ) -> SkillRegistration:
        output = await self._proxy.call(
            "skill.register",
            {
                "name": name,
                "path": path,
                "description": description,
            },
        )
        return SkillRegistration.from_dict(output)

    async def unregister(self, name: str) -> bool:
        output = await self._proxy.call("skill.unregister", {"name": name})
        return bool(output.get("removed", False))

    async def list(self) -> list[SkillRegistration]:
        output = await self._proxy.call("skill.list", {})
        return [
            SkillRegistration.from_dict(item)
            for item in output.get("skills", [])
            if isinstance(item, dict)
        ]


__all__ = ["SkillClient", "SkillRegistration"]
