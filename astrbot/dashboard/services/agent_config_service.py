"""Manage reusable AgentConfig resources independently of running sessions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING
from uuid import uuid4

from astrbot.core.agent.config import StoredAgentConfig
from astrbot.core.agent.config_store import AgentConfigStore
from astrbot.core.agent.runtime import AgentRuntime
from astrbot.dashboard.responses import ApiError

if TYPE_CHECKING:
    from astrbot.core.astrbot_config_mgr import AstrBotConfigManager


class AgentConfigService:
    def __init__(
        self,
        store: AgentConfigStore,
        runtimes: Mapping[str, AgentRuntime],
        config_manager: AstrBotConfigManager,
    ) -> None:
        """Bind configuration resources without depending on plugin Context.

        Args:
            store: Shared persistent AgentConfig storage and resource lock.
            runtimes: Registered runtimes used for validation and discovery.
            config_manager: Configuration profiles referencing stored AgentConfigs.
        """
        self.store = store
        self._runtimes = runtimes
        self._config_manager = config_manager

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
        runtime_name = agent["runtime"]
        runtime = self._runtimes.get(runtime_name)
        if runtime is None:
            raise ValueError(f"Agent runtime unavailable: {runtime_name}")
        config = runtime.normalize_config(agent.get("config", {}), delegated=delegated)
        for config_id in runtime.referenced_config_ids(config):
            await self.store.get(config_id)
        return {"runtime": runtime_name, "config": config}

    async def list(self) -> list[dict]:
        """Return saved configurations, including unavailable runtimes.

        Returns:
            Persisted configuration resources.
        """
        return [item.model_dump() for item in await self.store.list()]

    async def save(self, data: dict, config_id: str | None = None) -> dict:
        """Create or update one configuration under the shared resource lock.

        Args:
            data: Validated request fields.
            config_id: Existing ID, or None to create a new resource.

        Returns:
            The persisted configuration resource.
        """
        store = self.store
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
        async with self.store.lock:
            await self.store.get(config_id)
            references = []
            for profile_id, profile in self._config_manager.confs.items():
                agent = profile.get("agent", {})
                runtime = self._runtimes.get(agent.get("runtime"))
                if runtime is not None and config_id in runtime.referenced_config_ids(
                    agent.get("config", {})
                ):
                    references.append({"type": "profile", "id": profile_id})
            for agent in await self.store.list():
                runtime = self._runtimes.get(agent.runtime)
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
            await self.store.delete(config_id)

    def runtimes(self) -> list[dict]:
        """Describe callable runtimes and their reusable-agent defaults.

        Returns:
            Runtime names and default configuration objects.
        """
        return [
            {"runtime": name, "config": runtime.normalize_config({}, delegated=True)}
            for name, runtime in self._runtimes.items()
        ]
