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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("linux", ("linux", "")),
        ("linux:container", ("linux", "container")),
        ("LINUX:VM", ("linux", "vm")),
        ("ghcr.io/trycua/xfce:latest", ("ghcr.io/trycua/xfce:latest", "")),
        ("", ("", "")),
    ],
)
def test_split_image_kind(value, expected):
    assert CuaBooter._split_image_kind(value) == expected


def test_build_image_applies_the_requested_flavour():
    built = CuaBooter(image="linux:container")._build_image(_FakeImage)

    assert built.kwargs["kind"] == "container"


def test_build_image_keeps_the_sdk_default_without_a_flavour():
    built = CuaBooter(image="linux")._build_image(_FakeImage)

    assert built.kwargs["kind"] == "vm"


def test_build_image_ignores_a_flavour_the_sdk_does_not_support():
    built = CuaBooter(image="linux:container")._build_image(_KindlessImage)

    assert built == "linux-image"
