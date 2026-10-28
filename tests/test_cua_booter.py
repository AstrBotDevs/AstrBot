"""Tests for the CUA booter's image flavour selection."""

from __future__ import annotations

import pytest

from astrbot.core.computer.booters.cua import CuaBooter


class _FakeImage:
    """Stand-in for the CUA SDK's ``Image`` factory."""

    def __init__(self, name: str, **kwargs):
        self.name = name
        self.kwargs = kwargs

    @classmethod
    def linux(cls, distro: str = "ubuntu", version: str = "24.04", kind: str = "vm"):
        return cls("linux", distro=distro, version=version, kind=kind)


class _KindlessImage:
    """Stand-in for an SDK image factory without a ``kind`` option."""

    @classmethod
    def linux(cls):
        return "linux-image"


class _KwargsImage:
    """Stand-in for an SDK image factory that forwards ``**kwargs``."""

    def __init__(self, name: str, **kwargs):
        self.name = name
        self.kwargs = kwargs

    @classmethod
    def linux(cls, **kwargs):
        return cls("linux", **kwargs)


class _PositionalOnlyImage:
    """Stand-in for an SDK image factory with a positional-only ``kind``."""

    def __init__(self, name: str, kind: str):
        self.name = name
        self.kind = kind

    @classmethod
    def linux(cls, kind: str = "vm", /):
        return cls("linux", kind)


@pytest.mark.parametrize(
    ("value", "expected_kind"),
    [
        ("linux", "vm"),
        ("linux:container", "container"),
        ("LINUX:VM", "vm"),
        # A registry tag is not an image flavour.
        ("ghcr.io/trycua/xfce:latest", "vm"),
    ],
)
def test_build_image_selects_the_flavour(value, expected_kind):
    built = CuaBooter(image=value)._build_image(_FakeImage)

    assert built.kwargs["kind"] == expected_kind


def test_build_image_ignores_a_flavour_the_sdk_does_not_support():
    built = CuaBooter(image="linux:container")._build_image(_KindlessImage)

    assert built == "linux-image"


def test_build_image_passes_the_flavour_to_a_kwargs_factory():
    built = CuaBooter(image="linux:container")._build_image(_KwargsImage)

    assert built.kwargs["kind"] == "container"


def test_build_image_ignores_a_positional_only_flavour():
    built = CuaBooter(image="linux:container")._build_image(_PositionalOnlyImage)

    assert built.kind == "vm"
