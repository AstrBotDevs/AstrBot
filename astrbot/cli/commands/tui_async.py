"""Async TUI implementation that connects to a running AstrBot instance via HTTP API."""

from __future__ import annotations

import asyncio
import curses
import json
from dataclasses import dataclass, field
from enum import Enum

import httpx

from astrbot.tui.screen import Screen


class MessageSender(Enum):
    USER = "user"
    BOT = "bot"
    SYSTEM = "system"


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
    """TUI client that connects to AstrBot via HTTP API."""

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

        # Connection settings
        self.host = host.rstrip("/")
        self.api_key = api_key
        self.username = username
        self.password = password
        self.debug = debug

        # Session info
        self.session_id: str | None = None

        # HTTP client
        self._client: httpx.AsyncClient | None = None
        self._headers: dict[str, str] = {}

        # Pending tasks
        self._pending_tasks: list[asyncio.Task] = []

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
                "/api/chat/new_session",
                params={"platform_id": "webchat"},
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

            self.session_id = session_data.get("data", {}).get("session_id")
            if not self.session_id:
                self.state.status = "No session_id in response"
                return False

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

    def add_message(self, sender: MessageSender, text: str) -> None:
        """Add a message to the chat log."""
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
        """Send message to AstrBot and process the response."""
        if not self.session_id or not self._client:
            self.add_system_message("Not connected to AstrBot")
            return

        self.state.status = "Waiting for response..."

        try:
            # Format umo for webchat
            umo = f"webchat:FriendMessage:webchat!{self.username}!{self.session_id}"

            # Send message and stream response
            async with self._client.stream(
                "POST",
                "/api/chat/chat",
                headers=self._headers,
                json={
                    "umo": umo,
                    "message": text,
                    "streaming": True,
                },
                timeout=None,
            ) as response:
                if response.status_code != 200:
                    self.add_system_message(f"Error: HTTP {response.status_code}")
                    self.state.status = "Error"
                    return

                # Process streaming response
                accumulated_text = ""

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    data_str = line[6:]  # Remove "data: " prefix
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    msg_type = data.get("type")
                    msg_data = data.get("data", "")

                    if msg_type == "plain":
                        accumulated_text += msg_data
                        self._update_last_bot_message(accumulated_text)
                    elif msg_type == "image":
                        self._update_last_bot_message(f"[Image: {msg_data}]")
                    elif msg_type == "record":
                        self._update_last_bot_message(f"[Audio: {msg_data}]")
                    elif msg_type == "file":
                        self._update_last_bot_message(f"[File: {msg_data}]")
                    elif msg_type in ("complete", "end"):
                        break

                self.state.status = "Ready"

        except asyncio.CancelledError:
            self.state.status = "Cancelled"
        except Exception as e:
            self.add_system_message(f"Error: {e}")
            self.state.status = f"Error: {e}"
            if self.debug:
                import traceback

                traceback.print_exc()

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


def _run_tui_curses(
    screen: curses.window,
    host: str,
    api_key: str | None,
    username: str,
    password: str,
    debug: bool,
) -> None:
    """Curses wrapper for the async TUI."""
    screen.clear()
    screen.refresh()

    scr = Screen(screen)
    client = TUIClient(
        screen=scr,
        host=host,
        api_key=api_key,
        username=username,
        password=password,
        debug=debug,
    )

    # Create a new event loop for this thread since curses runs in its own thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(client.run_event_loop(screen))
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


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
