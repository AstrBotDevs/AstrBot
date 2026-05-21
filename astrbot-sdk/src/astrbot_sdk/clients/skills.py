"""技能注册客户端。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._errors import wrap_client_exception
from ._proxy import CapabilityProxy


@dataclass(slots=True)
class SkillRegistration:
    """已注册技能的元数据。"""

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
    """技能管理能力客户端。"""

    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def register(
        self,
        *,
        name: str,
        path: str,
        description: str = "",
    ) -> SkillRegistration:
        try:
            output = await self._proxy.call(
                "skill.register",
                {
                    "name": name,
                    "path": path,
                    "description": description,
                },
            )
        except Exception as exc:
            raise wrap_client_exception(
                client_name="SkillClient",
                method_name="register",
                details=f"name={name!r}, path={path!r}",
                exc=exc,
            ) from exc
        return SkillRegistration.from_dict(output)

    async def unregister(self, name: str) -> bool:
        try:
            output = await self._proxy.call("skill.unregister", {"name": name})
        except Exception as exc:
            raise wrap_client_exception(
                client_name="SkillClient",
                method_name="unregister",
                details=f"name={name!r}",
                exc=exc,
            ) from exc
        return bool(output.get("removed", False))

    async def list(self) -> list[SkillRegistration]:
        try:
            output = await self._proxy.call("skill.list", {})
        except Exception as exc:
            raise wrap_client_exception(
                client_name="SkillClient",
                method_name="list",
                exc=exc,
            ) from exc
        return [
            SkillRegistration.from_dict(item)
            for item in output.get("skills", [])
            if isinstance(item, dict)
        ]


__all__ = ["SkillClient", "SkillRegistration"]
