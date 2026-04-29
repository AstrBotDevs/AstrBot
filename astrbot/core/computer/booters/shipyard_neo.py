from __future__ import annotations

import asyncio
import os
import shlex
from typing import Any, cast

from astrbot.api import logger

from ..olayer import (
    BrowserComponent,
    FileSystemComponent,
    PythonComponent,
    ShellComponent,
)
from .base import ComputerBooter
from .shell_background import build_detached_shell_command
from .shipyard_search_file_util import search_files_via_shell

try:
    from shipyard_neo import BayClient
    from shipyard_neo.sandbox import Sandbox
except ImportError:
    logger.warning(
        "shipyard_neo_sdk is not installed. ShipyardNeoBooter will not work without it."
    )


def _maybe_model_dump(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, dict):
            return dumped
    return {}


def _slice_content_by_lines(
    content: str,
    *,
    offset: int | None = None,
    limit: int | None = None,
) -> str:
    lines = content.splitlines(keepends=True)
    start = 0 if offset is None else offset
    selected = lines[start:] if limit is None else lines[start : start + limit]
    return "".join(selected)


class NeoPythonComponent(PythonComponent):
    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    async def exec(
        self,
        code: str,
        kernel_id: str | None = None,
        timeout: int = 30,
        silent: bool = False,
    ) -> dict[str, Any]:
        _ = kernel_id  # Bay runtime does not expose kernel_id in current SDK.
        result = await self._sandbox.python.exec(code, timeout=timeout)
        payload = _maybe_model_dump(result)

        output_text = payload.get("output", "") or ""
        error_text = payload.get("error", "") or ""
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        rich_output = data.get("output") if isinstance(data.get("output"), dict) else {}
        if not isinstance(rich_output.get("images"), list):
            rich_output["images"] = []
        if "text" not in rich_output:
            rich_output["text"] = output_text

        if silent:
            rich_output["text"] = ""

        return {
            "success": bool(payload.get("success", error_text == "")),
            "data": {
                "output": rich_output,
                "error": error_text,
            },
            "execution_id": payload.get("execution_id"),
            "execution_time_ms": payload.get("execution_time_ms"),
            "code": payload.get("code"),
            "output": output_text,
            "error": error_text,
        }


class NeoShellComponent(ShellComponent):
    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = 300,
        shell: bool = True,
        background: bool = False,
    ) -> dict[str, Any]:
        if not shell:
            return {
                "stdout": "",
                "stderr": "error: only shell mode is supported in shipyard_neo booter.",
                "exit_code": 2,
                "success": False,
            }

        run_command = command
        if env:
            env_prefix = " ".join(
                f"{k}={shlex.quote(str(v))}" for k, v in sorted(env.items())
            )
            run_command = f"{env_prefix} {run_command}"

        if background:
            run_command = build_detached_shell_command(run_command)

        result = await self._sandbox.shell.exec(
            run_command,
            timeout=timeout or 300,
            cwd=cwd,
        )
        payload = _maybe_model_dump(result)

        stdout = payload.get("output", "") or ""
        stderr = payload.get("error", "") or ""
        exit_code = payload.get("exit_code")
        if background:
            pid: int | None = None
            try:
                pid = int(stdout.strip().splitlines()[-1])
            except Exception:
                pid = None
            return {
                "pid": pid,
                "stdout": (
                    f"Command is running in the background. pid={pid}"
                    if pid is not None
                    else "Command was submitted in the background."
                ),
                "stderr": stderr,
                "exit_code": exit_code,
                "success": bool(payload.get("success", not stderr)),
                "execution_id": payload.get("execution_id"),
                "execution_time_ms": payload.get("execution_time_ms"),
                "command": payload.get("command"),
            }

        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "success": bool(payload.get("success", not stderr)),
            "execution_id": payload.get("execution_id"),
            "execution_time_ms": payload.get("execution_time_ms"),
            "command": payload.get("command"),
        }


class NeoFileSystemComponent(FileSystemComponent):
    def __init__(self, sandbox: Sandbox, shell: ShellComponent) -> None:
        self._sandbox = sandbox
        self._shell = shell

    async def create_file(
        self,
        path: str,
        content: str = "",
        mode: int = 0o644,
    ) -> dict[str, Any]:
        _ = mode
        await self._sandbox.filesystem.write_file(path, content)
        return {"success": True, "path": path}

    async def read_file(
        self,
        path: str,
        encoding: str = "utf-8",
        offset: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        _ = encoding
        content = await self._sandbox.filesystem.read_file(path)
        return {
            "success": True,
            "path": path,
            "content": _slice_content_by_lines(
                content,
                offset=offset,
                limit=limit,
            ),
        }

    async def search_files(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        after_context: int | None = None,
        before_context: int | None = None,
    ) -> dict[str, Any]:
        return await search_files_via_shell(
            self._shell,
            pattern=pattern,
            path=path,
            glob=glob,
            after_context=after_context,
            before_context=before_context,
        )

    async def edit_file(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        _ = encoding
        content = await self._sandbox.filesystem.read_file(path)
        occurrences = content.count(old_string)
        if occurrences == 0:
            return {
                "success": False,
                "error": "old string not found in file",
                "replacements": 0,
            }
        if replace_all:
            updated = content.replace(old_string, new_string)
            replacements = occurrences
        else:
            updated = content.replace(old_string, new_string, 1)
            replacements = 1
        await self._sandbox.filesystem.write_file(path, updated)
        return {
            "success": True,
            "path": path,
            "replacements": replacements,
        }

    async def write_file(
        self,
        path: str,
        content: str,
        mode: str = "w",
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        _ = mode
        _ = encoding
        await self._sandbox.filesystem.write_file(path, content)
        return {"success": True, "path": path}

    async def delete_file(self, path: str) -> dict[str, Any]:
        await self._sandbox.filesystem.delete(path)
        return {"success": True, "path": path}

    async def list_dir(
        self,
        path: str = ".",
        show_hidden: bool = False,
    ) -> dict[str, Any]:
        entries = await self._sandbox.filesystem.list_dir(path)
        data = []
        for entry in entries:
            item = _maybe_model_dump(entry)
            if not show_hidden and str(item.get("name", "")).startswith("."):
                continue
            data.append(item)
        return {"success": True, "path": path, "entries": data}


class NeoBrowserComponent(BrowserComponent):
    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    async def exec(
        self,
        cmd: str,
        timeout: int = 30,
        description: str | None = None,
        tags: str | None = None,
        learn: bool = False,
        include_trace: bool = False,
    ) -> dict[str, Any]:
        result = await self._sandbox.browser.exec(
            cmd,
            timeout=timeout,
            description=description,
            tags=tags,
            learn=learn,
            include_trace=include_trace,
        )
        return _maybe_model_dump(result)

    async def exec_batch(
        self,
        commands: list[str],
        timeout: int = 60,
        stop_on_error: bool = True,
        description: str | None = None,
        tags: str | None = None,
        learn: bool = False,
        include_trace: bool = False,
    ) -> dict[str, Any]:
        result = await self._sandbox.browser.exec_batch(
            commands,
            timeout=timeout,
            stop_on_error=stop_on_error,
            description=description,
            tags=tags,
            learn=learn,
            include_trace=include_trace,
        )
        return _maybe_model_dump(result)

    async def run_skill(
        self,
        skill_key: str,
        timeout: int = 60,
        stop_on_error: bool = True,
        include_trace: bool = False,
        description: str | None = None,
        tags: str | None = None,
    ) -> dict[str, Any]:
        result = await self._sandbox.browser.run_skill(
            skill_key=skill_key,
            timeout=timeout,
            stop_on_error=stop_on_error,
            include_trace=include_trace,
            description=description,
            tags=tags,
        )
        return _maybe_model_dump(result)


class ShipyardNeoBooter(ComputerBooter):
    """Booter backed by Shipyard Neo (Bay).

    If *endpoint_url* is empty or set to ``"__auto__"``, Bay will be
    started automatically as a Docker container (like Boxlite does for
    Ship containers).
    """

    AUTO_SENTINEL = "__auto__"
    DEFAULT_PROFILE = "python-default"

    def __init__(
        self,
        endpoint_url: str,
        access_token: str,
        profile: str = DEFAULT_PROFILE,
        ttl: int = 3600,
    ) -> None:
        self._endpoint_url = endpoint_url
        self._access_token = access_token
        self._profile = profile
        self._ttl = ttl
        self._client: BayClient | None = None
        self._sandbox: Sandbox | None = None
        self._bay_manager: Any = None  # BayContainerManager when auto-started
        self._fs: FileSystemComponent | None = None
        self._python: PythonComponent | None = None
        self._shell: ShellComponent | None = None
        self._browser: BrowserComponent | None = None

    @property
    def bay_client(self) -> Any:
        return self._client

    @property
    def sandbox(self) -> Any:
        return self._sandbox

    @property
    def capabilities(self) -> tuple[str, ...] | None:
        """Sandbox capabilities from the Bay profile.

        Returns an immutable tuple after :meth:`boot`; ``None`` before boot.
        """
        if self._sandbox is None:
            return None
        caps = getattr(self._sandbox, "capabilities", None)
        return tuple(caps) if caps is not None else None

    @property
    def is_auto_mode(self) -> bool:
        """True when Bay should be auto-started."""
        ep = (self._endpoint_url or "").strip()
        return not ep or ep == self.AUTO_SENTINEL

    async def boot(self, session_id: str) -> None:
        _ = session_id

        # --- Auto-start Bay if needed ---
        if self.is_auto_mode:
            from .bay_manager import BayContainerManager

            # Clean up previous manager if re-booting
            if self._bay_manager is not None:
                await self._bay_manager.close_client()

            logger.info("[Computer] Neo auto-start mode: launching Bay container")
            self._bay_manager = BayContainerManager()
            self._endpoint_url = await self._bay_manager.ensure_running()
            await self._bay_manager.wait_healthy()
            # Read auto-provisioned credentials
            if not self._access_token:
                self._access_token = await self._bay_manager.read_credentials()
            logger.info("[Computer] Bay auto-started at %s", self._endpoint_url)

        if not self._endpoint_url or not self._access_token:
            if self._bay_manager is not None:
                raise ValueError(
                    "Bay container started but credentials could not be read. "
                    "Ensure Bay generated credentials.json, or set access_token manually."
                )
            raise ValueError(
                "Shipyard Neo sandbox configuration is incomplete. "
                "Set endpoint (default http://127.0.0.1:8114) and access token, "
                "or ensure Bay's credentials.json is accessible for auto-discovery."
            )

        self._client = BayClient(
            endpoint_url=self._endpoint_url,
            access_token=self._access_token,
        )
        await self._client.__aenter__()

        # Resolve profile: user-specified > smart selection > default
        resolved_profile = await self._resolve_profile(self._client)

        self._sandbox = await self._client.create_sandbox(
            profile=resolved_profile,
            ttl=self._ttl,
        )

        # --- Readiness gate: wait until sandbox session is READY ---
        await self._wait_until_ready(self._sandbox)

        self._shell = NeoShellComponent(self._sandbox)
        self._fs = NeoFileSystemComponent(self._sandbox, self._shell)
        self._python = NeoPythonComponent(self._sandbox)

        caps = self.capabilities or ()
        self._browser = (
            NeoBrowserComponent(self._sandbox) if "browser" in caps else None
        )

        logger.info(
            "Got Shipyard Neo sandbox: %s (profile=%s, capabilities=%s, auto=%s)",
            self._sandbox.id,
            resolved_profile,
            list(caps),
            bool(self._bay_manager),
        )

    async def _wait_until_ready(self, sandbox: Sandbox) -> None:
        """Poll sandbox status until READY, or raise on FAILED / timeout.

        Covers both warm-pool hits (near-instant) and cold starts (up to 180s).
        On FAILED, EXPIRED, or timeout the sandbox is deleted before raising
        so no orphan resources leak on Bay.
        """
        READINESS_TIMEOUT = 180  # seconds
        POLL_INTERVAL = 2  # seconds

        sandbox_id = sandbox.id
        deadline = asyncio.get_running_loop().time() + READINESS_TIMEOUT

        while True:
            await sandbox.refresh()
            status = getattr(sandbox.status, "value", str(sandbox.status))

            if status == "ready":
                logger.info(
                    "[Computer] Sandbox %s is ready (profile=%s)",
                    sandbox_id,
                    sandbox.profile,
                )
                return

            if status in {"failed", "expired"}:
                logger.error(
                    "[Computer] Sandbox %s reached terminal state: %s",
                    sandbox_id,
                    status,
                )
                try:
                    await sandbox.delete()
                except Exception as del_err:
                    logger.warning(
                        "[Computer] Failed to delete failed sandbox %s: %s",
                        sandbox_id,
                        del_err,
                    )
                raise RuntimeError(
                    f"Sandbox {sandbox_id} is in terminal state: {status}"
                )

            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                logger.error(
                    "[Computer] Sandbox %s did not become ready within %ds "
                    "(last status: %s)",
                    sandbox_id,
                    READINESS_TIMEOUT,
                    status,
                )
                try:
                    await sandbox.delete()
                except Exception as del_err:
                    logger.warning(
                        "[Computer] Failed to delete timed-out sandbox %s: %s",
                        sandbox_id,
                        del_err,
                    )
                raise TimeoutError(
                    f"Sandbox {sandbox_id} did not become ready within "
                    f"{READINESS_TIMEOUT}s (last status: {status})"
                )

            logger.debug(
                "[Computer] Sandbox %s status=%s, waiting...",
                sandbox_id,
                status,
            )
            await asyncio.sleep(POLL_INTERVAL)

    async def _resolve_profile(self, client: Any) -> str:
        """Pick the best profile for this session.

        Resolution order:
        1. User-specified profile (non-empty, non-default) → use as-is.
        2. Query ``GET /v1/profiles`` and pick the profile with the most
           capabilities, preferring profiles that include ``"browser"``.
        3. Fall back to :attr:`DEFAULT_PROFILE`.

        Auth errors (401/403) are re-raised immediately — they indicate a
        misconfigured token, and silently falling back would just delay the
        real failure to ``create_sandbox``.
        """
        # User explicitly set a profile → honour it
        if self._profile and self._profile != self.DEFAULT_PROFILE:
            logger.info("[Computer] Using user-specified profile: %s", self._profile)
            return self._profile

        # Query Bay for available profiles
        from shipyard_neo.errors import ForbiddenError, UnauthorizedError

        try:
            profile_list = await client.list_profiles()
            profiles = profile_list.items
        except (UnauthorizedError, ForbiddenError):
            raise  # auth errors must not be silenced
        except Exception as exc:
            logger.warning(
                "[Computer] Failed to query Bay profiles, falling back to %s: %s",
                self.DEFAULT_PROFILE,
                exc,
            )
            return self.DEFAULT_PROFILE

        if not profiles:
            return self.DEFAULT_PROFILE

        def _score(p: Any) -> tuple[int, int]:
            """(has_browser, capability_count) — higher is better."""
            caps = getattr(p, "capabilities", []) or []
            return (1 if "browser" in caps else 0, len(caps))

        best = max(profiles, key=_score)
        chosen = getattr(best, "id", self.DEFAULT_PROFILE)

        if chosen != self.DEFAULT_PROFILE:
            caps = getattr(best, "capabilities", [])
            logger.info(
                "[Computer] Auto-selected profile %s (capabilities=%s)",
                chosen,
                caps,
            )

        return chosen

    async def shutdown(self, *, delete_sandbox: bool = False) -> None:
        if self._client is not None:
            sandbox_id = getattr(self._sandbox, "id", "unknown")

            # Delete sandbox on Bay BEFORE closing the HTTP client.
            # This is critical for cleanup — calling delete after
            # __aexit__ would fail because the httpx session is already
            # torn down.
            if delete_sandbox and self._sandbox is not None:
                try:
                    logger.info(
                        "[Computer] Deleting Shipyard Neo sandbox: id=%s", sandbox_id
                    )
                    await self._sandbox.delete()
                    logger.info(
                        "[Computer] Shipyard Neo sandbox deleted: id=%s", sandbox_id
                    )
                except Exception as e:
                    logger.warning(
                        "[Computer] Failed to delete sandbox %s (may already be "
                        "cleaned up by Bay GC): %s",
                        sandbox_id,
                        e,
                    )

            logger.info(
                "[Computer] Shutting down Shipyard Neo sandbox client: id=%s",
                sandbox_id,
            )
            await self._client.__aexit__(None, None, None)
            self._client = None
            self._sandbox = None
            logger.info(
                "[Computer] Shipyard Neo sandbox client shut down: id=%s", sandbox_id
            )

        # NOTE: We intentionally do NOT stop the Bay container here.
        # It stays running for reuse by future sessions.  The user can
        # stop it manually or via ``BayContainerManager.stop()``.
        if self._bay_manager is not None:
            await self._bay_manager.close_client()

    @property
    def fs(self) -> FileSystemComponent:
        if self._fs is None:
            raise RuntimeError("ShipyardNeoBooter is not initialized.")
        return self._fs

    @property
    def python(self) -> PythonComponent:
        if self._python is None:
            raise RuntimeError("ShipyardNeoBooter is not initialized.")
        return self._python

    @property
    def shell(self) -> ShellComponent:
        if self._shell is None:
            raise RuntimeError("ShipyardNeoBooter is not initialized.")
        return self._shell

    @property
    def browser(self) -> BrowserComponent:
        if self._browser is None:
            raise RuntimeError("ShipyardNeoBooter is not initialized.")
        return self._browser

    async def upload_file(self, path: str, file_name: str) -> dict:
        if self._sandbox is None:
            raise RuntimeError("ShipyardNeoBooter is not initialized.")
        with open(path, "rb") as f:
            content = f.read()
        remote_path = file_name.lstrip("/")
        await self._sandbox.filesystem.upload(remote_path, content)
        logger.info("[Computer] File uploaded to Neo sandbox: %s", remote_path)
        return {
            "success": True,
            "message": "File uploaded successfully",
            "file_path": remote_path,
        }

    async def download_file(self, remote_path: str, local_path: str) -> None:
        if self._sandbox is None:
            raise RuntimeError("ShipyardNeoBooter is not initialized.")
        content = await self._sandbox.filesystem.download(remote_path.lstrip("/"))
        local_dir = os.path.dirname(local_path)
        if local_dir:
            os.makedirs(local_dir, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(cast(bytes, content))
        logger.info(
            "[Computer] File downloaded from Neo sandbox: %s -> %s",
            remote_path,
            local_path,
        )

    async def available(self) -> bool:
        if self._sandbox is None:
            return False
        try:
            await self._sandbox.refresh()
            status = getattr(self._sandbox.status, "value", str(self._sandbox.status))
            healthy = status not in {"failed", "expired"}
            logger.info(
                "[Computer] Neo sandbox health check: id=%s, status=%s, healthy=%s",
                getattr(self._sandbox, "id", "unknown"),
                status,
                healthy,
            )
            return healthy
        except Exception as e:
            logger.error(f"Error checking Shipyard Neo sandbox availability: {e}")
            return False
