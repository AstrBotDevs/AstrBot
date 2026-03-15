"""Agent Runner Registry.

Provides a global registry that allows plugins to register custom
third-party Agent Runners at runtime.  Built-in runners (Dify, Coze,
DashScope, DeerFlow) are still dispatched via the static if/elif chain
in ``third_party.py``; this registry is the *fallback* path for
plugin-provided runners.

Dynamic WebUI integration
~~~~~~~~~~~~~~~~~~~~~~~~~
When a runner is registered the registry injects the corresponding
``options`` / ``labels`` entry into ``CONFIG_METADATA_3`` so that the
dashboard dropdown automatically reflects the new runner type.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from astrbot.core.agent.runners.base import BaseAgentRunner

logger = logging.getLogger("astrbot")


@dataclass
class AgentRunnerEntry:
    """Descriptor for a plugin-provided agent runner."""

    runner_type: str
    """Unique identifier used in ``agent_runner_type`` config, e.g. ``"maibot"``."""

    runner_cls: type[BaseAgentRunner]
    """Concrete ``BaseAgentRunner`` subclass to instantiate."""

    provider_id_key: str
    """Config key that stores the selected provider ID,
    e.g. ``"maibot_agent_runner_provider_id"``."""

    display_name: str
    """Human-readable label shown in the WebUI dropdown."""

    on_initialize: Callable[..., Awaitable[None]] | None = None
    """Optional async callback invoked once when the pipeline stage initialises
    (for pre-connection, tool sync, etc.)."""

    conversation_id_key: str | None = None
    """If the runner manages its own conversation state, the sp key used
    to store the conversation/thread id.  ``None`` means no such state."""

    provider_config_fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    """Extra provider config field definitions to inject into
    CONFIG_METADATA_2, keyed by field name.
    e.g. ``{"maibot_ws_url": {"description": "MaiBot WebSocket URL", "type": "string", ...}}``
    """


class AgentRunnerRegistry:
    """Global singleton that holds all plugin-registered runner entries."""

    def __init__(self) -> None:
        self._entries: dict[str, AgentRunnerEntry] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, entry: AgentRunnerEntry) -> None:
        """Register an agent runner entry (and inject into WebUI config)."""
        if entry.runner_type in self._entries:
            logger.warning(
                "Replacing existing agent runner registration: %s",
                entry.runner_type,
            )

        self._entries[entry.runner_type] = entry
        self._inject_config_metadata(entry)
        logger.info(
            "Registered agent runner: %s (%s)",
            entry.runner_type,
            entry.display_name,
        )

    def unregister(self, runner_type: str) -> None:
        """Remove an agent runner entry (and clean up WebUI config)."""
        entry = self._entries.pop(runner_type, None)
        if entry:
            self._remove_config_metadata(entry)
            logger.info("Unregistered agent runner: %s", runner_type)

    def get(self, runner_type: str) -> AgentRunnerEntry | None:
        return self._entries.get(runner_type)

    def get_all(self) -> dict[str, AgentRunnerEntry]:
        return dict(self._entries)

    # ------------------------------------------------------------------
    # WebUI config injection helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _inject_config_metadata(entry: AgentRunnerEntry) -> None:
        """Mutate CONFIG_METADATA_3 to add the runner option."""
        try:
            from astrbot.core.config.astrbot_config import AstrBotConfig
            from astrbot.core.config.default import (
                CONFIG_METADATA_2,
                CONFIG_METADATA_3,
            )

            # --- CONFIG_METADATA_3: agent_runner dropdown ---
            agent_runner_section = (
                CONFIG_METADATA_3.get("ai_group", {})
                .get("metadata", {})
                .get("agent_runner", {})
                .get("items", {})
            )
            runner_type_field = agent_runner_section.get(
                "provider_settings.agent_runner_type",
            )
            if runner_type_field:
                options: list = runner_type_field.setdefault("options", [])
                labels: list = runner_type_field.setdefault("labels", [])
                if entry.runner_type not in options:
                    options.append(entry.runner_type)
                    labels.append(entry.display_name)

            # --- CONFIG_METADATA_3: provider_id selector ---
            prov_id_config_key = f"provider_settings.{entry.provider_id_key}"
            if prov_id_config_key not in agent_runner_section:
                agent_runner_section[prov_id_config_key] = {
                    "description": f"{entry.display_name} Agent 执行器提供商 ID",
                    "type": "string",
                    "_special": f"select_agent_runner_provider:{entry.runner_type}",
                    "condition": {
                        "provider_settings.agent_runner_type": entry.runner_type,
                        "provider_settings.enable": True,
                    },
                }

            # --- CONFIG_METADATA_2: provider_settings schema ---
            prov_settings_schema = (
                CONFIG_METADATA_2.get("provider_group", {})
                .get("metadata", {})
                .get("provider_settings", {})
                .get("items", {})
            )
            if (
                prov_settings_schema
                and entry.provider_id_key not in prov_settings_schema
            ):
                prov_settings_schema[entry.provider_id_key] = {
                    "type": "string",
                }

            # --- CONFIG_METADATA_2: extra provider config fields ---
            provider_schema = (
                CONFIG_METADATA_2.get("provider_group", {})
                .get("metadata", {})
                .get("provider", {})
                .get("items", {})
            )
            if provider_schema and entry.provider_config_fields:
                for field_name, field_def in entry.provider_config_fields.items():
                    if field_name not in provider_schema:
                        provider_schema[field_name] = field_def

            # --- Dynamic key registration ---
            # Tell config migration to preserve this key.
            AstrBotConfig.register_dynamic_key(
                f"provider_settings.{entry.provider_id_key}"
            )

            # --- CONFIG_METADATA_2: provider config_template ---
            provider_config_template = (
                CONFIG_METADATA_2.get("provider_group", {})
                .get("metadata", {})
                .get("provider", {})
                .get("config_template", {})
            )
            if entry.display_name not in provider_config_template:
                template: dict[str, Any] = {
                    "id": entry.runner_type,
                    "provider": entry.runner_type,
                    "type": entry.runner_type,
                    "provider_type": "agent_runner",
                    "enable": True,
                }
                for field_name, field_def in entry.provider_config_fields.items():
                    template[field_name] = field_def.get("default", "")
                provider_config_template[entry.display_name] = template

        except Exception:
            logger.warning(
                "Failed to inject config metadata for runner %s",
                entry.runner_type,
                exc_info=True,
            )

    @staticmethod
    def _remove_config_metadata(entry: AgentRunnerEntry) -> None:
        """Reverse the injection when a runner is unregistered."""
        try:
            from astrbot.core.config.astrbot_config import AstrBotConfig
            from astrbot.core.config.default import (
                CONFIG_METADATA_2,
                CONFIG_METADATA_3,
            )

            agent_runner_section = (
                CONFIG_METADATA_3.get("ai_group", {})
                .get("metadata", {})
                .get("agent_runner", {})
                .get("items", {})
            )
            runner_type_field = agent_runner_section.get(
                "provider_settings.agent_runner_type",
            )
            if runner_type_field:
                options: list = runner_type_field.get("options", [])
                labels: list = runner_type_field.get("labels", [])
                if entry.runner_type in options:
                    idx = options.index(entry.runner_type)
                    options.pop(idx)
                    if idx < len(labels):
                        labels.pop(idx)

            prov_id_config_key = f"provider_settings.{entry.provider_id_key}"
            agent_runner_section.pop(prov_id_config_key, None)

            prov_settings_schema = (
                CONFIG_METADATA_2.get("provider_group", {})
                .get("metadata", {})
                .get("provider_settings", {})
                .get("items", {})
            )
            if prov_settings_schema:
                prov_settings_schema.pop(entry.provider_id_key, None)

            provider_schema = (
                CONFIG_METADATA_2.get("provider_group", {})
                .get("metadata", {})
                .get("provider", {})
                .get("items", {})
            )
            if provider_schema and entry.provider_config_fields:
                for field_name in entry.provider_config_fields:
                    provider_schema.pop(field_name, None)

            # --- CONFIG_METADATA_2: config_template cleanup ---
            provider_config_template = (
                CONFIG_METADATA_2.get("provider_group", {})
                .get("metadata", {})
                .get("provider", {})
                .get("config_template", {})
            )
            provider_config_template.pop(entry.display_name, None)

            # --- Dynamic key unregister ---
            AstrBotConfig.unregister_dynamic_key(
                f"provider_settings.{entry.provider_id_key}"
            )

        except Exception:
            logger.warning(
                "Failed to remove config metadata for runner %s",
                entry.runner_type,
                exc_info=True,
            )


# Module-level singleton
agent_runner_registry = AgentRunnerRegistry()
