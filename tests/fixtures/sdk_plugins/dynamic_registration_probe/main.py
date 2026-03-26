from pathlib import Path

from astrbot_sdk import Context, Star, acknowledge_global_mcp_risk
from astrbot_sdk.decorators import provide_capability


@acknowledge_global_mcp_risk
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

    @staticmethod
    def _mcp_payload(record) -> dict | None:
        if record is None:
            return None
        return {
            "name": record.name,
            "scope": record.scope.value,
            "active": record.active,
            "running": record.running,
            "config": dict(record.config),
            "tools": list(record.tools),
            "errlogs": list(record.errlogs),
            "last_error": record.last_error,
        }

    @provide_capability(
        "dynamic_probe.skill.register",
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
        "dynamic_probe.skill.list",
        description="List registered probe skills through ctx.skills",
    )
    async def list_skill_capability(self, payload: dict, ctx: Context) -> dict:
        del payload
        items = await ctx.skills.list()
        return {"skills": [self._skill_payload(item) for item in items]}

    @provide_capability(
        "dynamic_probe.skill.unregister",
        description="Unregister the probe skill through ctx.skills",
    )
    async def unregister_skill_capability(self, payload: dict, ctx: Context) -> dict:
        removed = await ctx.skills.unregister(
            str(payload.get("name", "dynamic_probe.runtime_probe"))
        )
        return {"removed": bool(removed)}

    @provide_capability(
        "dynamic_probe.mcp.global.register",
        description="Register a global MCP server through ctx.mcp",
    )
    async def register_global_mcp_capability(self, payload: dict, ctx: Context) -> dict:
        record = await ctx.mcp.register_global_server(
            str(payload.get("name", "probe-global")),
            dict(payload.get("config", {"mock_tools": ["inspect"]})),
            timeout=float(payload.get("timeout", 0.2)),
        )
        return {"server": self._mcp_payload(record)}

    @provide_capability(
        "dynamic_probe.mcp.global.get",
        description="Get a global MCP server through ctx.mcp",
    )
    async def get_global_mcp_capability(self, payload: dict, ctx: Context) -> dict:
        record = await ctx.mcp.get_global_server(
            str(payload.get("name", "probe-global"))
        )
        return {"server": self._mcp_payload(record)}

    @provide_capability(
        "dynamic_probe.mcp.global.list",
        description="List global MCP servers through ctx.mcp",
    )
    async def list_global_mcp_capability(self, payload: dict, ctx: Context) -> dict:
        del payload
        records = await ctx.mcp.list_global_servers()
        return {"servers": [self._mcp_payload(record) for record in records]}

    @provide_capability(
        "dynamic_probe.mcp.global.disable",
        description="Disable a global MCP server through ctx.mcp",
    )
    async def disable_global_mcp_capability(self, payload: dict, ctx: Context) -> dict:
        record = await ctx.mcp.disable_global_server(
            str(payload.get("name", "probe-global"))
        )
        return {"server": self._mcp_payload(record)}

    @provide_capability(
        "dynamic_probe.mcp.global.enable",
        description="Enable a global MCP server through ctx.mcp",
    )
    async def enable_global_mcp_capability(self, payload: dict, ctx: Context) -> dict:
        record = await ctx.mcp.enable_global_server(
            str(payload.get("name", "probe-global")),
            timeout=float(payload.get("timeout", 0.2)),
        )
        return {"server": self._mcp_payload(record)}

    @provide_capability(
        "dynamic_probe.mcp.global.unregister",
        description="Unregister a global MCP server through ctx.mcp",
    )
    async def unregister_global_mcp_capability(
        self,
        payload: dict,
        ctx: Context,
    ) -> dict:
        record = await ctx.mcp.unregister_global_server(
            str(payload.get("name", "probe-global"))
        )
        return {"server": self._mcp_payload(record)}
