import asyncio
import contextlib
import os
import signal
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click
from filelock import FileLock, Timeout

from ..utils import check_astrbot_root, check_dashboard, get_astrbot_root

ShutdownCallback = Callable[[signal.Signals], None]


def _install_shutdown_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    callback: ShutdownCallback,
) -> Callable[[], None]:
    """Install SIGINT/SIGTERM handlers and return a cleanup callback."""
    handled_signals = (signal.SIGINT, signal.SIGTERM)
    previous_handlers: dict[signal.Signals, Any] = {}
    installed: list[signal.Signals] = []

    for signum in handled_signals:
        try:
            previous_handlers[signum] = signal.getsignal(signum)
        except ValueError:
            previous_handlers[signum] = None
        try:
            loop.add_signal_handler(signum, callback, signum)
            installed.append(signum)
        except (NotImplementedError, RuntimeError, ValueError):

            def fallback_handler(received_signum, frame):
                _ = frame
                if not loop.is_closed():
                    try:
                        loop.call_soon_threadsafe(
                            callback, signal.Signals(received_signum)
                        )
                    except RuntimeError:
                        pass

            try:
                signal.signal(signum, fallback_handler)
                installed.append(signum)
            except ValueError:
                pass

    def cleanup() -> None:
        for signum in installed:
            try:
                loop.remove_signal_handler(signum)
            except (NotImplementedError, RuntimeError, ValueError):
                pass
            previous_handler = previous_handlers.get(signum)
            if previous_handler is not None:
                try:
                    signal.signal(signum, previous_handler)
                except (TypeError, ValueError):
                    pass

    return cleanup


async def run_astrbot(astrbot_root: Path) -> None:
    """Run AstrBot"""
    from astrbot.core import LogBroker, LogManager, db_helper, logger
    from astrbot.core.initial_loader import InitialLoader

    await check_dashboard(astrbot_root / "data")

    log_broker = LogBroker()
    LogManager.set_queue_handler(logger, log_broker)
    db = db_helper

    core_lifecycle = InitialLoader(db, log_broker)

    loop = asyncio.get_running_loop()
    shutdown_requested = asyncio.Event()
    shutdown_signal: signal.Signals | None = None

    def request_shutdown(signum: signal.Signals) -> None:
        nonlocal shutdown_signal
        shutdown_signal = signum
        shutdown_requested.set()

    cleanup_signal_handlers = _install_shutdown_signal_handlers(loop, request_shutdown)
    runner_task = asyncio.create_task(core_lifecycle.start(), name="astrbot")
    shutdown_task = asyncio.create_task(
        shutdown_requested.wait(), name="astrbot_shutdown"
    )

    try:
        done, _ = await asyncio.wait(
            {runner_task, shutdown_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        shutdown_requested_by_signal = shutdown_task in done
        if shutdown_requested_by_signal and not runner_task.done():
            signal_name = shutdown_signal.name if shutdown_signal else "unknown"
            logger.info(f"Received {signal_name}; stopping AstrBot...")
            runner_task.cancel()
        try:
            await runner_task
        except asyncio.CancelledError:
            if not shutdown_requested_by_signal:
                raise
    finally:
        cleanup_signal_handlers()
        if not runner_task.done():
            runner_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await runner_task
        if not shutdown_task.done():
            shutdown_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await shutdown_task


@click.option("--reload", "-r", is_flag=True, help="Auto-reload plugins")
@click.option("--port", "-p", help="AstrBot Dashboard port", required=False, type=str)
@click.command()
def run(reload: bool, port: str) -> None:
    """Run AstrBot"""
    try:
        os.environ["ASTRBOT_CLI"] = "1"
        astrbot_root = get_astrbot_root()

        if not check_astrbot_root(astrbot_root):
            raise click.ClickException(
                f"{astrbot_root} is not a valid AstrBot root directory. Use 'astrbot init' to initialize",
            )

        os.environ["ASTRBOT_ROOT"] = str(astrbot_root)
        sys.path.insert(0, str(astrbot_root))

        if port:
            os.environ["DASHBOARD_PORT"] = port

        if reload:
            click.echo("Plugin auto-reload enabled")
            os.environ["ASTRBOT_RELOAD"] = "1"

        lock_file = astrbot_root / "astrbot.lock"
        lock = FileLock(lock_file, timeout=5)
        with lock.acquire():
            asyncio.run(run_astrbot(astrbot_root))
    except KeyboardInterrupt:
        click.echo("AstrBot has been shut down.")
    except Timeout:
        raise click.ClickException(
            "Cannot acquire lock file. Please check if another instance is running"
        )
    except Exception as e:
        raise click.ClickException(f"Runtime error: {e}\n{traceback.format_exc()}")
