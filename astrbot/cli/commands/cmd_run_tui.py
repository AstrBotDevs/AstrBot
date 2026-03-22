"""AstrBot Run TUI - A beautiful textual interface for running AstrBot.

This module provides a Textual-based TUI for `astrbot run` with:
- Animated ASCII logo
- Live log viewer
- Platform status indicators
- Only activates in interactive TTY environments
"""

from __future__ import annotations

import sys
import typing
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Log, Static

if typing.TYPE_CHECKING:
    from rich.console import Console
    from rich.style import Style
    from rich.text import Text
else:
    Console: Any = None
    Style: Any = None
    Text: Any = None


# AstrBot ASCII Logo
ASTRBOT_LOGO = r"""
     ___           _______.___________..______      .______     ______   .___________.
    /   \         /       |           ||   _  \     |   _  \   /  __  \  |           |
   /  ^  \       |   (----`---|  |----`|  |_)  |    |  |_)  | |  |  |  | `---|  |----`
  /  /_\  \       \   \       |  |     |      /     |   _  <  |  |  |  |     |  |
 /  _____  \  .----)   |      |  |     |  |\  \----.|  |_)  | |  `--'  |     |  |
/__/     \__\ |_______/       |__|     | _| `._____||______/   \______/      |__|
"""


class AstrBotRunTUI(App):
    """Textual TUI for AstrBot run command."""

    CSS = """
    Screen {
        background: $surface;
    }

    #logo-container {
        height: auto;
        padding: 1 2;
        background: $surface-darken-1;
        border: solid $primary;
    }

    #logo-text {
        color: $primary;
        text-style: bold;
        font-family: "JetBrains Mono", "Fira Code", monospace;
    }

    #main-container {
        height: 1fr;
    }

    #log-section {
        border: solid $accent;
        height: 70%;
        margin: 1 2;
    }

    #log-header {
        background: $accent-darken-1;
        padding: 1 2;
        color: $text;
        text-style: bold;
    }

    Log {
        background: $surface-darken-2;
        color: $text;
        border: solid $accent-darken-2;
    }

    #status-section {
        height: auto;
        padding: 1 2;
        background: $surface-darken-1;
        border-top: solid $primary;
    }

    .status-item {
        padding: 0 2;
    }

    .status-ok {
        color: $success;
        text-style: bold;
    }

    .status-pending {
        color: $warning;
    }

    .status-label {
        color: $text-muted;
    }

    .hidden {
        display: none;
    }
    """

    BINDINGS: typing.ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit", show=True),
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("l", "toggle_logs", "Toggle Logs", show=True),
    ]

    log_visible = reactive(True)

    def __init__(
        self,
        startup_coro: Callable[[], Awaitable[Any]],
        astrbot_root: Path,
        backend_only: bool = False,
        host: str | None = None,
        port: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.startup_coro = startup_coro
        self.astrbot_root = astrbot_root
        self.backend_only = backend_only
        self.host = host
        self.port = port
        self._animation_frame = 0
        self._startup_done = False
        self._log_lines: list[str] = []
        self.console: Any = Console() if Console else None

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()

        # Animated Logo
        with Container(id="logo-container"):
            yield Static(self._get_animated_logo(), id="logo-text")

        # Main content
        with Vertical(id="main-container"):
            # Log viewer
            with Container(
                id="log-section", classes="" if self.log_visible else "hidden"
            ):
                yield Static("📋 Live Logs", id="log-header")
                yield Log(id="log-viewer")

            # Status bar
            with Horizontal(id="status-section"):
                yield Static("🌟 AstrBot", classes="status-item status-ok")
                yield Static(
                    f"📁 {self.astrbot_root.name}",
                    classes="status-item",
                    id="root-status",
                )
                if not self.backend_only:
                    dashboard_url = (
                        f"http://{self.host or 'localhost'}:{self.port or '6185'}"
                    )
                    yield Static(
                        f"🌐 Dashboard: [link]{dashboard_url}[/link]",
                        classes="status-item",
                        id="dashboard-status",
                    )
                yield Static(
                    "⚡ Running", classes="status-item status-ok", id="run-status"
                )

        yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.title = "AstrBot"
        self.sub_title = "AI Chatbot Framework"

        # Start the startup coroutine
        self.set_timer(0.1, self._run_startup)

        # Animate logo
        self.set_interval(0.5, self._animate_logo)

        # Get the log widget and configure it
        log_widget = self.query_one("#log-viewer", Log)
        log_widget.write_line("🚀 AstrBot TUI initialized")
        log_widget.write_line(f"📁 Running from: {self.astrbot_root}")
        if not self.backend_only:
            log_widget.write_line(
                f"🌐 Dashboard will be available at: {self.host or 'localhost'}:{self.port or '6185'}"
            )
        log_widget.write_line("")

    def _get_animated_logo(self) -> str:
        """Get the logo with optional animation effect."""
        lines = ASTRBOT_LOGO.strip().split("\n")

        if self.console and hasattr(self, "_animation_frame"):
            # Create animated version with color cycling
            frame = self._animation_frame % 4
            colors = ["#00D9FF", "#00FF87", "#FFD700", "#FF6B6B"]
            color = colors[frame]

            text = Text()
            for i, line in enumerate(lines):
                style = Style(color=color, bold=True) if i == 0 else Style(color=color)
                text.append(line + "\n", style=style)
            return str(text)

        return ASTRBOT_LOGO

    def _animate_logo(self) -> None:
        """Update the animated logo."""
        self._animation_frame = (self._animation_frame + 1) % 4
        logo_widget = self.query_one("#logo-text", Static)
        logo_widget.update(self._get_animated_logo())

    async def _run_startup(self) -> None:
        """Run the AstrBot startup coroutine."""
        if self._startup_done:
            return
        self._startup_done = True

        try:
            log_widget = self.query_one("#log-viewer", Log)
            log_widget.write_line("⏳ Initializing AstrBot...")

            await self.startup_coro()

            log_widget.write_line("")
            log_widget.write_line("✅ AstrBot started successfully!")
        except Exception as e:
            log_widget = self.query_one("#log-viewer", Log)
            log_widget.write_line(f"❌ Error during startup: {e}")
            log_widget.write_line("Check logs for details.")

    def action_toggle_logs(self) -> None:
        """Toggle log visibility."""
        self.log_visible = not self.log_visible
        log_section = self.query_one("#log-section", Container)
        if self.log_visible:
            log_section.remove_class("hidden")
        else:
            log_section.add_class("hidden")

    async def action_quit(self) -> None:
        """Quit the application."""
        self.exit()

    def write_log(self, message: str) -> None:
        """Write a message to the log viewer (can be called from outside)."""
        log_widget = self.query_one("#log-viewer", Log)
        log_widget.write_line(message)


def is_interactive_tty() -> bool:
    """Check if we're running in an interactive TTY."""
    return sys.stdin.isatty() and sys.stdout.isatty()


async def run_tui(
    startup_coro: Callable[[], Awaitable[Any]],
    astrbot_root: Path,
    backend_only: bool = False,
    host: str | None = None,
    port: str | None = None,
) -> None:
    """Run the AstrBot TUI.

    Args:
        startup_coro: Coroutine to run on startup
        astrbot_root: AstrBot root directory
        backend_only: Whether backend-only mode is enabled
        host: Dashboard host
        port: Dashboard port
    """
    if not is_interactive_tty():
        # Not interactive, run without TUI
        await startup_coro()
        return

    app = AstrBotRunTUI(
        startup_coro=startup_coro,
        astrbot_root=astrbot_root,
        backend_only=backend_only,
        host=host,
        port=port,
    )

    try:
        await app.run_async()
    except Exception:
        # Fallback to non-TUI mode
        await startup_coro()
