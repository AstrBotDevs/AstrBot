from __future__ import annotations

import asyncio
import subprocess

import pytest

from astrbot.core.computer.booters import local as local_booter
from astrbot.core.computer.booters.local import (
    LocalShellComponent,
    _decode_bytes_with_fallback,
)


def test_local_shell_component_decodes_utf8_output() -> None:
    result = _decode_bytes_with_fallback("技能内容".encode())
    assert result == "技能内容"


def test_local_shell_component_prefers_utf8_before_windows_locale(
    monkeypatch,
) -> None:
    monkeypatch.setattr(local_booter.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "cp936",
    )

    result = _decode_bytes_with_fallback(
        "技能内容".encode(),
        preferred_encoding="utf-8",
    )
    assert result == "技能内容"


def test_local_shell_component_falls_back_to_gbk_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(local_booter.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "cp1252",
    )

    result = _decode_bytes_with_fallback("微博热搜".encode("gbk"))
    assert result == "微博热搜"


def test_local_shell_component_falls_back_to_utf8_replace(monkeypatch) -> None:
    monkeypatch.setattr(local_booter.os, "name", "posix", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "utf-8",
    )

    result = _decode_bytes_with_fallback(b"\xffabc")
    assert result == "�abc"


def test_local_shell_component_falls_back_when_windows_taskkill_fails(
    monkeypatch,
) -> None:
    class TimeoutProcess:
        pid = 12345
        returncode = None

        def __init__(self):
            self.killed = False

        def kill(self) -> None:
            self.killed = True

        async def wait(self) -> int:
            return 0

    class TimeoutSession:
        def __init__(self) -> None:
            self._proc = TimeoutProcess()

        async def exec(self, *args, **kwargs):
            _ = args, kwargs
            await asyncio.Event().wait()

    class TaskkillResult:
        returncode = 1

    session = TimeoutSession()
    cleaned_up: list[str] = []

    monkeypatch.setattr(
        local_booter.PersistentShellSession,
        "get_or_create",
        lambda _key: session,
    )
    monkeypatch.setattr(
        local_booter.PersistentShellSession,
        "cleanup",
        lambda key: _record_cleanup(cleaned_up, key),
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: TaskkillResult(),
    )
    monkeypatch.setattr(local_booter.sys, "platform", "win32")

    with pytest.raises(TimeoutError):
        asyncio.run(LocalShellComponent().exec("dummy", timeout=0.001))

    assert session._proc.killed
    assert cleaned_up == ["default"]


async def _record_cleanup(cleaned_up: list[str], key: str) -> None:
    cleaned_up.append(key)
