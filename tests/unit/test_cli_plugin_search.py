from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from astrbot.cli.commands.cmd_plug import search


def test_cli_plug_search_uses_shared_backend_ranking(monkeypatch) -> None:
    plugins = [
        {
            "name": "astrbot_plugin_exact",
            "desc": "general helper",
            "version": "1.0.0",
            "author": "alice",
            "repo": "https://github.com/example/exact",
            "status": "not-installed",
        },
        {
            "name": "other_plugin",
            "desc": "contains astrbot_plugin_exact in description only",
            "version": "1.0.0",
            "author": "bob",
            "repo": "https://github.com/example/other",
            "status": "not-installed",
        },
    ]
    monkeypatch.setattr(
        "astrbot.cli.commands.cmd_plug._get_data_path",
        lambda: Path("/tmp"),
    )
    monkeypatch.setattr(
        "astrbot.cli.commands.cmd_plug.build_plug_list",
        lambda _plugins_dir: plugins,
    )

    result = CliRunner().invoke(search, ["astrbot_plugin_exact"])

    assert result.exit_code == 0
    assert result.output.index("astrbot_plugin_exact") < result.output.index(
        "other_plugin"
    )
