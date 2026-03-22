"""AstrBot TUI - Entry point for python -m astrbot.tui"""

from astrbot.tui.screen import run_curses


def main(stdscr):
    """Main TUI loop - placeholder for future TUI implementation."""
    # For now, just display a message
    import curses

    curses.start_color()
    curses.curs_set(1)
    stdscr.clear()
    stdscr.addstr(0, 0, "AstrBot TUI - Coming soon!", curses.A_BOLD)
    stdscr.addstr(2, 0, "Press any key to exit...")
    stdscr.refresh()
    stdscr.getch()


if __name__ == "__main__":
    run_curses(main)
