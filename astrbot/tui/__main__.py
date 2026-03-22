"""AstrBot TUI - Entry point for python -m astrbot.tui"""

import asyncio
import sys


def main(stdscr):
    """Main TUI entry point when running via python -m astrbot.tui."""
    try:
        from astrbot.cli.commands.tui_async import TUIClient
        from astrbot.tui.screen import Screen

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        scr = Screen(stdscr)
        client = TUIClient(
            screen=scr,
            host="http://localhost:6185",
            api_key=None,
            username="astrbot",
            password="astrbot",
            debug=False,
        )
        try:
            loop.run_until_complete(client.run_event_loop(stdscr))
        finally:
            loop.close()
    except ImportError as e:
        import curses

        curses.curs_set(1)
        stdscr.clear()
        stdscr.addstr(0, 0, f"Error importing TUI module: {e}", curses.A_BOLD)
        stdscr.addstr(2, 0, "Press any key to exit...")
        stdscr.refresh()
        stdscr.getch()
        sys.exit(1)


if __name__ == "__main__":
    from astrbot.tui.screen import run_curses

    run_curses(main)
