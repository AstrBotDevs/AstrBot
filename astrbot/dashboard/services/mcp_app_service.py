"""Read only the MCP view attached to a user's completed tool call."""

import asyncio

from mcp.types import TextResourceContents

from astrbot.core.agent.mcp_client import MCPTool

from .chat_service import ChatServiceError

MAX_APP_HTML_BYTES = 1024 * 1024


async def read_chat_mcp_app(service, username, session_id, message_id, tool_call_id):
    """Resolve a view from persisted history, never from a caller-supplied URI.

    Args:
        service: Dashboard chat service.
        username: Authenticated conversation owner.
        session_id: Conversation containing the completed tool call.
        message_id: Persisted assistant message identifier.
        tool_call_id: Tool call within that message.

    Returns:
        Bundled HTML and the recorded tool input and result.

    Raises:
        ChatServiceError: If ownership, tool identity, or resource validation fails.
    """
    session = await service.db.get_platform_session_by_id(session_id)
    if not session or session.creator != username:
        raise ChatServiceError("Session not found or access denied")
    record = await service.db.get_platform_message_history_by_id(message_id)
    if (
        not record
        or record.user_id != session_id
        or record.platform_id != session.platform_id
        or not isinstance(record.content, dict)
        or record.content.get("type") != "bot"
    ):
        raise ChatServiceError("Assistant message not found")
    parts = record.content.get("message", [])
    call = next(
        (
            call
            for part in parts
            if isinstance(part, dict) and part.get("type") == "tool_call"
            for call in part.get("tool_calls", [])
            if isinstance(call, dict) and call.get("id") == tool_call_id
        ),
        None,
    )
    app = call.get("mcp_app") if call else None
    if not isinstance(app, dict):
        raise ChatServiceError("This tool call has no MCP App")
    manager = service.core_lifecycle.provider_manager.llm_tools
    tool = next((t for t in manager.func_list if t.name == call.get("name")), None)
    if (
        not isinstance(tool, MCPTool)
        or not tool.active
        or not tool.mcp_client.active
        or tool.mcp_server_name != app.get("server")
        or tool.ui_resource_uri != app.get("uri")
        or not tool.ui_resource_uri
        or tool.mcp_client.session is None
    ):
        raise ChatServiceError("The original MCP App is no longer available")
    try:
        resource = await asyncio.wait_for(
            tool.mcp_client.session.read_resource(tool.ui_resource_uri), timeout=20
        )
    except Exception as exc:
        raise ChatServiceError("Could not read the MCP App resource") from exc
    for content in resource.contents:
        if (
            isinstance(content, TextResourceContents)
            and str(content.uri) == tool.ui_resource_uri
            and content.mimeType == "text/html;profile=mcp-app"
            and len(content.text.encode("utf-8")) <= MAX_APP_HTML_BYTES
        ):
            return {
                "html": content.text,
                "arguments": call.get("args", {}),
                "result": app.get("result", {}),
            }
    raise ChatServiceError("MCP App must be bundled HTML of at most 1 MiB")
