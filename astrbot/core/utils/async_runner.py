"""Async runner utility with uvloop support."""

import asyncio
import sys

# Import uvloop on Linux
if sys.platform == "linux":
    try:
        import uvloop
    except ImportError:
        uvloop = None
else:
    uvloop = None


def run_async(coro):
    """Run async coroutine with uvloop on Linux if Python >= 3.11.

    This function creates a new event loop for each coroutine execution,
    which is the recommended pattern for standalone async operations.
    For long-running applications with continuous async operations,
    consider using uvloop.install() instead.

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine
    """
    if uvloop is not None and sys.version_info >= (3, 11):
        # Use asyncio.Runner with uvloop for Python 3.11+
        with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
            return runner.run(coro)
    else:
        # Fall back to standard asyncio.run for older Python or non-Linux
        return asyncio.run(coro)
