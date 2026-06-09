from pathlib import Path

from astrbot.cli.utils.plugin import PluginStatus, build_plug_list


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


def write_metadata(plugin_dir: Path, name: str, version: str) -> None:
    plugin_dir.mkdir()
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


def test_build_plug_list_treats_missing_plugin_path_as_empty_local_set(
    monkeypatch, tmp_path
):
    missing_plugins_dir = tmp_path / "missing-plugins"

    monkeypatch.setattr("astrbot.cli.utils.plugin.httpx.Client", FakeClient)

    plugins = build_plug_list(missing_plugins_dir)

    assert [plugin["name"] for plugin in plugins] == ["local-plugin", "remote-only"]
    assert all(plugin["status"] == PluginStatus.NOT_INSTALLED for plugin in plugins)
