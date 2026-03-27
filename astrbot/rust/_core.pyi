from typing import Any

class AstrbotOrchestrator:
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def is_running(self) -> bool: ...
    def register_star(self, name: str, handler: str) -> None: ...
    def unregister_star(self, name: str) -> None: ...
    def list_stars(self) -> list[str]: ...
    def record_activity(self) -> None: ...
    def get_stats(self) -> dict[str, Any]: ...
    def set_protocol_connected(self, protocol: str, connected: bool) -> None: ...
    def get_protocol_status(self, protocol: str) -> dict[str, Any] | None: ...

# ABP Plugin types - TODO: expose via PyO3 bindings

class PluginLoadMode:
    IN_PROCESS: PluginLoadMode
    OUT_OF_PROCESS: PluginLoadMode

class PluginTransport:
    STDIO: PluginTransport
    UNIX_SOCKET: PluginTransport
    HTTP: PluginTransport

class PluginConfig:
    name: str
    version: str
    load_mode: PluginLoadMode
    command: str | None
    args: list[str]
    env: dict[str, str]
    transport: PluginTransport
    url: str | None

class PluginCapabilities:
    tools: bool
    handlers: bool
    events: bool
    resources: bool

class PluginMetadata:
    display_name: str | None
    description: str | None
    author: str | None
    homepage: str | None
    support_platforms: list[str]
    astrbot_version: str | None

class AbpClient:
    def __init__(self) -> None: ...
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    def is_connected(self) -> bool: ...
    def register_in_process_plugin(self, config: PluginConfig) -> None: ...
    def register_out_of_process_plugin(self, config: PluginConfig) -> None: ...
    def unregister_plugin(self, name: str) -> None: ...
    def list_plugins(self) -> list[str]: ...
    def get_plugin_info(self, name: str) -> PluginInfo | None: ...
    async def call_tool(self, plugin_name: str, tool_name: str, arguments: dict[str, Any]) -> ToolResult: ...
    async def handle_event(self, plugin_name: str, event_type: str, event: dict[str, Any]) -> HandleEventResult: ...

class PluginInfo:
    name: str
    version: str
    load_mode: PluginLoadMode
    capabilities: PluginCapabilities
    metadata: PluginMetadata | None
    tools_count: int

class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]

class ToolResult:
    content: list[ToolContent]

class ToolContent:
    type: str
    text: str | None
    image: str | None
    url: str | None

class HandleEventResult:
    handled: bool
    results: list[MessageChainItem]
    stop_propagation: bool

class MessageChainItem:
    type: str
    text: str | None

def get_orchestrator() -> AstrbotOrchestrator: ...
def get_abp_client() -> AbpClient: ...
def cli(args: list[str]) -> None: ...
