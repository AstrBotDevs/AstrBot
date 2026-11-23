"""Typed Windows extension boundaries that remain inspectable on other hosts."""

from __future__ import annotations

import asyncio
import ctypes
import os
from typing import Protocol, cast, runtime_checkable


class WindowsCtypes(Protocol):
    """The Windows-only ctypes API, with CDLL's native function prototypes."""

    def WinDLL(self, name: str, *, use_last_error: bool = False) -> ctypes.CDLL: ...

    def WinError(self, code: int | None = None) -> OSError: ...

    def get_last_error(self) -> int: ...


class WindowsCRT(Protocol):
    def open_osfhandle(self, handle: int, flags: int) -> int: ...

    def get_osfhandle(self, fd: int) -> int: ...


class WindowsOS(Protocol):
    O_BINARY: int
    O_NOINHERIT: int

    def set_handle_inheritable(self, handle: int, inheritable: bool) -> None: ...


@runtime_checkable
class OwnedWindowsHandle(Protocol):
    """A pywin32 handle owner, not a borrowed integer handle value."""

    def __int__(self) -> int: ...

    def Close(self) -> None: ...


def require_owned_handle(value: object) -> OwnedWindowsHandle:
    """Reject missing or borrowed handles before registering ownership cleanup."""
    if not isinstance(value, OwnedWindowsHandle):
        raise TypeError("Windows operation did not return an owned handle")
    return value


class WindowsPipeFile(Protocol):
    def fileno(self) -> int: ...

    def close(self) -> None: ...


class WindowsAsyncioUtils(Protocol):
    def pipe(
        self,
        *,
        overlapped: tuple[bool, bool],
        duplex: bool,
    ) -> tuple[int, int]: ...

    def PipeHandle(self, handle: int) -> WindowsPipeFile: ...


@runtime_checkable
class WindowsProactor(Protocol):
    def send(self, conn: WindowsPipeFile, buf: bytes) -> asyncio.Future[int]: ...

    def recv(self, conn: WindowsPipeFile, nbytes: int) -> asyncio.Future[bytes]: ...

    def wait_for_handle(self, handle: int) -> asyncio.Future[bool]: ...


def running_windows_proactor() -> WindowsProactor:
    """Require the same IOCP loop used by native asyncio Windows subprocesses."""
    loop = asyncio.get_running_loop()
    loop_type = getattr(asyncio, "ProactorEventLoop", None)
    if loop_type is None or not isinstance(loop, loop_type):
        raise RuntimeError("Windows sandbox sessions require a ProactorEventLoop.")
    proactor = getattr(loop, "_proactor", None)
    if not isinstance(proactor, WindowsProactor):
        raise RuntimeError("Windows event loop has no usable IOCP proactor.")
    return proactor


# These modules expose these APIs on Windows. Casting the precise interfaces
# leaves DLL calling conventions, native prototypes, and missing-API errors intact.
windows_ctypes = cast(WindowsCtypes, ctypes)
windows_os = cast(WindowsOS, os)
