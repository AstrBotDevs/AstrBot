import asyncio
from pathlib import Path

from astrbot.core.computer.booters import local as local_booter
from astrbot.core.computer.booters.local import LocalFileSystemComponent


def _allow_tmp_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(local_booter, "get_astrbot_root", lambda: str(tmp_path))


def test_local_file_system_component_prefers_utf8_before_windows_locale(
    monkeypatch,
    tmp_path: Path,
):
    _allow_tmp_root(monkeypatch, tmp_path)
    monkeypatch.setattr(local_booter.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "cp936",
    )

    skill_path = tmp_path / "skills" / "demo.txt"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_bytes("技能内容".encode())

    result = asyncio.run(LocalFileSystemComponent().read_file(str(skill_path)))

    assert result["success"] is True
    assert result["content"] == "技能内容"


def test_local_file_system_component_falls_back_to_gbk_on_windows(
    monkeypatch,
    tmp_path: Path,
):
    _allow_tmp_root(monkeypatch, tmp_path)
    monkeypatch.setattr(local_booter.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "cp1252",
    )

    skill_path = tmp_path / "skills" / "weibo-hot.txt"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_bytes("微博热搜".encode("gbk"))

    result = asyncio.run(LocalFileSystemComponent().read_file(str(skill_path)))

    assert result["success"] is True
    assert result["content"] == "微博热搜"


def test_local_file_system_component_applies_requested_mode_to_unicode_path(
    monkeypatch,
    tmp_path: Path,
):
    """Creating a file keeps the requested permission policy on Windows paths."""
    _allow_tmp_root(monkeypatch, tmp_path)
    target = tmp_path / "含 空格" / "notes.txt"
    chmod_calls = []

    def record_chmod(path: str, mode: int) -> None:
        chmod_calls.append((Path(path), mode))

    monkeypatch.setattr(local_booter.os, "chmod", record_chmod)

    result = asyncio.run(
        LocalFileSystemComponent().create_file(
            str(target),
            "content",
            mode=0o600,
        )
    )

    assert result == {"success": True, "path": str(target.resolve())}
    assert target.read_text(encoding="utf-8") == "content"
    assert chmod_calls == [(target.resolve(), 0o600)]
