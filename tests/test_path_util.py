"""Path mapping has deterministic Linux and Windows expectations."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from astrbot.core.utils import path_util


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
