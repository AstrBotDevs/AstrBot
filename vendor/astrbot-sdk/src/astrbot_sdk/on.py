from .registration import on as _on

command = _on.command
direct_service = _on.direct_service
message = _on.message
service = _on.service
streaming_tool = _on.streaming_tool
tool = _on.tool
tool_discovery = _on.tool_discovery

__all__ = [
    "command",
    "direct_service",
    "message",
    "service",
    "streaming_tool",
    "tool",
    "tool_discovery",
]
