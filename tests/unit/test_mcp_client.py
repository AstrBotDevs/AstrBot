import pytest

from astrbot.core.agent import mcp_client


def test_prepare_stdio_env_adds_pathext_on_windows(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(mcp_client.sys, "platform", "win32")
    monkeypatch.setenv("PATHEXT", ".COM;.EXE")

    cfg = {"command": "uvx", "args": ["mcp-server-fetch"]}

    prepared = mcp_client._prepare_stdio_env(cfg)

    assert prepared["env"]["PATHEXT"] == ".COM;.EXE"


def test_prepare_stdio_env_merges_existing_env_on_windows(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(mcp_client.sys, "platform", "win32")
    monkeypatch.setenv("PATHEXT", ".COM;.EXE")

    cfg = {
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "env": {"HTTP_PROXY": "http://127.0.0.1:7890"},
    }

    prepared = mcp_client._prepare_stdio_env(cfg)

    assert prepared["env"] == {
        "HTTP_PROXY": "http://127.0.0.1:7890",
        "PATHEXT": ".COM;.EXE",
    }


def test_prepare_stdio_env_preserves_user_defined_pathext(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(mcp_client.sys, "platform", "win32")
    monkeypatch.setenv("PATHEXT", ".COM;.EXE")

    cfg = {
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "env": {"PATHEXT": ".BAT"},
    }

    prepared = mcp_client._prepare_stdio_env(cfg)

    assert prepared["env"]["PATHEXT"] == ".BAT"


def test_prepare_stdio_env_does_not_modify_non_windows(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(mcp_client.sys, "platform", "linux")
    monkeypatch.setenv("PATHEXT", ".COM;.EXE")

    cfg = {"command": "uvx", "args": ["mcp-server-fetch"]}

    prepared = mcp_client._prepare_stdio_env(cfg)

    assert "env" not in prepared
