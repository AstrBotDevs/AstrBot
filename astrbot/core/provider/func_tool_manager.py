"""
FunctionToolManager - Central registry for all function tools.

This module re-exports from _internal package for backward compatibility.
The canonical implementation is in astrbot._internal.tools.registry.
"""

from __future__ import annotations

# Constants that are still imported by other modules
SUPPORTED_TYPES = [
    "string",
    "number",
    "object",
    "array",
    "boolean",
]

PY_TO_JSON_TYPE = {
    "int": "number",
    "float": "number",
    "bool": "boolean",
    "str": "string",
    "dict": "object",
    "list": "array",
    "tuple": "array",
    "set": "array",
}

# Re-export from _internal for backward compatibility

from astrbot._internal.tools.registry import (
    DEFAULT_MCP_CONFIG,
    ENABLE_MCP_TIMEOUT_ENV,
    MCP_INIT_TIMEOUT_ENV,
    FuncCall,
    FunctionTool,
    FunctionToolManager,
    MCPAllServicesFailedError,
    MCPInitError,
    MCPInitSummary,
    MCPInitTimeoutError,
    MCPShutdownTimeoutError,
    ToolSet,
)

# For backward compatibility - alias FunctionTool as FuncTool
FuncTool = FunctionTool

__all__ = [
    "DEFAULT_MCP_CONFIG",
    "ENABLE_MCP_TIMEOUT_ENV",
    "MCP_INIT_TIMEOUT_ENV",
    "PY_TO_JSON_TYPE",
    "SUPPORTED_TYPES",
    "FuncCall",
    "FuncTool",
    "FunctionTool",
    "FunctionToolManager",
    "MCPAllServicesFailedError",
    "MCPInitError",
    "MCPInitSummary",
    "MCPInitTimeoutError",
    "MCPShutdownTimeoutError",
    "ToolSet",
]
