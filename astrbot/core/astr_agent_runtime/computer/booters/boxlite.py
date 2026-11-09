import asyncio
import posixpath
import random
import re
from pathlib import Path
from typing import Any

import aiohttp
import boxlite
from shipyard import FileSystemComponent as ShipyardFileSystemComponent
from shipyard.python import PythonComponent as ShipyardPythonComponent
from shipyard.shell import ShellComponent as ShipyardShellComponent

from astrbot.api import logger

from ..olayer import FileSystemComponent, PythonComponent, ShellComponent
from .base import ComputerBooter
from .shipyard import ShipyardFileSystemWrapper, ShipyardShellWrapper


def _normalize_sandbox_path(path: str) -> str:
    """Normalize a sandbox target path to be strictly workspace-relative.

    Strips workspace prefixes, absolute prefixes, and converts separators
    so the target path resolves within the sandbox workspace. Rejects path
    traversal attempts and paths outside the workspace.

    Args:
        path: Remote file path (absolute or relative).

    Returns:
        Workspace-relative file path with no leading slash.

    Raises:
        ValueError: If path is empty, attempts directory traversal, or escapes workspace.
    """
    if not path or not path.strip():
        raise ValueError("Target path cannot be empty")

    cleaned = path.strip().replace("\\", "/")
    # Strip drive letters (e.g. C:)
    cleaned = re.sub(r"^[a-zA-Z]:", "", cleaned)

    if cleaned.startswith("/"):
        # Absolute path check
        if cleaned.startswith("/workspace/"):
            subpath = cleaned[len("/workspace/") :]
        elif cleaned == "/workspace":
            subpath = ""
        elif match := re.match(r"^/home/ship_[^/]+/workspace(?:/(.*))?$", cleaned):
            subpath = match.group(1) or ""
        else:
            raise ValueError(f"Path outside workspace: {path}")
    else:
        # Relative path check
        if cleaned.startswith("workspace/"):
            subpath = cleaned[len("workspace/") :]
        elif cleaned == "workspace":
            subpath = ""
        else:
            subpath = cleaned

    subpath = subpath.strip().lstrip("/")
    if not subpath:
        raise ValueError(f"Invalid target path: {path}")

    norm = posixpath.normpath(subpath)
    if norm in (".", ""):
        raise ValueError(f"Invalid target path: {path}")
    if (
        norm == ".."
        or norm.startswith("../")
        or any(part == ".." for part in norm.split("/"))
    ):
        raise ValueError(f"Path traversal attempt detected: {path}")
    if norm.startswith("/"):
        raise ValueError(f"Path outside workspace: {path}")

    return norm


class ShipyardPythonWrapper:
    """Wraps Shipyard Python component to ensure standard envelope format.

    Direct calls to Ship microVM /ipython/exec return flat output/error
    dictionaries at the top level without a `data` wrapper. This wrapper
    normalizes responses so `result['data']['output']` is always populated.
    """

    def __init__(self, _shipyard_python: PythonComponent) -> None:
        self._python = _shipyard_python

    async def exec(
        self,
        code: str,
        kernel_id: str | None = None,
        timeout: int = 30,
        silent: bool = False,
    ) -> dict[str, Any]:
        """Execute Python code and normalize response structure.

        Args:
            code: Python code string to execute.
            kernel_id: Optional IPython kernel ID.
            timeout: Execution timeout in seconds.
            silent: Whether to suppress output text.

        Returns:
            Dictionary containing standard success, data, output, and error keys.
        """
        result = await self._python.exec(
            code=code,
            kernel_id=kernel_id,
            timeout=timeout,
            silent=silent,
        )
        if not isinstance(result, dict):
            return {
                "success": False,
                "data": {
                    "output": {"text": "", "images": []},
                    "error": "Invalid result",
                },
            }

        data = result.get("data")
        if isinstance(data, dict):
            return result

        raw_output = result.get("output", "") or ""
        error_text = str(result.get("error", "") or "")
        if isinstance(raw_output, dict):
            rich_output = dict(raw_output)
            if "text" not in rich_output:
                rich_output["text"] = ""
            if not isinstance(rich_output.get("images"), list):
                rich_output["images"] = []
        else:
            rich_output = {
                "text": str(raw_output),
                "images": [],
            }

        if silent:
            rich_output["text"] = ""

        success = bool(result.get("success", not error_text))
        return {
            "success": success,
            "data": {
                "output": rich_output,
                "error": error_text,
            },
            "output": rich_output["text"],
            "error": error_text,
            "execution_id": result.get("execution_id"),
            "execution_time_ms": result.get("execution_time_ms"),
        }


class MockShipyardSandboxClient:
    def __init__(self, sb_url: str, session_id: str = "default") -> None:
        url = sb_url.rstrip("/")
        if not url.startswith(("http://", "https://")):
            url = f"http://{url}"
        self.sb_url = url
        self.session_id = session_id

    async def _exec_operation(
        self,
        ship_id: str,
        operation_type: str,
        payload: dict[str, Any],
        session_id: str,
    ) -> dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            headers = {"X-SESSION-ID": session_id}
            async with session.post(
                f"{self.sb_url}/{operation_type}",
                json=payload,
                headers=headers,
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"Failed to exec operation: {response.status} {error_text}"
                    )

    async def upload_file(self, path: str, remote_path: str) -> dict:
        """Upload a file to the sandbox.

        Args:
            path: Local host file path to upload.
            remote_path: Target path inside the sandbox workspace.

        Returns:
            Dictionary with success flag, message, and normalized file_path.
        """
        url = f"{self.sb_url}/upload"
        try:
            target_path = _normalize_sandbox_path(remote_path)
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "message": "File upload failed",
            }

        try:
            with open(path, "rb") as f:
                file_content = f.read()

            data = aiohttp.FormData()
            data.add_field(
                "file",
                file_content,
                filename=target_path.split("/")[-1] or "file",
                content_type="application/octet-stream",
            )
            data.add_field("file_path", target_path)

            headers = {"X-SESSION-ID": self.session_id}
            timeout = aiohttp.ClientTimeout(total=120)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, data=data, headers=headers) as response:
                    if response.status == 200:
                        logger.info(
                            "[Computer] File uploaded to Boxlite sandbox: %s",
                            target_path,
                        )
                        return {
                            "success": True,
                            "message": "File uploaded successfully",
                            "file_path": target_path,
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "error": f"Server returned {response.status}: {error_text}",
                            "message": "File upload failed",
                        }

        except aiohttp.ClientError as e:
            logger.error(f"Failed to upload file: {e}")
            return {
                "success": False,
                "error": f"Connection error: {str(e)}",
                "message": "File upload failed",
            }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "File upload timeout",
                "message": "File upload failed",
            }
        except FileNotFoundError:
            logger.error(f"File not found: {path}")
            return {
                "success": False,
                "error": f"File not found: {path}",
                "message": "File upload failed",
            }
        except Exception as e:
            logger.error(f"Unexpected error uploading file: {e}")
            return {
                "success": False,
                "error": f"Internal error: {str(e)}",
                "message": "File upload failed",
            }

    async def download_file(self, remote_path: str, local_path: str) -> None:
        """Download a file from the sandbox VM via its /download endpoint.

        Streams chunks into a temporary file in the destination directory and
        atomically replaces the target upon successful completion.

        Args:
            remote_path: Target path inside the sandbox workspace.
            local_path: Host filesystem path to save downloaded file.

        Raises:
            ValueError: If remote_path or local_path is empty or invalid.
            RuntimeError: If download fails or server returns non-200.
        """
        if not local_path or not str(local_path).strip():
            raise ValueError("local_path cannot be empty")

        rel_path = _normalize_sandbox_path(remote_path)
        dest_path = Path(local_path)
        parent_dir = dest_path.parent if str(dest_path.parent) != "" else Path(".")
        parent_dir.mkdir(parents=True, exist_ok=True)

        url = f"{self.sb_url}/download"
        headers = {"X-SESSION-ID": self.session_id}
        timeout = aiohttp.ClientTimeout(total=300)

        temp_dest = (
            parent_dir / f".tmp_{dest_path.name}_{random.randint(100000, 999999)}"
        )

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    url, params={"file_path": rel_path}, headers=headers
                ) as response:
                    if response.status != 200:
                        error_text = (await response.text())[:200]
                        raise RuntimeError(
                            f"Failed to download file: HTTP {response.status} for {remote_path}: {error_text}"
                        )
                    with open(temp_dest, "wb") as f:
                        async for chunk in response.content.iter_chunked(65536):
                            f.write(chunk)
                        f.flush()
            temp_dest.replace(dest_path)
        finally:
            if temp_dest.exists():
                try:
                    temp_dest.unlink()
                except OSError:
                    pass

        logger.info(
            "[Computer] File downloaded from Boxlite sandbox: %s -> %s",
            remote_path,
            local_path,
        )

    async def wait_healthy(self, ship_id: str, session_id: str) -> None:
        """Mock wait healthy"""
        loop = 60
        while loop > 0:
            try:
                logger.info(
                    f"Checking health for sandbox {ship_id} on {self.sb_url}..."
                )
                url = f"{self.sb_url}/health"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            logger.info(f"Sandbox {ship_id} is healthy")
                return
            except Exception:
                await asyncio.sleep(1)
                loop -= 1


class BoxliteBooter(ComputerBooter):
    def __init__(self) -> None:
        self._closed = False
        self.box: Any = None
        self.mocked: MockShipyardSandboxClient | None = None
        self._python: PythonComponent | None = None
        self._shell: ShellComponent | None = None
        self._fs: FileSystemComponent | None = None

    async def boot(self, session_id: str) -> None:
        logger.info(
            f"Booting(Boxlite) for session: {session_id}, this may take a while..."
        )
        random_port = random.randint(20000, 30000)
        self.box = boxlite.SimpleBox(
            image="soulter/shipyard-ship",
            memory_mib=512,
            cpus=1,
            ports=[
                {
                    "host_port": random_port,
                    "guest_port": 8123,
                }
            ],
        )
        await self.box.start()
        logger.info(f"Boxlite booter started for session: {session_id}")
        self.mocked = MockShipyardSandboxClient(
            sb_url=f"http://127.0.0.1:{random_port}",
            session_id=session_id,
        )
        self._python = ShipyardPythonComponent(
            client=self.mocked,  # type: ignore
            ship_id=self.box.id,
            session_id=session_id,
        )
        self._python = ShipyardPythonWrapper(self._python)
        self._shell = ShipyardShellComponent(
            client=self.mocked,  # type: ignore
            ship_id=self.box.id,
            session_id=session_id,
        )
        # Boxlite talks to the same Shipyard exec API, so its results carry the
        # same `data` envelope; wrap the shell before handing it to the file
        # system wrapper (file search reuses the shell) and to callers.
        self._shell = ShipyardShellWrapper(self._shell)
        self._ship_fs = ShipyardFileSystemComponent(
            client=self.mocked,  # type: ignore
            ship_id=self.box.id,
            session_id=session_id,
        )
        self._fs = ShipyardFileSystemWrapper(
            _shipyard_fs=self._ship_fs, _shipyard_shell=self._shell
        )

        await self.mocked.wait_healthy(self.box.id, session_id)

    async def available(self) -> bool:
        """Check if the Boxlite sandbox is available.

        Returns:
            True if microVM is running and health check succeeds, False otherwise.
        """
        if getattr(self, "_closed", False):
            return False
        box = getattr(self, "box", None)
        mocked = getattr(self, "mocked", None)
        if box is None or mocked is None:
            return False

        box_id = getattr(box, "id", "unknown")
        if hasattr(box, "info"):
            try:
                info = box.info()
                if asyncio.iscoroutine(info):
                    info = await info
                if isinstance(info, dict):
                    status = str(info.get("status", "running")).lower()
                    if status not in {"running", "started"} or not info.get(
                        "running", True
                    ):
                        logger.info(
                            "[Computer] Boxlite sandbox health check: id=%s, status=%s, healthy=False",
                            box_id,
                            status,
                        )
                        return False
            except Exception as e:
                logger.error(f"Error checking Boxlite sandbox info: {e}")
                return False

        try:
            url = f"{mocked.sb_url}/health"
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    healthy = response.status == 200
                    logger.info(
                        "[Computer] Boxlite sandbox health check: id=%s, healthy=%s",
                        box_id,
                        healthy,
                    )
                    return healthy
        except Exception as e:
            logger.error(f"Error checking Boxlite sandbox availability: {e}")
            return False

    async def shutdown(self, **kwargs) -> None:
        """Shut down the Boxlite sandbox."""
        self._closed = True
        box = getattr(self, "box", None)
        if box is not None:
            box_id = getattr(box, "id", "unknown")
            logger.info(f"[Computer] Shutting down Boxlite booter for ship: {box_id}")
            try:
                if hasattr(box, "shutdown"):
                    res = box.shutdown()
                    if asyncio.iscoroutine(res):
                        await res
                elif hasattr(box, "stop"):
                    res = box.stop()
                    if asyncio.iscoroutine(res):
                        await res
            except Exception as e:
                logger.warning(f"[Computer] Failed to shutdown box instance: {e}")
            logger.info(f"[Computer] Boxlite booter for ship: {box_id} stopped")
        else:
            logger.info("[Computer] Boxlite booter shutdown.")

        self.box = None
        self.mocked = None
        self._python = None
        self._shell = None
        self._fs = None

    @property
    def capabilities(self) -> tuple[str, ...] | None:
        """Sandbox capabilities.

        Returns:
            Tuple of capabilities when initialized and active, None otherwise.
        """
        if getattr(self, "_closed", False) or self.mocked is None:
            return None
        return ("python", "shell", "filesystem")

    @property
    def fs(self) -> FileSystemComponent:
        if self._fs is None:
            raise RuntimeError("BoxliteBooter is not initialized.")
        return self._fs

    @property
    def python(self) -> PythonComponent:
        if self._python is None:
            raise RuntimeError("BoxliteBooter is not initialized.")
        return self._python

    @property
    def shell(self) -> ShellComponent:
        if self._shell is None:
            raise RuntimeError("BoxliteBooter is not initialized.")
        return self._shell

    async def upload_file(self, path: str, file_name: str) -> dict:
        """Upload file to sandbox."""
        if self.mocked is None:
            raise RuntimeError("BoxliteBooter is not initialized.")
        return await self.mocked.upload_file(path, file_name)

    async def download_file(self, remote_path: str, local_path: str) -> None:
        """Download file from sandbox."""
        if self.mocked is None:
            raise RuntimeError("BoxliteBooter is not initialized.")
        await self.mocked.download_file(remote_path, local_path)
