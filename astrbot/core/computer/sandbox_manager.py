from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from dataclasses import dataclass

from astrbot.api import logger
from astrbot.core.computer.booters.base import ComputerBooter
from astrbot.core.computer.sandbox_models import SandboxStatus
from astrbot.core.computer.sandbox_provider import SandboxProvider
from astrbot.core.computer.sandbox_registry import SandboxRegistry
from astrbot.core.star.context import Context

SANDBOX_LEASE_SECONDS = 300


@dataclass(slots=True)
class SandboxIdleState:
    expires_at: float
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
        self.boot_locks: dict[str, asyncio.Lock] = {}
        self.pending_boot_tasks: dict[str, asyncio.Task] = {}

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

    async def save_registry_async(self) -> None:
        try:
            await self.registry.save_async()
        except Exception as exc:
            logger.warning("[Computer] Failed to save sandbox registry: %s", exc)

    def _sandbox_boot_lock(self, sandbox_id: str) -> asyncio.Lock:
        lock = self.boot_locks.get(sandbox_id)
        if lock is None:
            lock = asyncio.Lock()
            self.boot_locks[sandbox_id] = lock
        return lock

    def drop_boot_lock(self, sandbox_id: str) -> None:
        self.boot_locks.pop(sandbox_id, None)

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
        connect_info: dict,
        is_default: bool = False,
        status: str = SandboxStatus.RUNNING,
    ) -> dict:
        return {
            "sandbox_id": sandbox_id,
            "sandbox_name": sandbox_name,
            "booter_type": provider_id,
            "provider": provider_id,
            "managed": True,
            "created_by_astrbot": True,
            "owner_user_id": session_id,
            "owner_session_id": session_id,
            "connect_info": connect_info,
            "capabilities": sorted(
                getattr(self.get_provider(provider_id), "capabilities", set())
            ),
            "is_default": is_default,
            "idle_timeout": idle_timeout,
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
            return True
        result = available() if callable(available) else available
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    def acquire_lease(
        self, sandbox_id: str, session_id: str, *, ttl: float | None = None
    ) -> bool:
        return self.registry.acquire_lease(
            sandbox_id=sandbox_id,
            session_id=session_id,
            user_id=session_id,
            ttl=SANDBOX_LEASE_SECONDS if ttl is None else ttl,
        )

    def sandbox_has_active_lease(self, sandbox_id: str) -> bool:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None:
            return False
        lease_expires_at = record.get("lease_expires_at")
        controller_session_id = record.get("controller_session_id")
        return bool(
            controller_session_id
            and lease_expires_at
            and lease_expires_at > time.time()
        )

    def sandbox_controlled_by_other_session(
        self, sandbox_id: str, session_id: str
    ) -> bool:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None:
            return False
        lease_expires_at = record.get("lease_expires_at")
        controller_session_id = record.get("controller_session_id")
        if not controller_session_id or controller_session_id == session_id:
            return False
        return bool(lease_expires_at and lease_expires_at > time.time())

    async def _upsert_new_sandbox_record(
        self, context: Context, session_id: str, provider_id: str, create_config: dict
    ) -> str:
        provider = self.get_provider(provider_id)
        sandbox_id = self.new_sandbox_id(provider_id)
        self.registry.upsert_sandbox(
            **self.build_record_payload(
                sandbox_id=sandbox_id,
                sandbox_name=sandbox_id,
                session_id=session_id,
                provider_id=provider_id,
                idle_timeout=provider.get_idle_timeout(context, session_id),
                connect_info=provider.build_connect_info(sandbox_id, create_config),
            )
        )
        await self.save_registry_async()
        return sandbox_id

    async def get_or_create_booter(
        self, context: Context, session_id: str, provider_id: str
    ) -> ComputerBooter:
        provider = self.get_provider(provider_id)
        create_config = provider.build_create_config(context, session_id)
        idle_timeout = provider.get_idle_timeout(context, session_id)

        current_sandbox_id = self.registry.get_current_sandbox_id(session_id)
        current_record = self.registry.get_sandbox(current_sandbox_id)
        if current_sandbox_id and (
            current_record is None or current_record.get("provider") != provider_id
        ):
            self.registry.set_current_sandbox_id(session_id, None)
            await self.save_registry_async()
            current_sandbox_id = None
            current_record = None
        if (
            current_sandbox_id
            and current_record
            and current_record.get("provider") == provider_id
            and current_sandbox_id in self.session_booter
        ):
            if not self.acquire_lease(current_sandbox_id, session_id):
                self.registry.set_current_sandbox_id(session_id, None)
                await self.save_registry_async()
            else:
                booter = self.session_booter[current_sandbox_id]
                if await self.booter_available(booter):
                    self.registry.touch_sandbox(current_sandbox_id)
                    await self.save_registry_async()
                    self.schedule_idle_cleanup(current_sandbox_id, idle_timeout)
                    return booter
                self.session_booter.pop(current_sandbox_id, None)
                self.registry.release_lease(current_sandbox_id)
                await self.save_registry_async()

        created_target_record = False
        target_sandbox_id = self.get_default_sandbox_id(provider_id)
        if target_sandbox_id is None:
            target_sandbox_id = self.new_sandbox_id(provider_id)
            created_target_record = True
            record = self.registry.upsert_sandbox(
                **self.build_record_payload(
                    sandbox_id=target_sandbox_id,
                    sandbox_name=target_sandbox_id,
                    session_id=session_id,
                    provider_id=provider_id,
                    idle_timeout=idle_timeout,
                    connect_info=provider.build_connect_info(
                        target_sandbox_id, create_config
                    ),
                    is_default=True,
                )
            )
            self.registry.set_default_sandbox_id(record["sandbox_id"])
            await self.save_registry_async()

        if self.sandbox_controlled_by_other_session(target_sandbox_id, session_id):
            target_sandbox_id = await self._upsert_new_sandbox_record(
                context, session_id, provider_id, create_config
            )
            created_target_record = True

        while True:
            async with self._sandbox_boot_lock(target_sandbox_id):
                if target_sandbox_id in self.session_booter and not self.acquire_lease(
                    target_sandbox_id, session_id
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
                    self.session_booter.pop(target_sandbox_id, None)
                    self.registry.release_lease(target_sandbox_id)
                    self.registry.update_sandbox_status(target_sandbox_id, "unknown")
                    await self.save_registry_async()

                if not self.acquire_lease(target_sandbox_id, session_id):
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
                            target_sandbox_id, "unknown"
                        )
                    self.drop_boot_lock(target_sandbox_id)
                    await self.save_registry_async()
                    raise
                setattr(client, "sandbox_id", target_sandbox_id)
                self.session_booter[target_sandbox_id] = client
                break

        await self._finalize_created_booter(
            provider,
            target_sandbox_id,
            session_id=session_id,
            idle_timeout=idle_timeout,
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
    ) -> None:
        """Common post-creation steps: persist, idle cleanup, skill sync, hooks."""
        self.registry.touch_sandbox(sandbox_id)
        self.registry.update_sandbox_status(sandbox_id, SandboxStatus.RUNNING)
        if session_id is not None:
            self.registry.set_current_sandbox_id(session_id, sandbox_id)
        await self.save_registry_async()
        self.schedule_idle_cleanup(sandbox_id, idle_timeout)

        # Auto-sync skills unless the provider opts out.  Best-effort: a sync
        # failure is logged but does not destroy the already-created sandbox.
        if getattr(provider, "auto_sync_skills", True):
            booter = self.session_booter.get(sandbox_id)
            if booter is not None and hasattr(booter, "shell"):
                try:
                    await self._sync_skills_to_booter(booter)
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
        async with self._sandbox_boot_lock(sandbox_id):
            record = self.registry.get_sandbox(sandbox_id) or {}
            if record.get("created_hook_fired"):
                return
            if not hasattr(provider, "on_sandbox_created"):
                # Mark as fired even when the hook is absent so we don't keep
                # re-checking on every subsequent lease operation.
                raw = self.registry._payload["sandboxes"].get(sandbox_id)
                if raw is not None:
                    raw["created_hook_fired"] = True
                    await self.save_registry_async()
                return
            try:
                await provider.on_sandbox_created(record)
            except Exception as hook_err:
                logger.warning(
                    "[Computer] on_sandbox_created hook failed for %s: %s",
                    sandbox_id,
                    hook_err,
                )
                return
            raw = self.registry._payload["sandboxes"].get(sandbox_id)
            if raw is not None:
                raw["created_hook_fired"] = True
                await self.save_registry_async()

    async def create_sandbox_uncontrolled(
        self,
        context: Context,
        session_id: str,
        provider_id: str,
        sandbox_name: str | None = None,
    ) -> dict:
        provider = self.get_provider(provider_id)
        create_config = provider.build_create_config(context, session_id)
        sandbox_id = self.new_sandbox_id(provider_id)
        sandbox_name = self._created_sandbox_name(sandbox_id, sandbox_name)
        idle_timeout = provider.get_idle_timeout(context, session_id)
        async with self._sandbox_boot_lock(sandbox_id):
            record = self.registry.upsert_sandbox(
                **self.build_record_payload(
                    sandbox_id=sandbox_id,
                    sandbox_name=sandbox_name,
                    session_id=session_id,
                    provider_id=provider_id,
                    idle_timeout=idle_timeout,
                    connect_info=provider.build_connect_info(
                        sandbox_name, create_config
                    ),
                    status=SandboxStatus.CREATING,
                )
            )
            try:
                client = await provider.create_booter(
                    context, session_id, sandbox_id, create_config
                )
            except Exception:
                self.registry.update_sandbox_status(sandbox_id, SandboxStatus.ERROR)
                self.registry.delete_sandbox(sandbox_id)
                self.drop_boot_lock(sandbox_id)
                await self.save_registry_async()
                raise
            setattr(client, "sandbox_id", sandbox_id)
            self.session_booter[sandbox_id] = client
            await self._finalize_created_booter(
                provider, sandbox_id, session_id=None, idle_timeout=idle_timeout
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
        create_config = provider.build_create_config(context, session_id)
        sandbox_id = self.new_sandbox_id(provider_id)
        sandbox_name = self._created_sandbox_name(sandbox_id, sandbox_name)
        idle_timeout = provider.get_idle_timeout(context, session_id)
        async with self._sandbox_boot_lock(sandbox_id):
            record = self.registry.upsert_sandbox(
                **self.build_record_payload(
                    sandbox_id=sandbox_id,
                    sandbox_name=sandbox_name,
                    session_id=session_id,
                    provider_id=provider_id,
                    idle_timeout=idle_timeout,
                    connect_info=provider.build_connect_info(
                        sandbox_name, create_config
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
                record=record,
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
        record: dict,
    ) -> None:
        try:
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
                        await provider.destroy_booter(client, record)
                    except Exception as destroy_err:
                        logger.warning(
                            "[Computer] Deferred sandbox cleanup failed after record removal: sandbox_id=%s error=%s",
                            sandbox_id,
                            destroy_err,
                        )
                    return

                setattr(client, "sandbox_id", sandbox_id)
                self.session_booter[sandbox_id] = client
                await self._finalize_created_booter(
                    provider, sandbox_id, session_id=None, idle_timeout=idle_timeout
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
        if not self.acquire_lease(sandbox_id, session_id):
            raise RuntimeError(f"Sandbox {sandbox_id} is busy")
        self.registry.set_current_sandbox_id(session_id, sandbox_id)
        await self.save_registry_async()
        provider = self.get_provider(sandbox.get("provider", ""))
        # Reset idle cleanup after lease acquisition.  The uncontrolled
        # creation path already schedules cleanup, but a slow skill-sync or
        # short idle_timeout could let the timer expire before the lease is
        # acquired.  Re-scheduling here guarantees a full idle window.
        idle_timeout = sandbox.get("idle_timeout") or 0
        if idle_timeout:
            self.schedule_idle_cleanup(sandbox_id, float(idle_timeout))
        await self._invoke_sandbox_created_hook(provider, sandbox_id)
        return self.registry.get_sandbox(sandbox_id) or sandbox

    def list_sandboxes(self) -> list[dict]:
        records = []
        for record in self.registry.list_sandboxes():
            if not record.get("managed"):
                continue
            provider = self.providers.get(record.get("provider"))
            record["capabilities"] = sorted(
                getattr(provider, "capabilities", set()) if provider else []
            )
            record["tool_names"] = sorted(
                getattr(provider, "tool_names", set()) if provider else []
            )
            records.append(record)
        return records

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
        provider = self.providers.get(record.get("provider", ""))
        if retention_policy not in {"temporary", "persistent"}:
            raise RuntimeError("retention_policy must be temporary or persistent")
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
        if retention_policy == "persistent" or not idle_timeout:
            self.clear_idle_state(sandbox_id)
        else:
            self.schedule_idle_cleanup(sandbox_id, float(idle_timeout))
        self.save_registry()
        return updated or record

    async def switch_current_sandbox_checked(
        self, session_id: str, sandbox_id: str
    ) -> dict:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None or not record.get("managed"):
            raise RuntimeError(f"Sandbox {sandbox_id} not found")
        booter = self.session_booter.get(sandbox_id)
        if booter is None:
            raise RuntimeError(f"Sandbox {sandbox_id} is not running")
        if not await self.booter_available(booter):
            self.session_booter.pop(sandbox_id, None)
            self.registry.update_sandbox_status(sandbox_id, "unknown")
            await self.save_registry_async()
            raise RuntimeError(f"Sandbox {sandbox_id} is not running")
        if not self.acquire_lease(sandbox_id, session_id):
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

    def get_current_sandbox(self, session_id: str) -> dict:
        sandbox_id = self.registry.get_current_sandbox_id(session_id)
        return {
            "current_sandbox_id": sandbox_id,
            "sandbox": self.registry.get_sandbox(sandbox_id) if sandbox_id else None,
        }

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

    async def takeover_sandbox(self, session_id: str, sandbox_id: str) -> dict:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None or not record.get("managed"):
            raise RuntimeError(f"Sandbox {sandbox_id} not found")
        updated = (
            self.registry.takeover_lease(
                sandbox_id=sandbox_id,
                session_id=session_id,
                user_id=session_id,
                ttl=SANDBOX_LEASE_SECONDS,
            )
            or record
        )
        self.registry.set_current_sandbox_id(session_id, sandbox_id)
        self.save_registry()
        provider = self.get_provider(record.get("provider", ""))
        await self._invoke_sandbox_created_hook(provider, sandbox_id)
        return updated

    async def destroy_sandbox(self, session_id: str, sandbox_id: str) -> dict:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None or not record.get("managed"):
            raise RuntimeError(f"Sandbox {sandbox_id} not found")
        controller_session_id = record.get("controller_session_id")
        if (
            controller_session_id
            and controller_session_id != session_id
            and self.sandbox_has_active_lease(sandbox_id)
        ):
            raise RuntimeError(f"Sandbox {sandbox_id} is controlled by another session")
        provider = self.get_provider(record.get("provider", ""))
        self.registry.update_sandbox_status(sandbox_id, SandboxStatus.STOPPING)
        await self.save_registry_async()
        await self.cancel_pending_boot_task(sandbox_id)
        booter = self.session_booter.get(sandbox_id)
        if booter is not None:
            try:
                await provider.destroy_booter(booter, record)
            except Exception as destroy_err:
                logger.warning(
                    "[Computer] destroy_booter failed for %s: %s",
                    sandbox_id,
                    destroy_err,
                )
            finally:
                self.session_booter.pop(sandbox_id, None)
        self.clear_idle_state(sandbox_id)
        if record.get("retention_policy") == "persistent":
            self.registry.update_sandbox_status(sandbox_id, SandboxStatus.STOPPED)
        else:
            self.registry.delete_sandbox(sandbox_id)
        self.drop_boot_lock(sandbox_id)
        await self.save_registry_async()

        if hasattr(provider, "on_sandbox_destroyed"):
            try:
                await provider.on_sandbox_destroyed(record)
            except Exception as hook_err:
                logger.warning(
                    "[Computer] on_sandbox_destroyed hook failed for %s: %s",
                    sandbox_id,
                    hook_err,
                )

        return record

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
        if (
            booter is None
            and context is not None
            and record.get("retention_policy") == "persistent"
        ):
            status = record.get("status")
            if status in {
                SandboxStatus.RUNNING,
                SandboxStatus.UNKNOWN,
            }:
                provider = self.get_provider(record.get("provider", ""))
                if getattr(provider, "supports_persistent_reconnect", False):
                    create_session_id = str(
                        record.get("owner_session_id") or session_id or "dashboard"
                    )
                    create_config = provider.build_create_config(
                        context, create_session_id
                    )
                    create_config = {
                        **create_config,
                        "persistent_name": str(
                            (record.get("connect_info") or {}).get("persistent_name")
                            or sandbox_id
                        ).strip(),
                        "resume": True,
                    }
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
                            previous_status = (
                                current.get("status") or SandboxStatus.UNKNOWN
                            )
                            self.registry.update_sandbox_status(
                                sandbox_id, SandboxStatus.CREATING
                            )
                            await self.save_registry_async()
                            try:
                                client = await provider.create_booter(
                                    context,
                                    create_session_id,
                                    sandbox_id,
                                    create_config,
                                )
                            except Exception:
                                latest = self.registry.get_sandbox(sandbox_id)
                                if (
                                    latest is not None
                                    and latest.get("status") == SandboxStatus.CREATING
                                ):
                                    self.registry.update_sandbox_status(
                                        sandbox_id, previous_status
                                    )
                                    await self.save_registry_async()
                                raise
                            setattr(client, "sandbox_id", sandbox_id)
                            self.session_booter[sandbox_id] = client
                            await self._finalize_created_booter(
                                provider,
                                sandbox_id,
                                session_id=None,
                                idle_timeout=provider.get_idle_timeout(
                                    context, create_session_id
                                ),
                            )
                        booter = self.session_booter.get(sandbox_id)
                        record = self.registry.get_sandbox(sandbox_id) or record
        status = record.get("status")
        if booter is None:
            if status == SandboxStatus.CREATING:
                raise RuntimeError(f"Sandbox {sandbox_id} is still being created")
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
            self.registry.update_sandbox_status(sandbox_id, SandboxStatus.ERROR)
            await self.save_registry_async()
            raise RuntimeError(
                f"Sandbox {sandbox_id} is unavailable (booter health check failed)"
            )
        # Only touch lifecycle when the caller actually holds the lease (or
        # the sandbox is unclaimed).  Pure observer access must not reset
        # idle timers for sandboxes controlled by other sessions.
        if not controlled_by_other:
            self.registry.touch_sandbox(sandbox_id)
            await self.save_registry_async()
            idle_timeout = record.get("idle_timeout") or 0
            self.schedule_idle_cleanup(sandbox_id, float(idle_timeout))
        return booter

    async def reconcile_on_startup(self) -> None:
        for sandbox_id in list(self.pending_boot_tasks):
            await self.cancel_pending_boot_task(sandbox_id)
        self.registry.load()
        self.registry.reconcile_startup()
        self.session_booter.clear()
        for sandbox_id in list(self.idle_state):
            self.clear_idle_state(sandbox_id)
        await self.save_registry_async()

    async def cleanup_managed_sandboxes(self) -> None:
        for sandbox_id in list(self.pending_boot_tasks):
            await self.cancel_pending_boot_task(sandbox_id)
        managed_records = self.list_sandboxes()
        for record in managed_records:
            sandbox_id = record["sandbox_id"]
            if record.get("retention_policy") == "persistent":
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
                self.session_booter.pop(sandbox_id, None)
            self.clear_idle_state(sandbox_id)
            self.registry.delete_sandbox(sandbox_id)
            self.drop_boot_lock(sandbox_id)
        await self.save_registry_async()

    def clear_idle_state(self, sandbox_id: str) -> None:
        state = self.idle_state.pop(sandbox_id, None)
        if state is not None and not state.task.done():
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

    async def _expire_when_idle(
        self, sandbox_id: str, timeout: float, initial_expires_at: float
    ) -> None:
        current_expires_at = initial_expires_at
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
                last_used_at = record.get("last_used_at")
                if last_used_at is not None:
                    idle_remaining = timeout - (time.time() - float(last_used_at))
                    if idle_remaining > 0:
                        current_expires_at = time.monotonic() + idle_remaining
                        self.idle_state[sandbox_id] = SandboxIdleState(
                            expires_at=current_expires_at, task=state.task
                        )
                        continue
                booter = self.session_booter.get(sandbox_id)
                if booter is not None:
                    try:
                        provider = self.get_provider(record.get("provider", ""))
                        self.session_booter.pop(sandbox_id, None)
                        await provider.destroy_booter(booter, record)
                    except Exception as shutdown_err:
                        self.session_booter[sandbox_id] = booter
                        self.registry.update_sandbox_status(sandbox_id, "unknown")
                        await self.save_registry_async()
                        logger.warning(
                            "[Computer] Failed to shutdown idle sandbox %s: %s",
                            sandbox_id,
                            shutdown_err,
                        )
                        # Retry cleanup after the normal timeout instead of
                        # leaving the sandbox without any scheduled cleanup.
                        current_expires_at = time.monotonic() + timeout
                        self.idle_state[sandbox_id] = SandboxIdleState(
                            expires_at=current_expires_at, task=state.task
                        )
                        continue
                if record.get("retention_policy") == "persistent":
                    self.registry.update_sandbox_status(sandbox_id, "stopped")
                else:
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
    async def _sync_skills_to_booter(booter: ComputerBooter) -> None:
        """Delay-import wrapper to avoid circular imports."""
        from astrbot.core.computer.computer_client import _sync_skills_to_sandbox

        await _sync_skills_to_sandbox(booter)
