"""Ephemeral MCP App capabilities minted from actual WebChat tool invocations."""

import json
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass, replace

from .mcp_client import MCPTool

APP_TTL_SECONDS = 900
MAX_APP_CAPABILITIES = 256
MAX_APP_DATA_BYTES = 1024 * 1024


@dataclass
class McpAppCapability:
    username: str
    session_id: str
    origin: str
    run_id: str
    checkpoint_id: str
    call_id: str
    tool: MCPTool
    connection: object
    server_name: str
    original_tool_name: str
    resource_uri: str
    arguments: dict
    result: dict | None = None
    expires: float = 0
    message_id: str | None = None

    def is_current(self) -> bool:
        """Check the exact live tool and ClientSession generation.

        Returns:
            Whether the invocation's authority is still available unchanged.
        """
        return (
            self.tool.active
            and self.tool.mcp_client.active
            and self.tool.mcp_client.session is self.connection
            and self.tool.mcp_server_name == self.server_name
            and self.tool.mcp_tool.name == self.original_tool_name
            and self.tool.ui_resource_uri == self.resource_uri
        )


class McpAppRegistry:
    def __init__(self):
        self.entries: OrderedDict[str, McpAppCapability] = OrderedDict()

    def capture(self, tool, event, call_id, arguments):
        """Capture server-owned identity before executing a WebChat MCP tool.

        Args:
            tool: Actual tool selected by the runner, not its displayed name.
            event: Originating platform event.
            call_id: The runner's tool-call identifier.
            arguments: Arguments passed to that tool.

        Returns:
            Invocation authority, or None for unsupported/incomplete contexts.
        """
        from astrbot.core.platform.sources.webchat.webchat_event import (
            WebChatMessageEvent,
        )

        if not isinstance(tool, MCPTool) or not isinstance(event, WebChatMessageEvent):
            return None
        raw = event.message_obj.raw_message
        if not isinstance(raw, tuple) or len(raw) != 3:
            return None
        username, session_id, payload = raw
        if not isinstance(payload, dict) or not all(
            isinstance(value, str) and value
            for value in (
                username,
                session_id,
                call_id,
                payload.get("message_id"),
                payload.get("llm_checkpoint_id"),
            )
        ):
            return None
        if not tool.ui_resource_uri or tool.mcp_client.session is None:
            return None
        return McpAppCapability(
            username=username,
            session_id=session_id,
            origin=event.unified_msg_origin,
            run_id=payload["message_id"],
            checkpoint_id=payload["llm_checkpoint_id"],
            call_id=call_id,
            tool=tool,
            connection=tool.mcp_client.session,
            server_name=tool.mcp_server_name,
            original_tool_name=tool.mcp_tool.name,
            resource_uri=tool.ui_resource_uri,
            arguments=json.loads(json.dumps(arguments)),
        )

    def issue(self, capability, result):
        """Issue an opaque reference after the captured invocation succeeds.

        Args:
            capability: Authority captured before invoking the tool.
            result: Its complete structured MCP result.

        Returns:
            An opaque reference, or None when the view cannot be retained safely.
        """
        if capability is None or not capability.is_current():
            return None
        encoded = json.dumps({"arguments": capability.arguments, "result": result})
        if len(encoded.encode("utf-8")) > MAX_APP_DATA_BYTES:
            return None
        now = time.monotonic()
        for key, value in list(self.entries.items()):
            if value.expires <= now:
                del self.entries[key]
        while len(self.entries) >= MAX_APP_CAPABILITIES:
            self.entries.popitem(last=False)
        ref = secrets.token_urlsafe(32)
        self.entries[ref] = replace(
            capability,
            result=json.loads(encoded)["result"],
            expires=now + APP_TTL_SECONDS,
            message_id=None,
        )
        return ref

    def bind_message(
        self, ref, username, session_id, run_id, checkpoint_id, call_id, message_id
    ):
        """Bind a reference once the authenticated chat run persists its message.

        Args:
            ref: Opaque capability from the tool-result event.
            username: Authenticated run owner.
            session_id: Conversation being persisted.
            run_id: Server-generated request identifier.
            checkpoint_id: Server-generated checkpoint identifier.
            call_id: Tool call stored in this message.
            message_id: Newly persisted assistant message identifier.
        """
        cap = self.entries.get(ref)
        if (
            cap
            and cap.message_id is None
            and (
                cap.username,
                cap.session_id,
                cap.run_id,
                cap.checkpoint_id,
                cap.call_id,
            )
            == (username, session_id, run_id, checkpoint_id, call_id)
        ):
            cap.message_id = str(message_id)

    def resolve(
        self, ref, username, session_id, origin, checkpoint_id, call_id, message_id
    ):
        """Validate a reference against its exact persisted invocation.

        Args:
            ref: Reference stored on the assistant tool-call part.
            username: Authenticated requester.
            session_id: Authorized conversation.
            origin: Conversation's canonical unified message origin.
            checkpoint_id: Checkpoint on the persisted message.
            call_id: Requested tool call.
            message_id: Requested assistant message.

        Returns:
            The original live invocation capability.

        Raises:
            ValueError: The capability is missing, expired, copied or unavailable.
        """
        cap = self.entries.get(ref) if isinstance(ref, str) else None
        if (
            not cap
            or cap.expires <= time.monotonic()
            or not cap.is_current()
            or (
                cap.username,
                cap.session_id,
                cap.origin,
                cap.checkpoint_id,
                cap.call_id,
                cap.message_id,
            )
            != (username, session_id, origin, checkpoint_id, call_id, str(message_id))
        ):
            raise ValueError("MCP App reference expired or is no longer available")
        return cap


mcp_apps = McpAppRegistry()
