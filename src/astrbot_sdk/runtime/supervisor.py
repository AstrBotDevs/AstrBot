from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml
from loguru import logger
from .rpc.client.stdio import StdioClient
from .rpc.jsonrpc import (
    JSONRPCErrorData,
    JSONRPCErrorResponse,
    JSONRPCMessage,
    JSONRPCRequest,
    JSONRPCSuccessResponse,
)
from .rpc.request_helper import RPCRequestHelper
from .rpc.server.base import JSONRPCServer
from .stars.registry import EventType, StarHandlerMetadata
from .types import CallHandlerRequest, HandshakeRequest

STATE_FILE_NAME = ".astrbot-worker-state.json"


def _venv_python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


@dataclass(slots=True)
class PluginSpec:
    name: str
    plugin_dir: Path
    manifest_path: Path
    requirements_path: Path
    python_version: str
    manifest_data: dict[str, Any]


@dataclass(slots=True)
class PluginDiscoveryResult:
    plugins: list[PluginSpec]
    skipped_plugins: dict[str, str]


def discover_plugins(plugins_dir: Path) -> PluginDiscoveryResult:
    plugins_root = plugins_dir.resolve()
    skipped_plugins: dict[str, str] = {}
    plugins: list[PluginSpec] = []
    seen_names: set[str] = set()

    if not plugins_root.exists():
        logger.warning(f"Plugins directory does not exist: {plugins_root}")
        return PluginDiscoveryResult([], {})

    for entry in sorted(plugins_root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue

        manifest_path = entry / "plugin.yaml"
        requirements_path = entry / "requirements.txt"
        if not manifest_path.exists():
            logger.warning(f"Skipping {entry}: missing plugin.yaml")
            continue
        if not requirements_path.exists():
            logger.warning(f"Skipping {entry}: missing requirements.txt")
            skipped_plugins[entry.name] = "missing requirements.txt"
            continue

        try:
            manifest_data = (
                yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            )
        except Exception as exc:
            skipped_plugins[entry.name] = f"failed to parse plugin.yaml: {exc}"
            continue

        plugin_name = manifest_data.get("name")
        components = manifest_data.get("components")
        runtime = manifest_data.get("runtime") or {}
        python_version = runtime.get("python")

        if not isinstance(plugin_name, str) or not plugin_name:
            skipped_plugins[entry.name] = "plugin name is required"
            continue
        if plugin_name in seen_names:
            skipped_plugins[plugin_name] = "duplicate plugin name"
            continue
        if not isinstance(components, list) or not components:
            skipped_plugins[plugin_name] = "components must be a non-empty list"
            continue
        if not isinstance(python_version, str) or not python_version:
            skipped_plugins[plugin_name] = "runtime.python is required"
            continue

        seen_names.add(plugin_name)
        plugins.append(
            PluginSpec(
                name=plugin_name,
                plugin_dir=entry.resolve(),
                manifest_path=manifest_path.resolve(),
                requirements_path=requirements_path.resolve(),
                python_version=python_version,
                manifest_data=manifest_data,
            )
        )

    return PluginDiscoveryResult(plugins=plugins, skipped_plugins=skipped_plugins)


class PluginEnvironmentManager:
    def __init__(self, repo_root: Path, uv_binary: str | None = None) -> None:
        self.repo_root = repo_root.resolve()
        self.uv_binary = uv_binary or shutil.which("uv")
        self.cache_dir = self.repo_root / ".uv-cache"

    def prepare_environment(self, plugin: PluginSpec) -> Path:
        if not self.uv_binary:
            raise RuntimeError("uv executable not found")

        state_path = plugin.plugin_dir / STATE_FILE_NAME
        venv_dir = plugin.plugin_dir / ".venv"
        python_path = _venv_python_path(venv_dir)
        fingerprint = self._fingerprint(plugin)
        state = self._load_state(state_path)

        if (
            not python_path.exists()
            or not self._matches_python_version(venv_dir, plugin.python_version)
            or state.get("fingerprint") != fingerprint
        ):
            self._rebuild(plugin, venv_dir, python_path)
            self._write_state(state_path, plugin, fingerprint)

        return python_path

    def _rebuild(self, plugin: PluginSpec, venv_dir: Path, python_path: Path) -> None:
        if venv_dir.exists():
            shutil.rmtree(venv_dir)

        venv_dir.parent.mkdir(parents=True, exist_ok=True)
        self._run_command(
            [
                self.uv_binary,
                "venv",
                "--python",
                plugin.python_version,
                "--system-site-packages",
                "--no-python-downloads",
                "--no-managed-python",
                str(venv_dir),
            ],
            cwd=self.repo_root,
            command_name=f"create venv for {plugin.name}",
        )

        requirements_text = plugin.requirements_path.read_text(encoding="utf-8").strip()
        if not requirements_text:
            return

        self._run_command(
            [
                self.uv_binary,
                "pip",
                "install",
                "--python",
                str(python_path),
                "-r",
                str(plugin.requirements_path),
            ],
            cwd=plugin.plugin_dir,
            command_name=f"install requirements for {plugin.name}",
        )

    def _run_command(
        self,
        command: list[str],
        *,
        cwd: Path,
        command_name: str,
    ) -> None:
        logger.info(f"{command_name}: {' '.join(command)}")
        process = subprocess.run(
            command,
            cwd=str(cwd),
            env={**os.environ, "UV_CACHE_DIR": str(self.cache_dir)},
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(
                f"{command_name} failed with exit code {process.returncode}: "
                f"{process.stderr.strip() or process.stdout.strip()}"
            )

    @staticmethod
    def _fingerprint(plugin: PluginSpec) -> str:
        requirements = plugin.requirements_path.read_text(encoding="utf-8")
        payload = {
            "python_version": plugin.python_version,
            "requirements": requirements,
        }
        return json.dumps(payload, ensure_ascii=True, sort_keys=True)

    @staticmethod
    def _load_state(state_path: Path) -> dict[str, Any]:
        if not state_path.exists():
            return {}
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _write_state(state_path: Path, plugin: PluginSpec, fingerprint: str) -> None:
        state_path.write_text(
            json.dumps(
                {
                    "plugin": plugin.name,
                    "python_version": plugin.python_version,
                    "fingerprint": fingerprint,
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _matches_python_version(venv_dir: Path, version: str) -> bool:
        pyvenv_cfg = venv_dir / "pyvenv.cfg"
        if not pyvenv_cfg.exists():
            return False
        try:
            content = pyvenv_cfg.read_text(encoding="utf-8")
        except OSError:
            return False
        match = re.search(r"version\s*=\s*(\d+\.\d+)\.\d+", content, re.IGNORECASE)
        return match is not None and match.group(1) == version


class WorkerRuntime:
    def __init__(
        self,
        plugin: PluginSpec,
        server: JSONRPCServer,
        repo_root: Path,
        env_manager: PluginEnvironmentManager,
    ) -> None:
        self.plugin = plugin
        self.server = server
        self.repo_root = repo_root.resolve()
        self.env_manager = env_manager
        self.rpc_helper = RPCRequestHelper()
        self.client: StdioClient | None = None
        self.raw_handshake: dict[str, Any] = {}
        self.handlers: list[StarHandlerMetadata] = []
        self._context_requests: dict[str, str] = {}
        self._forwarded_call_ids: set[str] = set()

    async def start(self) -> None:
        python_path = self.env_manager.prepare_environment(self.plugin)
        repo_src_dir = str(self.repo_root / "src")
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            f"{repo_src_dir}{os.pathsep}{existing_pythonpath}"
            if existing_pythonpath
            else repo_src_dir
        )

        self.client = StdioClient(
            command=[
                str(python_path),
                "-m",
                "astrbot_sdk",
                "worker",
                "--plugin-dir",
                str(self.plugin.plugin_dir),
            ],
            cwd=str(self.plugin.plugin_dir),
            env=env,
        )
        self.client.set_message_handler(self._handle_message)
        await self.client.start()

        response = await asyncio.wait_for(
            self.rpc_helper.call_rpc(
                self.client,
                HandshakeRequest(
                    jsonrpc="2.0",
                    id=self.rpc_helper._generate_request_id(),
                    method="handshake",
                ),
            ),
            timeout=15.0,
        )
        if not isinstance(response, JSONRPCSuccessResponse):
            raise RuntimeError(f"Handshake failed for plugin {self.plugin.name}")

        result = response.result
        if not isinstance(result, dict):
            raise RuntimeError(f"Invalid handshake payload for plugin {self.plugin.name}")

        self.raw_handshake = result
        self.handlers = self._parse_handlers(result)

    async def stop(self) -> None:
        if self.client is not None:
            await self.client.stop()

    async def forward_call_handler(self, request: JSONRPCRequest) -> None:
        if self.client is None:
            raise RuntimeError(f"Worker for {self.plugin.name} is not running")
        if request.id is not None:
            self._forwarded_call_ids.add(str(request.id))
        await self.client.send_message(request)

    async def handle_context_response(
        self, message: JSONRPCSuccessResponse | JSONRPCErrorResponse
    ) -> bool:
        message_id = str(message.id)
        worker_request_id = self._context_requests.pop(message_id, None)
        if worker_request_id is None:
            return False
        if self.client is None:
            return True

        if isinstance(message, JSONRPCSuccessResponse):
            await self.client.send_message(
                JSONRPCSuccessResponse(
                    jsonrpc="2.0",
                    id=worker_request_id,
                    result=message.result,
                )
            )
        else:
            await self.client.send_message(
                JSONRPCErrorResponse(
                    jsonrpc="2.0",
                    id=worker_request_id,
                    error=message.error,
                )
            )
        return True

    async def _handle_message(self, message: JSONRPCMessage) -> None:
        if isinstance(message, (JSONRPCSuccessResponse, JSONRPCErrorResponse)):
            if message.id in self.rpc_helper.pending_requests:
                self.rpc_helper.resolve_pending_request(message)
                return

            if message.id is not None and str(message.id) in self._forwarded_call_ids:
                self._forwarded_call_ids.discard(str(message.id))
                await self.server.send_message(message)
                return

        if not isinstance(message, JSONRPCRequest):
            return

        if message.method in [
            "handler_stream_start",
            "handler_stream_update",
            "handler_stream_end",
        ]:
            await self.server.send_message(message)
            return

        if message.method != "call_context_function":
            logger.warning(
                f"Worker {self.plugin.name} sent unknown request: {message.method}"
            )
            return

        supervisor_request_id = (
            f"ctx:{self.plugin.name}:{message.id}"
            if message.id is not None
            else f"ctx:{self.plugin.name}:none"
        )
        self._context_requests[supervisor_request_id] = str(message.id)
        await self.server.send_message(
            JSONRPCRequest(
                jsonrpc="2.0",
                id=supervisor_request_id,
                method=message.method,
                params=message.params,
            )
        )

    @staticmethod
    def _parse_handlers(handshake_payload: dict[str, Any]) -> list[StarHandlerMetadata]:
        handlers: list[StarHandlerMetadata] = []

        def _placeholder_handler(*args, **kwargs):
            raise NotImplementedError("Worker supervisor does not execute handlers")

        for star_info in handshake_payload.values():
            handlers_data = star_info.get("handlers") or []
            for handler_data in handlers_data:
                handlers.append(
                    StarHandlerMetadata(
                        event_type=EventType(handler_data["event_type"]),
                        handler_full_name=handler_data["handler_full_name"],
                        handler_name=handler_data["handler_name"],
                        handler_module_path=handler_data["handler_module_path"],
                        handler=_placeholder_handler,
                        event_filters=[],
                        desc=handler_data.get("desc", ""),
                        extras_configs=handler_data.get("extras_configs", {}),
                    )
                )
        return handlers


class SupervisorRuntime:
    def __init__(
        self,
        server: JSONRPCServer,
        plugins_dir: Path,
        *,
        env_manager: PluginEnvironmentManager | None = None,
        worker_factory: Callable[
            [PluginSpec, JSONRPCServer, Path, PluginEnvironmentManager], WorkerRuntime
        ]
        | None = None,
    ) -> None:
        self.server = server
        self.plugins_dir = plugins_dir.resolve()
        self.repo_root = Path(__file__).resolve().parents[3]
        self.env_manager = env_manager or PluginEnvironmentManager(self.repo_root)
        self.worker_factory = worker_factory or WorkerRuntime
        self.loaded_plugins: list[str] = []
        self.skipped_plugins: dict[str, str] = {}
        self._workers_by_name: dict[str, WorkerRuntime] = {}
        self._handler_to_worker: dict[str, WorkerRuntime] = {}

    async def start(self) -> None:
        discovery = discover_plugins(self.plugins_dir)
        self.skipped_plugins = dict(discovery.skipped_plugins)

        for plugin in discovery.plugins:
            worker = self.worker_factory(
                plugin,
                self.server,
                self.repo_root,
                self.env_manager,
            )
            try:
                await worker.start()
            except Exception as exc:
                self.skipped_plugins[plugin.name] = str(exc)
                logger.error(f"Failed to start worker for {plugin.name}: {exc}")
                await worker.stop()
                continue

            duplicate_handlers = [
                handler.handler_full_name
                for handler in worker.handlers
                if handler.handler_full_name in self._handler_to_worker
            ]
            if duplicate_handlers:
                self.skipped_plugins[plugin.name] = (
                    f"duplicate handlers: {', '.join(sorted(duplicate_handlers))}"
                )
                await worker.stop()
                continue

            self._workers_by_name[plugin.name] = worker
            self.loaded_plugins.append(plugin.name)
            for handler in worker.handlers:
                self._handler_to_worker[handler.handler_full_name] = worker

        self.loaded_plugins.sort()
        self.server.set_message_handler(self._handle_message)
        await self.server.start()
        self._log_startup_summary()

    async def stop(self) -> None:
        for worker in list(self._workers_by_name.values()):
            await worker.stop()
        await self.server.stop()

    async def _handle_message(self, message: JSONRPCMessage) -> None:
        if isinstance(message, JSONRPCRequest):
            if message.method == "handshake":
                await self.server.send_message(self._build_handshake_response(message.id))
                return
            if message.method == "call_handler":
                await self._route_call_handler(message)
                return
            logger.warning(f"Unknown method from core: {message.method}")
            return

        for worker in self._workers_by_name.values():
            if await worker.handle_context_response(message):
                return

        logger.warning(f"Received response for unknown request id: {message.id}")

    def _build_handshake_response(
        self, request_id: str | None
    ) -> JSONRPCSuccessResponse:
        payload: dict[str, Any] = {}
        for worker in self._workers_by_name.values():
            payload.update(worker.raw_handshake)
        return JSONRPCSuccessResponse(
            jsonrpc="2.0",
            id=request_id,
            result=payload,
        )

    async def _route_call_handler(self, message: JSONRPCRequest) -> None:
        try:
            params = CallHandlerRequest.Params.model_validate(message.params)
        except Exception as exc:
            await self.server.send_message(
                JSONRPCErrorResponse(
                    jsonrpc="2.0",
                    id=message.id,
                    error=JSONRPCErrorData(code=-32602, message=f"Invalid params: {exc}"),
                )
            )
            return

        worker = self._handler_to_worker.get(params.handler_full_name)
        if worker is None:
            await self.server.send_message(
                JSONRPCErrorResponse(
                    jsonrpc="2.0",
                    id=message.id,
                    error=JSONRPCErrorData(
                        code=-32601,
                        message=f"Handler not found: {params.handler_full_name}",
                    ),
                )
            )
            return

        await worker.forward_call_handler(message)

    def _log_startup_summary(self) -> None:
        loaded = ", ".join(self.loaded_plugins) if self.loaded_plugins else "none"
        logger.info(f"Loaded plugins: {loaded}")
        if not self.skipped_plugins:
            logger.info("Skipped plugins: none")
            return
        for plugin_name, reason in sorted(self.skipped_plugins.items()):
            logger.warning(f"Skipped plugin {plugin_name}: {reason}")
