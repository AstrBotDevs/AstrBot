"""Manage reusable AgentConfig resources independently of running sessions."""

from __future__ import annotations

from uuid import uuid4

from astrbot.core.agent.config import StoredAgentConfig
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.dashboard.responses import ApiError


class AgentConfigService:
    def __init__(self, core: AstrBotCoreLifecycle) -> None:
        self.core = core

    async def validate(self, agent: dict, *, delegated: bool = False) -> dict:
        """Normalize runtime configuration and check its persistent references.

        Args:
            agent: Runtime selection and configuration.
            delegated: Whether reusable-agent defaults apply.

        Returns:
            A validated runtime selection and detached configuration.

        Raises:
            ValueError: If the runtime or a referenced configuration is missing.
        """
        host = self.core.star_context
        runtime_name = agent["runtime"]
        runtime = host.agent_runtimes.get(runtime_name)
        if runtime is None:
            raise ValueError(f"Agent runtime unavailable: {runtime_name}")
        config = runtime.normalize_config(agent.get("config", {}), delegated=delegated)
        for config_id in runtime.referenced_config_ids(config):
            await host.agent_configs.get(config_id)
        return {"runtime": runtime_name, "config": config}

    async def list(self) -> list[dict]:
        """Return saved configurations, including unavailable runtimes.

        Returns:
            Persisted configuration resources.
        """
        return [
            item.model_dump()
            for item in await self.core.star_context.agent_configs.list()
        ]

    async def save(self, data: dict, config_id: str | None = None) -> dict:
        """Create or update one configuration under the shared resource lock.

        Args:
            data: Validated request fields.
            config_id: Existing ID, or None to create a new resource.

        Returns:
            The persisted configuration resource.
        """
        store = self.core.star_context.agent_configs
        async with store.lock:
            if config_id is not None:
                await store.get(config_id)
            agent = await self.validate(
                {"runtime": data["runtime"], "config": data.get("config", {})},
                delegated=True,
            )
            record = StoredAgentConfig(
                **agent,
                config_id=config_id or str(uuid4()),
                name=data["name"],
                description=data.get("description", ""),
                enabled=data.get("enabled", True),
            )
            return (await store.save(record)).model_dump()

    async def delete(self, config_id: str) -> None:
        """Reject deletion of configurations still referenced by persisted settings.

        Args:
            config_id: Resource to delete.

        Raises:
            ApiError: If any profile or stored configuration references it.
            ValueError: If the resource is missing.
        """
        host = self.core.star_context
        async with host.agent_configs.lock:
            await host.agent_configs.get(config_id)
            references = []
            for profile_id, profile in self.core.astrbot_config_mgr.confs.items():
                agent = profile.get("agent", {})
                runtime = host.agent_runtimes.get(agent.get("runtime"))
                if runtime is not None and config_id in runtime.referenced_config_ids(
                    agent.get("config", {})
                ):
                    references.append({"type": "profile", "id": profile_id})
            for agent in await host.agent_configs.list():
                runtime = host.agent_runtimes.get(agent.runtime)
                if (
                    agent.config_id != config_id
                    and runtime is not None
                    and config_id in runtime.referenced_config_ids(agent.config)
                ):
                    references.append(
                        {
                            "type": "agent_config",
                            "id": agent.config_id,
                            "name": agent.name,
                        }
                    )
            if references:
                raise ApiError(
                    "Agent configuration is still referenced",
                    status_code=409,
                    data={"references": references},
                )
            await host.agent_configs.delete(config_id)

    def runtimes(self) -> list[dict]:
        """Describe callable runtimes and their reusable-agent defaults.

        Returns:
            Runtime names and default configuration objects.
        """
        return [
            {"runtime": name, "config": runtime.normalize_config({}, delegated=True)}
            for name, runtime in self.core.star_context.agent_runtimes.items()
        ]
