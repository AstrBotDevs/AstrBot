from __future__ import annotations

import re
from datetime import timedelta
from typing import TYPE_CHECKING, Generic

import mcp

from astrbot.core.agent.run_context import ContextWrapper, TContext
from astrbot.core.agent.tool import FunctionTool

if TYPE_CHECKING:
    from .mcp_client import MCPClient


def build_mcp_resource_tool_names(
    server_name: str,
    *,
    include_templates: bool,
) -> list[str]:
    safe_server_name = _sanitize_tool_name_fragment(server_name)
    names = [
        f"mcp_{safe_server_name}_list_resources",
        f"mcp_{safe_server_name}_read_resource",
    ]
    if include_templates:
        names.append(f"mcp_{safe_server_name}_list_resource_templates")
    return names


def build_mcp_resource_tools(
    mcp_client: MCPClient,
    server_name: str,
) -> list[MCPResourceTool[TContext]]:
    if not getattr(mcp_client, "supports_resources", False):
        return []

    tools: list[MCPResourceTool[TContext]] = [
        MCPListResourcesTool(
            mcp_client=mcp_client,
            mcp_server_name=server_name,
        ),
        MCPReadResourceTool(
            mcp_client=mcp_client,
            mcp_server_name=server_name,
        ),
    ]
    if mcp_client.resource_templates_supported:
        tools.append(
            MCPListResourceTemplatesTool(
                mcp_client=mcp_client,
                mcp_server_name=server_name,
            )
        )
    return tools


class MCPResourceTool(FunctionTool, Generic[TContext]):
    """Server-scoped synthetic tool for MCP resources."""

    def __init__(self, *, name: str, description: str, parameters: dict) -> None:
        super().__init__(
            name=name,
            description=description,
            parameters=parameters,
        )
        self.mcp_client: MCPClient
        self.mcp_server_name: str


class MCPListResourcesTool(MCPResourceTool[TContext]):
    def __init__(self, *, mcp_client: MCPClient, mcp_server_name: str) -> None:
        super().__init__(
            name=build_mcp_resource_tool_names(
                mcp_server_name,
                include_templates=False,
            )[0],
            description=(
                f"List readable MCP resources exposed by server '{mcp_server_name}'. "
                "Use this before reading a specific resource URI."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "cursor": {
                        "type": "string",
                        "description": (
                            "Optional pagination cursor returned by a previous "
                            "resource listing call."
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
        response = await self.mcp_client.list_resources_and_save(
            cursor=kwargs.get("cursor"),
        )
        return _text_result(
            _format_resources_listing(
                server_name=self.mcp_server_name,
                response=response,
            )
        )


class MCPListResourceTemplatesTool(MCPResourceTool[TContext]):
    def __init__(self, *, mcp_client: MCPClient, mcp_server_name: str) -> None:
        super().__init__(
            name=build_mcp_resource_tool_names(
                mcp_server_name,
                include_templates=True,
            )[2],
            description=(
                f"List MCP resource URI templates exposed by server "
                f"'{mcp_server_name}'. Use the returned URI patterns to construct "
                "resource URIs for read_resource."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "cursor": {
                        "type": "string",
                        "description": (
                            "Optional pagination cursor returned by a previous "
                            "resource template listing call."
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
        response = await self.mcp_client.list_resource_templates_and_save(
            cursor=kwargs.get("cursor"),
        )
        return _text_result(
            _format_resource_templates_listing(
                server_name=self.mcp_server_name,
                response=response,
            )
        )


class MCPReadResourceTool(MCPResourceTool[TContext]):
    def __init__(self, *, mcp_client: MCPClient, mcp_server_name: str) -> None:
        super().__init__(
            name=build_mcp_resource_tool_names(
                mcp_server_name,
                include_templates=False,
            )[1],
            description=(
                f"Read a specific MCP resource from server '{mcp_server_name}' by "
                "its URI."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "uri": {
                        "type": "string",
                        "description": "The MCP resource URI to read.",
                    }
                },
                "required": ["uri"],
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
        uri = str(kwargs["uri"])
        response = await self.mcp_client.read_resource_with_reconnect(
            uri=uri,
            read_timeout_seconds=read_timeout,
        )
        return shape_read_resource_result(
            server_name=self.mcp_server_name,
            requested_uri=uri,
            response=response,
        )


def shape_read_resource_result(
    *,
    server_name: str,
    requested_uri: str,
    response: mcp.types.ReadResourceResult,
) -> mcp.types.CallToolResult:
    contents = response.contents
    if not contents:
        return _text_result(
            f"MCP server '{server_name}' returned no contents for resource "
            f"'{requested_uri}'."
        )

    if len(contents) == 1:
        content = contents[0]
        if isinstance(content, mcp.types.TextResourceContents):
            return _text_result(_format_single_text_resource(server_name, content))
        if (
            isinstance(content, mcp.types.BlobResourceContents)
            and content.mimeType
            and content.mimeType.startswith("image/")
        ):
            return mcp.types.CallToolResult(
                content=[
                    mcp.types.EmbeddedResource(
                        type="resource",
                        resource=content,
                    )
                ]
            )

    return _text_result(
        _format_multi_part_resource(
            server_name=server_name,
            requested_uri=requested_uri,
            contents=contents,
        )
    )


def _text_result(text: str) -> mcp.types.CallToolResult:
    return mcp.types.CallToolResult(
        content=[mcp.types.TextContent(type="text", text=text)]
    )


def _format_resources_listing(
    *,
    server_name: str,
    response: mcp.types.ListResourcesResult,
) -> str:
    if not response.resources:
        text = f"No MCP resources are currently exposed by server '{server_name}'."
        if response.nextCursor:
            text += f"\nNext cursor: {response.nextCursor}"
        return text

    lines = [f"MCP resources from server '{server_name}':"]
    for idx, resource in enumerate(response.resources, start=1):
        lines.extend(_format_resource_metadata(idx, resource))
    if response.nextCursor:
        lines.append(f"Next cursor: {response.nextCursor}")
    return "\n".join(lines)


def _format_resource_templates_listing(
    *,
    server_name: str,
    response: mcp.types.ListResourceTemplatesResult,
) -> str:
    if not response.resourceTemplates:
        text = (
            f"No MCP resource templates are currently exposed by server "
            f"'{server_name}'."
        )
        if response.nextCursor:
            text += f"\nNext cursor: {response.nextCursor}"
        return text

    lines = [f"MCP resource templates from server '{server_name}':"]
    for idx, template in enumerate(response.resourceTemplates, start=1):
        lines.extend(_format_resource_template_metadata(idx, template))
    if response.nextCursor:
        lines.append(f"Next cursor: {response.nextCursor}")
    return "\n".join(lines)


def _format_single_text_resource(
    server_name: str,
    content: mcp.types.TextResourceContents,
) -> str:
    lines = [
        f"MCP text resource from server '{server_name}':",
        f"URI: {content.uri}",
    ]
    if content.mimeType:
        lines.append(f"MIME type: {content.mimeType}")
    lines.extend(["", content.text])
    return "\n".join(lines)


def _format_multi_part_resource(
    *,
    server_name: str,
    requested_uri: str,
    contents: list[mcp.types.TextResourceContents | mcp.types.BlobResourceContents],
) -> str:
    lines = [
        f"MCP resource read result from server '{server_name}':",
        f"Requested URI: {requested_uri}",
        f"Returned parts: {len(contents)}",
    ]
    for idx, content in enumerate(contents, start=1):
        lines.append("")
        lines.append(f"Part {idx}:")
        lines.append(f"URI: {content.uri}")
        if content.mimeType:
            lines.append(f"MIME type: {content.mimeType}")
        if isinstance(content, mcp.types.TextResourceContents):
            lines.append("Text:")
            lines.append(content.text)
        else:
            lines.append(f"Binary blob returned (base64 length: {len(content.blob)}).")
    return "\n".join(lines)


def _format_resource_metadata(
    index: int,
    resource: mcp.types.Resource,
) -> list[str]:
    lines = [f"{index}. {resource.name}", f"   URI: {resource.uri}"]
    if resource.title:
        lines.append(f"   Title: {resource.title}")
    if resource.description:
        lines.append(f"   Description: {resource.description}")
    if resource.mimeType:
        lines.append(f"   MIME type: {resource.mimeType}")
    if resource.size is not None:
        lines.append(f"   Size: {resource.size} bytes")
    return lines


def _format_resource_template_metadata(
    index: int,
    template: mcp.types.ResourceTemplate,
) -> list[str]:
    lines = [f"{index}. {template.name}", f"   URI template: {template.uriTemplate}"]
    if template.title:
        lines.append(f"   Title: {template.title}")
    if template.description:
        lines.append(f"   Description: {template.description}")
    if template.mimeType:
        lines.append(f"   MIME type: {template.mimeType}")
    return lines


def _sanitize_tool_name_fragment(name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return sanitized or "server"
