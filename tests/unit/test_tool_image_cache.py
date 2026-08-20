import base64
import os

import pytest

import astrbot.core.agent.tool_image_cache as tool_image_cache_module
from astrbot.core.agent.tool_image_cache import ToolImageCache


def _encoded(value: bytes = b"image-bytes") -> str:
    return base64.b64encode(value).decode("ascii")


def test_save_image_recreates_cache_directory_after_storage_cleanup(tmp_path):
    cache_dir = tmp_path / "temp" / "tool_images"
    cache = ToolImageCache(cache_dir)
    cache_dir.rmdir()

    image = cache.save_image(_encoded(), "tool-call", "tool")

    assert cache_dir.is_dir()
    assert (cache_dir / "tool-call_0.png").read_bytes() == b"image-bytes"
    assert image.file_path == str(cache_dir / "tool-call_0.png")


def test_save_image_retries_when_cleaner_removes_directory_mid_write(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    cache_dir = tmp_path / "tool_images"
    cache = ToolImageCache(cache_dir)
    original_replace = os.replace
    remove_once = True

    def cleaner_interleaving_replace(source, destination):
        nonlocal remove_once
        if remove_once:
            remove_once = False
            os.unlink(source)
            cache_dir.rmdir()
            raise FileNotFoundError("cleaner removed the cache directory")
        original_replace(source, destination)

    monkeypatch.setattr(
        tool_image_cache_module.os, "replace", cleaner_interleaving_replace
    )

    image = cache.save_image(_encoded(), "tool-call", "tool")

    assert (cache_dir / "tool-call_0.png").read_bytes() == b"image-bytes"
    assert image.file_path == str(cache_dir / "tool-call_0.png")


def test_tool_image_cache_rejects_path_escape(tmp_path):
    cache = ToolImageCache(tmp_path / "tool_images")

    with pytest.raises(ValueError, match="escapes tool image cache"):
        cache._resolve_cache_path("../outside.png")


def test_failed_atomic_write_leaves_no_partial_file(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    cache_dir = tmp_path / "tool_images"
    cache = ToolImageCache(cache_dir)

    def fail_replace(_source, _destination):
        raise OSError("replace failed")

    monkeypatch.setattr(tool_image_cache_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        cache.save_image(_encoded(), "tool-call", "tool")

    assert list(cache_dir.iterdir()) == []
