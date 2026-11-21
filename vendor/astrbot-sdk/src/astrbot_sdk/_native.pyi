from __future__ import annotations

from collections.abc import Awaitable, Callable

class NativeHostClient:
    def invoke(
        self,
        capability: str,
        operation: str,
        input_json: str,
    ) -> Awaitable[str]: ...
    def is_retired(self) -> bool: ...
    def retire(self) -> None: ...

class NativePluginClient:
    def call_service(
        self,
        target_plugin_id: str,
        service: str,
        input_json: str,
    ) -> Awaitable[str]: ...

class NativeStartupContext:
    @property
    def config_json(self) -> str: ...
    @property
    def data_dir(self) -> str | None: ...
    @property
    def host(self) -> NativeHostClient: ...
    def current_config_json(self) -> str: ...
    def is_cancelled(self) -> bool: ...

class NativeInvocationContext:
    @property
    def call_id(self) -> str: ...
    @property
    def config_json(self) -> str: ...
    @property
    def host(self) -> NativeHostClient: ...
    @property
    def plugins(self) -> NativePluginClient: ...
    def current_config_json(self) -> str: ...
    def yield_value(
        self,
        value_json: str,
        wait_for_ack: bool = True,
    ) -> Awaitable[None]: ...
    def progress(self, payload_json: str) -> Awaitable[None]: ...
    def is_cancelled(self) -> bool: ...

class NativeDirectContext:
    @property
    def config_json(self) -> str: ...
    def current_config_json(self) -> str: ...
    def is_cancelled(self) -> bool: ...

class NativeWorker:
    @staticmethod
    def from_dir(plugin_root: str) -> NativeWorker: ...
    def register_command(
        self,
        path: str,
        aliases: list[str],
        description: str | None,
        priority: int,
        callback: Callable[[str, NativeInvocationContext], Awaitable[str | None]],
    ) -> None: ...
    def register_tool(
        self,
        name: str,
        description: str,
        parameters_schema_json: str,
        resumable: bool,
        streaming_input: bool,
        callback: Callable[[str, NativeInvocationContext], Awaitable[str | None]],
    ) -> None: ...
    def register_service(
        self,
        name: str,
        description: str,
        direct: bool,
        input_schema_json: str | None,
        callback: Callable[..., Awaitable[str | None]],
    ) -> None: ...
    def register_hook(
        self,
        stage: str,
        priority: int,
        callback: Callable[[str, NativeInvocationContext], Awaitable[str | None]],
    ) -> None: ...
    def register_web_route(
        self,
        route: str,
        methods: list[str],
        description: str,
        callback: Callable[[str, NativeInvocationContext], Awaitable[str | None]],
    ) -> None: ...
    def register_validate_config(
        self,
        callback: Callable[[str], Awaitable[str | None]],
    ) -> None: ...
    def register_on_config_changed(
        self,
        callback: Callable[[str], Awaitable[str | None]],
    ) -> None: ...
    def register_on_start(
        self,
        callback: Callable[[str, NativeStartupContext], Awaitable[str | None]],
    ) -> None: ...
    def register_on_stop(
        self,
        callback: Callable[[str], Awaitable[str | None]],
    ) -> None: ...
    def register_on_health(
        self,
        callback: Callable[[], Awaitable[None]],
    ) -> None: ...
    def register_tool_discovery(
        self,
        callback: Callable[[str, NativeStartupContext], Awaitable[str | None]],
    ) -> None: ...
    def run_stdio(self) -> Awaitable[None]: ...
    def run_ws(self, url: str, token: str | None = None) -> Awaitable[None]: ...
    def run_uds(self, credential_path: str) -> Awaitable[None]: ...

def validate_config_schema_file_py(path: str) -> str: ...
def has_sensitive_schema_fields_py(schema_json: str) -> bool: ...
def load_manifest_json(plugin_root: str) -> str: ...
