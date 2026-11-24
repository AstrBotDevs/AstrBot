"""Path mapping has deterministic Linux and Windows expectations."""

from nturl2path import url2pathname as windows_url2pathname
from pathlib import PureWindowsPath
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from astrbot.core.utils import media_utils, path_util


@pytest.mark.parametrize(
    ("mappings", "source", "expected"),
    [
        ([], "/some/path", "/some/path"),
        (["/a:/b"], "/some/path", "/some/path"),
        (
            ["/linux/path:/windows/path"],
            "/linux/path/file.txt",
            "/windows/path/file.txt",
        ),
        (
            ["/linux/path:/windows/path"],
            "file:///linux/path/file.txt",
            "/windows/path/file.txt",
        ),
        (["/a/:/b/"], "/a/file.txt", "/b/file.txt"),
        (["/a:/first", "/a:/second"], "/a/file.txt", "/first/file.txt"),
    ],
)
def test_path_mapping_returns_exact_result(mappings, source, expected):
    assert path_util.path_Mapping(mappings, source) == expected


@pytest.mark.parametrize("rule", ["invalid", "a:b:c:d:e"])
def test_invalid_mapping_is_reported_and_skipped(monkeypatch, rule):
    logger = Mock()
    monkeypatch.setattr(path_util, "logger", logger)
    assert (
        path_util.path_Mapping([rule, "/source:/target"], "/source/file")
        == "/target/file"
    )
    logger.warning.assert_called_once()
    assert rule in logger.warning.call_args.args[0]


def test_existing_windows_source_maps_to_linux_destination(monkeypatch):
    exists = Mock(side_effect=lambda path: path == "C:/src")
    monkeypatch.setattr(
        path_util, "os", SimpleNamespace(path=SimpleNamespace(exists=exists))
    )
    assert (
        path_util.path_Mapping(["C:/src:/dest"], "C:/src/file.txt") == "/dest/file.txt"
    )
    exists.assert_called_once_with("C:/src")


@pytest.mark.parametrize("windows_uri_paths", [False, True], ids=["native", "windows"])
@pytest.mark.parametrize(
    ("mapping", "source", "expected"),
    [
        ("/source:/dest", "file:///source/file.txt", "/dest/file.txt"),
        ("/source:/dest", "file://localhost/source/file.txt", "/dest/file.txt"),
        (
            "/source dir:/dest",
            "file:///source%20dir/voice%20note%252F.txt",
            "/dest/voice note%2F.txt",
        ),
        (
            "/source:/dest",
            "file:///source/nested%2Ffile%23%2B.txt",
            "/dest/nested/file#+.txt",
        ),
        ("C:/source:/dest", "file:///C:/source/file.txt", "/dest/file.txt"),
        (r"C:\source:/dest", "file:///C:/source/file.txt", "/dest/file.txt"),
        ("C:/source:/dest", "file://C:/source/file.txt", "/dest/file.txt"),
        (
            "//server/share/source:/dest",
            "file://server/share/source/file.txt",
            "/dest/file.txt",
        ),
        (
            r"\\server\share\source:/dest",
            "file://server/share/source/file.txt",
            "/dest/file.txt",
        ),
        ("/source:D:/dest", "file:///source/file.txt", r"D:\dest\file.txt"),
    ],
)
def test_file_uri_mapping_uses_source_separators_on_every_host(
    monkeypatch, windows_uri_paths, mapping, source, expected
):
    if windows_uri_paths:
        # Use the actual Windows URI decoder without changing the host OS.
        monkeypatch.setattr(media_utils, "url2pathname", windows_url2pathname)
        monkeypatch.setattr(media_utils, "Path", PureWindowsPath)
        monkeypatch.setattr(media_utils, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        path_util,
        "os",
        SimpleNamespace(
            path=SimpleNamespace(
                exists=lambda path: path in {"C:/source", r"C:\source"}
            )
        ),
    )

    assert path_util.path_Mapping([mapping], source) == expected
