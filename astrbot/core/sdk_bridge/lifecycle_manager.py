from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from astrbot.core import logger

if TYPE_CHECKING:
    from .plugin_bridge import SdkPluginBridge


class SdkPluginLifecycleManager:
    def __init__(self, *, bridge: SdkPluginBridge) -> None:
        self.bridge = bridge
        self._reload_lock = asyncio.Lock()
        self._startup_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self.bridge._started:
            return
        self.bridge._sweep_stale_mcp_leases()
        self.bridge._started = True
        self._schedule_background_reload(reset_restart_budget=True)

    async def stop(self) -> None:
        if not self.bridge._started and not self.bridge._records:
            return
        self.bridge._stopping = True
        if self._startup_task is not None:
            self._startup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._startup_task
            self._startup_task = None
        for plugin_id in list(self.bridge._records.keys()):
            await self.bridge._cancel_plugin_requests(plugin_id)
            await self.bridge._close_temporary_mcp_sessions(plugin_id)
        for record in list(self.bridge._records.values()):
            await self.bridge._shutdown_local_mcp_servers(record)
            if record.session is not None:
                await record.session.stop()
                record.session = None
        self.bridge._records.clear()
        self.bridge._request_contexts.clear()
        self.bridge._request_id_to_token.clear()
        self.bridge._request_plugin_ids.clear()
        for overlay in list(self.bridge._request_overlays.values()):
            if overlay.cleanup_task is not None:
                overlay.cleanup_task.cancel()
        self.bridge._request_overlays.clear()
        self.bridge._plugin_requests.clear()
        self.bridge._http_routes.clear()
        self.bridge._session_waiters.clear()
        self.bridge._schedule_job_ids.clear()
        self.bridge._temporary_mcp_sessions.clear()
        self.bridge._started = False
        self.bridge._stopping = False

    async def reload_all(self, *, reset_restart_budget: bool = False) -> None:
        async with self._reload_lock:
            discovered = self.bridge._discover_plugins()
            self.bridge._set_discovery_issues(discovered.issues)
            self.bridge.env_manager.plan(discovered.plugins)
            known = {plugin.name for plugin in discovered.plugins}
            self.bridge._make_skill_manager().prune_sdk_plugin_skills(known)
            for plugin_id in list(self.bridge._records.keys()):
                if plugin_id not in known:
                    await self.bridge._teardown_plugin(plugin_id)
                    self.bridge._records.pop(plugin_id, None)
            for load_order, plugin in enumerate(discovered.plugins):
                await self.bridge._load_or_reload_plugin(
                    plugin,
                    load_order=load_order,
                    reset_restart_budget=reset_restart_budget,
                )
            await self.bridge._refresh_native_platform_commands({"telegram"})

    async def reload_plugin(self, plugin_id: str) -> None:
        async with self._reload_lock:
            discovered = self.bridge._discover_plugins()
            self.bridge._set_discovery_issues(discovered.issues)
            self.bridge.env_manager.plan(discovered.plugins)
            for load_order, plugin in enumerate(discovered.plugins):
                if plugin.name != plugin_id:
                    continue
                await self.bridge._load_or_reload_plugin(
                    plugin,
                    load_order=load_order,
                    reset_restart_budget=True,
                )
                await self.bridge._refresh_native_platform_commands({"telegram"})
                return
            raise ValueError(f"SDK plugin not found: {plugin_id}")

    async def turn_off_plugin(self, plugin_id: str) -> None:
        async with self._reload_lock:
            record = self.bridge._records.get(plugin_id)
            if record is None:
                raise ValueError(f"SDK plugin not found: {plugin_id}")
            record.state = self.bridge.SDK_STATE_DISABLED
            await self.bridge._cancel_plugin_requests(plugin_id)
            await self.bridge._teardown_plugin(plugin_id)
            record.failure_reason = ""
            self.bridge._set_disabled_override(plugin_id, disabled=True)
            await self.bridge._refresh_native_platform_commands({"telegram"})

    async def turn_on_plugin(self, plugin_id: str) -> None:
        async with self._reload_lock:
            discovered = self.bridge._discover_plugins()
            self.bridge._set_discovery_issues(discovered.issues)
            self.bridge.env_manager.plan(discovered.plugins)
            for load_order, plugin in enumerate(discovered.plugins):
                if plugin.name != plugin_id:
                    continue
                self.bridge._set_disabled_override(plugin_id, disabled=False)
                await self.bridge._load_or_reload_plugin(
                    plugin,
                    load_order=load_order,
                    reset_restart_budget=True,
                )
                await self.bridge._refresh_native_platform_commands({"telegram"})
                return
            raise ValueError(f"SDK plugin not found: {plugin_id}")

    async def handle_worker_closed(self, plugin_id: str) -> None:
        async with self._reload_lock:
            if self.bridge._stopping:
                return
            await self.bridge._cancel_plugin_requests(plugin_id)
            await self.bridge._close_temporary_mcp_sessions(plugin_id)
            record = self.bridge._records.get(plugin_id)
            if record is None:
                return
            await self.bridge._shutdown_local_mcp_servers(record)
            record.session = None
            if record.state in {
                self.bridge.SDK_STATE_RELOADING,
                self.bridge.SDK_STATE_DISABLED,
            }:
                return
            if not record.restart_attempted:
                record.restart_attempted = True
                logger.warning(
                    "SDK plugin worker closed unexpectedly, retrying once: %s",
                    plugin_id,
                )
                await self.bridge._load_or_reload_plugin(
                    record.plugin,
                    load_order=record.load_order,
                    reset_restart_budget=False,
                )
                return
            record.state = self.bridge.SDK_STATE_FAILED
            self.bridge._http_routes.pop(plugin_id, None)
            self.bridge._session_waiters.pop(plugin_id, None)
            await self.bridge._unregister_schedule_jobs(plugin_id)
            await self.bridge._clear_plugin_skills(
                plugin_id=plugin_id,
                record=record,
                reason="worker failure cleanup",
            )

    def _schedule_background_reload(self, *, reset_restart_budget: bool) -> None:
        if self._startup_task is not None and not self._startup_task.done():
            return
        self._startup_task = asyncio.create_task(
            self._background_reload(reset_restart_budget=reset_restart_budget),
            name="sdk_plugin_bridge_startup",
        )

    async def _background_reload(self, *, reset_restart_budget: bool) -> None:
        try:
            await self.reload_all(reset_restart_budget=reset_restart_budget)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("SDK plugin background startup failed: %s", exc, exc_info=True)
        finally:
            self._startup_task = None
