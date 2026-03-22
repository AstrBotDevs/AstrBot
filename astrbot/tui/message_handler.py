"""Shared SSE message handler for AstrBot clients (WebChat, TUI, etc).

This module provides a unified way to parse and handle SSE messages from the
AstrBot chat API, supporting all message types including streaming responses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageType(Enum):
    """SSE message types from AstrBot API."""

    SESSION_ID = "session_id"
    PLAIN = "plain"
    IMAGE = "image"
    RECORD = "record"
    FILE = "file"
    TOOL_CALL = "tool_call"
    TOOL_CALL_RESULT = "tool_call_result"
    REASONING = "reasoning"
    AGENT_STATS = "agent_stats"
    AUDIO_CHUNK = "audio_chunk"
    COMPLETE = "complete"
    END = "end"
    MESSAGE_SAVED = "message_saved"
    ERROR = "error"


@dataclass
class ToolCall:
    """Represents a tool call in progress."""

    id: str
    name: str
    arguments: str | None = None
    result: str | None = None
    finished_ts: float | None = None


@dataclass
class ParsedMessage:
    """A parsed SSE message with type and data."""

    type: MessageType
    data: str
    raw: dict[str, Any] = field(default_factory=dict)
    chain_type: str | None = None
    streaming: bool = False
    message_id: str | None = None


@dataclass
class ChatResponse:
    """Complete chat response accumulated from SSE stream."""

    text: str = ""
    reasoning: str = ""
    tool_calls: dict[str, ToolCall] = field(default_factory=dict)
    agent_stats: dict[str, Any] = field(default_factory=dict)
    refs: dict[str, Any] = field(default_factory=dict)
    media_parts: list[dict[str, Any]] = field(default_factory=list)
    complete: bool = False
    session_id: str | None = None
    saved_message_id: str | None = None
    error: str | None = None

    def get_display_text(self) -> str:
        """Get the main text content for display."""
        return self.text

    def get_reasoning_display(self) -> str:
        """Get reasoning content formatted for display."""
        if not self.reasoning:
            return ""
        return f"[Reasoning]\n{self.reasoning}"

    def get_tool_calls_display(self) -> list[str]:
        """Get tool calls formatted for display."""
        results = []
        for tc in self.tool_calls.values():
            if tc.result:
                results.append(f"[Tool: {tc.name}]\n{tc.result}")
            else:
                results.append(f"[Tool: {tc.name}] (running...)")
        return results

    def get_stats_display(self) -> str:
        """Get agent stats formatted for display."""
        if not self.agent_stats:
            return ""
        parts = []
        for key, value in self.agent_stats.items():
            parts.append(f"{key}: {value}")
        return " | ".join(parts)


class SSEMessageParser:
    """Parse SSE messages from AstrBot chat API.

    Usage:
        parser = SSEMessageParser()
        async for msg in parser.parse_stream(response):
            handle_message(msg)
    """

    def __init__(self) -> None:
        self._tool_calls: dict[str, ToolCall] = {}
        self._accumulated_text: str = ""
        self._accumulated_reasoning: str = ""
        self._accumulated_parts: list[dict[str, Any]] = []

    def reset(self) -> None:
        """Reset parser state for a new stream."""
        self._tool_calls = {}
        self._accumulated_text = ""
        self._accumulated_reasoning = ""
        self._accumulated_parts = []

    def parse_line(self, line: str) -> ParsedMessage | None:
        """Parse a single SSE data line.

        Args:
            line: A line starting with "data: "

        Returns:
            ParsedMessage if valid, None if skip-worthy
        """
        if not line.startswith("data: "):
            return None

        data_str = line[6:]  # Remove "data: " prefix
        if not data_str:
            return None

        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            return None

        msg_type_str = data.get("type", "")
        msg_type = self._get_message_type(msg_type_str)
        msg_data = data.get("data", "")
        chain_type = data.get("chain_type")
        streaming = data.get("streaming", False)
        message_id = data.get("message_id")

        return ParsedMessage(
            type=msg_type,
            data=msg_data,
            raw=data,
            chain_type=chain_type,
            streaming=streaming,
            message_id=message_id,
        )

    def _get_message_type(self, type_str: str) -> MessageType:
        """Map string type to MessageType enum."""
        try:
            return MessageType(type_str)
        except ValueError:
            return MessageType.PLAIN

    def process_message(self, msg: ParsedMessage) -> tuple[ChatResponse, bool]:
        """Process a parsed message and update accumulated response.

        Args:
            msg: The parsed message

        Returns:
            tuple of (accumulated_response, is_complete)
        """
        response = ChatResponse()

        if msg.type == MessageType.SESSION_ID:
            response.session_id = msg.raw.get("session_id")
            return response, False

        if msg.type == MessageType.AGENT_STATS:
            try:
                response.agent_stats = json.loads(msg.data)
            except json.JSONDecodeError:
                pass
            return response, False

        if msg.type == MessageType.REASONING:
            self._accumulated_reasoning += msg.data
            response.reasoning = self._accumulated_reasoning
            return response, False

        if msg.type == MessageType.TOOL_CALL:
            try:
                tool_call = json.loads(msg.data)
                tc = ToolCall(
                    id=tool_call.get("id", ""),
                    name=tool_call.get("name", ""),
                    arguments=tool_call.get("arguments"),
                )
                self._tool_calls[tc.id] = tc
                self._accumulated_parts.append(
                    {"type": "plain", "text": self._accumulated_text}
                )
                self._accumulated_text = ""
            except json.JSONDecodeError:
                pass
            response.tool_calls = self._tool_calls
            return response, False

        if msg.type == MessageType.TOOL_CALL_RESULT:
            try:
                tcr = json.loads(msg.data)
                tc_id = tcr.get("id")
                if tc_id in self._tool_calls:
                    self._tool_calls[tc_id].result = tcr.get("result")
                    self._tool_calls[tc_id].finished_ts = tcr.get("ts")
                    self._accumulated_parts.append(
                        {
                            "type": "tool_call",
                            "tool_calls": [self._tool_calls[tc_id].__dict__],
                        }
                    )
                    self._tool_calls.pop(tc_id, None)
            except json.JSONDecodeError:
                pass
            response.tool_calls = self._tool_calls
            return response, False

        if msg.type == MessageType.PLAIN:
            if msg.chain_type == "tool_call":
                pass  # Already handled above
            elif msg.chain_type == "reasoning":
                self._accumulated_reasoning += msg.data
                response.reasoning = self._accumulated_reasoning
            elif msg.streaming:
                self._accumulated_text += msg.data
            else:
                self._accumulated_text = msg.data
            response.text = self._accumulated_text
            return response, False

        if msg.type == MessageType.IMAGE:
            filename = msg.data.replace("[IMAGE]", "")
            self._accumulated_parts.append({"type": "image", "filename": filename})
            response.media_parts = self._accumulated_parts
            return response, False

        if msg.type == MessageType.RECORD:
            filename = msg.data.replace("[RECORD]", "")
            self._accumulated_parts.append({"type": "record", "filename": filename})
            response.media_parts = self._accumulated_parts
            return response, False

        if msg.type == MessageType.FILE:
            filename = msg.data.replace("[FILE]", "")
            self._accumulated_parts.append({"type": "file", "filename": filename})
            response.media_parts = self._accumulated_parts
            return response, False

        if msg.type == MessageType.COMPLETE:
            response.text = self._accumulated_text
            response.reasoning = self._accumulated_reasoning
            response.tool_calls = self._tool_calls
            response.complete = True
            self.reset()
            return response, True

        if msg.type == MessageType.END:
            response.text = self._accumulated_text
            response.complete = True
            self.reset()
            return response, True

        if msg.type == MessageType.MESSAGE_SAVED:
            response.saved_message_id = msg.raw.get("data", {}).get("id")
            return response, False

        return response, False


async def parse_sse_stream(async_iterable, callback) -> ChatResponse:
    """Parse SSE stream and call callback for each message update.

    This is a convenience function for processing SSE streams.

    Args:
        async_iterable: Async iterable of SSE lines (e.g., response.aiter_lines())
        callback: Async function called with (ChatResponse, is_complete)

    Returns:
        Final ChatResponse when stream completes
    """
    parser = SSEMessageParser()
    final_response = ChatResponse()

    async for line in async_iterable:
        msg = parser.parse_line(line)
        if msg is None:
            continue

        response, is_complete = parser.process_message(msg)
        await callback(response, is_complete)
        final_response = response

        if is_complete:
            break

    return final_response
