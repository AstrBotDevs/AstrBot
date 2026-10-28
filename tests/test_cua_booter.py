"""Tests for the CUA booter's dependency diagnostics."""

from __future__ import annotations

import sys
import types

import pytest

from astrbot.core.computer.booters.cua import CuaBooter


def _install_fake_cua(monkeypatch, sandbox_cls) -> None:
    """Install a fake ``cua`` module exposing the given ``Sandbox`` class."""
    module = types.ModuleType("cua")
    module.Image = object
    module.Sandbox = sandbox_cls
    monkeypatch.setitem(sys.modules, "cua", module)


class _NativeHandleOnly:
    """Stand-in for the native SDK handle, which has no ``ephemeral``."""

    is_ephemeral = False


@pytest.mark.asyncio
async def test_boot_reports_a_missing_sandbox_facade(monkeypatch):
    _install_fake_cua(monkeypatch, _NativeHandleOnly)

    with pytest.raises(RuntimeError, match="cua-sandbox"):
        await CuaBooter().boot("session-id")


class _VersionMismatchContextManager:
    async def __aenter__(self):
        raise TypeError(
            "embedded() got an unexpected keyword argument 'fleet_from_env'"
        )

    async def __aexit__(self, *exc_info):
        return False


class _SandboxFacade:
    @classmethod
    def ephemeral(cls, image, **kwargs):
        return _VersionMismatchContextManager()


@pytest.mark.asyncio
async def test_boot_explains_a_mismatched_sdk_pair(monkeypatch):
    _install_fake_cua(monkeypatch, _SandboxFacade)

    with pytest.raises(RuntimeError, match="incompatible"):
        await CuaBooter().boot("session-id")
