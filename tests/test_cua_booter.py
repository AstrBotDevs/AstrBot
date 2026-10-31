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


def _install_fake_sdk(monkeypatch) -> None:
    """Install a fake ``cua_sandbox`` package that mimics the SDK mismatch.

    The stand-in is compiled inside a namespace named ``cua_sandbox`` so that
    the traceback of the raised error points at the facade package, the way the
    real facade reports a mismatched pair of releases.
    """
    namespace: dict[str, object] = {"__name__": "cua_sandbox"}
    exec(
        "def embedded(**kwargs):\n"
        "    raise TypeError(\n"
        "        \"embedded() got an unexpected keyword argument 'fleet_from_env'\"\n"
        "    )\n",
        namespace,
    )
    module = types.ModuleType("cua_sandbox")
    module.embedded = namespace["embedded"]
    monkeypatch.setitem(sys.modules, "cua_sandbox", module)


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
        from cua_sandbox import embedded

        return embedded(fleet_from_env=False)

    async def __aexit__(self, *exc_info):
        return False


class _SandboxFacade:
    @classmethod
    def ephemeral(cls, image, **kwargs):
        return _VersionMismatchContextManager()


@pytest.mark.asyncio
async def test_boot_explains_a_mismatched_sdk_pair(monkeypatch):
    _install_fake_cua(monkeypatch, _SandboxFacade)
    _install_fake_sdk(monkeypatch)

    with pytest.raises(RuntimeError, match="incompatible"):
        await CuaBooter().boot("session-id")


class _UnrelatedTypeErrorContextManager:
    async def __aenter__(self):
        raise TypeError("got an unexpected keyword argument 'typo'")

    async def __aexit__(self, *exc_info):
        return False


class _UnrelatedTypeErrorFacade:
    @classmethod
    def ephemeral(cls, image, **kwargs):
        return _UnrelatedTypeErrorContextManager()


@pytest.mark.asyncio
async def test_boot_does_not_blame_the_packages_for_an_unrelated_type_error(monkeypatch):
    _install_fake_cua(monkeypatch, _UnrelatedTypeErrorFacade)

    with pytest.raises(RuntimeError, match="CUA sandbox failed to start") as error:
        await CuaBooter().boot("session-id")

    assert "incompatible" not in str(error.value)


class _FailingContextManager:
    """A sandbox context manager whose entry fails."""

    def __init__(self) -> None:
        self.exited = False

    async def __aenter__(self):
        raise RuntimeError("the sandbox could not start")

    async def __aexit__(self, *exc_info):
        self.exited = True
        return False


class _FailingFacade:
    last_context_manager: _FailingContextManager | None = None

    @classmethod
    def ephemeral(cls, image, **kwargs):
        cls.last_context_manager = _FailingContextManager()
        return cls.last_context_manager


@pytest.mark.asyncio
async def test_boot_releases_the_sandbox_when_the_entry_fails(monkeypatch):
    _install_fake_cua(monkeypatch, _FailingFacade)

    booter = CuaBooter()
    with pytest.raises(RuntimeError, match="could not start"):
        await booter.boot("session-id")

    await booter.shutdown()
    assert _FailingFacade.last_context_manager is not None
    assert _FailingFacade.last_context_manager.exited is True
