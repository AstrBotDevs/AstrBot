from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass

from astrbot.api import logger
from astrbot.core.computer.booters.base import ComputerBooter
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

    def save_registry(self) -> None:
        try:
            self.registry.save()
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

    def get_idle_timeout(self, config: dict, provider_id: str) -> float:
        sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
        value = sandbox_cfg.get(f"{provider_id}_idle_timeout", 0)
        try:
            timeout = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(timeout, 0.0)

    def build_record_payload(
        self,
        *,
        sandbox_id: str,
        sandbox_name: str,
        session_id: str,
        provider_id: str,
        config: dict,
        idle_timeout: float,
        is_default: bool = False,
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
            "connect_info": {
                "name": sandbox_name,
                "local": config.get("local", True),
                "image": config.get("image"),
                "os_type": config.get("os_type"),
            },
            "is_default": is_default,
            "idle_timeout": idle_timeout,
        }

    def new_sandbox_id(self, provider_id: str) -> str:
        return f"{provider_id}-{uuid.uuid4().hex[:12]}"

    def get_provider(self, provider_id: str) -> SandboxProvider:
        provider = self.providers.get(provider_id)
        if provider is None:
            raise RuntimeError(f"Provider {provider_id} is not supported")
        return provider

    def get_default_sandbox_id(self, provider_id: str) -> str | None:
        default_sandbox_id = self.registry.default_sandbox_id
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
        return await available()

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

    async def get_or_create_booter(
        self, context: Context, session_id: str, provider_id: str
    ) -> ComputerBooter:
        provider = self.get_provider(provider_id)
        create_config = provider.build_create_config(context, session_id)

        current_sandbox_id = self.registry.get_current_sandbox_id(session_id)
        current_record = (
            self.registry.get_sandbox(current_sandbox_id)
            if current_sandbox_id
            else None
        )
        if (
            current_sandbox_id
            and current_record
            and current_record.get("provider") == provider_id
            and current_sandbox_id in self.session_booter
        ):
            if not self.acquire_lease(current_sandbox_id, session_id):
                raise RuntimeError(f"Sandbox {current_sandbox_id} is busy")
            booter = self.session_booter[current_sandbox_id]
            if await self.booter_available(booter):
                self.registry.touch_sandbox(current_sandbox_id)
                self.save_registry()
                self.schedule_idle_cleanup(
                    current_sandbox_id,
                    self.get_idle_timeout(
                        context.get_config(umo=session_id), provider_id
                    ),
                )
                return booter
            self.session_booter.pop(current_sandbox_id, None)

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
                    config=create_config,
                    idle_timeout=self.get_idle_timeout(
                        context.get_config(umo=session_id), provider_id
                    ),
                    is_default=True,
                )
            )
            self.registry.set_default_sandbox_id(record["sandbox_id"])
            self.save_registry()

        if self.sandbox_has_active_lease(
            target_sandbox_id
        ) and self.sandbox_controlled_by_other_session(target_sandbox_id, session_id):
            target_sandbox_id = self._upsert_new_sandbox_record(
                context, session_id, provider_id, create_config
            )
            created_target_record = True

        while True:
            async with self._sandbox_boot_lock(target_sandbox_id):
                if target_sandbox_id in self.session_booter and not self.acquire_lease(
                    target_sandbox_id, session_id
                ):
                    target_sandbox_id = self._upsert_new_sandbox_record(
                        context, session_id, provider_id, create_config
                    )
                    created_target_record = True
                    continue

                if target_sandbox_id in self.session_booter:
                    booter = self.session_booter[target_sandbox_id]
                    if await self.booter_available(booter):
                        break
                    self.session_booter.pop(target_sandbox_id, None)

                if not self.acquire_lease(target_sandbox_id, session_id):
                    target_sandbox_id = self._upsert_new_sandbox_record(
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
                    self.save_registry()
                    raise
                setattr(client, "sandbox_id", target_sandbox_id)
                self.session_booter[target_sandbox_id] = client
                break

            break

        self.registry.touch_sandbox(target_sandbox_id)
        self.registry.update_sandbox_status(target_sandbox_id, "running")
        self.registry.set_current_sandbox_id(session_id, target_sandbox_id)
        self.save_registry()
        self.schedule_idle_cleanup(
            target_sandbox_id,
            self.get_idle_timeout(context.get_config(umo=session_id), provider_id),
        )
        return self.session_booter[target_sandbox_id]

    async def create_sandbox_uncontrolled(
        self,
        context: Context,
        session_id: str,
        provider_id: str,
        sandbox_name: str | None = None,
    ) -> dict:
        provider = self.get_provider(provider_id)
        create_config = provider.build_create_config(context, session_id)
        config = context.get_config(umo=session_id)
        sandbox_id = self.new_sandbox_id(provider_id)
        sandbox_name = sandbox_name or sandbox_id
        idle_timeout = self.get_idle_timeout(config, provider_id)
        record = self.registry.upsert_sandbox(
            **self.build_record_payload(
                sandbox_id=sandbox_id,
                sandbox_name=sandbox_name,
                session_id=session_id,
                provider_id=provider_id,
                config=create_config,
                idle_timeout=idle_timeout,
            )
        )
        try:
            client = await provider.create_booter(
                context, session_id, sandbox_id, create_config
            )
        except Exception:
            self.registry.delete_sandbox(sandbox_id)
            self.drop_boot_lock(sandbox_id)
            self.save_registry()
            raise
        setattr(client, "sandbox_id", sandbox_id)
        self.session_booter[sandbox_id] = client
        self.registry.touch_sandbox(sandbox_id)
        self.registry.update_sandbox_status(sandbox_id, "running")
        self.save_registry()
        self.schedule_idle_cleanup(sandbox_id, idle_timeout)
        return self.registry.get_sandbox(sandbox_id) or record

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
        self.acquire_lease(sandbox_id, session_id)
        self.registry.set_current_sandbox_id(session_id, sandbox_id)
        self.save_registry()
        return self.registry.get_sandbox(sandbox_id) or sandbox

    def list_sandboxes(self) -> list[dict]:
        return [
            record for record in self.registry.list_sandboxes() if record.get("managed")
        ]

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
        idle_timeout: int | float | None,
        expires_at: int | float | None,
        retention_policy: str,
    ) -> dict:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None or not record.get("managed"):
            raise RuntimeError(f"Sandbox {sandbox_id} not found")
        if retention_policy not in {"temporary", "persistent"}:
            raise RuntimeError("retention_policy must be temporary or persistent")
        if retention_policy == "persistent":
            idle_timeout = None
            expires_at = None
        updated = self.registry.update_sandbox_config(
            sandbox_id,
            idle_timeout=idle_timeout,
            expires_at=expires_at,
            retention_policy=retention_policy,
        )
        if retention_policy == "persistent" or not idle_timeout:
            self.clear_idle_state(sandbox_id)
        else:
            self.schedule_idle_cleanup(sandbox_id, float(idle_timeout))
        self.save_registry()
        return updated or record

    def _upsert_new_sandbox_record(
        self, context: Context, session_id: str, provider_id: str, create_config: dict
    ) -> str:
        sandbox_id = self.new_sandbox_id(provider_id)
        self.registry.upsert_sandbox(
            **self.build_record_payload(
                sandbox_id=sandbox_id,
                sandbox_name=sandbox_id,
                session_id=session_id,
                provider_id=provider_id,
                config=create_config,
                idle_timeout=self.get_idle_timeout(
                    context.get_config(umo=session_id), provider_id
                ),
            )
        )
        self.save_registry()
        return sandbox_id

    def switch_current_sandbox(self, session_id: str, sandbox_id: str) -> dict:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None or not record.get("managed"):
            raise RuntimeError(f"Sandbox {sandbox_id} not found")
        booter = self.session_booter.get(sandbox_id)
        if booter is None:
            raise RuntimeError(f"Sandbox {sandbox_id} is not running")
        if not self.acquire_lease(sandbox_id, session_id):
            raise RuntimeError(f"Sandbox {sandbox_id} is busy")
        previous_sandbox_id = self.registry.get_current_sandbox_id(session_id)
        if previous_sandbox_id and previous_sandbox_id != sandbox_id:
            previous = self.registry.get_sandbox(previous_sandbox_id)
            if previous and previous.get("controller_session_id") == session_id:
                self.registry.release_lease(previous_sandbox_id)
        self.registry.set_current_sandbox_id(session_id, sandbox_id)
        self.registry.touch_sandbox(sandbox_id)
        self.save_registry()
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

    def takeover_sandbox(self, session_id: str, sandbox_id: str) -> dict:
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
        self.save_registry()
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
        booter = self.session_booter.pop(sandbox_id, None)
        if booter is not None:
            await provider.destroy_booter(booter, record)
        self.clear_idle_state(sandbox_id)
        self.registry.delete_sandbox(sandbox_id)
        self.drop_boot_lock(sandbox_id)
        self.save_registry()
        return record

    async def get_observer_booter_by_id(self, sandbox_id: str) -> ComputerBooter:
        record = self.registry.get_sandbox(sandbox_id)
        if record is None or not record.get("managed"):
            raise RuntimeError(f"Sandbox {sandbox_id} not found")
        booter = self.session_booter.get(sandbox_id)
        if booter is None or not await self.booter_available(booter):
            raise RuntimeError(f"Sandbox {sandbox_id} is not running")
        self.registry.touch_sandbox(sandbox_id)
        self.save_registry()
        idle_timeout = record.get("idle_timeout") or 0
        self.schedule_idle_cleanup(sandbox_id, float(idle_timeout))
        return booter

    async def reconcile_on_startup(self) -> None:
        self.registry.load()
        self.registry.reconcile_startup()
        self.session_booter.clear()
        for sandbox_id in list(self.idle_state):
            self.clear_idle_state(sandbox_id)
        self.registry.save()

    async def cleanup_managed_sandboxes(self) -> None:
        managed_records = self.list_sandboxes()
        for record in managed_records:
            sandbox_id = record["sandbox_id"]
            if record.get("retention_policy") == "persistent":
                logger.info(
                    "[Computer] Preserve persistent sandbox during shutdown: sandbox_id=%s",
                    sandbox_id,
                )
                continue
            booter = self.session_booter.pop(sandbox_id, None)
            if booter is not None:
                try:
                    await self.get_provider(record.get("provider", "")).destroy_booter(
                        booter, record
                    )
                except Exception as shutdown_err:
                    logger.warning(
                        "[Computer] Failed to shutdown managed sandbox %s: %s",
                        sandbox_id,
                        shutdown_err,
                    )
            self.clear_idle_state(sandbox_id)
            self.registry.delete_sandbox(sandbox_id)
            self.drop_boot_lock(sandbox_id)
        self.registry.save()

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
                        self.save_registry()
                        logger.warning(
                            "[Computer] Failed to shutdown idle sandbox %s: %s",
                            sandbox_id,
                            shutdown_err,
                        )
                        return
                if record.get("retention_policy") == "persistent":
                    self.registry.update_sandbox_status(sandbox_id, "stopped")
                else:
                    self.registry.delete_sandbox(sandbox_id)
                    self.drop_boot_lock(sandbox_id)
                self.save_registry()
                return
        except asyncio.CancelledError:
            raise
        finally:
            state = self.idle_state.get(sandbox_id)
            if state is not None and state.expires_at == current_expires_at:
                self.idle_state.pop(sandbox_id, None)
