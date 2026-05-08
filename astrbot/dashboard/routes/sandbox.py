from __future__ import annotations

import base64
import shlex
import time
import uuid
from pathlib import Path
from typing import Any

from quart import request

from astrbot.core import logger
from astrbot.core.computer.computer_client import (
    create_sandbox,
    create_sandbox_uncontrolled,
    destroy_sandbox,
    get_current_sandbox,
    get_sandbox_observer_booter_by_id,
    list_sandboxes,
    release_current_sandbox,
    set_default_sandbox,
    switch_current_sandbox,
    takeover_sandbox,
    update_sandbox_config,
)
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from .route import Response, Route, RouteContext


class _DashboardSandboxContext:
    def __init__(self, config: Any):
        self._config = config

    def get_config(self, umo: str | None = None):
        return self._config


def _session_id(data: dict[str, Any]) -> str:
    value = data.get("session_id") or data.get("umo") or "dashboard"
    return str(value)


def _terminal_command(command: str) -> str:
    quoted = shlex.quote(command)
    return (
        f"TERM=xterm-256color COLUMNS=160 LINES=40 script -q -e -c {quoted} /dev/null"
    )


class SandboxRoute(Route):
    """Provider-neutral sandbox management APIs.

    Phase 1 actions are backed by the managed CUA implementation, while response
    payloads keep provider/booter_type fields so the dashboard can represent CUA,
    Shipyard Neo, Shipyard, and future providers in one surface.
    """

    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)
        self.routes = {
            "/sandboxes": ("GET", self.list_sandboxes),
            "/sandboxes/current": ("GET", self.get_current),
            "/sandboxes/create": ("POST", self.create_sandbox),
            "/sandboxes/switch-current": ("POST", self.switch_current),
            "/sandboxes/release": ("POST", self.release_sandbox),
            "/sandboxes/takeover": ("POST", self.takeover_sandbox),
            "/sandboxes/destroy": ("POST", self.destroy_sandbox),
            "/sandboxes/screenshot": ("POST", self.screenshot_sandbox),
            "/sandboxes/shell": ("POST", self.shell_sandbox),
            "/sandboxes/default/ensure": ("POST", self.ensure_default),
            "/sandboxes/default/set": ("POST", self.set_default),
            "/sandboxes/config/update": ("POST", self.update_sandbox_config),
        }
        self.register_routes()

    async def list_sandboxes(self):
        return Response().ok({"sandboxes": list_sandboxes()}).__dict__

    async def get_current(self):
        session_id = (
            request.args.get("session_id") or request.args.get("umo") or "dashboard"
        )
        return Response().ok(get_current_sandbox(str(session_id))).__dict__

    async def create_sandbox(self):
        data = await request.json
        if not isinstance(data, dict):
            data = {}
        provider = str(data.get("provider") or "cua")
        if provider != "cua":
            return (
                Response().error(f"Provider {provider} is not supported yet.").__dict__
            )
        try:
            sandbox = await create_sandbox_uncontrolled(
                _DashboardSandboxContext(self.config),
                _session_id(data),
                provider,
                sandbox_name=data.get("sandbox_name"),
            )
            return Response().ok({"sandbox": sandbox}).__dict__
        except Exception as e:
            return Response().error(str(e)).__dict__

    async def switch_current(self):
        data = await request.json
        if not isinstance(data, dict):
            data = {}
        sandbox_id = data.get("sandbox_id")
        if not sandbox_id:
            return Response().error("sandbox_id is required.").__dict__
        try:
            sandbox = switch_current_sandbox(_session_id(data), str(sandbox_id))
            return Response().ok({"sandbox": sandbox}).__dict__
        except Exception as e:
            return Response().error(str(e)).__dict__

    async def release_sandbox(self):
        data = await request.json
        if not isinstance(data, dict):
            data = {}
        sandbox_id = data.get("sandbox_id")
        try:
            sandbox = release_current_sandbox(
                _session_id(data),
                str(sandbox_id) if sandbox_id else None,
            )
            return Response().ok({"sandbox": sandbox}).__dict__
        except Exception as e:
            return Response().error(str(e)).__dict__

    async def takeover_sandbox(self):
        data = await request.json
        if not isinstance(data, dict):
            data = {}
        sandbox_id = data.get("sandbox_id")
        if not sandbox_id:
            return Response().error("sandbox_id is required.").__dict__
        try:
            sandbox = takeover_sandbox(_session_id(data), str(sandbox_id))
            return Response().ok({"sandbox": sandbox}).__dict__
        except Exception as e:
            return Response().error(str(e)).__dict__

    async def destroy_sandbox(self):
        data = await request.json
        if not isinstance(data, dict):
            data = {}
        sandbox_id = data.get("sandbox_id")
        if not sandbox_id:
            return Response().error("sandbox_id is required.").__dict__
        try:
            sandbox = await destroy_sandbox(_session_id(data), str(sandbox_id))
            return Response().ok({"sandbox": sandbox}).__dict__
        except Exception as e:
            return Response().error(str(e)).__dict__

    async def screenshot_sandbox(self):
        data = await request.json
        if not isinstance(data, dict):
            data = {}
        sandbox_id = data.get("sandbox_id")
        if not sandbox_id:
            return Response().error("sandbox_id is required.").__dict__
        try:
            booter = await get_sandbox_observer_booter_by_id(str(sandbox_id))
            gui = getattr(booter, "gui", None)
            if gui is None:
                return (
                    Response()
                    .error("Target sandbox does not support screenshot.")
                    .__dict__
                )
            screenshot_dir = Path(get_astrbot_temp_path()) / "sandbox_screenshots"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            path = screenshot_dir / f"{uuid.uuid4().hex}.png"
            result = await gui.screenshot(str(path))
            try:
                mime_type = result.get("mime_type") or "image/png"
                image_base64 = result.get("base64")
                if not image_base64:
                    image_base64 = base64.b64encode(path.read_bytes()).decode("ascii")
                return (
                    Response()
                    .ok(
                        {
                            "screenshot": {
                                "mime_type": mime_type,
                                "base64": image_base64,
                                "data_url": f"{mime_type};base64,{image_base64}"
                                if mime_type.startswith("data:")
                                else f"data:{mime_type};base64,{image_base64}",
                            }
                        }
                    )
                    .__dict__
                )
            finally:
                path.unlink(missing_ok=True)
        except Exception as e:
            return Response().error(str(e)).__dict__

    async def shell_sandbox(self):
        data = await request.json
        if not isinstance(data, dict):
            data = {}
        sandbox_id = data.get("sandbox_id")
        command = str(data.get("command") or "").strip()
        if not sandbox_id:
            return Response().error("sandbox_id is required.").__dict__
        if not command:
            return Response().error("command is required.").__dict__
        started_at = time.monotonic()
        try:
            logger.info(
                "[Dashboard] Sandbox shell exec start: sandbox_id=%s timeout=%s background=%s command=%r",
                sandbox_id,
                data.get("timeout") or 300,
                bool(data.get("background", False)),
                command[:500],
            )
            booter = await get_sandbox_observer_booter_by_id(str(sandbox_id))
            shell = getattr(booter, "shell", None)
            if shell is None:
                return (
                    Response().error("Target sandbox does not support shell.").__dict__
                )
            cwd = data.get("cwd")
            result = await shell.exec(
                _terminal_command(command),
                cwd=str(cwd) if cwd else None,
                timeout=int(data.get("timeout") or 300),
                background=bool(data.get("background", False)),
            )
            logger.info(
                "[Dashboard] Sandbox shell exec done: sandbox_id=%s exit_code=%s elapsed_ms=%d stdout_len=%d stderr_len=%d",
                sandbox_id,
                result.get("exit_code", result.get("returncode")),
                int((time.monotonic() - started_at) * 1000),
                len(str(result.get("stdout", "") or "")),
                len(str(result.get("stderr", "") or "")),
            )
            return Response().ok({"result": result}).__dict__
        except Exception as e:
            logger.warning(
                "[Dashboard] Sandbox shell exec failed: sandbox_id=%s elapsed_ms=%d error=%s",
                sandbox_id,
                int((time.monotonic() - started_at) * 1000),
                str(e) or type(e).__name__,
                exc_info=True,
            )
            return Response().error(str(e)).__dict__

    async def ensure_default(self):
        try:
            sandbox = await create_sandbox(
                _DashboardSandboxContext(self.config),
                "dashboard",
                "cua",
                sandbox_name="default-cua",
            )
            return Response().ok({"sandbox": sandbox}).__dict__
        except Exception as e:
            return Response().error(str(e)).__dict__

    async def set_default(self):
        data = await request.json
        if not isinstance(data, dict):
            data = {}
        sandbox_id = data.get("sandbox_id")
        if not sandbox_id:
            return Response().error("sandbox_id is required.").__dict__
        try:
            sandbox = set_default_sandbox(str(sandbox_id))
            return Response().ok({"sandbox": sandbox}).__dict__
        except Exception as e:
            return Response().error(str(e)).__dict__

    async def update_sandbox_config(self):
        data = await request.json
        if not isinstance(data, dict):
            data = {}
        sandbox_id = data.get("sandbox_id")
        if not sandbox_id:
            return Response().error("sandbox_id is required.").__dict__
        try:
            sandbox = update_sandbox_config(
                str(sandbox_id),
                idle_timeout=data.get("idle_timeout"),
                expires_at=data.get("expires_at"),
                retention_policy=str(data.get("retention_policy") or "temporary"),
            )
            return Response().ok({"sandbox": sandbox}).__dict__
        except Exception as e:
            return Response().error(str(e)).__dict__
