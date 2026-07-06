from __future__ import annotations

from typing import Any

from astrbot.core import logger
from astrbot.core.computer import computer_client
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle


class SandboxServiceError(Exception):
    pass


def _is_sandbox_name_conflict(error: Exception) -> bool:
    return isinstance(error, RuntimeError) and str(error).startswith("Sandbox name ")


def _is_sandbox_limit_error(error: Exception) -> bool:
    return isinstance(error, RuntimeError) and str(error).startswith(
        "Sandbox limit reached"
    )


def _is_sandbox_user_error(error: Exception) -> bool:
    if not isinstance(error, (RuntimeError, ValueError)):
        return False
    message = str(error)
    return (
        _is_sandbox_name_conflict(error)
        or _is_sandbox_limit_error(error)
        or "does not support persistent sandboxes" in message
        or "retention_policy must be" in message
        or "sandbox_name must be" in message
    )


class SandboxService:
    def __init__(self, core_lifecycle: AstrBotCoreLifecycle) -> None:
        self.core_lifecycle = core_lifecycle

    def list_providers(self, session_id: str) -> dict[str, Any]:
        config = self.core_lifecycle.star_context.get_config(umo=session_id)
        sandbox_config = config.get("provider_settings", {}).get("sandbox", {})
        default_provider_id = ""
        if isinstance(sandbox_config, dict):
            configured_provider_id = str(sandbox_config.get("booter") or "").strip()
            if computer_client.get_sandbox_provider_info(configured_provider_id):
                default_provider_id = configured_provider_id
        return {
            "providers": computer_client.list_sandbox_providers(),
            "default_provider_id": default_provider_id,
        }

    def list_sandboxes(self) -> dict[str, Any]:
        return {"sandboxes": computer_client.sandbox_manager.list_sandboxes()}

    def get_current_sandbox(self, session_id: str) -> Any:
        return computer_client.sandbox_manager.get_current_sandbox(session_id)

    async def create_sandbox(
        self,
        session_id: str,
        provider_id: str,
        sandbox_name: str | None = None,
    ) -> dict[str, Any]:
        if not provider_id:
            raise SandboxServiceError("provider_id is required")
        try:
            sandbox = await computer_client.sandbox_manager.create_sandbox_uncontrolled_deferred(
                self.core_lifecycle.star_context,
                session_id,
                provider_id,
                sandbox_name=sandbox_name,
            )
        except RuntimeError as exc:
            if _is_sandbox_name_conflict(exc) or _is_sandbox_limit_error(exc):
                logger.warning(str(exc))
                raise SandboxServiceError(str(exc)) from exc
            raise
        return {"sandbox": sandbox}

    async def switch_sandbox(self, session_id: str, sandbox_id: str) -> dict[str, Any]:
        sandbox = await computer_client.sandbox_manager.switch_current_sandbox_checked(
            session_id,
            sandbox_id,
            context=self.core_lifecycle.star_context,
        )
        return {"sandbox": sandbox}

    def release_current_sandbox(
        self,
        session_id: str,
        sandbox_id: str | None = None,
    ) -> dict[str, Any]:
        if sandbox_id:
            sandbox = computer_client.sandbox_manager.force_release_sandbox(sandbox_id)
        else:
            sandbox = computer_client.sandbox_manager.release_current_sandbox(session_id)
        return {"sandbox": sandbox}

    async def takeover_sandbox(self, session_id: str, sandbox_id: str) -> dict[str, Any]:
        sandbox = await computer_client.sandbox_manager.takeover_sandbox(
            session_id,
            sandbox_id,
            context=self.core_lifecycle.star_context,
        )
        return {"sandbox": sandbox}

    def set_default_sandbox(self, sandbox_id: str) -> dict[str, Any]:
        sandbox = computer_client.sandbox_manager.set_default_sandbox(sandbox_id)
        return {"sandbox": sandbox}

    async def run_shell(
        self,
        session_id: str,
        sandbox_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        command = str(payload.get("command") or "").strip()
        if not command:
            raise SandboxServiceError("command is required")
        booter = await computer_client.sandbox_manager.get_observer_booter_by_id(
            sandbox_id,
            session_id,
            require_lease=False,
            context=self.core_lifecycle.star_context,
        )
        shell = getattr(booter, "shell", None)
        if shell is None:
            raise SandboxServiceError("Sandbox does not support shell.")
        result = await shell.exec(
            command,
            cwd=payload.get("cwd"),
            env=payload.get("env"),
            timeout=payload.get("timeout", 300),
            shell=payload.get("shell", True),
        )
        return {"result": result}

    async def capture_screenshot(
        self,
        session_id: str,
        sandbox_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        booter = await computer_client.sandbox_manager.get_observer_booter_by_id(
            sandbox_id,
            session_id,
            require_lease=False,
            context=self.core_lifecycle.star_context,
        )
        gui = getattr(booter, "gui", None)
        if gui is None:
            raise SandboxServiceError("Sandbox does not support screenshots.")
        screenshot = await gui.screenshot(path=payload.get("path"))
        return {"screenshot": screenshot}

    def update_sandbox(self, sandbox_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current_sandbox = computer_client.sandbox_manager.registry.get_sandbox(
            sandbox_id
        )
        retention_policy = payload.get(
            "retention_policy",
            current_sandbox.get("retention_policy", "temporary")
            if current_sandbox
            else "temporary",
        )
        idle_timeout = payload.get(
            "idle_timeout",
            current_sandbox.get("idle_timeout") if current_sandbox else None,
        )
        expires_at = payload.get(
            "expires_at",
            current_sandbox.get("expires_at") if current_sandbox else None,
        )
        try:
            sandbox = computer_client.sandbox_manager.update_sandbox_config(
                sandbox_id,
                sandbox_name=payload.get("sandbox_name"),
                idle_timeout=idle_timeout,
                expires_at=expires_at,
                retention_policy=retention_policy,
            )
        except Exception as exc:
            if _is_sandbox_user_error(exc):
                logger.info("Failed to update sandbox: %s", exc)
                raise SandboxServiceError(str(exc)) from exc
            raise
        return {"sandbox": sandbox}

    async def destroy_sandbox(self, session_id: str, sandbox_id: str) -> dict[str, Any]:
        sandbox = await computer_client.sandbox_manager.destroy_sandbox_deferred(
            session_id,
            sandbox_id,
        )
        return {"sandbox": sandbox}
