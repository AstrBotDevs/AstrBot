"""Curses screen management for AstrBot TUI - Modern Design."""

from __future__ import annotations

import curses
from collections.abc import Callable
from enum import Enum


class ColorPair(Enum):
    # Basic colors
    WHITE = 1
    CYAN = 2
    GREEN = 3
    YELLOW = 4
    RED = 5
    MAGENTA = 6
    DIM = 7
    BOLD = 8
    # Extended colors for new design
    HEADER_BG = 9
    HEADER_FG = 10
    USER_MSG = 11
    BOT_MSG = 12
    SYSTEM_MSG = 13
    INPUT_BG = 14
    STATUS_BG = 15
    BORDER = 16


_COLOR_MAP = {
    ColorPair.WHITE: curses.COLOR_WHITE,
    ColorPair.CYAN: curses.COLOR_CYAN,
    ColorPair.GREEN: curses.COLOR_GREEN,
    ColorPair.YELLOW: curses.COLOR_YELLOW,
    ColorPair.RED: curses.COLOR_RED,
    ColorPair.MAGENTA: curses.COLOR_MAGENTA,
    ColorPair.DIM: curses.COLOR_WHITE,
    ColorPair.HEADER_BG: curses.COLOR_BLUE,
    ColorPair.HEADER_FG: curses.COLOR_WHITE,
    ColorPair.USER_MSG: curses.COLOR_GREEN,
    ColorPair.BOT_MSG: curses.COLOR_CYAN,
    ColorPair.SYSTEM_MSG: curses.COLOR_YELLOW,
    ColorPair.INPUT_BG: curses.COLOR_BLACK,
    ColorPair.STATUS_BG: curses.COLOR_BLUE,
    ColorPair.BORDER: curses.COLOR_CYAN,
}


# Box drawing characters
BOX_VERT = "│"
BOX_HORIZ = "─"
BOX_TL = "┌"
BOX_TR = "┐"
BOX_BL = "└"
BOX_BR = "┘"
BOX_LT = "├"
BOX_RT = "┤"
BOX_BT = "┴"
BOX_TT = "┬"
BOX_CROSS = "┼"

# Header and footer characters
HEADER_PREFIX = "╭"
HEADER_CONTENT = "┤"
HEADER_SUFFIX = "├"
FOOTER_PREFIX = "├"
FOOTER_CONTENT = "┤"
FOOTER_SUFFIX = "┴"


class Screen:
    """Main curses screen manager with modern design."""

    def __init__(self, stdscr: curses.window):
        self.stdscr = stdscr
        self.height, self.width = stdscr.getmaxyx()
        self._header_height = 1
        self._footer_height = 1
        self._chat_height = self.height - self._header_height - self._footer_height - 3
        self._input_height = 3
        self._header_win: curses.window | None = None
        self._chat_win: curses.window | None = None
        self._footer_win: curses.window | None = None
        self._input_win: curses.window | None = None
        self._running = False
        self._color_pairs: dict[int, int] = {}

    def setup_colors(self) -> None:
        curses.start_color()
        curses.use_default_colors()
        curses.curs_set(1)
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(True)

        # Initialize all color pairs
        for i, (name, fg) in enumerate(_COLOR_MAP.items(), start=1):
            if name in (ColorPair.HEADER_BG, ColorPair.INPUT_BG, ColorPair.STATUS_BG):
                curses.init_pair(i, fg, curses.COLOR_BLACK)
            elif name == ColorPair.DIM:
                curses.init_pair(i, fg, curses.COLOR_BLACK)
                self._color_pairs[name.value] = curses.color_pair(i) | curses.A_DIM
            elif name == ColorPair.BOLD:
                curses.init_pair(i, curses.COLOR_WHITE, curses.COLOR_BLACK)
                self._color_pairs[name.value] = curses.color_pair(i) | curses.A_BOLD
            else:
                curses.init_pair(i, fg, curses.COLOR_BLACK)
                self._color_pairs[name.value] = curses.color_pair(i)

    def get_color(self, pair: ColorPair) -> int:
        """Get curses attribute for a color pair."""
        return self._color_pairs.get(pair.value, curses.color_pair(pair.value))

    def layout_windows(self) -> None:
        """Create the window layout with modern design."""
        self.height, self.width = self.stdscr.getmaxyx()
        self._chat_height = max(
            1,
            self.height
            - self._header_height
            - self._footer_height
            - self._input_height
            - 2,
        )

        # Header window (top bar with branding)
        self._header_win = curses.newwin(self._header_height, self.width, 0, 0)
        self._header_win.nodelay(True)

        # Chat window (middle area)
        self._chat_win = curses.newwin(
            self._chat_height, self.width, self._header_height + 1, 0
        )
        # Disable auto-scroll so text stays visible for copy/mouse selection
        self._chat_win.scrollok(False)
        self._chat_win.idlok(True)
        self._chat_win.leaveok(False)
        # Enable mouse wheel support (KEY_MOUSE reports scroll events)
        self._chat_win.keypad(True)

        # Footer window (separator above status)
        self._footer_win = curses.newwin(
            self._footer_height,
            self.width,
            self._header_height + 1 + self._chat_height,
            0,
        )
        self._footer_win.nodelay(True)

        # Input window (bottom)
        self._input_win = curses.newwin(
            self._input_height, self.width, self.height - self._input_height, 0
        )
        self._input_win.keypad(True)
        self._input_win.timeout(100)

        self._running = True

    @property
    def chat_win(self):
        return self._chat_win

    @property
    def input_win(self):
        return self._input_win

    @property
    def footer_win(self):
        return self._footer_win

    @property
    def header_win(self):
        return self._header_win

    def draw_border_line(self) -> None:
        """Draw the border/divider line in the footer window."""
        if not self._footer_win:
            return
        self._footer_win.clear()
        if self.width >= 4:
            line = BOX_TL + BOX_HORIZ * (self.width - 2) + BOX_TR
            try:
                self._footer_win.addstr(0, 0, line, self.get_color(ColorPair.BORDER))
            except curses.error:
                pass
        self._footer_win.refresh()

    def draw_header(self) -> None:
        """Draw the header bar with AstrBot branding."""
        if not self._header_win:
            return
        self._header_win.clear()

        # Create header content
        title = " AstrBot TUI "

        try:
            # Draw background with color
            self._header_win.bkgdset(curses.color_pair(ColorPair.HEADER_FG.value))
            self._header_win.erase()

            # Draw title with bold
            title_attr = curses.color_pair(ColorPair.HEADER_FG.value) | curses.A_BOLD
            self._header_win.addstr(0, 0, title, title_attr)

            # Draw decorative border continuation
            if self.width > len(title) + 2:
                border_attr = self.get_color(ColorPair.HEADER_FG)
                remaining = self.width - len(title)
                self._header_win.addstr(
                    0, len(title), BOX_HORIZ * remaining, border_attr
                )

        except curses.error:
            pass
        self._header_win.refresh()

    def draw_chat_log(self, lines: list[tuple[str, str]]) -> None:
        """Draw the chat log window with styled message bubbles.

        Args:
            lines: List of tuples (sender_type, text) where sender_type is
                   'user', 'bot', or 'system'
        """
        if not self._chat_win:
            return
        self._chat_win.clear()

        y = 0
        max_y = self._chat_height - 1

        # Only show last N lines that fit
        visible_lines = lines[-max_y:] if len(lines) > max_y else lines

        for sender, text in visible_lines:
            if y >= self._chat_height:
                break

            # Select color based on sender
            if sender == "user":
                indicator = ">"
                color = self.get_color(ColorPair.USER_MSG)
            elif sender == "bot":
                indicator = "✦"
                color = self.get_color(ColorPair.BOT_MSG)
            else:  # system
                indicator = "●"
                color = self.get_color(ColorPair.SYSTEM_MSG)

            # Truncate text to fit width
            max_text_width = self.width - 4  # Account for indicator and spacing
            if max_text_width < 1:
                continue

            # Word wrap text
            words = text.split()
            current_line = ""
            lines_buffer = []

            for word in words:
                test_line = current_line + (" " if current_line else "") + word
                if len(test_line) <= max_text_width:
                    current_line = test_line
                else:
                    if current_line:
                        lines_buffer.append(current_line)
                    current_line = word

            if current_line:
                lines_buffer.append(current_line)

            # Draw each line of the message
            for i, line_text in enumerate(lines_buffer):
                if y >= self._chat_height:
                    break
                try:
                    if i == 0:
                        self._chat_win.addstr(
                            y, 0, f"{indicator} ", color | curses.A_BOLD
                        )
                        self._chat_win.addstr(y, 2, line_text, color)
                    else:
                        # Continuation lines - indent
                        self._chat_win.addstr(y, 0, "  ", color)
                        self._chat_win.addstr(y, 2, line_text, color)
                except curses.error:
                    pass
                y += 1

        self._chat_win.clrtobot()
        self._chat_win.refresh()

    def draw_input(self, text: str, cursor_x: int) -> None:
        """Draw the input area with modern styling."""
        if not self._input_win:
            return
        self._input_win.clear()

        # Draw input box with border
        prompt = "> "
        prompt_len = 2
        max_input_width = self.width - 2

        try:
            # Draw prompt
            self._input_win.addstr(
                0, 0, prompt, curses.color_pair(ColorPair.GREEN.value) | curses.A_BOLD
            )

            # Draw text content
            display_text = text[: max_input_width - prompt_len]
            self._input_win.addstr(
                0, prompt_len, display_text, curses.color_pair(ColorPair.WHITE.value)
            )

            # Draw cursor
            cursor_pos = min(cursor_x + prompt_len, self.width - 1)
            self._input_win.chgat(0, cursor_pos, 1, curses.A_REVERSE)

        except curses.error:
            pass

        self._input_win.clrtobot()
        self._input_win.refresh()

    def draw_status(self, status: str) -> None:
        """Draw the status bar at the bottom."""
        if not self._footer_win:
            return

        self._footer_win.clear()

        # Status bar at the very bottom
        status_y = self.height - 1

        # Truncate status text
        status_text = status[: self.width - 2]

        try:
            # Use the main stdscr for bottom status
            attr = curses.color_pair(ColorPair.HEADER_FG.value) | curses.A_BOLD
            self.stdscr.addstr(status_y, 0, " " + status_text, attr)

            # Fill remainder of line
            remaining = self.width - len(status_text) - 1
            if remaining > 0:
                self.stdscr.addstr(
                    status_y, len(status_text) + 1, " " * remaining, attr
                )

            self.stdscr.chgat(status_y, 0, self.width, attr)
        except curses.error:
            pass
        self.stdscr.refresh()

    def draw_all(
        self, lines: list[tuple[str, str]], input_text: str, cursor_x: int, status: str
    ) -> None:
        """Redraw all windows."""
        self.draw_header()
        self.draw_border_line()
        self.draw_chat_log(lines)
        self.draw_input(input_text, cursor_x)
        self.draw_status(status)

    def resize(self) -> bool:
        """Handle resize event. Returns True if resized."""
        self.height, self.width = self.stdscr.getmaxyx()
        if self._chat_win:
            self._chat_win.clear()
        self.layout_windows()
        return True

    def clear_status(self) -> None:
        """Clear the status line at bottom."""
        try:
            attr = curses.color_pair(ColorPair.HEADER_FG.value) | curses.A_BOLD
            self.stdscr.addstr(self.height - 1, 0, " " * self.width, attr)
            self.stdscr.refresh()
        except curses.error:
            pass


def run_curses(main_loop: Callable[[curses.window], None]):
    """Entry point for curses wrapper."""

    def _main(stdscr: curses.window):
        main_loop(stdscr)

    curses.wrapper(_main)
