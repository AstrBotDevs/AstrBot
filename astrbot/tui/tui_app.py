"""AstrBot TUI Application - Main chat interface (sync version for testing).

This module provides a basic TUI application without network connectivity,
useful for testing the UI components and as a reference implementation.
"""

from __future__ import annotations

import curses
from dataclasses import dataclass, field
from enum import Enum

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
    status: str = "Ready"
    running: bool = True
    connected: bool = False


class AstrBotTUI:
    """Main TUI application for AstrBot (local/testing version)."""

    def __init__(self, screen: Screen):
        self.screen = screen
        self.state = TUIState()
        self._input_history: list[str] = []
        self._history_index: int = -1
        self._max_history: int = 100

    def add_message(self, sender: MessageSender, text: str) -> None:
        """Add a message to the chat log."""
        self.state.messages.append(Message(sender=sender, text=text))
        if len(self.state.messages) > 1000:
            self.state.messages = self.state.messages[-1000:]

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
                self._submit_message()
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

    def _submit_message(self) -> None:
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

        # Process the message (echo back for testing)
        self._process_user_message(text)

    def _process_user_message(self, text: str) -> None:
        """Process user message and generate bot response (echo for testing)."""
        self.add_message(MessageSender.BOT, f"Echo: {text}")

    def render(self) -> None:
        """Render the current state to the screen."""
        lines = [(msg.sender.value, msg.text) for msg in self.state.messages]

        self.screen.draw_all(
            lines=lines,
            input_text=self.state.input_buffer,
            cursor_x=self.state.cursor_x,
            status=self.state.status,
        )

    def run_event_loop(self, stdscr: curses.window) -> None:
        """Main event loop for the TUI."""
        # Setup
        self.screen.setup_colors()
        self.screen.layout_windows()

        # Welcome message
        self.add_system_message("Welcome to AstrBot TUI (local mode)!")
        self.add_system_message("Type your message and press Enter to send.")
        self.add_system_message("Press ESC or Ctrl+C to exit.")

        # Initial render
        self.render()

        # Main event loop
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
            curses.napms(10)


def run_tui(stdscr: curses.window) -> None:
    """Entry point to run the TUI application."""
    screen = Screen(stdscr)
    app = AstrBotTUI(screen)
    app.run_event_loop(stdscr)
