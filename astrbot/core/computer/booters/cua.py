from __future__ import annotations

import base64
import inspect
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astrbot.api import logger

from ..olayer import FileSystemComponent, GUIComponent, PythonComponent, ShellComponent
from .base import ComputerBooter
from .cua_defaults import CUA_CONFIG_KEYS, CUA_DEFAULT_CONFIG
from .shipyard_search_file_util import search_files_via_shell

_POSIX_OS_TYPES = {"linux", "darwin", "macos"}

_CUA_BACKGROUND_LAUNCHER = """
import subprocess, sys, time

p = subprocess.Popen(
    ["sh", "-lc", sys.argv[1]],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,
)
sys.stdout.write(str(p.pid) + "\\n")
sys.stdout.flush()
time.sleep(0.2)
code = p.poll()
sys.exit(0 if code is None else code)
""".strip()


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def build_cua_booter_kwargs(sandbox_cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        name: sandbox_cfg.get(config_key, CUA_DEFAULT_CONFIG[name])
        for name, config_key in CUA_CONFIG_KEYS.items()
    }


async def _write_base64_via_shell(
    shell: ShellComponent,
    path: str,
    data: bytes,
) -> dict[str, Any]:
    encoded = base64.b64encode(data).decode("ascii")
    decoder = (
        "import base64,pathlib,sys; "
        "pathlib.Path(sys.argv[1]).write_bytes(base64.b64decode(sys.stdin.read()))"
    )
    return await shell.exec(
        f"python3 -c {shlex.quote(decoder)} {shlex.quote(path)} <<'EOF'\n{encoded}\nEOF"
    )


@dataclass(slots=True)
class ProcessResult:
    stdout: str
    stderr: str
    exit_code: int | None
    success: bool


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


def _normalize_process_result(raw: Any) -> ProcessResult:
    payload = _maybe_model_dump(raw)
    if not payload and isinstance(raw, str):
        payload = {"stdout": raw}

    stdout = _result_text(payload, "stdout", "output")
    stderr = _result_text(payload, "stderr", "error")
    exit_code = payload.get(
        "exit_code", payload.get("returncode", 0 if not stderr else 1)
    )
    success = bool(payload.get("success", not stderr and exit_code in (0, None)))
    return ProcessResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        success=success,
    )


def _is_missing_python3_error(stderr: str) -> bool:
    lowered = stderr.lower()
    return "python3" in lowered and (
        "not found" in lowered
        or "command not found" in lowered
        or "no such file" in lowered
    )


def _python3_requirement_error(operation: str, stderr: str) -> str:
    return f"CUA {operation} requires python3 in the sandbox image: {stderr}"


def _is_posix_os_type(os_type: str) -> bool:
    return os_type.lower() in _POSIX_OS_TYPES


def _non_posix_filesystem_result(path: str, os_type: str) -> dict[str, Any]:
    return {
        "success": False,
        "path": path,
        "error": (
            "CUA filesystem shell fallback is only supported for POSIX images; "
            f"os_type={os_type!r} does not support the required shell commands."
        ),
    }


def _split_listing_entries(output: str) -> list[str]:
    return [line for line in output.splitlines() if line.strip()]


def _require_component_method(
    root: Any,
    component_name: str,
    method_names: str | tuple[str, ...],
) -> Any:
    component = getattr(root, component_name, None)
    names = (method_names,) if isinstance(method_names, str) else method_names
    if component is not None:
        for method_name in names:
            method = getattr(component, method_name, None)
            if method is not None:
                return method
    candidates = ", ".join(f"{component_name}.{name}" for name in names)
    raise RuntimeError(
        f"CUA sandbox does not provide any of: {candidates}. "
        "Please check the installed CUA SDK version and sandbox backend."
    )


def _has_component_method(root: Any, component_name: str, method_name: str) -> bool:
    component = getattr(root, component_name, None)
    return getattr(component, method_name, None) is not None


class CuaShellComponent(ShellComponent):
    def __init__(self, sandbox: Any, os_type: str = "linux") -> None:
        self._sandbox = sandbox
        self._os_type = os_type.lower()
        shell = sandbox.shell
        self._exec_raw = getattr(shell, "exec", None) or getattr(shell, "run", None)
        if self._exec_raw is None:
            raise RuntimeError("CUA sandbox shell must provide `.exec` or `.run`.")

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
            if not _is_posix_os_type(self._os_type):
                return {
                    "stdout": "",
                    "stderr": "error: background shell execution is only supported for POSIX CUA images.",
                    "exit_code": 2,
                    "success": False,
                }
            command = _build_cua_background_command(command)

        result = await _maybe_await(self._exec_raw(command, **kwargs))
        proc = _normalize_process_result(result)
        stderr = proc.stderr
        if background and stderr and _is_missing_python3_error(stderr):
            stderr = _python3_requirement_error("background execution", stderr)
        response = {
            "stdout": proc.stdout,
            "stderr": stderr,
            "exit_code": proc.exit_code,
            "success": proc.success,
        }
        if background:
            try:
                response["pid"] = int(proc.stdout.strip().splitlines()[-1])
            except Exception:
                response["pid"] = None
        return response


def _build_cua_background_command(command: str) -> str:
    return f"python3 -c {shlex.quote(_CUA_BACKGROUND_LAUNCHER)} {shlex.quote(command)}"


class CuaPythonComponent(PythonComponent):
    def __init__(self, sandbox: Any, os_type: str = "linux") -> None:
        self._sandbox = sandbox
        self._os_type = os_type
        python = getattr(sandbox, "python", None)
        self._python_exec = None
        if python is not None:
            self._python_exec = getattr(python, "exec", None) or getattr(
                python, "run", None
            )

    async def exec(
        self,
        code: str,
        kernel_id: str | None = None,
        timeout: int = 30,
        silent: bool = False,
    ) -> dict[str, Any]:
        _ = kernel_id
        if self._python_exec is not None:
            result = await _maybe_await(self._python_exec(code, timeout=timeout))
            proc = _normalize_process_result(result)
        else:
            shell = CuaShellComponent(self._sandbox, os_type=self._os_type)
            result = await shell.exec(f"python3 - <<'PY'\n{code}\nPY", timeout=timeout)
            error = result.get("stderr", "")
            if error and _is_missing_python3_error(error):
                error = _python3_requirement_error("Python execution fallback", error)
            proc = ProcessResult(
                stdout=result.get("stdout", ""),
                stderr=error,
                exit_code=result.get("exit_code"),
                success=bool(result.get("success", False)),
            )

        output_text = "" if silent else proc.stdout
        error_text = proc.stderr
        return {
            "success": proc.success if not silent else not bool(error_text),
            "data": {
                "output": {"text": output_text, "images": []},
                "error": error_text,
            },
            "output": output_text,
            "error": error_text,
        }


def _write_result(path: str, result: dict[str, Any]) -> dict[str, Any]:
    stderr = result.get("stderr", "")
    if stderr and _is_missing_python3_error(stderr):
        result = {
            **result,
            "stderr": _python3_requirement_error("filesystem write fallback", stderr),
        }
    if result.get("stderr") or result.get("success") is False:
        return {"success": False, "path": path, **result}
    return {"success": True, "path": path, **result}


class CuaFileSystemComponent(FileSystemComponent):
    def __init__(
        self, sandbox: Any, os_type: str = CUA_DEFAULT_CONFIG["os_type"]
    ) -> None:
        self._shell = CuaShellComponent(sandbox, os_type=os_type)
        self._fs = getattr(sandbox, "filesystem", None)
        self._os_type = os_type.lower()

    async def create_file(
        self,
        path: str,
        content: str = "",
        mode: int = 0o644,
    ) -> dict[str, Any]:
        write_result = await self.write_file(path, content)
        if not write_result.get("success"):
            return {**write_result, "mode": mode, "mode_applied": False}
        return {"success": True, "path": path, "mode": mode, "mode_applied": False}

    async def read_file(
        self,
        path: str,
        encoding: str = "utf-8",
        offset: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        read_file = None if self._fs is None else getattr(self._fs, "read_file", None)
        if read_file is None:
            if not _is_posix_os_type(self._os_type):
                return _non_posix_filesystem_result(path, self._os_type)
            result = await self._shell.exec(f"cat {shlex.quote(path)}")
            if result.get("stderr"):
                return {"success": False, "path": path, "error": result["stderr"]}
            content = result.get("stdout", "")
        else:
            content = await _maybe_await(read_file(path))
        if isinstance(content, bytes):
            content = content.decode(encoding, errors="replace")
        return {
            "success": True,
            "path": path,
            "content": _slice_content_by_lines(
                str(content), offset=offset, limit=limit
            ),
        }

    async def write_file(
        self,
        path: str,
        content: str,
        mode: str = "w",
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        _ = mode
        write_file = None if self._fs is None else getattr(self._fs, "write_file", None)
        if write_file is None:
            if not _is_posix_os_type(self._os_type):
                return _non_posix_filesystem_result(path, self._os_type)
            result = await _write_base64_via_shell(
                self._shell, path, content.encode(encoding)
            )
            return _write_result(path, result)
        else:
            await _maybe_await(write_file(path, content))
        return {"success": True, "path": path}

    async def delete_file(self, path: str) -> dict[str, Any]:
        delete = None
        if self._fs is not None:
            delete = getattr(self._fs, "delete", None) or getattr(
                self._fs, "delete_file", None
            )
        if delete is None:
            if not _is_posix_os_type(self._os_type):
                return _non_posix_filesystem_result(path, self._os_type)
            result = await self._shell.exec(f"rm -rf {shlex.quote(path)}")
            if result.get("stderr"):
                return {"success": False, "path": path, "error": result["stderr"]}
        else:
            await _maybe_await(delete(path))
        return {"success": True, "path": path}

    async def list_dir(
        self,
        path: str = ".",
        show_hidden: bool = False,
    ) -> dict[str, Any]:
        list_dir = None if self._fs is None else getattr(self._fs, "list_dir", None)
        if list_dir is not None:
            entries = await _maybe_await(list_dir(path))
            return {"success": True, "path": path, "entries": entries}
        if not _is_posix_os_type(self._os_type):
            return _non_posix_filesystem_result(path, self._os_type)
        return await _list_dir_via_shell(self._shell, path, show_hidden)

    async def search_files(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        after_context: int | None = None,
        before_context: int | None = None,
    ) -> dict[str, Any]:
        if not _is_posix_os_type(self._os_type):
            return _non_posix_filesystem_result(path or ".", self._os_type)
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


async def _list_dir_via_shell(
    shell: CuaShellComponent,
    path: str,
    show_hidden: bool,
) -> dict[str, Any]:
    flags = "-1A" if show_hidden else "-1"
    result = await shell.exec(f"ls {flags} {shlex.quote(path)}")
    return {
        "success": not bool(result.get("stderr")),
        "path": path,
        "entries": _split_listing_entries(result.get("stdout", "")),
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
        click = _require_component_method(self._sandbox, "mouse", "click")
        result = await _maybe_await(click(x, y, button=button))
        payload = _maybe_model_dump(result)
        return {"success": bool(payload.get("success", True)), **payload}

    async def type_text(self, text: str) -> dict[str, Any]:
        type_text = _require_component_method(self._sandbox, "keyboard", "type")
        result = await _maybe_await(type_text(text))
        payload = _maybe_model_dump(result)
        return {"success": bool(payload.get("success", True)), **payload}

    async def press_key(self, key: str) -> dict[str, Any]:
        press = _require_component_method(
            self._sandbox, "keyboard", ("press", "key_press", "press_key")
        )
        result = await _maybe_await(press(key))
        payload = _maybe_model_dump(result)
        return {"success": bool(payload.get("success", True)), **payload}


def _screenshot_to_bytes(raw: Any) -> bytes:
    if isinstance(raw, (bytes, bytearray)):
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


@dataclass(slots=True)
class _CuaRuntime:
    sandbox_cm: Any
    sandbox: Any
    shell: CuaShellComponent
    python: CuaPythonComponent
    fs: CuaFileSystemComponent
    gui: CuaGUIComponent | None


class CuaBooter(ComputerBooter):
    def __init__(
        self,
        image: str = CUA_DEFAULT_CONFIG["image"],
        os_type: str = CUA_DEFAULT_CONFIG["os_type"],
        ttl: int = CUA_DEFAULT_CONFIG["ttl"],
        telemetry_enabled: bool = CUA_DEFAULT_CONFIG["telemetry_enabled"],
        local: bool = CUA_DEFAULT_CONFIG["local"],
        api_key: str = CUA_DEFAULT_CONFIG["api_key"],
    ) -> None:
        self.image = image
        self.os_type = os_type
        self.ttl = ttl
        self.telemetry_enabled = telemetry_enabled
        self.local = local
        self.api_key = api_key
        self._runtime: _CuaRuntime | None = None

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
        sandbox_cm = Sandbox.ephemeral(image_obj, **ephemeral_kwargs)
        sandbox = await sandbox_cm.__aenter__()
        self._runtime = _CuaRuntime(
            sandbox_cm=sandbox_cm,
            sandbox=sandbox,
            shell=CuaShellComponent(sandbox, os_type=self.os_type),
            python=CuaPythonComponent(sandbox, os_type=self.os_type),
            fs=CuaFileSystemComponent(sandbox, os_type=self.os_type),
            gui=CuaGUIComponent(sandbox),
        )
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
        if "local" in parameters:
            kwargs["local"] = self.local
        if "api_key" in parameters and self.api_key:
            kwargs["api_key"] = self.api_key
        return kwargs

    async def shutdown(self) -> None:
        if self._runtime is not None:
            await self._runtime.sandbox_cm.__aexit__(None, None, None)
            self._runtime = None

    @property
    def capabilities(self) -> tuple[str, ...] | None:
        capabilities = ["python", "shell", "filesystem"]
        if self._runtime is None:
            return tuple(capabilities)

        sandbox = self._runtime.sandbox
        has_screenshot = getattr(sandbox, "screenshot", None) is not None
        has_mouse = _has_component_method(sandbox, "mouse", "click")
        has_keyboard = _has_component_method(sandbox, "keyboard", "type")
        if has_screenshot or has_mouse or has_keyboard:
            capabilities.append("gui")
        if has_screenshot:
            capabilities.append("screenshot")
        if has_mouse:
            capabilities.append("mouse")
        if has_keyboard:
            capabilities.append("keyboard")
        return tuple(capabilities)

    @property
    def fs(self) -> FileSystemComponent:
        if self._runtime is None:
            raise RuntimeError("CuaBooter is not initialized.")
        return self._runtime.fs

    @property
    def python(self) -> PythonComponent:
        if self._runtime is None:
            raise RuntimeError("CuaBooter is not initialized.")
        return self._runtime.python

    @property
    def shell(self) -> ShellComponent:
        if self._runtime is None:
            raise RuntimeError("CuaBooter is not initialized.")
        return self._runtime.shell

    @property
    def gui(self) -> GUIComponent | None:
        return None if self._runtime is None else self._runtime.gui

    async def upload_file(self, path: str, file_name: str) -> dict:
        local_path = Path(path)
        if not local_path.is_file():
            return {"success": False, "error": f"File not found: {path}"}
        sandbox = None if self._runtime is None else self._runtime.sandbox
        if sandbox is not None and hasattr(sandbox, "upload_file"):
            return _maybe_model_dump(
                await sandbox.upload_file(str(local_path), file_name)
            )
        result = await _write_base64_via_shell(
            self.shell, file_name, local_path.read_bytes()
        )
        return {
            "success": not bool(result.get("stderr")),
            "file_path": file_name,
            **result,
        }

    async def download_file(self, remote_path: str, local_path: str) -> None:
        sandbox = None if self._runtime is None else self._runtime.sandbox
        if sandbox is not None and hasattr(sandbox, "download_file"):
            await sandbox.download_file(remote_path, local_path)
            return
        result = await self.shell.exec(f"base64 {remote_path!r}")
        if result.get("stderr"):
            raise RuntimeError(result["stderr"])
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        Path(local_path).write_bytes(base64.b64decode(result.get("stdout", "")))

    async def available(self) -> bool:
        return self._runtime is not None
