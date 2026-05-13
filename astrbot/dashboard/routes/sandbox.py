import traceback

from quart import jsonify, request

from astrbot.core import logger
from astrbot.core.computer import computer_client
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle

from .route import Response, Route, RouteContext


def _is_sandbox_name_conflict(error: Exception) -> bool:
    return isinstance(error, RuntimeError) and str(error).startswith("Sandbox name ")


def _is_sandbox_limit_error(error: Exception) -> bool:
    return isinstance(error, RuntimeError) and str(error).startswith(
        "Sandbox limit reached"
    )


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
        ]
        self.register_routes()

    def _session_id(self) -> str:
        return request.args.get("session_id") or "dashboard"

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
