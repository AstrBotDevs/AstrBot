from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any


def has_native_runtime() -> bool:
    """Return whether the compiled Rust/PyO3 native runtime (`_native`) is available."""
    try:
        from . import _native  # noqa: F401
    except ImportError:
        return False
    return True


def _serialize_result(value: Any) -> str | None:
    """Encode a Python callback return value into JSON for NativeWorker."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


class Worker:
    """High-level wrapper over the Rust/PyO3 `NativeWorker` engine.

    Allows Python plugins to declare handlers backed by the compiled Tokio
    transport, scoped contexts, resumable streams, and direct UDS server.
    """

    def __init__(self, native_worker: Any) -> None:
        """Wrap an initialized `_native.NativeWorker` instance."""
        self._native = native_worker

    @classmethod
    def from_dir(cls, plugin_root: Path | str) -> Worker:
        """Create a Worker from a plugin dir with `plugin.json` or `metadata.yaml`.

        Args:
            plugin_root: Plugin root directory.

        Returns:
            Initialized Worker instance.

        Raises:
            RuntimeError: The compiled `astrbot_sdk._native` extension is not built.
        """
        if not has_native_runtime():
            raise RuntimeError(
                "astrbot_sdk._native is not built; build/install native ext first"
            )
        from . import _native

        return cls(_native.NativeWorker.from_dir(str(Path(plugin_root).resolve())))

    @staticmethod
    def _wrap_two_arg(
        cb: Callable[[Any, Any], Awaitable[Any] | Any],
    ) -> Callable[[str, Any], Awaitable[str | None]]:
        async def _inner(raw_json: str, ctx: Any) -> str | None:
            payload = json.loads(raw_json) if raw_json else {}
            res = cb(payload, ctx)
            if inspect.isawaitable(res):
                res = await res
            return _serialize_result(res)

        return _inner

    def command(
        self,
        path: str,
        callback: Callable[[Any, Any], Awaitable[Any] | Any],
        *,
        aliases: Sequence[str] = (),
        description: str | None = None,
        priority: int = 0,
    ) -> Worker:
        """Register a command handler backed by the native Tokio engine."""
        self._native.register_command(
            path,
            list(aliases),
            description,
            priority,
            self._wrap_two_arg(callback),
        )
        return self

    def tool(
        self,
        name: str,
        description: str,
        parameters_schema: dict[str, Any],
        callback: Callable[[Any, Any], Awaitable[Any] | Any],
        *,
        resumable: bool = False,
        streaming_input: bool = False,
    ) -> Worker:
        """Register an LLM tool backed by the native Tokio engine."""
        self._native.register_tool(
            name,
            description,
            json.dumps(parameters_schema, ensure_ascii=False),
            resumable,
            streaming_input,
            self._wrap_two_arg(callback),
        )
        return self

    def service(
        self,
        name: str,
        description: str,
        callback: Callable[[Any, Any], Awaitable[Any] | Any],
        *,
        direct: bool = False,
        input_schema: dict[str, Any] | None = None,
    ) -> Worker:
        """Register a cross-plugin service handler (host-scoped or direct UDS)."""
        schema_json = (
            json.dumps(input_schema, ensure_ascii=False)
            if input_schema is not None
            else None
        )
        self._native.register_service(
            name,
            description,
            direct,
            schema_json,
            self._wrap_two_arg(callback),
        )
        return self

    def hook(
        self,
        stage: str,
        callback: Callable[[Any, Any], Awaitable[Any] | Any],
        *,
        priority: int = 0,
    ) -> Worker:
        """Register a Host pipeline hook handler."""
        self._native.register_hook(stage, priority, self._wrap_two_arg(callback))
        return self

    def web_route(
        self,
        route: str,
        methods: Sequence[str],
        description: str,
        callback: Callable[[Any, Any], Awaitable[Any] | Any],
    ) -> Worker:
        """Register a web route handler."""
        self._native.register_web_route(
            route,
            list(methods),
            description,
            self._wrap_two_arg(callback),
        )
        return self

    def validate_config(
        self,
        callback: Callable[[Any], Awaitable[Any] | Any],
    ) -> Worker:
        """Register a candidate config validation callback."""

        async def _inner(raw_json: str) -> str | None:
            payload = json.loads(raw_json) if raw_json else {}
            res = callback(payload)
            if inspect.isawaitable(res):
                res = await res
            return _serialize_result(res)

        self._native.register_validate_config(_inner)
        return self

    def on_config_changed(
        self,
        callback: Callable[[Any], Awaitable[Any] | Any],
    ) -> Worker:
        """Register a live configuration change callback."""

        async def _inner(raw_json: str) -> str | None:
            payload = json.loads(raw_json) if raw_json else {}
            res = callback(payload)
            if inspect.isawaitable(res):
                res = await res
            return _serialize_result(res)

        self._native.register_on_config_changed(_inner)
        return self

    def on_start(
        self,
        callback: Callable[[Any, Any], Awaitable[Any] | Any],
    ) -> Worker:
        """Register an instance startup callback."""
        self._native.register_on_start(self._wrap_two_arg(callback))
        return self

    def on_stop(
        self,
        callback: Callable[[str], Awaitable[Any] | Any],
    ) -> Worker:
        """Register an instance shutdown callback."""

        async def _inner(reason: str) -> str | None:
            res = callback(reason)
            if inspect.isawaitable(res):
                res = await res
            return _serialize_result(res)

        self._native.register_on_stop(_inner)
        return self

    def on_health(self, callback: Callable[[], Awaitable[None] | None]) -> Worker:
        """Register a periodic health check callback."""

        async def _inner() -> None:
            res = callback()
            if inspect.isawaitable(res):
                await res

        self._native.register_on_health(_inner)
        return self

    def tool_discovery(
        self,
        callback: Callable[[Any, Any], Awaitable[Any] | Any],
    ) -> Worker:
        """Register a dynamic tool discovery callback."""
        self._native.register_tool_discovery(self._wrap_two_arg(callback))
        return self

    async def run_stdio(self) -> None:
        """Serve protocol-v1 frames over process stdio."""
        await self._native.run_stdio()

    async def run_ws(self, url: str, token: str | None = None) -> None:
        """Connect to the Host WebSocket listener and serve protocol-v1 frames."""
        await self._native.run_ws(url, token)

    async def run_uds(self, credential_path: Path | str) -> None:
        """Connect to the Host Unix domain socket using an external credential file."""
        await self._native.run_uds(str(Path(credential_path)))
