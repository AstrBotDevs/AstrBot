from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Generic

import mcp

from astrbot.core.agent.run_context import ContextWrapper, TContext
from astrbot.core.agent.tool import FunctionTool

if TYPE_CHECKING:
    from .mcp_client import MCPClient


def build_mcp_prompt_tool_names(server_name: str) -> list[str]:
    safe_server_name = _sanitize_tool_name_fragment(server_name)
    return [
        f"mcp_{safe_server_name}_list_prompts",
        f"mcp_{safe_server_name}_get_prompt",
    ]


def build_mcp_prompt_tools(
    mcp_client: MCPClient,
    server_name: str,
) -> list[MCPPromptTool[TContext]]:
    if not getattr(mcp_client, "supports_prompts", False):
        return []

    return [
        MCPListPromptsTool(
            mcp_client=mcp_client,
            mcp_server_name=server_name,
        ),
        MCPGetPromptTool(
            mcp_client=mcp_client,
            mcp_server_name=server_name,
        ),
    ]


class MCPPromptTool(FunctionTool, Generic[TContext]):
    """Server-scoped synthetic tool for MCP prompts."""

    def __init__(self, *, name: str, description: str, parameters: dict) -> None:
        super().__init__(
            name=name,
            description=description,
            parameters=parameters,
        )
        self.mcp_client: MCPClient
        self.mcp_server_name: str


class MCPListPromptsTool(MCPPromptTool[TContext]):
    def __init__(self, *, mcp_client: MCPClient, mcp_server_name: str) -> None:
        super().__init__(
            name=build_mcp_prompt_tool_names(mcp_server_name)[0],
            description=(
                f"List MCP prompts exposed by server '{mcp_server_name}'. "
                "Use this before getting a specific prompt template."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "cursor": {
                        "type": "string",
                        "description": (
                            "Optional pagination cursor returned by a previous "
                            "prompt listing call."
                        ),
                    }
                },
            },
        )
        self.mcp_client = mcp_client
        self.mcp_server_name = mcp_server_name

    async def call(
        self,
        context: ContextWrapper[TContext],
        **kwargs,
    ) -> mcp.types.CallToolResult:
        _ = context
        response = await self.mcp_client.list_prompts_and_save(
            cursor=kwargs.get("cursor"),
        )
        return _text_result(
            _format_prompts_listing(
                server_name=self.mcp_server_name,
                response=response,
            )
        )


class MCPGetPromptTool(MCPPromptTool[TContext]):
    def __init__(self, *, mcp_client: MCPClient, mcp_server_name: str) -> None:
        super().__init__(
            name=build_mcp_prompt_tool_names(mcp_server_name)[1],
            description=(
                f"Get a specific MCP prompt from server '{mcp_server_name}' by "
                "name, optionally providing prompt arguments."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The MCP prompt name to resolve.",
                    },
                    "arguments": {
                        "type": "object",
                        "description": (
                            "Optional prompt arguments. Keys and values are sent to "
                            "the MCP server as strings."
                        ),
                        "additionalProperties": {
                            "type": "string",
                        },
                    },
                },
                "required": ["name"],
            },
        )
        self.mcp_client = mcp_client
        self.mcp_server_name = mcp_server_name

    async def call(
        self,
        context: ContextWrapper[TContext],
        **kwargs,
    ) -> mcp.types.CallToolResult:
        read_timeout = timedelta(seconds=context.tool_call_timeout)
        name = str(kwargs["name"])
        response = await self.mcp_client.get_prompt_with_reconnect(
            name=name,
            arguments=_normalize_prompt_arguments(kwargs.get("arguments")),
            read_timeout_seconds=read_timeout,
        )
        return _text_result(
            shape_get_prompt_result(
                server_name=self.mcp_server_name,
                prompt_name=name,
                response=response,
            )
        )


def shape_get_prompt_result(
    *,
    server_name: str,
    prompt_name: str,
    response: mcp.types.GetPromptResult,
) -> str:
    lines = [
        f"MCP prompt from server '{server_name}':",
        f"Prompt: {prompt_name}",
    ]
    if response.description:
        lines.append(f"Description: {response.description}")

    if not response.messages:
        lines.append("No prompt messages were returned.")
        return "\n".join(lines)

    lines.append(f"Returned messages: {len(response.messages)}")
    for idx, message in enumerate(response.messages, start=1):
        lines.append("")
        lines.append(f"Message {idx} ({message.role}):")
        lines.extend(_format_prompt_message_content(message.content))
    return "\n".join(lines)


def _text_result(text: str) -> mcp.types.CallToolResult:
    return mcp.types.CallToolResult(
        content=[mcp.types.TextContent(type="text", text=text)]
    )


def _format_prompts_listing(
    *,
    server_name: str,
    response: mcp.types.ListPromptsResult,
) -> str:
    if not response.prompts:
        text = f"No MCP prompts are currently exposed by server '{server_name}'."
        if response.nextCursor:
            text += f"\nNext cursor: {response.nextCursor}"
        return text

    lines = [f"MCP prompts from server '{server_name}':"]
    for idx, prompt in enumerate(response.prompts, start=1):
        lines.extend(_format_prompt_metadata(idx, prompt))
    if response.nextCursor:
        lines.append(f"Next cursor: {response.nextCursor}")
    return "\n".join(lines)


def _format_prompt_metadata(index: int, prompt: mcp.types.Prompt) -> list[str]:
    lines = [f"{index}. {prompt.name}"]
    if prompt.title:
        lines.append(f"   Title: {prompt.title}")
    if prompt.description:
        lines.append(f"   Description: {prompt.description}")
    if prompt.arguments:
        lines.append("   Arguments:")
        for argument in prompt.arguments:
            lines.append(_format_prompt_argument(argument))
    return lines


def _format_prompt_argument(argument: mcp.types.PromptArgument) -> str:
    required_suffix = "required" if argument.required else "optional"
    if argument.description:
        return f"   - {argument.name} ({required_suffix}): {argument.description}"
    return f"   - {argument.name} ({required_suffix})"


def _format_prompt_message_content(
    content: mcp.types.ContentBlock,
) -> list[str]:
    if isinstance(content, mcp.types.TextContent):
        return content.text.splitlines() or [content.text]
    if isinstance(content, mcp.types.ImageContent):
        return [
            "Image block returned.",
            f"MIME type: {content.mimeType}",
            f"Base64 length: {len(content.data)}",
        ]
    if isinstance(content, mcp.types.AudioContent):
        return [
            "Audio block returned.",
            f"MIME type: {content.mimeType}",
            f"Base64 length: {len(content.data)}",
        ]
    if isinstance(content, mcp.types.EmbeddedResource):
        resource = content.resource
        if isinstance(resource, mcp.types.TextResourceContents):
            lines = [
                "Embedded text resource returned.",
                f"URI: {resource.uri}",
            ]
            if resource.mimeType:
                lines.append(f"MIME type: {resource.mimeType}")
            lines.append("Text:")
            lines.extend(resource.text.splitlines() or [resource.text])
            return lines
        if isinstance(resource, mcp.types.BlobResourceContents):
            lines = [
                "Embedded binary resource returned.",
                f"URI: {resource.uri}",
            ]
            if resource.mimeType:
                lines.append(f"MIME type: {resource.mimeType}")
            lines.append(f"Base64 length: {len(resource.blob)}")
            return lines
    return [f"Unsupported prompt content block: {type(content).__name__}"]


def _normalize_prompt_arguments(
    raw_arguments: Any,
) -> dict[str, str] | None:
    if raw_arguments is None:
        return None
    if isinstance(raw_arguments, str):
        stripped = raw_arguments.strip()
        if not stripped:
            return None
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        raw_arguments = parsed
    if not isinstance(raw_arguments, dict):
        return None
    normalized: dict[str, str] = {}
    for key, value in raw_arguments.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        normalized[key_text] = "" if value is None else str(value)
    return normalized or None


def _sanitize_tool_name_fragment(name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return sanitized or "server"
