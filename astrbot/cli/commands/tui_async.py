"""Async TUI implementation that connects to a running AstrBot instance via HTTP API.

This module provides a terminal UI that connects to AstrBot via the dashboard API,
supporting streaming responses and all message types.
"""

from __future__ import annotations

import asyncio
import curses
import json
from dataclasses import dataclass, field
from enum import Enum

import httpx

from astrbot.tui.message_handler import (
    ChatResponse,
    MessageType,
    ParsedMessage,
    SSEMessageParser,
)
from astrbot.tui.screen import Screen


class MessageSender(Enum):
    USER = "user"
    BOT = "bot"
    SYSTEM = "system"
    TOOL = "tool"
    REASONING = "reasoning"


@dataclass
class Message:
    sender: MessageSender
    text: str
    timestamp: float | None = None


@dataclass
class TUIState:
    messages: list[Message] = field(default_factory=list)
    input_buffer: str = ""
    cursor_x: int = 0
    status: str = "Connecting..."
    running: bool = True
    connected: bool = False


class TUIClient:
    """TUI client that connects to AstrBot via HTTP API.

    Supports full streaming responses including:
    - Plain text (streaming)
    - Tool calls and results
    - Reasoning chains
    - Agent stats
    - Media (images, audio, files)
    """

    def __init__(
        self,
        screen: Screen,
        host: str,
        api_key: str | None,
        username: str,
        password: str,
        debug: bool = False,
    ):
        self.screen = screen
        self.state = TUIState()
        self._input_history: list[str] = []
        self._history_index: int = -1
        self._max_history: int = 100
        self._max_messages: int = 1000
        self._pending_tasks: list[asyncio.Task[None]] = []

        # Connection settings
        self.host = host.rstrip("/")
        self.api_key = api_key
        self.username = username
        self.password = password
        self.debug = debug

        # Session info
        self.session_id: str | None = None
        self.conversation_id: str | None = None

        # HTTP client
        self._client: httpx.AsyncClient | None = None
        self._headers: dict[str, str] = {}

        # SSE parser
        self._parser = SSEMessageParser()

    async def connect(self) -> bool:
        """Connect to AstrBot and authenticate."""
        self._client = httpx.AsyncClient(base_url=self.host, timeout=30.0)

        try:
            # Login or use API key
            if self.api_key:
                self._headers["Authorization"] = f"Bearer {self.api_key}"
            else:
                login_resp = await self._client.post(
                    "/api/auth/login",
                    json={"username": self.username, "password": self.password},
                )
                if login_resp.status_code != 200:
                    self.state.status = f"Login failed: {login_resp.status_code}"
                    return False
                data = login_resp.json()
                self._headers["Authorization"] = (
                    f"Bearer {data.get('access_token', '')}"
                )

            # Create new session for TUI
            new_session_resp = await self._client.get(
                "/api/tui/new_session",
                params={"platform_id": "tui"},
                headers=self._headers,
            )
            if new_session_resp.status_code != 200:
                self.state.status = (
                    f"Failed to create session: {new_session_resp.status_code}"
                )
                return False

            session_data = new_session_resp.json()
            if session_data.get("code") != 0:
                self.state.status = f"Session error: {session_data.get('msg')}"
                return False

            self.conversation_id = session_data.get("data", {}).get("session_id")
            if not self.conversation_id:
                self.state.status = "No session_id in response"
                return False

            self.session_id = self.conversation_id
            self.state.connected = True
            self.state.status = "Connected"
            return True

        except Exception as e:
            self.state.status = f"Connection error: {e}"
            if self.debug:
                import traceback

                traceback.print_exc()
            return False

    async def disconnect(self) -> None:
        """Disconnect from AstrBot."""
        if self._client:
            await self._client.aclose()
        self.state.connected = False

    async def load_history(self) -> None:
        """Load message history for the current session."""
        if not self._client or not self.conversation_id:
            return

        try:
            resp = await self._client.get(
                "/api/tui/get_session",
                params={"session_id": self.conversation_id},
                headers=self._headers,
            )
            if resp.status_code != 200:
                return

            data = resp.json()
            history = data.get("data", {}).get("history", [])

            for record in reversed(history):
                content = record.get("content", {})
                msg_type = content.get("type")
                message_parts = content.get("message", [])

                if msg_type == "user":
                    for part in message_parts:
                        if part.get("type") == "plain":
                            self.add_message(MessageSender.USER, part.get("text", ""))
                elif msg_type == "bot":
                    for part in message_parts:
                        if part.get("type") == "plain":
                            self.add_message(MessageSender.BOT, part.get("text", ""))

        except Exception:
            if self.debug:
                import traceback

                traceback.print_exc()

    def add_message(self, sender: MessageSender, text: str) -> None:
        """Add a message to the chat log."""
        if not text:
            return
        self.state.messages.append(Message(sender=sender, text=text))
        if len(self.state.messages) > self._max_messages:
            self.state.messages = self.state.messages[-self._max_messages :]

    def add_system_message(self, text: str) -> None:
        """Add a system message."""
        self.add_message(MessageSender.SYSTEM, text)

    def handle_key(self, key: int) -> bool:
        """Handle a keypress. Returns True if the application should continue running."""
        if key in (curses.KEY_EXIT, 27):  # ESC or ctrl-c
            return False

        if key == curses.KEY_RESIZE:
            self.screen.resize()
            return True

        # Handle arrow keys for navigation
        if key == curses.KEY_LEFT:
            if self.state.cursor_x > 0:
                self.state.cursor_x -= 1
        elif key == curses.KEY_RIGHT:
            if self.state.cursor_x < len(self.state.input_buffer):
                self.state.cursor_x += 1
        elif key == curses.KEY_HOME:
            self.state.cursor_x = 0
        elif key == curses.KEY_END:
            self.state.cursor_x = len(self.state.input_buffer)

        # Handle backspace
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if self.state.cursor_x > 0:
                self.state.input_buffer = (
                    self.state.input_buffer[: self.state.cursor_x - 1]
                    + self.state.input_buffer[self.state.cursor_x :]
                )
                self.state.cursor_x -= 1

        # Handle delete
        elif key == curses.KEY_DC:
            if self.state.cursor_x < len(self.state.input_buffer):
                self.state.input_buffer = (
                    self.state.input_buffer[: self.state.cursor_x]
                    + self.state.input_buffer[self.state.cursor_x + 1 :]
                )

        # Handle Enter/Return - submit message
        elif key in (curses.KEY_ENTER, 10, 13):
            if self.state.input_buffer.strip():
                task = asyncio.create_task(self._submit_message())
                self._pending_tasks.append(task)
            return True

        # Handle history navigation (up/down arrows)
        elif key == curses.KEY_UP:
            if (
                self._input_history
                and self._history_index < len(self._input_history) - 1
            ):
                self._history_index += 1
                self.state.input_buffer = self._input_history[self._history_index]
                self.state.cursor_x = len(self.state.input_buffer)
        elif key == curses.KEY_DOWN:
            if self._history_index > 0:
                self._history_index -= 1
                self.state.input_buffer = self._input_history[self._history_index]
                self.state.cursor_x = len(self.state.input_buffer)
            elif self._history_index == 0:
                self._history_index = -1
                self.state.input_buffer = ""
                self.state.cursor_x = 0

        # Regular character input
        elif 32 <= key <= 126:
            char = chr(key)
            self.state.input_buffer = (
                self.state.input_buffer[: self.state.cursor_x]
                + char
                + self.state.input_buffer[self.state.cursor_x :]
            )
            self.state.cursor_x += 1

        # Clear input with Ctrl+L
        elif key == 12:  # Ctrl+L
            self.state.input_buffer = ""
            self.state.cursor_x = 0

        return True

    async def _submit_message(self) -> None:
        """Submit the current input buffer as a user message."""
        text = self.state.input_buffer.strip()
        if not text:
            return

        # Add to history
        self._input_history.insert(0, text)
        if len(self._input_history) > self._max_history:
            self._input_history = self._input_history[: self._max_history]
        self._history_index = -1

        # Add user message to chat
        self.add_message(MessageSender.USER, text)

        # Clear input
        self.state.input_buffer = ""
        self.state.cursor_x = 0

        # Process the message via API
        await self._process_user_message(text)

    async def _process_user_message(self, text: str) -> None:
        """Send message to AstrBot and process the streaming response."""
        if not self.conversation_id or not self._client:
            self.add_system_message("Not connected to AstrBot")
            return

        self.state.status = "Waiting for response..."

        try:
            # Format umo for tui
            umo = (
                f"tui:FriendMessage:tui!{self.username}!{self.conversation_id}"
            )

            # Reset parser for new stream
            self._parser.reset()

            # Send message and stream response using proper SSE
            async with self._client.stream(
                "POST",
                "/api/tui/chat",
                headers=self._headers,
                json={
                    "umo": umo,
                    "message": text,
                    "session_id": self.conversation_id,
                    "streaming": True,
                },
                timeout=None,
            ) as response:
                if response.status_code != 200:
                    self._update_last_bot_message(f"Error: HTTP {response.status_code}")
                    self.state.status = "Error"
                    return

                # Process streaming SSE
                async for line in response.aiter_lines():
                    parsed = self._parser.parse_line(line)
                    if parsed is None:
                        continue

                    update, is_complete = self._process_parsed_message(parsed)

                    # Update display based on message type
                    if parsed.type == MessageType.TOOL_CALL:
                        tool_call = json.loads(parsed.data)
                        self.add_message(
                            MessageSender.TOOL,
                            f"[Tool: {tool_call.get('name', 'unknown')}]",
                        )
                        self.state.status = "Running tool..."
                    elif parsed.type == MessageType.TOOL_CALL_RESULT:
                        try:
                            tcr = json.loads(parsed.data)
                            self.add_message(
                                MessageSender.TOOL,
                                f"[Result] {tcr.get('result', '')[:100]}...",
                            )
                        except json.JSONDecodeError:
                            pass
                    elif parsed.type == MessageType.REASONING:
                        self._update_last_bot_message(
                            f"[Thinking] {update.reasoning[-200:]}"
                        )
                        self.state.status = "Thinking..."
                    elif parsed.type == MessageType.AGENT_STATS:
                        self.state.status = (
                            f"Tokens: {update.agent_stats.get('total_tokens', 0)}"
                        )
                    elif update.text:
                        self._update_last_bot_message(update.text)

                    if is_complete:
                        break

            # Final status
            if update.reasoning:
                self.add_message(
                    MessageSender.REASONING, f"[Reasoning]\n{update.reasoning}"
                )

            for tool_display in update.get_tool_calls_display():
                self.add_message(MessageSender.TOOL, tool_display)

            if update.error:
                self.add_message(MessageSender.SYSTEM, f"Error: {update.error}")

            self.state.status = "Ready"

        except asyncio.CancelledError:
            self.state.status = "Cancelled"
        except Exception as e:
            self.add_system_message(f"Error: {e}")
            self.state.status = f"Error: {e}"
            if self.debug:
                import traceback

                traceback.print_exc()

    def _process_parsed_message(self, msg: ParsedMessage) -> tuple[ChatResponse, bool]:
        """Process a parsed message and return updated response state."""
        return self._parser.process_message(msg)

    def _update_last_bot_message(self, text: str) -> None:
        """Update the last bot message with new text (for streaming)."""
        for i in range(len(self.state.messages) - 1, -1, -1):
            if self.state.messages[i].sender == MessageSender.BOT:
                self.state.messages[i] = Message(
                    sender=MessageSender.BOT,
                    text=text,
                    timestamp=self.state.messages[i].timestamp,
                )
                break
        else:
            self.add_message(MessageSender.BOT, text)

    def render(self) -> None:
        """Render the current state to the screen."""
        lines = [(msg.sender.value, msg.text) for msg in self.state.messages]

        self.screen.draw_all(
            lines=lines,
            input_text=self.state.input_buffer,
            cursor_x=self.state.cursor_x,
            status=self.state.status,
        )

    async def run_event_loop(self, stdscr: curses.window) -> None:
        """Main event loop for the TUI."""
        # Setup
        self.screen.setup_colors()
        self.screen.layout_windows()

        # Connect to AstrBot
        connected = await self.connect()
        if not connected:
            self.add_system_message(f"Failed to connect: {self.state.status}")
        else:
            self.add_system_message("Connected to AstrBot!")
            # Load history
            await self.load_history()

        # Welcome message
        self.add_system_message("Type your message and press Enter to send.")
        self.add_system_message("Press ESC or Ctrl+C to exit.")

        # Initial render
        self.render()

        # Input loop
        while self.state.running:
            # Get input with timeout
            self.screen.input_win.nodelay(True)
            try:
                key = self.screen.input_win.getch()
            except curses.error:
                key = -1

            if key != -1:
                if not self.handle_key(key):
                    self.state.running = False
                    break
                self.render()

            # Small sleep to prevent CPU hogging
            await asyncio.sleep(0.01)

        # Cleanup
        await self.disconnect()


def run_tui_async(
    debug: bool = False,
    host: str = "http://localhost:6185",
    api_key: str | None = None,
    username: str = "astrbot",
    password: str = "astrbot",
) -> None:
    """Entry point to run the TUI application."""
    from astrbot.tui.screen import run_curses

    def main(stdscr: curses.window) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        scr = Screen(stdscr)
        client = TUIClient(
            screen=scr,
            host=host,
            api_key=api_key,
            username=username,
            password=password,
            debug=debug,
        )
        try:
            loop.run_until_complete(client.run_event_loop(stdscr))
        finally:
            loop.close()

    run_curses(main)


if __name__ == "__main__":
    run_tui_async()
