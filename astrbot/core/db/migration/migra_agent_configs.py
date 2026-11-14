"""Import legacy expert definitions before removing their configuration source."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from astrbot.core.agent.config import StoredAgentConfig
from astrbot.core.agent.config_store import AgentConfigStore
from astrbot.core.config.agent import normalize_agent

if TYPE_CHECKING:
    from astrbot.core.config.astrbot_config import AstrBotConfig
    from astrbot.core.db import BaseDatabase


async def migrate_agent_configs(db: BaseDatabase, configs: list[AstrBotConfig]) -> None:
    """Import staged legacy agents after all configuration profiles are migrated.

    Args:
        db: Initialized database receiving reusable agent configurations.
        configs: Loaded and persisted profiles, with the default profile first.

    Raises:
        ValueError: If a staged migration does not contain a configuration object.
        OSError: If a staged source cannot be read or removed.
    """
    if not configs:
        return
    source = Path(configs[0].config_path).with_suffix(".subagents-migration.json")
    if source.exists():
        with source.open(encoding="utf-8") as source_file:
            legacy = json.load(source_file)
        if not isinstance(legacy, dict):
            raise ValueError("Pending subagent migration must contain an object")
        store = AgentConfigStore(db)
        existing = {item.config_id for item in await store.list()}
        for item in legacy.get("agents", []):
            config_id = str(
                uuid5(NAMESPACE_URL, "astrbot:agent-config:" + item["name"])
            )
            if config_id in existing:
                continue
            agent_config = normalize_agent(
                {
                    "runtime": "astrbot",
                    "config": {
                        "model": {"provider_id": item.get("provider_id") or ""},
                        "persona": {
                            "persona_id": item.get("persona_id") or "",
                            "system_prompt": item.get("system_prompt", ""),
                            "tools": item.get("tools", []),
                        },
                        "misc": {"max_steps": legacy.get("max_steps", 30)},
                    },
                },
                delegated=True,
            )
            await store.save(
                StoredAgentConfig(
                    config_id=config_id,
                    name=item["name"],
                    description=item.get("public_description", ""),
                    enabled=item.get("enabled", True),
                    **agent_config,
                )
            )
    # Keep the shared default source until profile cleanup also succeeds.
    # Stable IDs let a restart resume partial imports without replacing edits.
    for profile in [*configs[1:], configs[0]]:
        Path(profile.config_path).with_suffix(".subagents-migration.json").unlink(
            missing_ok=True
        )
