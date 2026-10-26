"""Run a self-contained MCP Apps picker with: uv run examples/mcp_apps/photo_picker.py."""

import asyncio
from pathlib import Path

from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, Resource, TextContent, Tool

server = Server("astrbot-photo-picker")
URI = "ui://photo-picker/index.html"


@server.list_tools()
async def list_tools():
    """Return the demo picker tool."""
    return [
        Tool(
            name="show_photo_picker",
            description="Show three sample illustrations for the user to choose from. Wait for their selection before recommending a cover.",
            inputSchema={"type": "object", "properties": {}},
            _meta={"ui": {"resourceUri": URI}},
        )
    ]


@server.list_resources()
async def list_resources():
    """Return the bundled interactive view."""
    return [
        Resource(uri=URI, name="Photo picker", mimeType="text/html;profile=mcp-app")
    ]


@server.read_resource()
async def read_resource(uri):
    """Read the picker HTML without accessing the network."""
    if str(uri) != URI:
        raise ValueError("Unknown resource")
    return [
        ReadResourceContents(
            content=Path(__file__)
            .with_name("photo_picker.html")
            .read_text(encoding="utf-8"),
            mime_type="text/html;profile=mcp-app",
        )
    ]


@server.call_tool()
async def call_tool(name, arguments):
    """Return sample items as both textual fallback and structured view data."""
    if name != "show_photo_picker":
        raise ValueError("Unknown tool")
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text="Choose sample illustrations: 1 Forest, 2 Sunset, 3 Ocean. Reply with their numbers, or open the interactive app in WebChat.",
            )
        ],
        structuredContent={
            "photos": [
                {"id": "1", "label": "Forest", "color": "#28705c"},
                {"id": "2", "label": "Sunset", "color": "#b85b46"},
                {"id": "3", "label": "Ocean", "color": "#315f91"},
            ]
        },
    )


async def main():
    """Serve the example over stdio."""
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
