from __future__ import annotations

import base64
import inspect
from pathlib import Path
from typing import Any

from astrbot.api import logger

from ..olayer import FileSystemComponent, GUIComponent, PythonComponent, ShellComponent
from .base import ComputerBooter
from .shipyard_search_file_util import search_files_via_shell


def _maybe_model_dump(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, dict):
            return dumped
    if hasattr(value, "dict"):
        dumped = value.dict()
        if isinstance(dumped, dict):
            return dumped
    return {}


async def _call_first(
    obj: Any, names: tuple[str, ...], *args: Any, **kwargs: Any
) -> Any:
    for name in names:
        method = getattr(obj, name, None)
        if method is None:
            continue
        return await method(*args, **kwargs)
    raise AttributeError(f"None of these methods exist: {', '.join(names)}")


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


def _result_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return str(value)
    return ""


class CuaShellComponent(ShellComponent):
    def __init__(self, sandbox: Any) -> None:
        self._sandbox = sandbox

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = 30,
        shell: bool = True,
        background: bool = False,
    ) -> dict[str, Any]:
        if not shell:
            return {
                "stdout": "",
                "stderr": "error: only shell mode is supported in CUA booter.",
                "exit_code": 2,
                "success": False,
            }

        kwargs: dict[str, Any] = {}
        if cwd is not None:
            kwargs["cwd"] = cwd
        if timeout is not None:
            kwargs["timeout"] = timeout
        if env:
            kwargs["env"] = env
        if background:
            command = (
                f"nohup sh -lc {command!r} >/tmp/astrbot_cua_bg.log 2>&1 & echo $!"
            )

        result = await _call_first(
            self._sandbox.shell, ("run", "exec"), command, **kwargs
        )
        payload = _maybe_model_dump(result)
        if not payload and isinstance(result, str):
            payload = {"stdout": result}

        stdout = _result_text(payload, "stdout", "output")
        stderr = _result_text(payload, "stderr", "error")
        exit_code = payload.get(
            "exit_code", payload.get("returncode", 0 if not stderr else 1)
        )
        response = {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "success": bool(
                payload.get("success", not stderr and exit_code in (0, None))
            ),
        }
        if background:
            try:
                response["pid"] = int(stdout.strip().splitlines()[-1])
            except Exception:
                response["pid"] = None
        return response


class CuaPythonComponent(PythonComponent):
    def __init__(self, sandbox: Any) -> None:
        self._sandbox = sandbox

    async def exec(
        self,
        code: str,
        kernel_id: str | None = None,
        timeout: int = 30,
        silent: bool = False,
    ) -> dict[str, Any]:
        _ = kernel_id
        python = getattr(self._sandbox, "python", None)
        if python is not None:
            result = await _call_first(python, ("run", "exec"), code, timeout=timeout)
            payload = _maybe_model_dump(result)
        else:
            shell = CuaShellComponent(self._sandbox)
            result = await shell.exec(f"python3 - <<'PY'\n{code}\nPY", timeout=timeout)
            payload = {
                "output": result.get("stdout", ""),
                "error": result.get("stderr", ""),
            }

        output_text = "" if silent else _result_text(payload, "stdout", "output")
        error_text = _result_text(payload, "stderr", "error")
        return {
            "success": bool(payload.get("success", not error_text)),
            "data": {
                "output": {"text": output_text, "images": []},
                "error": error_text,
            },
            "output": output_text,
            "error": error_text,
        }


class CuaFileSystemComponent(FileSystemComponent):
    def __init__(self, sandbox: Any) -> None:
        self._sandbox = sandbox
        self._shell = CuaShellComponent(sandbox)

    @property
    def _filesystem(self) -> Any:
        return getattr(self._sandbox, "filesystem", None)

    async def create_file(
        self,
        path: str,
        content: str = "",
        mode: int = 0o644,
    ) -> dict[str, Any]:
        await self.write_file(path, content)
        return {"success": True, "path": path, "mode": mode}

    async def read_file(
        self,
        path: str,
        encoding: str = "utf-8",
        offset: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        fs = self._filesystem
        if fs is not None and hasattr(fs, "read_file"):
            content = await fs.read_file(path)
        else:
            result = await self._shell.exec(f"cat {path!r}")
            if result.get("stderr"):
                return {"success": False, "path": path, "error": result["stderr"]}
            content = result.get("stdout", "")
        if isinstance(content, bytes):
            content = content.decode(encoding, errors="replace")
        return {
            "success": True,
            "path": path,
            "content": _slice_content_by_lines(
                str(content), offset=offset, limit=limit
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
        read_result = await self.read_file(path, encoding=encoding)
        if not read_result.get("success"):
            return read_result
        content = read_result.get("content", "")
        occurrences = content.count(old_string)
        if occurrences == 0:
            return {
                "success": False,
                "error": "old string not found in file",
                "replacements": 0,
            }
        updated = content.replace(old_string, new_string, -1 if replace_all else 1)
        await self.write_file(path, updated, encoding=encoding)
        return {
            "success": True,
            "path": path,
            "replacements": occurrences if replace_all else 1,
        }

    async def write_file(
        self,
        path: str,
        content: str,
        mode: str = "w",
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        _ = mode
        fs = self._filesystem
        if fs is not None and hasattr(fs, "write_file"):
            await fs.write_file(path, content)
        else:
            encoded = base64.b64encode(content.encode(encoding)).decode()
            await self._shell.exec(f"base64 -d > {path!r} <<'EOF'\n{encoded}\nEOF")
        return {"success": True, "path": path}

    async def delete_file(self, path: str) -> dict[str, Any]:
        fs = self._filesystem
        if fs is not None:
            if hasattr(fs, "delete"):
                await fs.delete(path)
            elif hasattr(fs, "delete_file"):
                await fs.delete_file(path)
            else:
                await self._shell.exec(f"rm -rf {path!r}")
        else:
            await self._shell.exec(f"rm -rf {path!r}")
        return {"success": True, "path": path}

    async def list_dir(
        self,
        path: str = ".",
        show_hidden: bool = False,
    ) -> dict[str, Any]:
        fs = self._filesystem
        if fs is not None and hasattr(fs, "list_dir"):
            entries = await fs.list_dir(path)
            return {"success": True, "path": path, "entries": entries}
        flags = "-la" if show_hidden else "-l"
        result = await self._shell.exec(f"ls {flags} {path!r}")
        return {
            "success": not bool(result.get("stderr")),
            "path": path,
            "entries": result.get("stdout", ""),
            "error": result.get("stderr", ""),
        }


class CuaGUIComponent(GUIComponent):
    def __init__(self, sandbox: Any) -> None:
        self._sandbox = sandbox

    async def screenshot(self, path: str | None = None) -> dict[str, Any]:
        raw = await self._sandbox.screenshot()
        data = _screenshot_to_bytes(raw)
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(data)
        return {
            "success": True,
            "path": path,
            "mime_type": "image/png",
            "base64": base64.b64encode(data).decode("ascii"),
        }

    async def click(self, x: int, y: int, button: str = "left") -> dict[str, Any]:
        result = await self._sandbox.mouse.click(x, y, button=button)
        payload = _maybe_model_dump(result)
        return {"success": bool(payload.get("success", True)), **payload}

    async def type_text(self, text: str) -> dict[str, Any]:
        result = await self._sandbox.keyboard.type(text)
        payload = _maybe_model_dump(result)
        return {"success": bool(payload.get("success", True)), **payload}


def _screenshot_to_bytes(raw: Any) -> bytes:
    if isinstance(raw, bytes | bytearray):
        return bytes(raw)
    if isinstance(raw, str):
        if raw.startswith("data:image"):
            raw = raw.split(",", 1)[1]
        try:
            return base64.b64decode(raw, validate=True)
        except Exception:
            candidate = Path(raw)
            if candidate.is_file():
                return candidate.read_bytes()
            return raw.encode("utf-8")
    if hasattr(raw, "save"):
        import io

        output = io.BytesIO()
        raw.save(output, format="PNG")
        return output.getvalue()
    payload = _maybe_model_dump(raw)
    for key in ("data", "base64", "image"):
        value = payload.get(key)
        if value:
            return _screenshot_to_bytes(value)
    raise TypeError(f"Unsupported CUA screenshot result: {type(raw)!r}")


class CuaBooter(ComputerBooter):
    def __init__(
        self,
        image: str = "linux",
        os_type: str = "linux",
        ttl: int = 3600,
        telemetry_enabled: bool = False,
    ) -> None:
        self.image = image
        self.os_type = os_type
        self.ttl = ttl
        self.telemetry_enabled = telemetry_enabled
        self._sandbox: Any | None = None
        self._sandbox_cm: Any | None = None
        self._shell: CuaShellComponent | None = None
        self._python: CuaPythonComponent | None = None
        self._fs: CuaFileSystemComponent | None = None
        self._gui: CuaGUIComponent | None = None

    async def boot(self, session_id: str) -> None:
        _ = session_id
        try:
            from cua import Image, Sandbox
        except ImportError as exc:
            raise RuntimeError(
                "CUA sandbox support requires the optional `cua` package. "
                "Install it with `pip install cua` in the AstrBot environment."
            ) from exc

        image_obj = self._build_image(Image)
        ephemeral_kwargs = self._build_ephemeral_kwargs(Sandbox.ephemeral)
        self._sandbox_cm = Sandbox.ephemeral(image_obj, **ephemeral_kwargs)
        self._sandbox = await self._sandbox_cm.__aenter__()
        self._shell = CuaShellComponent(self._sandbox)
        self._python = CuaPythonComponent(self._sandbox)
        self._fs = CuaFileSystemComponent(self._sandbox)
        self._gui = CuaGUIComponent(self._sandbox)
        logger.info(
            "[Computer] CUA sandbox booted: image=%s, os_type=%s",
            self.image,
            self.os_type,
        )

    def _build_image(self, image_cls: Any) -> Any:
        image_name = (self.image or self.os_type or "linux").strip().lower()
        factory = getattr(image_cls, image_name, None)
        if callable(factory):
            return factory()
        os_factory = getattr(image_cls, (self.os_type or "linux").strip().lower(), None)
        if callable(os_factory):
            return os_factory()
        return image_name

    def _build_ephemeral_kwargs(self, ephemeral: Any) -> dict[str, Any]:
        try:
            parameters = inspect.signature(ephemeral).parameters
        except (TypeError, ValueError):
            return {}
        kwargs: dict[str, Any] = {}
        if "ttl" in parameters:
            kwargs["ttl"] = self.ttl
        if "telemetry_enabled" in parameters:
            kwargs["telemetry_enabled"] = self.telemetry_enabled
        return kwargs

    async def shutdown(self) -> None:
        if self._sandbox_cm is not None:
            await self._sandbox_cm.__aexit__(None, None, None)
            self._sandbox_cm = None
            self._sandbox = None

    @property
    def capabilities(self) -> tuple[str, ...] | None:
        return (
            "python",
            "shell",
            "filesystem",
            "gui",
            "screenshot",
            "mouse",
            "keyboard",
        )

    @property
    def fs(self) -> FileSystemComponent:
        if self._fs is None:
            raise RuntimeError("CuaBooter is not initialized.")
        return self._fs

    @property
    def python(self) -> PythonComponent:
        if self._python is None:
            raise RuntimeError("CuaBooter is not initialized.")
        return self._python

    @property
    def shell(self) -> ShellComponent:
        if self._shell is None:
            raise RuntimeError("CuaBooter is not initialized.")
        return self._shell

    @property
    def gui(self) -> GUIComponent | None:
        return self._gui

    async def upload_file(self, path: str, file_name: str) -> dict:
        local_path = Path(path)
        if not local_path.is_file():
            return {"success": False, "error": f"File not found: {path}"}
        if self._sandbox is not None and hasattr(self._sandbox, "upload_file"):
            return _maybe_model_dump(
                await self._sandbox.upload_file(str(local_path), file_name)
            )
        content = local_path.read_bytes()
        encoded = base64.b64encode(content).decode("ascii")
        result = await self.shell.exec(
            f"base64 -d > {file_name!r} <<'EOF'\n{encoded}\nEOF"
        )
        return {
            "success": not bool(result.get("stderr")),
            "file_path": file_name,
            **result,
        }

    async def download_file(self, remote_path: str, local_path: str) -> None:
        if self._sandbox is not None and hasattr(self._sandbox, "download_file"):
            await self._sandbox.download_file(remote_path, local_path)
            return
        result = await self.shell.exec(f"base64 {remote_path!r}")
        if result.get("stderr"):
            raise RuntimeError(result["stderr"])
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        Path(local_path).write_bytes(base64.b64decode(result.get("stdout", "")))

    async def available(self) -> bool:
        return self._sandbox is not None
