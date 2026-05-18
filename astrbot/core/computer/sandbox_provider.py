from __future__ import annotations

from typing import Any, Protocol

from astrbot.core.computer.booters.base import ComputerBooter
from astrbot.core.star.context import Context


class SandboxProvider(Protocol):
    """Protocol for plugin-provided sandbox runtime providers.

    Required attributes:
        provider_id: Unique provider identifier (e.g. "browser", "python_sandbox").
        capabilities: Set of capability strings (e.g. {"shell", "python", "gui"}).
        tool_names: Set of tool names this provider contributes to the LLM.

    Optional attributes (core uses ``getattr`` with safe fallbacks):
        provider_api_version: Provider API compatibility version. Defaults to "1.0".
        system_prompt: Runtime-specific instructions exposed in provider metadata.
        plugin_config: Plugin-specific configuration dict.  Implementations are
            encouraged to accept this as an ``__init__`` parameter so the
            provider is fully initialized at construction time.
        auto_sync_skills: If ``False``, core will skip automatic skill sync after
            booting a sandbox for this provider. Defaults to ``True``.
        default_retention_policy: Default lifecycle policy for new managed
            sandboxes. Defaults to ``temporary``.
    """

    provider_id: str
    capabilities: set[str]
    tool_names: set[str]
    system_prompt: str = ""
    plugin_config: dict[str, Any] | None = None
    provider_api_version: str = "1.0"
    auto_sync_skills: bool = True
    supports_persistent_reconnect: bool = False
    default_retention_policy: str = "temporary"

    def build_create_config(self, context: Context, session_id: str) -> dict: ...

    def build_connect_info(self, sandbox_name: str, config: dict) -> dict: ...

    def update_connect_info(self, record: dict, *, sandbox_name: str) -> dict: ...

    async def create_booter(
        self,
        context: Context,
        session_id: str,
        sandbox_id: str,
        config: dict,
    ) -> ComputerBooter: ...

    async def destroy_booter(self, booter: ComputerBooter, record: dict) -> None: ...

    # Optional lifecycle hooks -- core checks ``hasattr`` before invoking.

    async def on_sandbox_created(self, record: dict) -> None:
        """Called after a sandbox is successfully created and leased."""

    async def on_sandbox_destroyed(self, record: dict) -> None:
        """Called after a sandbox is destroyed and removed from registry."""
