from __future__ import annotations

from astrbot.core.computer.booters import local as local_booter
from astrbot.core.computer.booters.local import _decode_bytes_with_fallback


def test_local_shell_component_decodes_utf8_output():
    result = _decode_bytes_with_fallback("技能内容".encode())
    assert result == "技能内容"


def test_local_shell_component_prefers_utf8_before_windows_locale(
    monkeypatch,
):
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


def test_local_shell_component_falls_back_to_gbk_on_windows(monkeypatch):
    monkeypatch.setattr(local_booter.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "cp1252",
    )

    result = _decode_bytes_with_fallback("微博热搜".encode("gbk"))
    assert result == "微博热搜"


def test_local_shell_component_falls_back_to_utf8_replace(monkeypatch):
    monkeypatch.setattr(local_booter.os, "name", "posix", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "utf-8",
    )

    result = _decode_bytes_with_fallback(b"\xffabc")
    assert result == "�abc"
