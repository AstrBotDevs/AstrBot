"""Local booter lifecycle and unsupported transfer behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.astr_agent_runtime.computer.booters import local as local_booter
from astrbot.core.astr_agent_runtime.computer.booters.local import (
    LocalBooter,
    LocalFileSystemComponent,
    LocalPythonComponent,
    LocalShellComponent,
    _decode_bytes_with_fallback,
)


@pytest.mark.asyncio
async def test_local_lifecycle_reuses_components_and_awaits_session_cleanup(
    monkeypatch,
):
    booter = LocalBooter()
    components = booter.fs, booter.python, booter.shell
    assert isinstance(components[0], LocalFileSystemComponent)
    assert isinstance(components[1], LocalPythonComponent)
    assert isinstance(components[2], LocalShellComponent)
    cleanup = AsyncMock()
    monkeypatch.setattr(booter.shell, "shutdown_sessions", cleanup)
    await booter.boot("local-test")
    assert await booter.available() is True
    assert (booter.fs, booter.python, booter.shell) == components
    await booter.shutdown()
    cleanup.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["upload_file", "download_file"])
async def test_local_transfers_are_explicitly_unsupported(operation):
    with pytest.raises(NotImplementedError, match=f"does not support {operation}"):
        await getattr(LocalBooter(), operation)("source", "destination")


@pytest.mark.parametrize(
    "data,encoding,expected",
    [
        (None, None, ""),
        (b"", None, ""),
        ("中文".encode(), None, "中文"),
        ("café".encode("latin-1"), "latin-1", "café"),
    ],
)
def test_output_decoding_preserves_known_encodings(
    monkeypatch, data, encoding, expected
):
    monkeypatch.setattr(
        "astrbot.core.astr_agent_runtime.computer.booters.local.locale.getpreferredencoding",
        lambda _: "utf-8",
    )
    assert _decode_bytes_with_fallback(data, preferred_encoding=encoding) == expected


@pytest.mark.parametrize(
    "platform_name,locale_encoding,expected",
    [("posix", "utf-8", "�"), ("nt", "cp1252", "ÿ")],
)
def test_output_decoding_uses_platform_fallback(
    monkeypatch: pytest.MonkeyPatch,
    platform_name: str,
    locale_encoding: str,
    expected: str,
) -> None:
    monkeypatch.setattr(local_booter, "os", SimpleNamespace(name=platform_name))
    monkeypatch.setattr(
        local_booter.locale, "getpreferredencoding", lambda _: locale_encoding
    )
    assert (
        _decode_bytes_with_fallback(b"\xff", preferred_encoding="not-an-encoding")
        == expected
    )
