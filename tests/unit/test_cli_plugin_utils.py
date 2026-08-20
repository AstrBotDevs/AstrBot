import io
import zipfile
from pathlib import Path

import click
import pytest

from astrbot.cli.utils.plugin import PluginStatus, build_plug_list, get_git_repo
from astrbot.core.utils.outbound_http import (
    DEFAULT_PLUGIN_MARKET_URLS,
    OutboundRequestError,
)

REMOTE_PLUGINS = {
    "$meta": {"schema_version": 1},
    "local-plugin": {
        "desc": "remote description",
        "version": "2.0.0",
        "author": "remote-author",
        "repo": "https://example.com/local-plugin",
    },
    "remote-only": {
        "desc": "remote only",
        "version": "1.0.0",
        "author": "remote-author",
        "repo": "https://example.com/remote-only",
    },
}


def patch_fetch_json(monkeypatch, handler=None):
    async def fake_fetch_json(url, policy, **kwargs):
        del policy, kwargs
        if handler is not None:
            return handler(url)
        assert url in DEFAULT_PLUGIN_MARKET_URLS
        return REMOTE_PLUGINS

    monkeypatch.setattr("astrbot.cli.utils.plugin.fetch_json", fake_fetch_json)


def write_metadata(plugin_dir: Path, name: str, version: str) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_dir.joinpath("metadata.yaml").write_text(
        f"""
name: {name}
desc: local description
version: {version}
author: local-author
repo: https://example.com/{name}
""".strip(),
        encoding="utf-8",
    )


def test_build_plug_list_merges_local_and_remote_plugins(monkeypatch, tmp_path):
    write_metadata(tmp_path / "local-plugin", "local-plugin", "1.0.0")
    write_metadata(tmp_path / "unpublished-plugin", "unpublished-plugin", "1.0.0")
    tmp_path.joinpath("ignored-file").write_text("not a plugin", encoding="utf-8")

    patch_fetch_json(monkeypatch)

    plugins = build_plug_list(tmp_path)
    plugins_by_name = {plugin["name"]: plugin for plugin in plugins}

    assert plugins_by_name["local-plugin"]["status"] == PluginStatus.NEED_UPDATE
    assert plugins_by_name["unpublished-plugin"]["status"] == PluginStatus.NOT_PUBLISHED
    assert plugins_by_name["remote-only"]["status"] == PluginStatus.NOT_INSTALLED
    assert len(plugins) == 3


def test_build_plug_list_treats_file_plugin_path_as_empty_local_set(
    monkeypatch, tmp_path
):
    plugins_file = tmp_path / "plugins"
    plugins_file.write_text("not a directory", encoding="utf-8")

    patch_fetch_json(monkeypatch)

    plugins = build_plug_list(plugins_file)

    assert [plugin["name"] for plugin in plugins] == ["local-plugin", "remote-only"]
    assert all(plugin["status"] == PluginStatus.NOT_INSTALLED for plugin in plugins)


def test_build_plug_list_local_version_equal_or_newer(monkeypatch, tmp_path):
    patch_fetch_json(monkeypatch)

    # 1. test if local version == remote version
    dir_equal = tmp_path / "dir_equal"
    write_metadata(dir_equal / "local-plugin", "local-plugin", "2.0.0")

    plugins_equal = build_plug_list(dir_equal)
    plugins_equal_by_name = {p["name"]: p for p in plugins_equal}
    assert plugins_equal_by_name["local-plugin"]["status"] == PluginStatus.INSTALLED

    # 2. test if local version > remote version
    dir_newer = tmp_path / "dir_newer"
    write_metadata(dir_newer / "local-plugin", "local-plugin", "3.0.0")

    plugins_newer = build_plug_list(dir_newer)
    plugins_newer_by_name = {p["name"]: p for p in plugins_newer}
    assert plugins_newer_by_name["local-plugin"]["status"] == PluginStatus.INSTALLED


def test_build_plug_list_non_existent_path(monkeypatch, tmp_path):
    non_existent_dir = tmp_path / "completely_non_existent_path"

    patch_fetch_json(monkeypatch)

    plugins = build_plug_list(non_existent_dir)

    assert [plugin["name"] for plugin in plugins] == ["local-plugin", "remote-only"]
    assert all(plugin["status"] == PluginStatus.NOT_INSTALLED for plugin in plugins)


def test_build_plug_list_rejects_description_alias(monkeypatch, tmp_path):
    plugin_dir = tmp_path / "legacy-plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_dir.joinpath("metadata.yaml").write_text(
        """
name: legacy-plugin
description: legacy description alias
version: 1.0.0
author: legacy-author
repo: https://example.com/legacy-plugin
""".strip(),
        encoding="utf-8",
    )

    patch_fetch_json(monkeypatch)

    plugins = build_plug_list(tmp_path)

    assert all(plugin["name"] != "legacy-plugin" for plugin in plugins)
    assert all(plugin["name"] != "$meta" for plugin in plugins)


def test_get_git_repo_rejects_zip_path_traversal(monkeypatch, tmp_path):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr(
            "repo-main/metadata.yaml",
            "name: repo\ndesc: x\nversion: 1\nauthor: y\n",
        )
        zip_file.writestr("../escape.txt", "escape")
    archive.seek(0)

    monkeypatch.setattr(
        "astrbot.cli.utils.plugin._download_plugin_archive",
        lambda *_args, **_kwargs: archive,
    )
    monkeypatch.setattr(
        "astrbot.cli.utils.plugin._resolve_download_url",
        lambda url, proxy=None: url,
    )

    with pytest.raises(click.ClickException, match="Unsafe plugin archive path"):
        get_git_repo("https://github.com/example/repo", tmp_path / "repo")

    assert not (tmp_path / "escape.txt").exists()


def test_build_plug_list_falls_back_after_non_object_source(monkeypatch, tmp_path):
    calls: list[str] = []

    def handler(url: str):
        calls.append(url)
        if "raw.githubusercontent.com" in url:
            return ["not-an-object"]
        if "jsdelivr.net" in url:
            return REMOTE_PLUGINS
        raise AssertionError(url)

    patch_fetch_json(monkeypatch, handler)
    plugins = build_plug_list(tmp_path)
    assert {plugin["name"] for plugin in plugins} == {"local-plugin", "remote-only"}
    assert calls[0].startswith("https://raw.githubusercontent.com/")
    assert "jsdelivr.net" in calls[1]


def test_build_plug_list_falls_back_after_fetch_error(monkeypatch, tmp_path):
    calls: list[str] = []

    def handler(url: str):
        calls.append(url)
        if "raw.githubusercontent.com" in url:
            raise OutboundRequestError("The remote response is not valid JSON.")
        if "jsdelivr.net" in url:
            return REMOTE_PLUGINS
        raise AssertionError(url)

    patch_fetch_json(monkeypatch, handler)
    plugins = build_plug_list(tmp_path)
    assert "remote-only" in {plugin["name"] for plugin in plugins}
    assert "jsdelivr.net" in calls[1]
