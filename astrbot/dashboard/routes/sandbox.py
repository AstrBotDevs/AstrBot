import base64
import inspect
import shlex
import time
import traceback
import uuid
from pathlib import Path

from quart import jsonify, request

from astrbot.core import logger
from astrbot.core.computer import computer_client
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from .route import Response, Route, RouteContext


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


def _legacy_session_id(data: dict) -> str:
    return str(data.get("session_id") or data.get("umo") or "dashboard")


def _legacy_terminal_command(command: str) -> str:
    return f"script -q -e -c {shlex.quote(command)} /dev/null"


class SandboxRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.routes = [
            ("/sandbox/providers", ("GET", self.list_providers)),
            ("/sandbox", ("GET", self.list_sandboxes)),
            ("/sandbox/current", ("GET", self.get_current_sandbox)),
            ("/sandbox/current", ("DELETE", self.release_current_sandbox)),
            ("/sandbox", ("POST", self.create_sandbox)),
            ("/sandbox/<sandbox_id>/switch", ("POST", self.switch_sandbox)),
            ("/sandbox/<sandbox_id>/takeover", ("POST", self.takeover_sandbox)),
            ("/sandbox/<sandbox_id>/default", ("POST", self.set_default_sandbox)),
            ("/sandbox/<sandbox_id>/shell", ("POST", self.run_shell)),
            ("/sandbox/<sandbox_id>/screenshot", ("POST", self.capture_screenshot)),
            ("/sandbox/<sandbox_id>", ("PATCH", self.update_sandbox)),
            ("/sandbox/<sandbox_id>", ("DELETE", self.destroy_sandbox)),
            ("/sandboxes", ("GET", self.legacy_list_sandboxes)),
            ("/sandboxes/current", ("GET", self.legacy_get_current_sandbox)),
            ("/sandboxes/create", ("POST", self.legacy_create_sandbox)),
            ("/sandboxes/switch-current", ("POST", self.legacy_switch_current)),
            ("/sandboxes/release", ("POST", self.legacy_release_sandbox)),
            ("/sandboxes/takeover", ("POST", self.legacy_takeover_sandbox)),
            ("/sandboxes/destroy", ("POST", self.legacy_destroy_sandbox)),
            ("/sandboxes/screenshot", ("POST", self.legacy_capture_screenshot)),
            ("/sandboxes/shell", ("POST", self.legacy_run_shell)),
            ("/sandboxes/default/set", ("POST", self.legacy_set_default_sandbox)),
            ("/sandboxes/config/update", ("POST", self.legacy_update_sandbox)),
        ]
        self.register_routes()

    def _session_id(self) -> str:
        return request.args.get("session_id") or "dashboard"

    def _legacy_registry(self):
        return getattr(
            computer_client,
            "cua_registry",
            computer_client.sandbox_manager.registry,
        )

    @staticmethod
    def _legacy_sandbox_payload(record: dict) -> dict:
        payload = dict(record)
        payload.setdefault("booter_type", payload.get("provider"))
        if payload.get("provider") == "cua" and not payload.get("capabilities"):
            payload["capabilities"] = ["create", "destroy", "screenshot", "shell"]
        else:
            payload["capabilities"] = sorted(payload.get("capabilities", []))
        payload["tool_names"] = sorted(payload.get("tool_names", []))
        return payload

    def _legacy_list_sandbox_payloads(self) -> list[dict]:
        return [
            self._legacy_sandbox_payload(record)
            for record in self._legacy_registry().list_sandboxes()
            if record.get("managed")
        ]

    async def _legacy_json(self) -> dict:
        data = await request.get_json(silent=True)
        return data if isinstance(data, dict) else {}

    @staticmethod
    async def _legacy_booter_available(booter) -> bool:
        available = getattr(booter, "available", None)
        if available is None:
            return True
        result = available()
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    def _legacy_save_registry(self) -> None:
        try:
            self._legacy_registry().save()
        except Exception as exc:
            logger.warning("Failed to save legacy sandbox registry: %s", exc)

    async def _legacy_get_running_booter(self, sandbox_id: str):
        record = self._legacy_registry().get_sandbox(sandbox_id)
        if record is None or not record.get("managed"):
            raise RuntimeError(f"Sandbox {sandbox_id} not found")
        booter = computer_client.sandbox_manager.session_booter.get(sandbox_id)
        if booter is None or not await self._legacy_booter_available(booter):
            raise RuntimeError(f"Sandbox {sandbox_id} is not running")
        return booter

    async def legacy_list_sandboxes(self):
        try:
            return jsonify(
                Response()
                .ok(data={"sandboxes": self._legacy_list_sandbox_payloads()})
                .__dict__
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(
                Response().error(f"Failed to list sandboxes: {e!s}").__dict__
            )

    async def legacy_get_current_sandbox(self):
        try:
            session_id = (
                request.args.get("session_id") or request.args.get("umo") or "dashboard"
            )
            sandbox_id = self._legacy_registry().get_current_sandbox_id(str(session_id))
            return jsonify(
                Response()
                .ok(
                    data={
                        "current_sandbox_id": sandbox_id,
                        "sandbox": self._legacy_registry().get_sandbox(sandbox_id)
                        if sandbox_id
                        else None,
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(
                Response().error(f"Failed to get current sandbox: {e!s}").__dict__
            )

    async def legacy_create_sandbox(self):
        data = await self._legacy_json()
        provider = str(data.get("provider") or data.get("provider_id") or "cua")
        if provider != "cua":
            return jsonify(
                Response().error(f"Provider {provider} is not supported.").__dict__
            )
        session_id = _legacy_session_id(data)
        sandbox_id = f"cua-{uuid.uuid4().hex[:12]}"
        sandbox_name = str(data.get("sandbox_name") or sandbox_id)
        cua_kwargs = {"image": "linux"}
        try:
            booter_factory = computer_client._boot_managed_cua_sandbox
            record = self._legacy_registry().upsert_sandbox(
                sandbox_id=sandbox_id,
                sandbox_name=sandbox_name,
                booter_type="cua",
                provider="cua",
                managed=True,
                created_by_astrbot=True,
                owner_user_id=session_id,
                owner_session_id=session_id,
                connect_info={"name": sandbox_name},
                capabilities=["create", "destroy", "screenshot", "shell"],
            )
            client = await booter_factory(
                self.core_lifecycle.star_context,
                session_id,
                sandbox_id,
                cua_kwargs,
            )
            client.sandbox_id = sandbox_id
            computer_client.sandbox_manager.session_booter[sandbox_id] = client
            self._legacy_registry().touch_sandbox(sandbox_id)
            self._legacy_save_registry()
            return jsonify(
                Response()
                .ok(
                    data={
                        "sandbox": self._legacy_registry().get_sandbox(sandbox_id)
                        or record
                    }
                )
                .__dict__
            )
        except Exception as e:
            self._legacy_registry().delete_sandbox(sandbox_id)
            self._legacy_save_registry()
            return jsonify(Response().error(str(e)).__dict__)

    async def legacy_switch_current(self):
        data = await self._legacy_json()
        sandbox_id = data.get("sandbox_id")
        if not sandbox_id:
            return jsonify(Response().error("sandbox_id is required.").__dict__)
        session_id = _legacy_session_id(data)
        try:
            record = self._legacy_registry().get_sandbox(str(sandbox_id))
            if record is None or not record.get("managed"):
                raise RuntimeError(f"Sandbox {sandbox_id} not found")
            if not self._legacy_registry().acquire_lease(
                sandbox_id=str(sandbox_id),
                session_id=session_id,
                user_id=session_id,
                ttl=300,
            ):
                raise RuntimeError(f"Sandbox {sandbox_id} is busy")
            self._legacy_registry().set_current_sandbox_id(session_id, str(sandbox_id))
            self._legacy_registry().touch_sandbox(str(sandbox_id))
            self._legacy_save_registry()
            return jsonify(
                Response()
                .ok(
                    data={
                        "sandbox": self._legacy_registry().get_sandbox(str(sandbox_id))
                        or record
                    }
                )
                .__dict__
            )
        except Exception as e:
            return jsonify(Response().error(str(e)).__dict__)

    async def legacy_release_sandbox(self):
        data = await self._legacy_json()
        session_id = _legacy_session_id(data)
        sandbox_id = data.get(
            "sandbox_id"
        ) or self._legacy_registry().get_current_sandbox_id(session_id)
        if not sandbox_id:
            return jsonify(Response().error("No current sandbox").__dict__)
        try:
            record = self._legacy_registry().get_sandbox(str(sandbox_id))
            if record is None:
                raise RuntimeError(f"Sandbox {sandbox_id} not found")
            controller_session_id = record.get("controller_session_id")
            lease_expires_at = record.get("lease_expires_at")
            if (
                controller_session_id
                and controller_session_id != session_id
                and lease_expires_at
                and float(lease_expires_at) > time.time()
            ):
                raise RuntimeError(
                    f"Sandbox {sandbox_id} is controlled by another session"
                )
            released = self._legacy_registry().release_lease(str(sandbox_id)) or record
            if self._legacy_registry().get_current_sandbox_id(session_id) == sandbox_id:
                self._legacy_registry().set_current_sandbox_id(session_id, None)
            self._legacy_save_registry()
            return jsonify(Response().ok(data={"sandbox": released}).__dict__)
        except Exception as e:
            return jsonify(Response().error(str(e)).__dict__)

    async def legacy_takeover_sandbox(self):
        data = await self._legacy_json()
        sandbox_id = data.get("sandbox_id")
        if not sandbox_id:
            return jsonify(Response().error("sandbox_id is required.").__dict__)
        session_id = _legacy_session_id(data)
        try:
            record = self._legacy_registry().get_sandbox(str(sandbox_id))
            if record is None or not record.get("managed"):
                raise RuntimeError(f"Sandbox {sandbox_id} not found")
            updated = (
                self._legacy_registry().takeover_lease(
                    sandbox_id=str(sandbox_id),
                    session_id=session_id,
                    user_id=session_id,
                    ttl=300,
                )
                or record
            )
            self._legacy_registry().set_current_sandbox_id(session_id, str(sandbox_id))
            self._legacy_save_registry()
            return jsonify(Response().ok(data={"sandbox": updated}).__dict__)
        except Exception as e:
            return jsonify(Response().error(str(e)).__dict__)

    async def legacy_destroy_sandbox(self):
        data = await self._legacy_json()
        sandbox_id = data.get("sandbox_id")
        if not sandbox_id:
            return jsonify(Response().error("sandbox_id is required.").__dict__)
        session_id = _legacy_session_id(data)
        try:
            record = self._legacy_registry().get_sandbox(str(sandbox_id))
            if record is None or not record.get("managed"):
                raise RuntimeError(f"Sandbox {sandbox_id} not found")
            controller_session_id = record.get("controller_session_id")
            lease_expires_at = record.get("lease_expires_at")
            if (
                controller_session_id
                and controller_session_id != session_id
                and lease_expires_at
                and float(lease_expires_at) > time.time()
            ):
                raise RuntimeError(
                    f"Sandbox {sandbox_id} is controlled by another session"
                )
            booter = computer_client.sandbox_manager.session_booter.pop(
                str(sandbox_id), None
            )
            if booter is not None:
                shutdown = getattr(booter, "shutdown", None)
                if shutdown is not None:
                    result = shutdown()
                    if inspect.isawaitable(result):
                        await result
            self._legacy_registry().delete_sandbox(str(sandbox_id))
            self._legacy_save_registry()
            return jsonify(Response().ok(data={"sandbox": record}).__dict__)
        except Exception as e:
            return jsonify(Response().error(str(e)).__dict__)

    async def legacy_set_default_sandbox(self):
        data = await self._legacy_json()
        sandbox_id = data.get("sandbox_id")
        if not sandbox_id:
            return jsonify(Response().error("sandbox_id is required.").__dict__)
        try:
            record = self._legacy_registry().get_sandbox(str(sandbox_id))
            if record is None or not record.get("managed"):
                raise RuntimeError(f"Sandbox {sandbox_id} not found")
            self._legacy_registry().set_default_sandbox_id(str(sandbox_id))
            self._legacy_save_registry()
            return jsonify(
                Response()
                .ok(
                    data={
                        "sandbox": self._legacy_registry().get_sandbox(str(sandbox_id))
                        or record
                    }
                )
                .__dict__
            )
        except Exception as e:
            return jsonify(Response().error(str(e)).__dict__)

    async def legacy_update_sandbox(self):
        data = await self._legacy_json()
        sandbox_id = data.get("sandbox_id")
        if not sandbox_id:
            return jsonify(Response().error("sandbox_id is required.").__dict__)
        try:
            retention_policy = str(data.get("retention_policy") or "temporary")
            if retention_policy not in {"temporary", "persistent"}:
                raise RuntimeError("retention_policy must be temporary or persistent")
            idle_timeout = data.get("idle_timeout")
            expires_at = data.get("expires_at")
            if retention_policy == "persistent":
                idle_timeout = None
                expires_at = None
            updated = self._legacy_registry().update_sandbox_config(
                str(sandbox_id),
                sandbox_name=data.get("sandbox_name")
                if "sandbox_name" in data
                else None,
                idle_timeout=idle_timeout,
                expires_at=expires_at,
                retention_policy=retention_policy,
            )
            if updated is None:
                raise RuntimeError(f"Sandbox {sandbox_id} not found")
            self._legacy_save_registry()
            return jsonify(Response().ok(data={"sandbox": updated}).__dict__)
        except Exception as e:
            return jsonify(Response().error(str(e)).__dict__)

    async def legacy_capture_screenshot(self):
        data = await self._legacy_json()
        sandbox_id = data.get("sandbox_id")
        if not sandbox_id:
            return jsonify(Response().error("sandbox_id is required.").__dict__)
        try:
            booter = await self._legacy_get_running_booter(str(sandbox_id))
            gui = getattr(booter, "gui", None)
            if gui is None:
                return jsonify(
                    Response()
                    .error("Target sandbox does not support screenshot.")
                    .__dict__
                )
            screenshot_dir = Path(get_astrbot_temp_path()) / "sandbox_screenshots"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            path = screenshot_dir / f"{uuid.uuid4().hex}.png"
            try:
                result = await gui.screenshot(str(path))
                mime_type = result.get("mime_type") or "image/png"
                image_base64 = result.get("base64")
                if not image_base64:
                    image_base64 = base64.b64encode(path.read_bytes()).decode("ascii")
                screenshot = {
                    "mime_type": mime_type,
                    "base64": image_base64,
                    "data_url": f"data:{mime_type};base64,{image_base64}",
                }
                return jsonify(Response().ok(data={"screenshot": screenshot}).__dict__)
            finally:
                path.unlink(missing_ok=True)
        except Exception as e:
            return jsonify(Response().error(str(e)).__dict__)

    async def legacy_run_shell(self):
        data = await self._legacy_json()
        sandbox_id = data.get("sandbox_id")
        command = str(data.get("command") or "").strip()
        if not sandbox_id:
            return jsonify(Response().error("sandbox_id is required.").__dict__)
        if not command:
            return jsonify(Response().error("command is required.").__dict__)
        started_at = time.monotonic()
        try:
            logger.info(
                "[Dashboard] Legacy sandbox shell exec start: sandbox_id=%s timeout=%s background=%s command=%r",
                sandbox_id,
                data.get("timeout") or 300,
                bool(data.get("background", False)),
                command[:500],
            )
            booter = await self._legacy_get_running_booter(str(sandbox_id))
            shell = getattr(booter, "shell", None)
            if shell is None:
                return jsonify(
                    Response().error("Target sandbox does not support shell.").__dict__
                )
            result = await shell.exec(
                _legacy_terminal_command(command),
                cwd=str(data["cwd"]) if data.get("cwd") else None,
                timeout=int(data.get("timeout") or 300),
                background=bool(data.get("background", False)),
            )
            logger.info(
                "[Dashboard] Legacy sandbox shell exec done: sandbox_id=%s exit_code=%s elapsed_ms=%d stdout_len=%d stderr_len=%d",
                sandbox_id,
                result.get("exit_code", result.get("returncode")),
                int((time.monotonic() - started_at) * 1000),
                len(str(result.get("stdout", "") or "")),
                len(str(result.get("stderr", "") or "")),
            )
            return jsonify(Response().ok(data={"result": result}).__dict__)
        except Exception as e:
            logger.warning(
                "[Dashboard] Legacy sandbox shell exec failed: sandbox_id=%s elapsed_ms=%d error=%s",
                sandbox_id,
                int((time.monotonic() - started_at) * 1000),
                str(e) or type(e).__name__,
                exc_info=True,
            )
            return jsonify(Response().error(str(e)).__dict__)

    async def list_providers(self):
        try:
            config = self.core_lifecycle.star_context.get_config(umo=self._session_id())
            sandbox_config = config.get("provider_settings", {}).get("sandbox", {})
            default_provider_id = ""
            if isinstance(sandbox_config, dict):
                configured_provider_id = str(sandbox_config.get("booter") or "").strip()
                if computer_client.get_sandbox_provider_info(configured_provider_id):
                    default_provider_id = configured_provider_id
            return jsonify(
                Response()
                .ok(
                    data={
                        "providers": computer_client.list_sandbox_providers(),
                        "default_provider_id": default_provider_id,
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(
                Response().error(f"Failed to list sandbox providers: {e!s}").__dict__
            )

    async def list_sandboxes(self):
        try:
            return jsonify(
                Response()
                .ok(
                    data={"sandboxes": computer_client.sandbox_manager.list_sandboxes()}
                )
                .__dict__
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(
                Response().error(f"Failed to list sandboxes: {e!s}").__dict__
            )

    async def get_current_sandbox(self):
        try:
            return jsonify(
                Response()
                .ok(
                    data=computer_client.sandbox_manager.get_current_sandbox(
                        self._session_id()
                    )
                )
                .__dict__
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(
                Response().error(f"Failed to get current sandbox: {e!s}").__dict__
            )

    async def create_sandbox(self):
        try:
            data = await request.get_json(silent=True) or {}
            provider_id = str(data.get("provider_id") or "").strip()
            if not provider_id:
                return jsonify(Response().error("provider_id is required").__dict__)
            sandbox = await computer_client.sandbox_manager.create_sandbox_uncontrolled_deferred(
                self.core_lifecycle.star_context,
                self._session_id(),
                provider_id,
                sandbox_name=data.get("sandbox_name"),
            )
            return jsonify(Response().ok(data={"sandbox": sandbox}).__dict__)
        except RuntimeError as e:
            if _is_sandbox_name_conflict(e) or _is_sandbox_limit_error(e):
                logger.warning(str(e))
                return jsonify(Response().error(str(e)).__dict__)
            logger.error(traceback.format_exc())
            return jsonify(
                Response().error(f"Failed to create sandbox: {e!s}").__dict__
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(
                Response().error(f"Failed to create sandbox: {e!s}").__dict__
            )

    async def switch_sandbox(self, sandbox_id: str):
        try:
            sandbox = (
                await computer_client.sandbox_manager.switch_current_sandbox_checked(
                    self._session_id(),
                    sandbox_id,
                    context=self.core_lifecycle.star_context,
                )
            )
            return jsonify(Response().ok(data={"sandbox": sandbox}).__dict__)
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(
                Response().error(f"Failed to switch sandbox: {e!s}").__dict__
            )

    async def release_current_sandbox(self):
        try:
            sandbox_id = request.args.get("sandbox_id")
            if sandbox_id:
                sandbox = computer_client.sandbox_manager.force_release_sandbox(
                    sandbox_id
                )
            else:
                sandbox = computer_client.sandbox_manager.release_current_sandbox(
                    self._session_id()
                )
            return jsonify(Response().ok(data={"sandbox": sandbox}).__dict__)
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(
                Response().error(f"Failed to release sandbox: {e!s}").__dict__
            )

    async def takeover_sandbox(self, sandbox_id: str):
        try:
            sandbox = await computer_client.sandbox_manager.takeover_sandbox(
                self._session_id(), sandbox_id, context=self.core_lifecycle.star_context
            )
            return jsonify(Response().ok(data={"sandbox": sandbox}).__dict__)
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(
                Response().error(f"Failed to takeover sandbox: {e!s}").__dict__
            )

    async def set_default_sandbox(self, sandbox_id: str):
        try:
            sandbox = computer_client.sandbox_manager.set_default_sandbox(sandbox_id)
            return jsonify(Response().ok(data={"sandbox": sandbox}).__dict__)
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(
                Response().error(f"Failed to set default sandbox: {e!s}").__dict__
            )

    async def run_shell(self, sandbox_id: str):
        try:
            data = await request.get_json(silent=True) or {}
            command = str(data.get("command") or "").strip()
            if not command:
                return jsonify(Response().error("command is required").__dict__)
            # Dashboard shell access is an administrative operation; it does
            # not need a lease so admins can operate any sandbox at any time.
            booter = await computer_client.sandbox_manager.get_observer_booter_by_id(
                sandbox_id,
                self._session_id(),
                require_lease=False,
                context=self.core_lifecycle.star_context,
            )
            shell = getattr(booter, "shell", None)
            if shell is None:
                return jsonify(
                    Response().error("Sandbox does not support shell.").__dict__
                )
            result = await shell.exec(
                command,
                cwd=data.get("cwd"),
                env=data.get("env"),
                timeout=data.get("timeout", 300),
                shell=data.get("shell", True),
            )
            return jsonify(Response().ok(data={"result": result}).__dict__)
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(
                Response().error(f"Failed to run sandbox shell: {e!s}").__dict__
            )

    async def capture_screenshot(self, sandbox_id: str):
        try:
            data = await request.get_json(silent=True) or {}
            # Dashboard screenshot is a read-only observer operation; it does
            # not need a lease and must not reset the sandbox idle timer.
            booter = await computer_client.sandbox_manager.get_observer_booter_by_id(
                sandbox_id,
                self._session_id(),
                require_lease=False,
                context=self.core_lifecycle.star_context,
            )
            gui = getattr(booter, "gui", None)
            if gui is None:
                return jsonify(
                    Response().error("Sandbox does not support screenshots.").__dict__
                )
            screenshot = await gui.screenshot(path=data.get("path"))
            return jsonify(Response().ok(data={"screenshot": screenshot}).__dict__)
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(
                Response()
                .error(f"Failed to capture sandbox screenshot: {e!s}")
                .__dict__
            )

    async def update_sandbox(self, sandbox_id: str):
        try:
            data = await request.get_json(silent=True) or {}
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
            return jsonify(Response().ok(data={"sandbox": sandbox}).__dict__)
        except Exception as e:
            if _is_sandbox_user_error(e):
                logger.info("Failed to update sandbox: %s", e)
            else:
                logger.error(traceback.format_exc())
            return jsonify(
                Response().error(f"Failed to update sandbox: {e!s}").__dict__
            )

    async def destroy_sandbox(self, sandbox_id: str):
        try:
            sandbox = await computer_client.sandbox_manager.destroy_sandbox_deferred(
                self._session_id(), sandbox_id
            )
            return jsonify(Response().ok(data={"sandbox": sandbox}).__dict__)
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(
                Response().error(f"Failed to destroy sandbox: {e!s}").__dict__
            )
