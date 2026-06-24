from __future__ import annotations

import asyncio
import inspect
import math
import time
import uuid
from dataclasses import dataclass

from astrbot.api import logger
from astrbot.core.computer.booters.base import ComputerBooter
from astrbot.core.computer.sandbox_models import SandboxRecord, SandboxStatus
from astrbot.core.computer.sandbox_provider import SandboxProvider
from astrbot.core.computer.sandbox_registry import SandboxRegistry
from astrbot.core.computer.sandbox_timeouts import (
    DEFAULT_SANDBOX_LEASE_TIMEOUT_SECONDS,
    expires_at_from_timeout,
    get_provider_sandbox_config,
    idle_cleanup_at_from_record,
    lease_is_active,
    resolve_sandbox_timeout,
)
from astrbot.core.star.context import Context

SANDBOX_LEASE_SECONDS = int(DEFAULT_SANDBOX_LEASE_TIMEOUT_SECONDS)
MAX_SANDBOX_LEASE_ATTEMPTS = 3
MAX_IDLE_DESTROY_ATTEMPTS = 3
SANDBOX_TTL_DESTROY_RETRY_SECONDS = 60


@dataclass(slots=True)
class SandboxIdleState:
    expires_at: float
    task: asyncio.Task


@dataclass(slots=True)
class SandboxExpirationState:
    expires_at: float
    monotonic_expires_at: float
    task: asyncio.Task


class SandboxManager:
    def __init__(
        self,
        *,
        registry: SandboxRegistry,
        providers: dict[str, SandboxProvider],
    ) -> None:
        self.registry = registry
        self.providers = providers
        self.session_booter: dict[str, ComputerBooter] = {}
        self.idle_state: dict[str, SandboxIdleState] = {}
        self.expiration_state: dict[str, SandboxExpirationState] = {}
        self.boot_locks: dict[str, asyncio.Lock] = {}
        self.created_hook_inflight: set[str] = set()
        self.pending_boot_tasks: dict[str, asyncio.Task] = {}
        self.pending_destroy_tasks: dict[str, asyncio.Task] = {}

    def _ensure_unique_sandbox_name(
        self, sandbox_name: str, *, exclude_sandbox_id: str | None = None
    ) -> str:
        normalized_name = str(sandbox_name).strip()
        for record in self.registry.list_sandboxes():
            if record.get("sandbox_id") == exclude_sandbox_id:
                continue
            if str(record.get("sandbox_name") or "").strip() == normalized_name:
                raise RuntimeError(f"Sandbox name '{normalized_name}' already exists")
        return normalized_name

    def _created_sandbox_name(self, sandbox_id: str, sandbox_name: str | None) -> str:
        if sandbox_name is None:
            return sandbox_id
        normalized_name = str(sandbox_name).strip()
        if not normalized_name:
            return sandbox_id
        return self._ensure_unique_sandbox_name(normalized_name)

    def save_registry(self) -> None:
        try:
            self.registry.save()
        except Exception as exc:
            logger.warning("[Computer] Failed to save sandbox registry: %s", exc)
            raise

    async def save_registry_async(self) -> None:
        try:
            await self.registry.save_async()
        except Exception as exc:
            logger.warning("[Computer] Failed to save sandbox registry: %s", exc)
            raise

    async def _defer_lifecycle_task_start(self) -> None:
        # Let the request that queued this lifecycle work finish before a
        # provider boot/destroy path gets a chance to monopolize the event loop.
        await asyncio.sleep(0)

    def _sandbox_boot_lock(self, sandbox_id: str) -> asyncio.Lock:
        lock = self.boot_locks.get(sandbox_id)
        if lock is None:
            lock = asyncio.Lock()
            self.boot_locks[sandbox_id] = lock
        return lock

    def _lease_timeout(self, context: Context | None, session_id: str) -> float:
        sandbox_cfg = get_provider_sandbox_config(context, session_id)
        return resolve_sandbox_timeout(
            sandbox_cfg,
            "sandbox_lease_timeout",
            aliases=("lease_timeout",),
            default=DEFAULT_SANDBOX_LEASE_TIMEOUT_SECONDS,
        )

    def _idle_timeout(self, context: Context | None, session_id: str) -> float:
        sandbox_cfg = get_provider_sandbox_config(context, session_id)
        return resolve_sandbox_timeout(
            sandbox_cfg,
            "sandbox_idle_timeout",
            default=0.0,
        )

    def _expires_at(
        self, context: Context | None, session_id: str, idle_timeout: float
    ) -> float | None:
        if idle_timeout > 0:
            return None
        sandbox_cfg = get_provider_sandbox_config(context, session_id)
        ttl = resolve_sandbox_timeout(
            sandbox_cfg,
            "sandbox_ttl",
            default=0.0,
        )
        return expires_at_from_timeout(ttl)

    def _sandbox_policy_timeouts(
        self, context: Context | None, session_id: str
    ) -> tuple[float, float | None]:
        idle_timeout = self._idle_timeout(context, session_id)
        return idle_timeout, self._expires_at(context, session_id, idle_timeout)

    def _max_sandboxes(self, context: Context | None, session_id: str) -> int:
        sandbox_cfg = get_provider_sandbox_config(context, session_id)
        try:
            max_sandboxes = int(sandbox_cfg.get("max_sandboxes", 10))
        except (TypeError, ValueError):
            return 10
        if max_sandboxes < 0:
            return 0
        return max_sandboxes

    def _ensure_under_max_sandboxes(
        self, context: Context | None, session_id: str
    ) -> None:
        max_sandboxes = self._max_sandboxes(context, session_id)
        if max_sandboxes <= 0:
            return
        managed_count = sum(
            1 for record in self.registry.list_sandboxes() if record.get("managed")
        )
        if managed_count >= max_sandboxes:
            raise RuntimeError(
                f"Sandbox limit reached. Maximum managed sandboxes: {max_sandboxes}."
            )

    def drop_boot_lock(self, sandbox_id: str) -> None:
        self.boot_locks.pop(sandbox_id, None)

    def clear_runtime_state(self, sandbox_id: str) -> None:
        self.session_booter.pop(sandbox_id, None)
        self.clear_idle_state(sandbox_id)
        self.clear_expiration_state(sandbox_id)
        self.created_hook_inflight.discard(sandbox_id)

    def clear_runtime_state_and_drop_lock(self, sandbox_id: str) -> None:
        self.clear_runtime_state(sandbox_id)
        self.drop_boot_lock(sandbox_id)

    def clear_all_runtime_state(self) -> None:
        for sandbox_id in list(self.session_booter):
            self.clear_runtime_state(sandbox_id)
        for sandbox_id in list(self.idle_state):
            self.clear_runtime_state_and_drop_lock(sandbox_id)
        for sandbox_id in list(self.expiration_state):
            self.clear_runtime_state(sandbox_id)
        self.boot_locks.clear()

    async def cancel_pending_boot_task(self, sandbox_id: str) -> None:
        task = self.pending_boot_tasks.pop(sandbox_id, None)
        if task is None:
            return
        task.cancel()
        try:
            done, _pending = await asyncio.wait({task}, timeout=1)
            if not done:
                logger.warning(
                    "[Computer] Timed out waiting for pending sandbox boot task cancellation: %s",
                    sandbox_id,
                )
                return
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning(
                "[Computer] Pending sandbox boot task ended with error for %s: %s",
                sandbox_id,
                exc,
            )

    async def wait_pending_destroy_task(
        self, sandbox_id: str, *, timeout: float | None = 1
    ) -> None:
        task = self.pending_destroy_tasks.get(sandbox_id)
        if task is None:
            return
        try:
            if timeout is None:
                await asyncio.shield(task)
            else:
                await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except TimeoutError:
            if not task.done():
                logger.warning(
                    "[Computer] Timed out waiting for pending sandbox destroy task: %s",
                    sandbox_id,
                )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning(
                "[Computer] Pending sandbox destroy task ended with error for %s: %s",
                sandbox_id,
                exc,
            )
        finally:
            if task.done():
                self.pending_destroy_tasks.pop(sandbox_id, None)

    def get_provider(self, provider_id: str) -> SandboxProvider:
        provider = self.providers.get(provider_id)
        if provider is None:
            raise RuntimeError(f"Provider {provider_id} is not supported")
        return provider

    def build_record_payload(
        self,
        *,
        sandbox_id: str,
        sandbox_name: str,
        session_id: str,
        provider_id: str,
        idle_timeout: float,
        expires_at: float | None,
        connect_info: dict,
        is_default: bool = False,
        status: str = SandboxStatus.RUNNING,
    ) -> dict:
        return {
            "sandbox_id": sandbox_id,
            "sandbox_name": sandbox_name,
            "provider": provider_id,
            "managed": True,
            "created_by_astrbot": True,
            "owner_user_id": session_id,
            "owner_session_id": session_id,
            "connect_info": connect_info,
            "capabilities": sorted(
                getattr(self.get_provider(provider_id), "capabilities", set())
            ),
            "tool_names": sorted(
                getattr(self.get_provider(provider_id), "tool_names", set())
            ),
            "is_default": is_default,
            "idle_timeout": idle_timeout,
            "expires_at": expires_at,
            "status": status,
        }

    def new_sandbox_id(self, provider_id: str) -> str:
        return f"{provider_id}-{uuid.uuid4().hex[:12]}"

    def get_default_sandbox_id(self, provider_id: str) -> str | None:
        default_sandbox_id = self.registry.get_default_sandbox_id(provider_id)
        if default_sandbox_id:
            record = self.registry.get_sandbox(default_sandbox_id)
            if record and record.get("provider") == provider_id:
                return default_sandbox_id
        for record in self.registry.list_sandboxes():
            if record.get("managed") and record.get("provider") == provider_id:
                return record["sandbox_id"]
        return None

    async def booter_available(self, booter: ComputerBooter) -> bool:
        available = getattr(booter, "available", None)
        if available is None:
            return False
        if getattr(available, "__isabstractmethod__", False):
            return False
        result = available() if callable(available) else available
        if inspect.isawaitable(result):
            result = await result
        if result is None:
            return False
        return bool(result)

    def acquire_lease(
        self, sandbox_id: str, session_id: str, *, ttl: float | None = None
    ) -> bool:
        return self.registry.acquire_lease(
            sandbox_id=sandbox_id,
            session_id=session_id,
            user_id=session_id,
            ttl=DEFAULT_SANDBOX_LEASE_TIMEOUT_SECONDS if ttl is None else ttl,
        )

    def sandbox_has_active_lease(self, sandbox_id: str) -> bool:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None:
            return False
        return lease_is_active(
            record.get("controller_session_id"),
            record.get("lease_expires_at"),
        )

    def _release_expired_lease(self, record: dict) -> dict:
        sandbox_id = record.get("sandbox_id")
        controller_session_id = record.get("controller_session_id")
        if not sandbox_id or not controller_session_id:
            return record
        if lease_is_active(controller_session_id, record.get("lease_expires_at")):
            return record
        released = self.registry.release_lease(sandbox_id) or record
        if self.registry.get_current_sandbox_id(controller_session_id) == sandbox_id:
            self.registry.set_current_sandbox_id(controller_session_id, None)
        return released

    def sandbox_controlled_by_other_session(
        self, sandbox_id: str, session_id: str
    ) -> bool:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None:
            return False
        controller_session_id = record.get("controller_session_id")
        if not controller_session_id or controller_session_id == session_id:
            return False
        return lease_is_active(controller_session_id, record.get("lease_expires_at"))

    async def _upsert_new_sandbox_record(
        self, context: Context, session_id: str, provider_id: str, create_config: dict
    ) -> str:
        self._ensure_under_max_sandboxes(context, session_id)
        provider = self.get_provider(provider_id)
        sandbox_id = self.new_sandbox_id(provider_id)
        idle_timeout, expires_at = self._sandbox_policy_timeouts(context, session_id)
        self.registry.upsert_sandbox(
            **self.build_record_payload(
                sandbox_id=sandbox_id,
                sandbox_name=sandbox_id,
                session_id=session_id,
                provider_id=provider_id,
                idle_timeout=idle_timeout,
                expires_at=expires_at,
                connect_info=provider.build_connect_info(
                    sandbox_id,
                    {**create_config, "sandbox_id": sandbox_id},
                ),
            )
        )
        await self.save_registry_async()
        return sandbox_id

    def _find_idle_provider_sandbox_id(
        self, provider_id: str, *, exclude: set[str] | None = None
    ) -> str | None:
        excluded = exclude or set()
        for record in self.registry.list_sandboxes():
            sandbox_id = record.get("sandbox_id")
            if not sandbox_id or sandbox_id in excluded:
                continue
            if not record.get("managed") or record.get("provider") != provider_id:
                continue
            if record.get("status") != SandboxStatus.RUNNING:
                continue
            if self.sandbox_has_active_lease(sandbox_id):
                continue
            if sandbox_id not in self.session_booter:
                continue
            return sandbox_id
        return None

    @staticmethod
    def _sandbox_can_be_bootstrapped(record: dict) -> bool:
        status = record.get("status")
        if status == SandboxStatus.RUNNING:
            return True
        return bool(
            record.get("retention_policy") == "persistent"
            and status == SandboxStatus.UNKNOWN
        )

    async def get_or_create_booter(
        self,
        context: Context,
        session_id: str,
        provider_id: str,
        *,
        exclude_sandbox_ids: set[str] | None = None,
    ) -> ComputerBooter:
        provider = self.get_provider(provider_id)
        create_config = provider.build_create_config(context, session_id)
        idle_timeout, expires_at = self._sandbox_policy_timeouts(context, session_id)
        lease_timeout = self._lease_timeout(context, session_id)

        current_sandbox_id = self.registry.get_current_sandbox_id(session_id)
        current_record = self.registry.get_sandbox(current_sandbox_id)
        excluded_stale_current_ids = set(exclude_sandbox_ids or set())
        if current_sandbox_id and (
            current_record is None or current_record.get("provider") != provider_id
        ):
            if (
                current_record
                and current_record.get("controller_session_id") == session_id
            ):
                self.registry.release_lease(current_sandbox_id)
            self.registry.set_current_sandbox_id(session_id, None)
            await self.save_registry_async()
            current_sandbox_id = None
            current_record = None
        if current_sandbox_id and current_record:
            status = current_record.get("status")
            current_controller_session_id = current_record.get("controller_session_id")
            if status == SandboxStatus.RUNNING and (
                current_controller_session_id != session_id
                or not lease_is_active(
                    current_controller_session_id,
                    current_record.get("lease_expires_at"),
                )
            ):
                self._release_expired_lease(current_record)
                self.registry.set_current_sandbox_id(session_id, None)
                await self.save_registry_async()
                excluded_stale_current_ids.add(current_sandbox_id)
                current_sandbox_id = None
                current_record = None
                status = None
        if current_sandbox_id and current_record:
            status = current_record.get("status")
            if status == SandboxStatus.CREATING:
                pending_boot_task = self.pending_boot_tasks.get(current_sandbox_id)
                if pending_boot_task is not None:
                    await asyncio.shield(pending_boot_task)
                    current_record = self.registry.get_sandbox(current_sandbox_id)
                    status = current_record.get("status") if current_record else None
            if status in {
                SandboxStatus.CREATING,
                SandboxStatus.RESTORING,
                SandboxStatus.STOPPING,
                SandboxStatus.ERROR,
            }:
                if current_record.get("controller_session_id") == session_id:
                    self.registry.release_lease(current_sandbox_id)
                self.registry.set_current_sandbox_id(session_id, None)
                await self.save_registry_async()
                current_sandbox_id = None
                current_record = None
            elif (
                current_record.get("retention_policy") == "persistent"
                and status == SandboxStatus.UNKNOWN
                and current_sandbox_id not in self.session_booter
            ):
                current_record = await self._revive_persistent_booter_if_needed(
                    current_record, current_sandbox_id, session_id, context
                )
        if (
            current_sandbox_id
            and current_record
            and current_record.get("provider") == provider_id
            and current_sandbox_id in self.session_booter
        ):
            if not self.acquire_lease(
                current_sandbox_id, session_id, ttl=lease_timeout
            ):
                self.registry.set_current_sandbox_id(session_id, None)
                await self.save_registry_async()
            else:
                booter = self.session_booter[current_sandbox_id]
                if await self.booter_available(booter):
                    self.registry.touch_sandbox(current_sandbox_id)
                    await self.save_registry_async()
                    self.schedule_lifecycle_cleanup(
                        current_sandbox_id,
                        idle_timeout,
                        current_record.get("expires_at"),
                    )
                    return booter
                self.clear_runtime_state(current_sandbox_id)
                self.registry.release_lease(current_sandbox_id)
                await self.save_registry_async()

        created_target_record = False
        target_sandbox_id = self.get_default_sandbox_id(provider_id)
        if target_sandbox_id in excluded_stale_current_ids:
            target_sandbox_id = None
        target_record = self.registry.get_sandbox(target_sandbox_id)
        if (
            target_sandbox_id
            and target_record
            and target_record.get("provider") == provider_id
            and target_record.get("retention_policy") == "persistent"
            and target_record.get("status") == SandboxStatus.UNKNOWN
        ):
            target_record = await self._revive_persistent_booter_if_needed(
                target_record, target_sandbox_id, session_id, context
            )
        elif target_record and not self._sandbox_can_be_bootstrapped(target_record):
            target_sandbox_id = None

        if target_sandbox_id is None:
            self._ensure_under_max_sandboxes(context, session_id)
            target_sandbox_id = self.new_sandbox_id(provider_id)
            created_target_record = True
            record = self.registry.upsert_sandbox(
                **self.build_record_payload(
                    sandbox_id=target_sandbox_id,
                    sandbox_name=target_sandbox_id,
                    session_id=session_id,
                    provider_id=provider_id,
                    idle_timeout=idle_timeout,
                    expires_at=expires_at,
                    connect_info=provider.build_connect_info(
                        target_sandbox_id,
                        {**create_config, "sandbox_id": target_sandbox_id},
                    ),
                    is_default=True,
                )
            )
            self.registry.set_default_sandbox_id(record["sandbox_id"])
            await self.save_registry_async()

        if self.sandbox_controlled_by_other_session(target_sandbox_id, session_id):
            reusable_sandbox_id = self._find_idle_provider_sandbox_id(
                provider_id, exclude={target_sandbox_id}
            )
            if reusable_sandbox_id is not None:
                target_sandbox_id = reusable_sandbox_id
                created_target_record = False
            else:
                target_sandbox_id = await self._upsert_new_sandbox_record(
                    context, session_id, provider_id, create_config
                )
                created_target_record = True

        for _attempt in range(MAX_SANDBOX_LEASE_ATTEMPTS):
            async with self._sandbox_boot_lock(target_sandbox_id):
                target_record = self.registry.get_sandbox(target_sandbox_id)
                if target_record and not self._sandbox_can_be_bootstrapped(
                    target_record
                ):
                    target_sandbox_id = await self._upsert_new_sandbox_record(
                        context, session_id, provider_id, create_config
                    )
                    created_target_record = True
                    continue

                if target_sandbox_id in self.session_booter and not self.acquire_lease(
                    target_sandbox_id, session_id, ttl=lease_timeout
                ):
                    target_sandbox_id = await self._upsert_new_sandbox_record(
                        context, session_id, provider_id, create_config
                    )
                    created_target_record = True
                    continue

                if target_sandbox_id in self.session_booter:
                    booter = self.session_booter[target_sandbox_id]
                    if await self.booter_available(booter):
                        break
                    self.clear_runtime_state(target_sandbox_id)
                    self.registry.release_lease(target_sandbox_id)
                    self.registry.update_sandbox_status(
                        target_sandbox_id, SandboxStatus.UNKNOWN
                    )
                    await self.save_registry_async()

                if not self.acquire_lease(
                    target_sandbox_id, session_id, ttl=lease_timeout
                ):
                    target_sandbox_id = await self._upsert_new_sandbox_record(
                        context, session_id, provider_id, create_config
                    )
                    created_target_record = True
                    continue

                try:
                    client = await provider.create_booter(
                        context, session_id, target_sandbox_id, create_config
                    )
                except Exception:
                    if created_target_record:
                        self.registry.delete_sandbox(target_sandbox_id)
                    else:
                        self.registry.release_lease(target_sandbox_id)
                        self.registry.update_sandbox_status(
                            target_sandbox_id, SandboxStatus.UNKNOWN
                        )
                    self.clear_runtime_state(target_sandbox_id)
                    await self.save_registry_async()
                    raise
                setattr(client, "sandbox_id", target_sandbox_id)
                setattr(client, "provider_id", provider_id)
                self.session_booter[target_sandbox_id] = client
                break
        else:
            raise RuntimeError(
                "Could not acquire sandbox lease after multiple attempts"
            )

        await self._finalize_created_booter(
            provider,
            target_sandbox_id,
            session_id=session_id,
            idle_timeout=idle_timeout,
            remove_record_on_failure=created_target_record,
        )
        await self._invoke_sandbox_created_hook(provider, target_sandbox_id)
        return self.session_booter[target_sandbox_id]

    async def _finalize_created_booter(
        self,
        provider: SandboxProvider,
        sandbox_id: str,
        *,
        session_id: str | None = None,
        idle_timeout: float,
        remove_record_on_failure: bool = False,
    ) -> None:
        """Common post-creation steps: persist, idle cleanup, skill sync, hooks."""
        booter = self.session_booter.get(sandbox_id)
        record = self.registry.get_sandbox(sandbox_id) or {}
        update_connect_info_after_boot = getattr(
            provider, "update_connect_info_after_boot", None
        )
        if booter is not None and callable(update_connect_info_after_boot):
            connect_info = update_connect_info_after_boot(record, booter)
            if connect_info is not None:
                self.registry.update_sandbox_config(
                    sandbox_id, connect_info=connect_info
                )
        self.registry.touch_sandbox(sandbox_id)
        self.registry.update_sandbox_status(sandbox_id, SandboxStatus.RUNNING)
        if session_id is not None:
            self.registry.set_current_sandbox_id(session_id, sandbox_id)
        try:
            await self.save_registry_async()
        except Exception:
            if booter is not None:
                try:
                    await provider.destroy_booter(
                        booter, self.registry.get_sandbox(sandbox_id) or {}
                    )
                except Exception as destroy_err:
                    logger.warning(
                        "[Computer] Failed to rollback sandbox %s after registry save error: %s",
                        sandbox_id,
                        destroy_err,
                    )
            self.clear_runtime_state(sandbox_id)
            if remove_record_on_failure:
                self.registry.delete_sandbox(sandbox_id)
            else:
                self.registry.release_lease(sandbox_id)
                self.registry.update_sandbox_status(sandbox_id, SandboxStatus.UNKNOWN)
            if session_id is not None:
                self.registry.set_current_sandbox_id(session_id, None)
            raise
        record = self.registry.get_sandbox(sandbox_id) or {}
        self.schedule_lifecycle_cleanup(
            sandbox_id, idle_timeout, record.get("expires_at")
        )

        # Auto-sync skills unless the provider opts out.  Best-effort: a sync
        # failure is logged but does not destroy the already-created sandbox.
        if getattr(provider, "auto_sync_skills", True):
            booter = self.session_booter.get(sandbox_id)
            if booter is not None and hasattr(booter, "shell"):
                try:
                    await self._sync_skills_to_booter(
                        booter,
                        provider_id=getattr(provider, "provider_id", None),
                    )
                except Exception as sync_err:
                    logger.warning(
                        "[Computer] Auto skill sync failed for %s: %s",
                        sandbox_id,
                        sync_err,
                    )

    async def _invoke_sandbox_created_hook(
        self, provider: SandboxProvider, sandbox_id: str
    ) -> None:
        """Invoke provider's on_sandbox_created hook if present.

        Each sandbox only fires the hook once, guarded by a persistent flag in
        the registry record so that dashboard-created sandboxes still receive
        the hook when they are first leased via switch/takeover.

        The flag is only set on success so that a transient hook failure can
        be retried on the next lease operation.  The check-and-set is protected
        by the sandbox boot lock to prevent duplicate triggers under concurrent
        lease operations.
        """
        if not hasattr(provider, "on_sandbox_created"):
            async with self._sandbox_boot_lock(sandbox_id):
                if not self.registry.has_created_hook_fired(sandbox_id):
                    self.registry.mark_created_hook_fired(sandbox_id)
                    await self.save_registry_async()
            return

        async with self._sandbox_boot_lock(sandbox_id):
            record = self.registry.get_sandbox(sandbox_id) or {}
            if (
                record.get("created_hook_fired")
                or sandbox_id in self.created_hook_inflight
            ):
                return
            self.created_hook_inflight.add(sandbox_id)

        should_mark_fired = False
        try:
            await provider.on_sandbox_created(record)
            should_mark_fired = True
        except Exception as hook_err:
            logger.warning(
                "[Computer] on_sandbox_created hook failed for %s: %s",
                sandbox_id,
                hook_err,
            )
            return
        finally:
            async with self._sandbox_boot_lock(sandbox_id):
                if should_mark_fired:
                    if not self.registry.has_created_hook_fired(sandbox_id):
                        self.registry.mark_created_hook_fired(sandbox_id)
                        await self.save_registry_async()
                self.created_hook_inflight.discard(sandbox_id)

    async def create_sandbox_uncontrolled(
        self,
        context: Context,
        session_id: str,
        provider_id: str,
        sandbox_name: str | None = None,
    ) -> dict:
        provider = self.get_provider(provider_id)
        sandbox_id = self.new_sandbox_id(provider_id)
        sandbox_name = self._created_sandbox_name(sandbox_id, sandbox_name)
        self._ensure_under_max_sandboxes(context, session_id)
        create_config = provider.build_create_config(context, session_id)
        idle_timeout, expires_at = self._sandbox_policy_timeouts(context, session_id)
        async with self._sandbox_boot_lock(sandbox_id):
            record = self.registry.upsert_sandbox(
                **self.build_record_payload(
                    sandbox_id=sandbox_id,
                    sandbox_name=sandbox_name,
                    session_id=session_id,
                    provider_id=provider_id,
                    idle_timeout=idle_timeout,
                    expires_at=expires_at,
                    connect_info=provider.build_connect_info(
                        sandbox_name,
                        {**create_config, "sandbox_id": sandbox_id},
                    ),
                    status=SandboxStatus.CREATING,
                )
            )
            try:
                client = await provider.create_booter(
                    context, session_id, sandbox_id, create_config
                )
            except asyncio.CancelledError:
                self.registry.update_sandbox_status(sandbox_id, SandboxStatus.ERROR)
                self.clear_runtime_state(sandbox_id)
                await self.save_registry_async()
                raise
            except Exception:
                self.registry.update_sandbox_status(sandbox_id, SandboxStatus.ERROR)
                self.clear_runtime_state(sandbox_id)
                await self.save_registry_async()
                raise
            setattr(client, "sandbox_id", sandbox_id)
            setattr(client, "provider_id", provider_id)
            self.session_booter[sandbox_id] = client
            await self._finalize_created_booter(
                provider,
                sandbox_id,
                session_id=None,
                idle_timeout=idle_timeout,
                remove_record_on_failure=True,
            )
            return self.registry.get_sandbox(sandbox_id) or record

    async def create_sandbox_uncontrolled_deferred(
        self,
        context: Context,
        session_id: str,
        provider_id: str,
        sandbox_name: str | None = None,
    ) -> dict:
        provider = self.get_provider(provider_id)
        sandbox_id = self.new_sandbox_id(provider_id)
        sandbox_name = self._created_sandbox_name(sandbox_id, sandbox_name)
        self._ensure_under_max_sandboxes(context, session_id)
        create_config = provider.build_create_config(context, session_id)
        idle_timeout, expires_at = self._sandbox_policy_timeouts(context, session_id)
        async with self._sandbox_boot_lock(sandbox_id):
            record = self.registry.upsert_sandbox(
                **self.build_record_payload(
                    sandbox_id=sandbox_id,
                    sandbox_name=sandbox_name,
                    session_id=session_id,
                    provider_id=provider_id,
                    idle_timeout=idle_timeout,
                    expires_at=expires_at,
                    connect_info=provider.build_connect_info(
                        sandbox_name,
                        {**create_config, "sandbox_id": sandbox_id},
                    ),
                    status=SandboxStatus.CREATING,
                )
            )
            await self.save_registry_async()

        task = asyncio.create_task(
            self._boot_sandbox_uncontrolled_deferred(
                context=context,
                session_id=session_id,
                provider=provider,
                sandbox_id=sandbox_id,
                create_config=create_config,
                idle_timeout=idle_timeout,
            )
        )
        self.pending_boot_tasks[sandbox_id] = task

        return self.registry.get_sandbox(sandbox_id) or record

    async def _boot_sandbox_uncontrolled_deferred(
        self,
        *,
        context: Context,
        session_id: str,
        provider: SandboxProvider,
        sandbox_id: str,
        create_config: dict,
        idle_timeout: float,
    ) -> None:
        try:
            await self._defer_lifecycle_task_start()
            async with self._sandbox_boot_lock(sandbox_id):
                current = self.registry.get_sandbox(sandbox_id)
                if current is None or current.get("status") != SandboxStatus.CREATING:
                    return

                try:
                    client = await provider.create_booter(
                        context, session_id, sandbox_id, create_config
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as boot_err:
                    self.registry.update_sandbox_status(sandbox_id, SandboxStatus.ERROR)
                    await self.save_registry_async()
                    logger.warning(
                        "[Computer] Deferred sandbox boot failed: sandbox_id=%s session_id=%s error=%s",
                        sandbox_id,
                        session_id,
                        boot_err,
                    )
                    return

                current = self.registry.get_sandbox(sandbox_id)
                if current is None or current.get("status") != SandboxStatus.CREATING:
                    try:
                        cleanup_record = self.registry.get_sandbox(sandbox_id) or {}
                        await provider.destroy_booter(client, cleanup_record)
                    except Exception as destroy_err:
                        logger.warning(
                            "[Computer] Deferred sandbox cleanup failed after record removal: sandbox_id=%s error=%s",
                            sandbox_id,
                            destroy_err,
                        )
                    return

                setattr(client, "sandbox_id", sandbox_id)
                setattr(client, "provider_id", provider.provider_id)
                self.session_booter[sandbox_id] = client
                await self._finalize_created_booter(
                    provider,
                    sandbox_id,
                    session_id=None,
                    idle_timeout=idle_timeout,
                    remove_record_on_failure=True,
                )
        finally:
            self.pending_boot_tasks.pop(sandbox_id, None)

    async def create_sandbox(
        self,
        context: Context,
        session_id: str,
        provider_id: str,
        sandbox_name: str | None = None,
    ) -> dict:
        sandbox = await self.create_sandbox_uncontrolled(
            context, session_id, provider_id, sandbox_name
        )
        sandbox_id = sandbox["sandbox_id"]
        lease_timeout = self._lease_timeout(context, session_id)
        if not self.acquire_lease(sandbox_id, session_id, ttl=lease_timeout):
            provider = self.get_provider(sandbox.get("provider", ""))
            await self._destroy_sandbox_cleanup(provider, sandbox_id, sandbox)
            raise RuntimeError(f"Sandbox {sandbox_id} is busy")
        await self._set_current_sandbox_after_lease(session_id, sandbox_id, sandbox)
        provider = self.get_provider(sandbox.get("provider", ""))
        # Reset idle cleanup after lease acquisition.  The uncontrolled
        # creation path already schedules cleanup, but a slow skill-sync or
        # short idle_timeout could let the timer expire before the lease is
        # acquired.  Re-scheduling here guarantees a full idle window.
        idle_timeout = sandbox.get("idle_timeout") or 0
        self.schedule_lifecycle_cleanup(
            sandbox_id, float(idle_timeout), sandbox.get("expires_at")
        )
        await self._invoke_sandbox_created_hook(provider, sandbox_id)
        return self.registry.get_sandbox(sandbox_id) or sandbox

    def list_sandboxes(self) -> list[dict]:
        records = []
        for record in self.registry.list_sandboxes():
            if not record.get("managed"):
                continue
            if "booter_type" in record:
                record = SandboxRecord.from_dict(record).to_dict()
            record = self._release_expired_lease(record)
            provider = self.providers.get(record.get("provider"))
            updated = dict(record)
            updated["capabilities"] = sorted(
                getattr(provider, "capabilities", record.get("capabilities", []))
                if provider
                else record.get("capabilities", [])
            )
            updated["tool_names"] = sorted(
                getattr(provider, "tool_names", record.get("tool_names", []))
                if provider
                else record.get("tool_names", [])
            )
            if self.sandbox_has_active_lease(updated["sandbox_id"]):
                updated["idle_cleanup_at"] = None
            else:
                updated["idle_cleanup_at"] = idle_cleanup_at_from_record(
                    last_used_at=updated.get("last_used_at"),
                    idle_timeout=updated.get("idle_timeout"),
                )
            records.append(updated)
        return records

    async def list_sandboxes_checked(self) -> list[dict]:
        changed = False
        for record in self.registry.list_sandboxes():
            sandbox_id = record.get("sandbox_id")
            if not sandbox_id or not record.get("managed"):
                continue
            booter = self.session_booter.get(sandbox_id)
            if booter is None:
                continue
            try:
                available = await self.booter_available(booter)
            except Exception as exc:
                logger.warning(
                    "[Computer] Sandbox health check failed for %s: %s",
                    sandbox_id,
                    exc,
                )
                available = False
            if available:
                continue
            self.clear_runtime_state_and_drop_lock(sandbox_id)
            next_status = (
                SandboxStatus.UNKNOWN
                if record.get("retention_policy") == "persistent"
                else SandboxStatus.ERROR
            )
            self.registry.update_sandbox_status(sandbox_id, next_status)
            changed = True
        if changed:
            await self.save_registry_async()
        return self.list_sandboxes()

    def set_default_sandbox(self, sandbox_id: str) -> dict:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None or not record.get("managed"):
            raise RuntimeError(f"Sandbox {sandbox_id} not found")
        self.registry.set_default_sandbox_id(sandbox_id)
        self.save_registry()
        return self.registry.get_sandbox(sandbox_id) or record

    def update_sandbox_config(
        self,
        sandbox_id: str,
        *,
        sandbox_name: str | None = None,
        idle_timeout: int | float | None,
        expires_at: int | float | None,
        retention_policy: str,
    ) -> dict:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None or not record.get("managed"):
            raise RuntimeError(f"Sandbox {sandbox_id} not found")
        provider_id = record.get("provider", "")
        provider = self.providers.get(provider_id)
        if retention_policy not in {"temporary", "persistent"}:
            raise RuntimeError("retention_policy must be temporary or persistent")
        if retention_policy == "persistent" and provider is None:
            raise RuntimeError(f"Provider {provider_id} is not available")
        if (
            retention_policy == "persistent"
            and provider is not None
            and not getattr(provider, "supports_persistent_reconnect", False)
        ):
            raise RuntimeError(
                f"Provider {record.get('provider')} does not support persistent sandboxes"
            )
        if retention_policy == "persistent":
            idle_timeout = None
            expires_at = None
        elif idle_timeout and float(idle_timeout) > 0:
            expires_at = None
        updates = {
            "idle_timeout": idle_timeout,
            "expires_at": expires_at,
            "retention_policy": retention_policy,
        }
        if sandbox_name is not None:
            normalized_name = str(sandbox_name).strip()
            if not normalized_name:
                raise ValueError("sandbox_name must be a non-empty string")
            normalized_name = self._ensure_unique_sandbox_name(
                normalized_name, exclude_sandbox_id=sandbox_id
            )
            updates["sandbox_name"] = normalized_name
            if provider is not None:
                updates["connect_info"] = provider.update_connect_info(
                    record,
                    sandbox_name=normalized_name,
                )
        updated = self.registry.update_sandbox_config(sandbox_id, **updates)
        if retention_policy == "persistent":
            self.clear_idle_state(sandbox_id)
            self.clear_expiration_state(sandbox_id)
        else:
            self.schedule_lifecycle_cleanup(
                sandbox_id, float(idle_timeout or 0), expires_at
            )
        self.save_registry()
        return updated or record

    def set_sandbox_retention_policy(
        self,
        context: Context | None,
        session_id: str,
        sandbox_id: str,
        retention_policy: str,
        *,
        sandbox_name: str | None = None,
    ) -> dict:
        idle_timeout: float | None
        expires_at: float | None
        if retention_policy == "persistent":
            idle_timeout = None
            expires_at = None
        else:
            idle_timeout, expires_at = self._sandbox_policy_timeouts(
                context, session_id
            )
        return self.update_sandbox_config(
            sandbox_id,
            sandbox_name=sandbox_name,
            idle_timeout=idle_timeout,
            expires_at=expires_at,
            retention_policy=retention_policy,
        )

    async def _revive_persistent_booter_if_needed(
        self,
        record: dict,
        sandbox_id: str,
        session_id: str | None,
        context: Context | None,
    ) -> dict:
        if (
            context is None
            or record.get("retention_policy") != "persistent"
            or record.get("status")
            not in {SandboxStatus.RUNNING, SandboxStatus.UNKNOWN}
        ):
            return record

        provider = self.get_provider(record.get("provider", ""))
        if not getattr(provider, "supports_persistent_reconnect", False):
            return record

        create_session_id = str(
            record.get("owner_session_id") or session_id or "dashboard"
        )
        create_config = provider.build_create_config(context, create_session_id)
        connect_info = record.get("connect_info") or {}
        create_config = {
            **create_config,
            "persistent_name": str(
                connect_info.get("persistent_name") or sandbox_id
            ).strip(),
            "resume": True,
        }
        existing_runtime_id = connect_info.get("sandbox_id")
        if existing_runtime_id:
            create_config["sandbox_id"] = existing_runtime_id
        existing_host_port = connect_info.get("host_port")
        if existing_host_port:
            create_config["host_port"] = existing_host_port

        async with self._sandbox_boot_lock(sandbox_id):
            current = self.registry.get_sandbox(sandbox_id)
            booter = self.session_booter.get(sandbox_id)
            if (
                booter is None
                and current is not None
                and current.get("status")
                in {
                    SandboxStatus.RUNNING,
                    SandboxStatus.UNKNOWN,
                }
            ):
                previous_status = current.get("status") or SandboxStatus.UNKNOWN
                self.registry.update_sandbox_status(sandbox_id, SandboxStatus.RESTORING)
                await self.save_registry_async()
                try:
                    client = await provider.create_booter(
                        context,
                        create_session_id,
                        sandbox_id,
                        create_config,
                    )
                except asyncio.CancelledError:
                    latest = self.registry.get_sandbox(sandbox_id)
                    if (
                        latest is not None
                        and latest.get("status") == SandboxStatus.RESTORING
                    ):
                        self.registry.update_sandbox_status(sandbox_id, previous_status)
                        await self.save_registry_async()
                    raise
                except Exception:
                    latest = self.registry.get_sandbox(sandbox_id)
                    if (
                        latest is not None
                        and latest.get("status") == SandboxStatus.RESTORING
                    ):
                        self.registry.update_sandbox_status(sandbox_id, previous_status)
                        await self.save_registry_async()
                    raise
                setattr(client, "sandbox_id", sandbox_id)
                setattr(client, "provider_id", provider.provider_id)
                self.session_booter[sandbox_id] = client
                await self._finalize_created_booter(
                    provider,
                    sandbox_id,
                    session_id=None,
                    idle_timeout=(
                        0
                        if record.get("retention_policy") == "persistent"
                        else self._idle_timeout(context, create_session_id)
                    ),
                )
            return self.registry.get_sandbox(sandbox_id) or record

    async def switch_current_sandbox_checked(
        self, session_id: str, sandbox_id: str, context: Context | None = None
    ) -> dict:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None or not record.get("managed"):
            raise RuntimeError(f"Sandbox {sandbox_id} not found")
        record = await self._revive_persistent_booter_if_needed(
            record, sandbox_id, session_id, context
        )
        booter = self.session_booter.get(sandbox_id)
        if booter is None:
            raise RuntimeError(f"Sandbox {sandbox_id} is not running")
        if not await self.booter_available(booter):
            self.session_booter.pop(sandbox_id, None)
            self.registry.update_sandbox_status(sandbox_id, SandboxStatus.UNKNOWN)
            await self.save_registry_async()
            raise RuntimeError(f"Sandbox {sandbox_id} is not running")
        lease_timeout = self._lease_timeout(context, session_id)
        if not self.acquire_lease(sandbox_id, session_id, ttl=lease_timeout):
            raise RuntimeError(f"Sandbox {sandbox_id} is busy")
        result = await self._set_current_sandbox_after_lease(
            session_id, sandbox_id, record
        )
        provider = self.get_provider(record.get("provider", ""))
        await self._invoke_sandbox_created_hook(provider, sandbox_id)
        return result

    async def _set_current_sandbox_after_lease(
        self, session_id: str, sandbox_id: str, record: dict
    ) -> dict:
        previous_sandbox_id = self.registry.get_current_sandbox_id(session_id)
        if previous_sandbox_id and previous_sandbox_id != sandbox_id:
            previous = self.registry.get_sandbox(previous_sandbox_id)
            if previous and previous.get("controller_session_id") == session_id:
                self.registry.release_lease(previous_sandbox_id)
        self.registry.set_current_sandbox_id(session_id, sandbox_id)
        self.registry.touch_sandbox(sandbox_id)
        await self.save_registry_async()
        return self.registry.get_sandbox(sandbox_id) or record

    def get_current_sandbox(
        self, session_id: str, *, include_stale_current_id: bool = False
    ) -> dict:
        sandbox_id = self.registry.get_current_sandbox_id(session_id)
        sandbox = self.registry.get_sandbox(sandbox_id) if sandbox_id else None
        stale_current_sandbox_id = None
        if sandbox:
            controller_session_id = sandbox.get("controller_session_id")
            if controller_session_id != session_id or not lease_is_active(
                controller_session_id, sandbox.get("lease_expires_at")
            ):
                stale_current_sandbox_id = sandbox_id
                self._release_expired_lease(sandbox)
                self.registry.set_current_sandbox_id(session_id, None)
                self.save_registry()
                sandbox_id = None
                sandbox = None
        if sandbox:
            provider = self.providers.get(sandbox.get("provider"))
            if provider:
                sandbox = dict(sandbox)
                sandbox["capabilities"] = sorted(
                    getattr(provider, "capabilities", sandbox.get("capabilities", []))
                )
                sandbox["tool_names"] = sorted(
                    getattr(provider, "tool_names", sandbox.get("tool_names", []))
                )
        result = {
            "current_sandbox_id": sandbox_id,
            "sandbox": sandbox,
        }
        if include_stale_current_id:
            result["stale_current_sandbox_id"] = stale_current_sandbox_id
        return result

    def release_current_sandbox(
        self, session_id: str, sandbox_id: str | None = None
    ) -> dict:
        target_sandbox_id = sandbox_id or self.registry.get_current_sandbox_id(
            session_id
        )
        if target_sandbox_id is None:
            raise RuntimeError("No current sandbox")
        record = self.registry.get_sandbox(target_sandbox_id)
        if record is None:
            raise RuntimeError(f"Sandbox {target_sandbox_id} not found")
        controller_session_id = record.get("controller_session_id")
        if (
            controller_session_id
            and controller_session_id != session_id
            and self.sandbox_has_active_lease(target_sandbox_id)
        ):
            raise RuntimeError(
                f"Sandbox {target_sandbox_id} is controlled by another session"
            )
        released = self.registry.release_lease(target_sandbox_id) or record
        if self.registry.get_current_sandbox_id(session_id) == target_sandbox_id:
            self.registry.set_current_sandbox_id(session_id, None)
        self.save_registry()
        return released

    def force_release_sandbox(self, sandbox_id: str) -> dict:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None:
            raise RuntimeError(f"Sandbox {sandbox_id} not found")
        controller_session_id = record.get("controller_session_id")
        released = self.registry.release_lease(sandbox_id) or record
        if controller_session_id:
            if (
                self.registry.get_current_sandbox_id(controller_session_id)
                == sandbox_id
            ):
                self.registry.set_current_sandbox_id(controller_session_id, None)
        self.save_registry()
        return released

    async def renew_current_sandbox_lease(
        self,
        session_id: str,
        ttl_seconds: int | float | None = None,
        context: Context | None = None,
    ) -> dict:
        current = self.get_current_sandbox(session_id)
        sandbox_id = current.get("current_sandbox_id")
        if sandbox_id is None:
            raise RuntimeError("No current sandbox")
        record = self.registry.get_sandbox(sandbox_id)
        if record is None or not record.get("managed"):
            raise RuntimeError(f"Sandbox {sandbox_id} not found")
        status = record.get("status")
        if status == SandboxStatus.CREATING:
            raise RuntimeError(f"Sandbox {sandbox_id} is still being created")
        if status == SandboxStatus.RESTORING:
            raise RuntimeError(f"Sandbox {sandbox_id} is being restored")
        if status == SandboxStatus.STOPPING:
            raise RuntimeError(f"Sandbox {sandbox_id} is being destroyed")
        if status == SandboxStatus.STOPPED:
            raise RuntimeError(f"Sandbox {sandbox_id} has been destroyed")
        if status == SandboxStatus.ERROR:
            raise RuntimeError(
                f"Sandbox {sandbox_id} encountered an error during creation"
            )
        if status != SandboxStatus.RUNNING:
            raise RuntimeError(f"Sandbox {sandbox_id} is not running")
        booter = self.session_booter.get(sandbox_id)
        if booter is None:
            raise RuntimeError(f"Sandbox {sandbox_id} is not running")
        if not await self.booter_available(booter):
            self.session_booter.pop(sandbox_id, None)
            self.registry.update_sandbox_status(sandbox_id, SandboxStatus.UNKNOWN)
            await self.save_registry_async()
            raise RuntimeError(f"Sandbox {sandbox_id} is not running")
        controller_session_id = record.get("controller_session_id")
        if controller_session_id and controller_session_id != session_id:
            raise RuntimeError(f"Sandbox {sandbox_id} is controlled by another session")
        ttl = (
            self._lease_timeout(context, session_id)
            if ttl_seconds is None
            else float(ttl_seconds)
        )
        if not math.isfinite(ttl):
            raise RuntimeError("ttl_seconds must be finite")
        if ttl < 0:
            raise RuntimeError("ttl_seconds must be non-negative")
        if not self.acquire_lease(sandbox_id, session_id, ttl=ttl):
            raise RuntimeError(f"Sandbox {sandbox_id} is busy")
        self.registry.touch_sandbox(sandbox_id)
        self.save_registry()
        return self.registry.get_sandbox(sandbox_id) or record

    async def takeover_sandbox(
        self,
        session_id: str,
        sandbox_id: str,
        context: Context | None = None,
    ) -> dict:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None or not record.get("managed"):
            raise RuntimeError(f"Sandbox {sandbox_id} not found")
        record = await self._revive_persistent_booter_if_needed(
            record, sandbox_id, session_id, context
        )
        booter = self.session_booter.get(sandbox_id)
        status = record.get("status")
        if booter is None:
            if status == SandboxStatus.CREATING:
                raise RuntimeError(f"Sandbox {sandbox_id} is still being created")
            if status == SandboxStatus.RESTORING:
                raise RuntimeError(f"Sandbox {sandbox_id} is being restored")
            if status == SandboxStatus.STOPPING:
                raise RuntimeError(f"Sandbox {sandbox_id} is being destroyed")
            if status == SandboxStatus.STOPPED:
                raise RuntimeError(f"Sandbox {sandbox_id} has been destroyed")
            if status == SandboxStatus.ERROR:
                raise RuntimeError(
                    f"Sandbox {sandbox_id} encountered an error during creation"
                )
            raise RuntimeError(f"Sandbox {sandbox_id} is not running")
        if not await self.booter_available(booter):
            self.clear_runtime_state(sandbox_id)
            next_status = (
                SandboxStatus.UNKNOWN
                if record.get("retention_policy") == "persistent"
                else SandboxStatus.ERROR
            )
            self.registry.update_sandbox_status(sandbox_id, next_status)
            await self.save_registry_async()
            raise RuntimeError(
                f"Sandbox {sandbox_id} is unavailable (booter health check failed)"
            )
        previous_controller_session_id = record.get("controller_session_id")
        updated = (
            self.registry.takeover_lease(
                sandbox_id=sandbox_id,
                session_id=session_id,
                user_id=session_id,
                ttl=self._lease_timeout(context, session_id),
            )
            or record
        )
        updated = await self._set_current_sandbox_after_lease(
            session_id, sandbox_id, updated
        )
        if (
            previous_controller_session_id
            and previous_controller_session_id != session_id
            and self.registry.get_current_sandbox_id(previous_controller_session_id)
            == sandbox_id
        ):
            self.registry.set_current_sandbox_id(previous_controller_session_id, None)
            await self.save_registry_async()
        provider = self.get_provider(record.get("provider", ""))
        await self._invoke_sandbox_created_hook(provider, sandbox_id)
        return updated

    async def _destroy_sandbox_cleanup(
        self,
        provider: SandboxProvider,
        sandbox_id: str,
        record: dict,
    ) -> None:
        destroy_err: Exception | None = None
        async with self._sandbox_boot_lock(sandbox_id):
            current = self.registry.get_sandbox(sandbox_id) or record
            booter = self.session_booter.get(sandbox_id)
            if booter is not None:
                try:
                    await provider.destroy_booter(booter, current)
                except Exception as exc:
                    destroy_err = exc
                    logger.warning(
                        "[Computer] destroy_booter failed for %s: %s",
                        sandbox_id,
                        exc,
                    )
                    self.registry.update_sandbox_status(sandbox_id, SandboxStatus.ERROR)
                    await self.save_registry_async()
                else:
                    self.clear_runtime_state(sandbox_id)
            if destroy_err is None:
                self.registry.delete_sandbox(sandbox_id)
                await self.save_registry_async()

        self.drop_boot_lock(sandbox_id)

        if destroy_err is not None:
            raise destroy_err

        if hasattr(provider, "on_sandbox_destroyed"):
            try:
                await provider.on_sandbox_destroyed(record)
            except Exception as hook_err:
                logger.warning(
                    "[Computer] on_sandbox_destroyed hook failed for %s: %s",
                    sandbox_id,
                    hook_err,
                )

    async def destroy_sandbox(self, session_id: str, sandbox_id: str) -> dict:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None or not record.get("managed"):
            raise RuntimeError(f"Sandbox {sandbox_id} not found")
        if record.get("status") == SandboxStatus.STOPPING:
            return record
        controller_session_id = record.get("controller_session_id")
        if (
            controller_session_id
            and controller_session_id != session_id
            and self.sandbox_has_active_lease(sandbox_id)
        ):
            raise RuntimeError(f"Sandbox {sandbox_id} is controlled by another session")
        try:
            provider = self.get_provider(record.get("provider", ""))
        except RuntimeError:
            if record.get("retention_policy") != "persistent":
                raise
            self.clear_runtime_state_and_drop_lock(sandbox_id)
            self.registry.delete_sandbox(sandbox_id)
            await self.save_registry_async()
            return record
        self.registry.update_sandbox_status(sandbox_id, SandboxStatus.STOPPING)
        await self.save_registry_async()
        await self.cancel_pending_boot_task(sandbox_id)
        await self._destroy_sandbox_cleanup(provider, sandbox_id, record)
        return record

    async def destroy_sandbox_deferred(self, session_id: str, sandbox_id: str) -> dict:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None or not record.get("managed"):
            raise RuntimeError(f"Sandbox {sandbox_id} not found")
        if record.get("status") == SandboxStatus.STOPPING:
            return record
        controller_session_id = record.get("controller_session_id")
        if (
            controller_session_id
            and controller_session_id != session_id
            and self.sandbox_has_active_lease(sandbox_id)
        ):
            raise RuntimeError(f"Sandbox {sandbox_id} is controlled by another session")
        try:
            provider = self.get_provider(record.get("provider", ""))
        except RuntimeError:
            if record.get("retention_policy") != "persistent":
                raise
            self.clear_runtime_state_and_drop_lock(sandbox_id)
            self.registry.delete_sandbox(sandbox_id)
            await self.save_registry_async()
            return record
        self.registry.update_sandbox_status(sandbox_id, SandboxStatus.STOPPING)
        await self.save_registry_async()

        async def _run_destroy_cleanup() -> None:
            try:
                await self._defer_lifecycle_task_start()
                await self.cancel_pending_boot_task(sandbox_id)
                await self._destroy_sandbox_cleanup(provider, sandbox_id, record)
            finally:
                self.pending_destroy_tasks.pop(sandbox_id, None)

        task = asyncio.create_task(_run_destroy_cleanup())
        self.pending_destroy_tasks[sandbox_id] = task
        return self.registry.get_sandbox(sandbox_id) or record

    async def get_observer_booter_by_id(
        self,
        sandbox_id: str,
        session_id: str | None = None,
        *,
        require_lease: bool = True,
        context: Context | None = None,
    ) -> ComputerBooter:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None or not record.get("managed"):
            raise RuntimeError(f"Sandbox {sandbox_id} not found")
        controlled_by_other = bool(
            session_id
            and self.sandbox_controlled_by_other_session(sandbox_id, session_id)
        )
        if controlled_by_other and require_lease:
            raise RuntimeError(f"Sandbox {sandbox_id} is controlled by another session")
        booter = self.session_booter.get(sandbox_id)
        record = await self._revive_persistent_booter_if_needed(
            record, sandbox_id, session_id, context
        )
        booter = self.session_booter.get(sandbox_id)
        status = record.get("status")
        if booter is None:
            if status == SandboxStatus.CREATING:
                raise RuntimeError(f"Sandbox {sandbox_id} is still being created")
            if status == SandboxStatus.RESTORING:
                raise RuntimeError(f"Sandbox {sandbox_id} is being restored")
            if status == SandboxStatus.STOPPING:
                raise RuntimeError(f"Sandbox {sandbox_id} is being destroyed")
            if status == SandboxStatus.STOPPED:
                raise RuntimeError(f"Sandbox {sandbox_id} has been destroyed")
            if status == SandboxStatus.ERROR:
                raise RuntimeError(
                    f"Sandbox {sandbox_id} encountered an error during creation"
                )
            raise RuntimeError(f"Sandbox {sandbox_id} is not running")
        if not await self.booter_available(booter):
            self.session_booter.pop(sandbox_id, None)
            next_status = (
                SandboxStatus.UNKNOWN
                if record.get("retention_policy") == "persistent"
                else SandboxStatus.ERROR
            )
            self.registry.update_sandbox_status(sandbox_id, next_status)
            await self.save_registry_async()
            raise RuntimeError(
                f"Sandbox {sandbox_id} is unavailable (booter health check failed)"
            )
        if require_lease and session_id:
            lease_timeout = self._lease_timeout(context, session_id)
            if not self.acquire_lease(sandbox_id, session_id, ttl=lease_timeout):
                raise RuntimeError(f"Sandbox {sandbox_id} is busy")
            record = self.registry.get_sandbox(sandbox_id) or record
        # Only touch lifecycle when the caller actually holds the lease (or
        # the sandbox is unclaimed).  Pure observer access must not reset
        # idle timers for sandboxes controlled by other sessions.
        if session_id and record.get("controller_session_id") == session_id:
            self.registry.touch_sandbox(sandbox_id)
            await self.save_registry_async()
            idle_timeout = record.get("idle_timeout") or 0
            self.schedule_lifecycle_cleanup(
                sandbox_id, float(idle_timeout), record.get("expires_at")
            )
        return booter

    async def reconcile_on_startup(self) -> None:
        for sandbox_id in list(self.pending_boot_tasks):
            await self.cancel_pending_boot_task(sandbox_id)
        for sandbox_id in list(self.pending_destroy_tasks):
            await self.wait_pending_destroy_task(sandbox_id, timeout=None)
        self.registry.load()
        self.registry.reconcile_startup()
        self.clear_all_runtime_state()

        # Validate persistent sandbox records against provider reality.
        # If a provider reports that its persistent sandbox no longer exists
        # externally, remove the stale registry record so the dashboard does
        # not show ghost entries.
        for record in list(self.registry.list_sandboxes()):
            if record.get("retention_policy") != "persistent":
                continue
            try:
                provider = self.get_provider(record.get("provider", ""))
            except RuntimeError:
                sandbox_id = record["sandbox_id"]
                logger.info(
                    "[Computer] Provider for persistent sandbox %s is unavailable; keeping registry record",
                    sandbox_id,
                )
                self.clear_runtime_state_and_drop_lock(sandbox_id)
                self.registry.update_sandbox_status(sandbox_id, SandboxStatus.UNKNOWN)
                continue
            if not getattr(provider, "supports_persistent_reconnect", False):
                continue
            check_exists = getattr(provider, "check_persistent_sandbox_exists", None)
            if check_exists is None:
                continue
            try:
                exists = await check_exists(record)
            except Exception as exc:
                logger.warning(
                    "[Computer] Failed to check persistent sandbox %s existence: %s",
                    record.get("sandbox_id"),
                    exc,
                )
                continue
            if not exists:
                sandbox_id = record["sandbox_id"]
                if not getattr(provider, "prune_missing_persistent_records", False):
                    logger.info(
                        "[Computer] Persistent sandbox %s was not confirmed externally; keeping registry record as unknown",
                        sandbox_id,
                    )
                    self.clear_runtime_state_and_drop_lock(sandbox_id)
                    self.registry.update_sandbox_status(
                        sandbox_id, SandboxStatus.UNKNOWN
                    )
                    continue
                logger.info(
                    "[Computer] Persistent sandbox %s no longer exists externally; removing registry record",
                    sandbox_id,
                )
                self.clear_runtime_state_and_drop_lock(sandbox_id)
                self.registry.delete_sandbox(sandbox_id)

        await self.save_registry_async()

    async def restore_persistent_sandboxes(
        self,
        context: Context,
        *,
        per_sandbox_timeout: float | None = None,
    ) -> tuple[int, int]:
        restored = 0
        deleted = 0
        for record in self.registry.list_sandboxes():
            sandbox_id = record["sandbox_id"]
            if not record.get("managed"):
                continue
            if record.get("retention_policy") != "persistent":
                continue
            if record.get("status") not in {
                SandboxStatus.RUNNING,
                SandboxStatus.UNKNOWN,
            }:
                continue
            try:
                restore_coro = self._revive_persistent_booter_if_needed(
                    record=record,
                    sandbox_id=sandbox_id,
                    session_id=str(record.get("owner_session_id") or "dashboard"),
                    context=context,
                )
                if per_sandbox_timeout is None:
                    await restore_coro
                else:
                    await asyncio.wait_for(restore_coro, timeout=per_sandbox_timeout)
                restored += 1
            except asyncio.TimeoutError:
                self.session_booter.pop(sandbox_id, None)
                self.clear_idle_state(sandbox_id)
                self.registry.update_sandbox_status(sandbox_id, SandboxStatus.UNKNOWN)
                self.drop_boot_lock(sandbox_id)
                await self.save_registry_async()
                deleted += 1
                logger.warning(
                    "[Computer] Persistent sandbox restore timed out; keeping registry record as unknown: %s",
                    sandbox_id,
                )
            except Exception as exc:
                logger.warning(
                    "[Computer] Failed to restore persistent sandbox %s: %s",
                    sandbox_id,
                    exc,
                )
        return restored, deleted

    async def cleanup_managed_sandboxes(self) -> None:
        for sandbox_id in list(self.pending_boot_tasks):
            await self.cancel_pending_boot_task(sandbox_id)
        for sandbox_id in list(self.pending_destroy_tasks):
            await self.wait_pending_destroy_task(sandbox_id, timeout=None)
        managed_records = [
            record
            for record in self.list_sandboxes()
            if record["sandbox_id"] not in self.pending_destroy_tasks
        ]
        for record in managed_records:
            sandbox_id = record["sandbox_id"]
            if record.get("retention_policy") == "persistent":
                booter = self.session_booter.get(sandbox_id)
                if booter is not None:
                    try:
                        await booter.shutdown()
                    except Exception as shutdown_err:
                        logger.warning(
                            "[Computer] Failed to close persistent sandbox runtime %s: %s",
                            sandbox_id,
                            shutdown_err,
                        )
                self.clear_runtime_state_and_drop_lock(sandbox_id)
                continue
            provider = None
            try:
                provider = self.get_provider(record.get("provider", ""))
            except RuntimeError as provider_error:
                logger.warning(
                    "[Computer] Provider unavailable for sandbox %s: %s",
                    sandbox_id,
                    provider_error,
                )
            booter = self.session_booter.get(sandbox_id)
            if booter is not None:
                if provider is not None:
                    try:
                        await provider.destroy_booter(booter, record)
                    except Exception as shutdown_err:
                        logger.warning(
                            "[Computer] Failed to shutdown managed sandbox %s: %s",
                            sandbox_id,
                            shutdown_err,
                        )
                # Always pop the booter so memory is freed even when the
                # provider has already been unregistered.
                self.clear_runtime_state(sandbox_id)
            self.registry.delete_sandbox(sandbox_id)
            self.clear_runtime_state(sandbox_id)
            self.drop_boot_lock(sandbox_id)
        await self.save_registry_async()

    def clear_idle_state(self, sandbox_id: str) -> None:
        state = self.idle_state.pop(sandbox_id, None)
        if (
            state is not None
            and not state.task.done()
            and state.task is not asyncio.current_task()
        ):
            state.task.cancel()

    def clear_expiration_state(self, sandbox_id: str) -> None:
        state = self.expiration_state.pop(sandbox_id, None)
        if (
            state is not None
            and not state.task.done()
            and state.task is not asyncio.current_task()
        ):
            state.task.cancel()

    def schedule_idle_cleanup(self, sandbox_id: str, timeout: float) -> None:
        self.clear_idle_state(sandbox_id)
        if timeout <= 0:
            return
        self.registry.touch_sandbox(sandbox_id)
        expires_at = time.monotonic() + timeout
        task = asyncio.create_task(
            self._expire_when_idle(sandbox_id, timeout, expires_at)
        )
        self.idle_state[sandbox_id] = SandboxIdleState(expires_at=expires_at, task=task)

    def schedule_ttl_cleanup(self, sandbox_id: str, expires_at: float | None) -> None:
        self.clear_expiration_state(sandbox_id)
        if expires_at is None:
            return
        monotonic_expires_at = time.monotonic() + max(
            0.0, float(expires_at) - time.time()
        )
        task = asyncio.create_task(
            self._expire_at_fixed_time(
                sandbox_id, float(expires_at), monotonic_expires_at
            )
        )
        self.expiration_state[sandbox_id] = SandboxExpirationState(
            expires_at=float(expires_at),
            monotonic_expires_at=monotonic_expires_at,
            task=task,
        )

    def schedule_lifecycle_cleanup(
        self,
        sandbox_id: str,
        idle_timeout: float,
        expires_at: float | None,
    ) -> None:
        if idle_timeout > 0:
            self.clear_expiration_state(sandbox_id)
            self.schedule_idle_cleanup(sandbox_id, idle_timeout)
            return
        self.clear_idle_state(sandbox_id)
        self.schedule_ttl_cleanup(sandbox_id, expires_at)

    async def _expire_at_fixed_time(
        self,
        sandbox_id: str,
        expires_at: float,
        monotonic_expires_at: float,
    ) -> None:
        current_task = asyncio.current_task()
        destroy_attempts = 0
        try:
            while True:
                remaining = monotonic_expires_at - time.monotonic()
                if remaining > 0:
                    await asyncio.sleep(remaining)
                state = self.expiration_state.get(sandbox_id)
                if (
                    state is None
                    or state.task is not current_task
                    or state.expires_at != float(expires_at)
                ):
                    return
                record = self.registry.get_sandbox(sandbox_id)
                if record is None:
                    self.session_booter.pop(sandbox_id, None)
                    return
                if float(record.get("expires_at") or 0) != float(expires_at):
                    return
                booter = self.session_booter.get(sandbox_id)
                if booter is not None:
                    try:
                        provider = self.get_provider(record.get("provider", ""))
                        await provider.destroy_booter(booter, record)
                    except Exception as shutdown_err:
                        logger.warning(
                            "[Computer] Failed to shutdown expired sandbox %s: %s",
                            sandbox_id,
                            shutdown_err,
                        )
                        destroy_attempts += 1
                        if destroy_attempts < MAX_IDLE_DESTROY_ATTEMPTS:
                            self.registry.update_sandbox_status(
                                sandbox_id, SandboxStatus.UNKNOWN
                            )
                            await self.save_registry_async()
                            await asyncio.sleep(SANDBOX_TTL_DESTROY_RETRY_SECONDS)
                            continue
                        self.registry.update_sandbox_status(
                            sandbox_id, SandboxStatus.ERROR
                        )
                        await self.save_registry_async()
                        return
                self.clear_runtime_state(sandbox_id)
                if record.get("retention_policy") == "persistent":
                    self.registry.update_sandbox_status(
                        sandbox_id, SandboxStatus.STOPPED
                    )
                else:
                    self.registry.delete_sandbox(sandbox_id)
                    self.drop_boot_lock(sandbox_id)
                await self.save_registry_async()
                return
        finally:
            state = self.expiration_state.get(sandbox_id)
            if (
                state is not None
                and state.task is current_task
                and state.expires_at == float(expires_at)
            ):
                self.expiration_state.pop(sandbox_id, None)

    async def _expire_when_idle(
        self, sandbox_id: str, timeout: float, initial_expires_at: float
    ) -> None:
        current_expires_at = initial_expires_at
        destroy_attempts = 0
        try:
            while True:
                remaining = current_expires_at - time.monotonic()
                if remaining > 0:
                    await asyncio.sleep(remaining)
                state = self.idle_state.get(sandbox_id)
                if state is None or state.expires_at != current_expires_at:
                    return
                record = self.registry.get_sandbox(sandbox_id)
                if record is None:
                    self.session_booter.pop(sandbox_id, None)
                    return
                if self.sandbox_has_active_lease(sandbox_id):
                    current_expires_at = time.monotonic() + timeout
                    self.idle_state[sandbox_id] = SandboxIdleState(
                        expires_at=current_expires_at, task=state.task
                    )
                    continue
                if record.get("retention_policy") == "persistent":
                    return
                booter = self.session_booter.get(sandbox_id)
                if booter is not None:
                    try:
                        provider = self.get_provider(record.get("provider", ""))
                        self.session_booter.pop(sandbox_id, None)
                        await provider.destroy_booter(booter, record)
                    except Exception as shutdown_err:
                        logger.warning(
                            "[Computer] Failed to shutdown idle sandbox %s: %s",
                            sandbox_id,
                            shutdown_err,
                        )
                        try:
                            booter_available = await self.booter_available(booter)
                        except Exception:
                            booter_available = False
                        if booter_available:
                            destroy_attempts += 1
                            if destroy_attempts < MAX_IDLE_DESTROY_ATTEMPTS:
                                self.session_booter[sandbox_id] = booter
                                self.registry.update_sandbox_status(
                                    sandbox_id, SandboxStatus.UNKNOWN
                                )
                                await self.save_registry_async()
                                # Retry cleanup after the normal timeout instead of
                                # leaving the sandbox without any scheduled cleanup.
                                current_expires_at = time.monotonic() + timeout
                                self.idle_state[sandbox_id] = SandboxIdleState(
                                    expires_at=current_expires_at, task=state.task
                                )
                                continue
                            logger.warning(
                                "[Computer] Giving up on idle sandbox %s after %d destroy attempts",
                                sandbox_id,
                                destroy_attempts,
                            )
                            self.session_booter[sandbox_id] = booter
                            self.registry.update_sandbox_status(
                                sandbox_id, SandboxStatus.ERROR
                            )
                            self.idle_state.pop(sandbox_id, None)
                            await self.save_registry_async()
                            return
                        self.clear_runtime_state(sandbox_id)
                        self.registry.delete_sandbox(sandbox_id)
                        self.drop_boot_lock(sandbox_id)
                        await self.save_registry_async()
                        return
                self.registry.delete_sandbox(sandbox_id)
                self.drop_boot_lock(sandbox_id)
                await self.save_registry_async()
                return
        except asyncio.CancelledError:
            raise
        finally:
            state = self.idle_state.get(sandbox_id)
            if state is not None and state.expires_at == current_expires_at:
                self.idle_state.pop(sandbox_id, None)

    @staticmethod
    async def _sync_skills_to_booter(
        booter: ComputerBooter,
        provider_id: str | None = None,
    ) -> None:
        """Delay-import wrapper to avoid circular imports."""
        from astrbot.core.computer.computer_client import _sync_skills_to_sandbox

        await _sync_skills_to_sandbox(booter, provider_id=provider_id)
