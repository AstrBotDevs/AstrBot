from pathlib import Path

from astrbot_sdk import Context, Star
from astrbot_sdk.decorators import provide_capability


class DynamicRegistrationProbe(Star):
    @staticmethod
    def _skill_dir() -> Path:
        return Path(__file__).resolve().parent / "skills" / "runtime_probe"

    @staticmethod
    def _skill_payload(record) -> dict:
        return {
            "name": record.name,
            "description": record.description,
            "path": record.path,
            "skill_dir": record.skill_dir,
        }

    @provide_capability(
        "dynamic_registration_probe.skill.register",
        description="Register the probe skill through ctx.skills",
    )
    async def register_skill_capability(self, payload: dict, ctx: Context) -> dict:
        description = str(payload.get("description", "Runtime probe skill"))
        record = await ctx.skills.register(
            name=str(payload.get("name", "dynamic_probe.runtime_probe")),
            path=str(self._skill_dir()),
            description=description,
        )
        return self._skill_payload(record)

    @provide_capability(
        "dynamic_registration_probe.skill.list",
        description="List registered probe skills through ctx.skills",
    )
    async def list_skill_capability(self, payload: dict, ctx: Context) -> dict:
        del payload
        items = await ctx.skills.list()
        return {"skills": [self._skill_payload(item) for item in items]}

    @provide_capability(
        "dynamic_registration_probe.skill.unregister",
        description="Unregister the probe skill through ctx.skills",
    )
    async def unregister_skill_capability(self, payload: dict, ctx: Context) -> dict:
        removed = await ctx.skills.unregister(
            str(payload.get("name", "dynamic_probe.runtime_probe"))
        )
        return {"removed": bool(removed)}
