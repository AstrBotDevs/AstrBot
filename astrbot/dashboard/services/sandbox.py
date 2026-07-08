import json
import traceback
from collections.abc import AsyncIterator

from astrbot.core import logger
from astrbot.core.computer import computer_client
from astrbot.core.computer.olayer import ShellComponent
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle

from .sandbox_helpers import (
    is_sandbox_limit_error,
    is_sandbox_name_conflict,
    is_sandbox_user_error,
    sanitize_shell_timeout,
)


class SandboxServiceError(Exception):
    def __init__(
        self,
        message: str,
        *,
        public_message: str | None = None,
        log_traceback: bool = True,
    ) -> None:
        super().__init__(message)
        self.public_message = public_message or message
        self.log_traceback = log_traceback


class SandboxService:
    def __init__(self, core_lifecycle: AstrBotCoreLifecycle) -> None:
        self.core_lifecycle = core_lifecycle

    def list_providers(self, session_id: str) -> dict:
        try:
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
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SandboxServiceError(
                f"Failed to list sandbox providers: {exc!s}",
                public_message="Failed to list sandbox providers.",
            ) from exc

    async def list_sandboxes(self) -> dict:
        try:
            return {
                "sandboxes": await computer_client.sandbox_manager.list_sandboxes_checked()
            }
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SandboxServiceError(
                f"Failed to list sandboxes: {exc!s}",
                public_message="Failed to list sandboxes.",
            ) from exc

    def get_current_sandbox(self, session_id: str) -> dict:
        try:
            return computer_client.sandbox_manager.get_current_sandbox(session_id)
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SandboxServiceError(
                f"Failed to get current sandbox: {exc!s}",
                public_message="Failed to get current sandbox.",
            ) from exc

    async def create_sandbox(self, session_id: str, data: dict) -> dict:
        try:
            provider_id = str(data.get("provider_id") or "").strip()
            if not provider_id:
                raise SandboxServiceError(
                    "provider_id is required", log_traceback=False
                )
            sandbox = await computer_client.sandbox_manager.create_sandbox_uncontrolled_deferred(
                self.core_lifecycle.star_context,
                session_id,
                provider_id,
                sandbox_name=data.get("sandbox_name"),
            )
            return {"sandbox": sandbox}
        except RuntimeError as exc:
            if is_sandbox_name_conflict(exc) or is_sandbox_limit_error(exc):
                logger.warning(str(exc))
                raise SandboxServiceError(str(exc), log_traceback=False) from exc
            logger.error(traceback.format_exc())
            raise SandboxServiceError(
                f"Failed to create sandbox: {exc!s}",
                public_message="Failed to create sandbox.",
            ) from exc
        except SandboxServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SandboxServiceError(
                f"Failed to create sandbox: {exc!s}",
                public_message="Failed to create sandbox.",
            ) from exc

    async def switch_sandbox(self, session_id: str, sandbox_id: str) -> dict:
        try:
            sandbox = (
                await computer_client.sandbox_manager.switch_current_sandbox_checked(
                    session_id,
                    sandbox_id,
                    context=self.core_lifecycle.star_context,
                )
            )
            return {"sandbox": sandbox}
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SandboxServiceError(
                f"Failed to switch sandbox: {exc!s}",
                public_message="Failed to switch sandbox.",
            ) from exc

    def release_current_sandbox(
        self,
        session_id: str,
        sandbox_id: str | None = None,
        *,
        is_dashboard_user: bool = False,
    ) -> dict:
        try:
            sandbox = (
                computer_client.sandbox_manager.registry.get_sandbox(sandbox_id)
                if sandbox_id
                else None
            )
            controller_session_id = str(
                sandbox.get("controller_session_id") if sandbox else ""
            )
            can_dashboard_bypass_lease = is_dashboard_user and (
                not controller_session_id
                or controller_session_id.startswith("webchat:")
            )
            if sandbox_id and can_dashboard_bypass_lease:
                sandbox = computer_client.sandbox_manager.force_release_sandbox(
                    sandbox_id
                )
            else:
                sandbox = computer_client.sandbox_manager.release_current_sandbox(
                    session_id,
                    sandbox_id,
                )
            return {"sandbox": sandbox}
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SandboxServiceError(
                f"Failed to release sandbox: {exc!s}",
                public_message="Failed to release sandbox.",
            ) from exc

    def force_release_sandbox(self, sandbox_id: str) -> dict:
        try:
            sandbox = computer_client.sandbox_manager.force_release_sandbox(sandbox_id)
            return {"sandbox": sandbox}
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SandboxServiceError(
                f"Failed to force release sandbox: {exc!s}",
                public_message="Failed to force release sandbox.",
            ) from exc

    async def takeover_sandbox(self, session_id: str, sandbox_id: str) -> dict:
        try:
            sandbox = await computer_client.sandbox_manager.takeover_sandbox(
                session_id, sandbox_id, context=self.core_lifecycle.star_context
            )
            return {"sandbox": sandbox}
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SandboxServiceError(
                f"Failed to takeover sandbox: {exc!s}",
                public_message="Failed to takeover sandbox.",
            ) from exc

    def set_default_sandbox(self, sandbox_id: str) -> dict:
        try:
            sandbox = computer_client.sandbox_manager.set_default_sandbox(sandbox_id)
            return {"sandbox": sandbox}
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SandboxServiceError(
                f"Failed to set default sandbox: {exc!s}",
                public_message="Failed to set default sandbox.",
            ) from exc

    async def run_shell(
        self,
        session_id: str,
        sandbox_id: str,
        data: dict,
        *,
        is_dashboard_user: bool = False,
    ) -> dict:
        try:
            command = str(data.get("command") or "").strip()
            if not command:
                raise SandboxServiceError("command is required", log_traceback=False)
            sandbox = computer_client.sandbox_manager.registry.get_sandbox(sandbox_id)
            controller_session_id = str(
                sandbox.get("controller_session_id") if sandbox else ""
            )
            require_lease = not (
                is_dashboard_user
                and (
                    not controller_session_id
                    or controller_session_id.startswith("webchat:")
                )
            )
            booter = await computer_client.sandbox_manager.get_observer_booter_by_id(
                sandbox_id,
                session_id,
                require_lease=require_lease,
                context=self.core_lifecycle.star_context,
            )
            shell = getattr(booter, "shell", None)
            if shell is None:
                raise SandboxServiceError(
                    "Sandbox does not support shell.", log_traceback=False
                )
            result = await shell.exec(
                command,
                cwd=data.get("cwd"),
                env=data.get("env"),
                timeout=sanitize_shell_timeout(data.get("timeout", 300)),
                shell=data.get("shell", True),
            )
            return {"result": result}
        except SandboxServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SandboxServiceError(
                f"Failed to run sandbox shell: {exc!s}",
                public_message="Failed to run sandbox shell.",
            ) from exc

    async def admin_run_shell(self, sandbox_id: str, data: dict) -> dict:
        try:
            command = str(data.get("command") or "").strip()
            if not command:
                raise SandboxServiceError("command is required", log_traceback=False)
            booter = await computer_client.sandbox_manager.get_observer_booter_by_id(
                sandbox_id,
                "dashboard",
                require_lease=False,
                context=self.core_lifecycle.star_context,
            )
            shell = getattr(booter, "shell", None)
            if shell is None:
                raise SandboxServiceError(
                    "Sandbox does not support shell.", log_traceback=False
                )
            result = await shell.exec(
                command,
                cwd=data.get("cwd"),
                env=data.get("env"),
                timeout=sanitize_shell_timeout(data.get("timeout", 300)),
                shell=data.get("shell", True),
            )
            return {"result": result}
        except SandboxServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SandboxServiceError(
                f"Failed to run admin sandbox shell: {exc!s}",
                public_message="Failed to run admin sandbox shell.",
            ) from exc

    async def admin_run_shell_stream(
        self, sandbox_id: str, data: dict
    ) -> AsyncIterator[str]:
        """Run an admin shell command and yield SSE-formatted stream events.

        Args:
            sandbox_id: Sandbox identifier.
            data: Shell execution request payload.

        Yields:
            Server-sent event chunks containing shell stream events.
        """
        try:
            command = str(data.get("command") or "").strip()
            if not command:
                raise SandboxServiceError("command is required", log_traceback=False)
            booter = await computer_client.sandbox_manager.get_observer_booter_by_id(
                sandbox_id,
                "dashboard",
                require_lease=False,
                context=self.core_lifecycle.star_context,
            )
            shell = getattr(booter, "shell", None)
            if shell is None:
                raise SandboxServiceError(
                    "Sandbox does not support shell.", log_traceback=False
                )

            exec_stream = None
            for cls in type(shell).mro():
                if cls is ShellComponent:
                    break
                if "exec_stream" in cls.__dict__:
                    exec_stream = getattr(shell, "exec_stream", None)
                    break
            if callable(exec_stream):
                stream = exec_stream(
                    command,
                    cwd=data.get("cwd"),
                    env=data.get("env"),
                    timeout=sanitize_shell_timeout(data.get("timeout", 300)),
                    shell=data.get("shell", True),
                )
                if hasattr(stream, "__aiter__"):
                    async for event in stream:
                        yield self._shell_stream_sse(event)
                    return

            result = await shell.exec(
                command,
                cwd=data.get("cwd"),
                env=data.get("env"),
                timeout=sanitize_shell_timeout(data.get("timeout", 300)),
                shell=data.get("shell", True),
            )
            stdout = str(result.get("stdout") or "")
            stderr = str(result.get("stderr") or "")
            if stdout:
                yield self._shell_stream_sse({"type": "stdout", "data": stdout})
            if stderr:
                yield self._shell_stream_sse({"type": "stderr", "data": stderr})
            yield self._shell_stream_sse(
                {
                    "type": "exit",
                    "exit_code": result.get("exit_code", result.get("returncode")),
                    "success": result.get("success"),
                }
            )
        except SandboxServiceError as exc:
            if exc.log_traceback:
                logger.error(traceback.format_exc())
            yield self._shell_stream_sse(
                {"type": "error", "message": exc.public_message}
            )
        except Exception as exc:
            logger.error(traceback.format_exc())
            yield self._shell_stream_sse(
                {
                    "type": "error",
                    "message": f"Failed to run admin sandbox shell: {exc!s}",
                }
            )

    @staticmethod
    def _shell_stream_sse(event: dict) -> str:
        """Encode a shell stream event as a server-sent event chunk.

        Args:
            event: Shell stream event payload.

        Returns:
            SSE chunk string.
        """
        return (
            f"data: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n"
        )

    async def capture_screenshot(
        self,
        session_id: str,
        sandbox_id: str,
        data: dict,
        *,
        is_dashboard_user: bool = False,
    ) -> dict:
        try:
            sandbox = computer_client.sandbox_manager.registry.get_sandbox(sandbox_id)
            controller_session_id = str(
                sandbox.get("controller_session_id") if sandbox else ""
            )
            require_lease = not (
                is_dashboard_user
                and (
                    not controller_session_id
                    or controller_session_id.startswith("webchat:")
                )
            )
            booter = await computer_client.sandbox_manager.get_observer_booter_by_id(
                sandbox_id,
                session_id,
                require_lease=require_lease,
                context=self.core_lifecycle.star_context,
            )
            gui = getattr(booter, "gui", None)
            if gui is None:
                raise SandboxServiceError(
                    "Sandbox does not support screenshots.", log_traceback=False
                )
            screenshot = await gui.screenshot(path=data.get("path"))
            return {"screenshot": screenshot}
        except SandboxServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SandboxServiceError(
                f"Failed to capture sandbox screenshot: {exc!s}",
                public_message="Failed to capture sandbox screenshot.",
            ) from exc

    async def admin_capture_screenshot(self, sandbox_id: str, data: dict) -> dict:
        try:
            booter = await computer_client.sandbox_manager.get_observer_booter_by_id(
                sandbox_id,
                "dashboard",
                require_lease=False,
                context=self.core_lifecycle.star_context,
            )
            gui = getattr(booter, "gui", None)
            if gui is None:
                raise SandboxServiceError(
                    "Sandbox does not support screenshots.", log_traceback=False
                )
            screenshot = await gui.screenshot(path=data.get("path"))
            return {"screenshot": screenshot}
        except SandboxServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SandboxServiceError(
                f"Failed to capture admin sandbox screenshot: {exc!s}",
                public_message="Failed to capture admin sandbox screenshot.",
            ) from exc

    def update_sandbox(self, sandbox_id: str, data: dict) -> dict:
        try:
            current_sandbox = computer_client.sandbox_manager.registry.get_sandbox(
                sandbox_id
            )
            retention_policy = data.get(
                "retention_policy",
                current_sandbox.get("retention_policy", "temporary")
                if current_sandbox
                else "temporary",
            )
            idle_timeout = data.get(
                "idle_timeout",
                current_sandbox.get("idle_timeout") if current_sandbox else None,
            )
            expires_at = data.get(
                "expires_at",
                current_sandbox.get("expires_at") if current_sandbox else None,
            )
            sandbox = computer_client.sandbox_manager.update_sandbox_config(
                sandbox_id,
                sandbox_name=data.get("sandbox_name"),
                idle_timeout=idle_timeout,
                expires_at=expires_at,
                retention_policy=retention_policy,
            )
            return {"sandbox": sandbox}
        except Exception as exc:
            if is_sandbox_user_error(exc):
                logger.info("Failed to update sandbox: %s", exc)
                raise SandboxServiceError(str(exc), log_traceback=False) from exc
            logger.error(traceback.format_exc())
            raise SandboxServiceError(
                f"Failed to update sandbox: {exc!s}",
                public_message="Failed to update sandbox.",
            ) from exc

    async def destroy_sandbox(self, session_id: str, sandbox_id: str) -> dict:
        try:
            sandbox = await computer_client.sandbox_manager.destroy_sandbox_deferred(
                session_id, sandbox_id
            )
            return {"sandbox": sandbox}
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SandboxServiceError(
                f"Failed to destroy sandbox: {exc!s}",
                public_message="Failed to destroy sandbox.",
            ) from exc

    async def force_destroy_sandbox(self, sandbox_id: str) -> dict:
        try:
            computer_client.sandbox_manager.force_release_sandbox(sandbox_id)
            sandbox = await computer_client.sandbox_manager.destroy_sandbox_deferred(
                "dashboard", sandbox_id
            )
            return {"sandbox": sandbox}
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SandboxServiceError(
                f"Failed to force destroy sandbox: {exc!s}",
                public_message="Failed to force destroy sandbox.",
            ) from exc
