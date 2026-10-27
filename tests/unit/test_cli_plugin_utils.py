from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from astrbot.cli.utils.plugin import PluginStatus, build_plug_list, download_repository


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
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


class FakeClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url):
        assert url == "https://api.soulter.top/astrbot/plugins"
        return FakeResponse()


def test_download_repository_uses_head_without_metadata_lookup(
    monkeypatch, tmp_path, capsys
):
    archive = BytesIO()
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("plugin-commit/main.py", "VALUE = 1\n")
    requested_urls = []

    class ArchiveResponse:
        content = archive.getvalue()

        def raise_for_status(self):
            return None

    class ArchiveClient:
        def __init__(self, **kwargs):
            assert kwargs == {"follow_redirects": True, "trust_env": True}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            requested_urls.append(url)
            return ArchiveResponse()

    monkeypatch.setattr("astrbot.cli.utils.plugin.httpx.Client", ArchiveClient)

    target_path = tmp_path / "plugin"
    download_repository("https://github.com/example/plugin", target_path)

    assert requested_urls == ["https://github.com/example/plugin/archive/HEAD.zip"]
    assert (target_path / "main.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert "default reference HEAD" in capsys.readouterr().out


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

    monkeypatch.setattr("astrbot.cli.utils.plugin.httpx.Client", FakeClient)

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

    monkeypatch.setattr("astrbot.cli.utils.plugin.httpx.Client", FakeClient)

    plugins = build_plug_list(plugins_file)

    assert [plugin["name"] for plugin in plugins] == ["local-plugin", "remote-only"]
    assert all(plugin["status"] == PluginStatus.NOT_INSTALLED for plugin in plugins)


def test_build_plug_list_local_version_equal_or_newer(monkeypatch, tmp_path):
    monkeypatch.setattr("astrbot.cli.utils.plugin.httpx.Client", FakeClient)

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

    monkeypatch.setattr("astrbot.cli.utils.plugin.httpx.Client", FakeClient)

    plugins = build_plug_list(non_existent_dir)

    assert [plugin["name"] for plugin in plugins] == ["local-plugin", "remote-only"]
    assert all(plugin["status"] == PluginStatus.NOT_INSTALLED for plugin in plugins)
