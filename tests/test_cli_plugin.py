from pathlib import Path

import httpx
import pytest
from click import ClickException
from click.testing import CliRunner

import astrbot.cli.utils.plugin as plugin_utils
from astrbot.cli.commands.cmd_plug import plug


def _write_plugin(path: Path, name: str = "astrbot_plugin_local_demo") -> None:
    path.mkdir(parents=True)
    (path / "metadata.yaml").write_text(
        "\n".join(
            [
                f"name: {name}",
                "desc: Local plugin",
                "version: 1.0.0",
                "author: AstrBot",
                "repo: https://example.com/local-plugin",
            ],
        ),
        encoding="utf-8",
    )
    (path / "main.py").write_text("PLUGIN_LOADED = True\n", encoding="utf-8")


def _write_ignored_plugin_files(path: Path) -> None:
    for ignored_dir in [".git", ".venv", "__pycache__", ".idea", ".vscode", ".zed"]:
        ignored_path = path / ignored_dir
        ignored_path.mkdir()
        (ignored_path / "ignored.txt").write_text("ignored\n", encoding="utf-8")
    (path / "__pycache__" / "main.pyc").write_bytes(b"ignored")


def _write_astrbot_root(path: Path) -> None:
    (path / ".astrbot").touch()
    (path / "data" / "plugins").mkdir(parents=True)


def test_plugin_install_editable_symlinks_local_plugin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    require_symlink: Path,
) -> None:
    root = tmp_path / "root"
    source = tmp_path / "source-plugin"
    root.mkdir()
    _write_astrbot_root(root)
    _write_plugin(source)
    monkeypatch.chdir(root)

    result = CliRunner().invoke(
        plug,
        ["install", "-e", str(source)],
        catch_exceptions=False,
    )

    target = root / "data" / "plugins" / "astrbot_plugin_local_demo"
    target = root / "data" / "plugins" / "astrbot_plugin_local_demo"
    assert result.exit_code == 0
    assert target.is_symlink()
    assert (target / "metadata.yaml").exists()
    assert (target / "main.py").read_text(encoding="utf-8") == "PLUGIN_LOADED = True\n"


def test_plugin_install_accepts_local_path_without_editable_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    source = tmp_path / "source-plugin"
    root.mkdir()
    _write_astrbot_root(root)
    _write_plugin(source)
    _write_ignored_plugin_files(source)
    monkeypatch.chdir(root)

    result = CliRunner().invoke(plug, ["install", str(source)])

    target = root / "data" / "plugins" / "astrbot_plugin_local_demo"
    assert result.exit_code == 0
    assert not target.is_symlink()
    assert (target / "metadata.yaml").exists()
    assert not (target / ".git").exists()
    assert not (target / ".venv").exists()
    assert not (target / "__pycache__").exists()
    assert not (target / ".idea").exists()
    assert not (target / ".vscode").exists()
    assert not (target / ".zed").exists()


def test_plugin_install_editable_rejects_existing_plugin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    source = tmp_path / "source-plugin"
    root.mkdir()
    _write_astrbot_root(root)
    _write_plugin(source)
    _write_plugin(root / "data" / "plugins" / "astrbot_plugin_local_demo")
    monkeypatch.chdir(root)

    result = CliRunner().invoke(plug, ["install", "-e", str(source)])

    assert result.exit_code != 0
    assert "already exists" in result.output


@pytest.mark.parametrize("editable", [False, True], ids=["copy", "editable"])
def test_remove_local_plugin_preserves_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    request: pytest.FixtureRequest,
    editable: bool,
) -> None:
    if editable:
        request.getfixturevalue("require_symlink")
    name = "astrbot_plugin_local_demo"
    source = tmp_path / "source-plugin"
    _write_astrbot_root(tmp_path)
    _write_plugin(source, name)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        httpx.Client,
        "get",
        lambda self, url: httpx.Response(
            200, request=httpx.Request("GET", url), json={}
        ),
    )

    runner = CliRunner()
    install_args = ["install", "-e"] if editable else ["install"]
    installed = runner.invoke(plug, [*install_args, str(source)])
    assert installed.exit_code == 0, installed.output

    removed = runner.invoke(plug, ["remove", name], input="y\n")
    assert removed.exit_code == 0, removed.output
    assert not (tmp_path / "data" / "plugins" / name).exists()
    assert (source / "main.py").read_text(encoding="utf-8") == "PLUGIN_LOADED = True\n"


@pytest.mark.parametrize("source_state", ["moved", "deleted"])
def test_remove_stale_editable_plugin_allows_reinstall(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    require_symlink: Path,
    source_state: str,
) -> None:
    name = "astrbot_plugin_local_demo"
    source = tmp_path / "source-plugin"
    _write_astrbot_root(tmp_path)
    _write_plugin(source, name)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        httpx.Client,
        "get",
        lambda self, url: httpx.Response(
            200, request=httpx.Request("GET", url), json={name: {}}
        ),
    )

    runner = CliRunner()
    installed = runner.invoke(plug, ["install", "-e", str(source)])
    assert installed.exit_code == 0, installed.output
    target = tmp_path / "data" / "plugins" / name
    if source_state == "moved":
        source = source.rename(tmp_path / "moved-source")
    else:
        (source / "main.py").unlink()
        (source / "metadata.yaml").unlink()
        source.rmdir()
    assert target.is_symlink() and not target.exists()

    cancelled = runner.invoke(plug, ["remove", name], input="n\n")
    assert cancelled.exit_code != 0
    assert "Aborted" in cancelled.output
    assert target.is_symlink()

    removed = runner.invoke(plug, ["remove", name], input="y\n")
    assert removed.exit_code == 0, removed.output
    assert not target.is_symlink()
    if source_state == "deleted":
        _write_plugin(source, name)
    assert (source / "main.py").read_text(encoding="utf-8") == "PLUGIN_LOADED = True\n"
    reinstalled = runner.invoke(plug, ["install", "-e", str(source)])
    assert reinstalled.exit_code == 0, reinstalled.output
    assert target.is_symlink()
    assert target.resolve() == source


@pytest.mark.parametrize(
    "absolute", [False, True], ids=["parent-path", "absolute-path"]
)
def test_remove_stale_plugin_rejects_paths_outside_plugins(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    require_symlink: Path,
    absolute: bool,
) -> None:
    _write_astrbot_root(tmp_path)
    outside = tmp_path / "data" / "outside"
    outside.symlink_to(tmp_path / "missing-source", target_is_directory=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("astrbot.cli.commands.cmd_plug.build_plug_list", lambda _: [])

    name = str(outside) if absolute else "../outside"
    result = CliRunner().invoke(plug, ["remove", name], input="y\n")

    assert result.exit_code != 0
    assert "does not exist or is not installed" in result.output
    assert outside.is_symlink()


@pytest.mark.parametrize("symlink", [False, True], ids=["directory", "live-symlink"])
def test_remove_does_not_delete_unrecognized_live_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    request: pytest.FixtureRequest,
    symlink: bool,
) -> None:
    if symlink:
        request.getfixturevalue("require_symlink")
    _write_astrbot_root(tmp_path)
    target = tmp_path / "data" / "plugins" / "unrecognized"
    source = tmp_path / "source" if symlink else target
    source.mkdir()
    (source / "keep.txt").write_text("keep\n", encoding="utf-8")
    if symlink:
        target.symlink_to(source, target_is_directory=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("astrbot.cli.commands.cmd_plug.build_plug_list", lambda _: [])

    result = CliRunner().invoke(plug, ["remove", target.name], input="y\n")

    assert result.exit_code != 0
    assert "does not exist or is not installed" in result.output
    assert (target / "keep.txt").read_text(encoding="utf-8") == "keep\n"


def test_plugin_install_rejects_plugin_name_with_path_separator(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    source = tmp_path / "source-plugin"
    root.mkdir()
    _write_astrbot_root(root)
    _write_plugin(source, name="../bad_plugin")
    monkeypatch.chdir(root)

    result = CliRunner().invoke(plug, ["install", str(source)])

    assert result.exit_code != 0
    assert "invalid name" in result.output
    assert not (root / "data" / "bad_plugin").exists()


def test_plugin_install_copy_does_not_delete_existing_target_on_race(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    source = tmp_path / "source-plugin"
    root.mkdir()
    _write_astrbot_root(root)
    _write_plugin(source)
    monkeypatch.chdir(root)

    target = root / "data" / "plugins" / "astrbot_plugin_local_demo"
    target.mkdir()
    marker = target / "keep.txt"
    marker.write_text("keep\n", encoding="utf-8")

    result = CliRunner().invoke(plug, ["install", str(source)])

    assert result.exit_code != 0
    assert "already exists" in result.output
    assert marker.read_text(encoding="utf-8") == "keep\n"


def test_plugin_install_copy_does_not_delete_concurrently_created_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source-plugin"
    plugins_dir = tmp_path / "plugins"
    _write_plugin(source)

    target = plugins_dir / "astrbot_plugin_local_demo"

    def create_target_then_fail(
        _source_path: Path,
        _plugins_dir: Path,
        _target_path: Path,
    ) -> None:
        target.mkdir(parents=True)
        (target / "keep.txt").write_text("keep\n", encoding="utf-8")
        raise FileExistsError

    monkeypatch.setattr(plugin_utils, "_copy_local_plugin", create_target_then_fail)

    with pytest.raises(ClickException, match="already exists"):
        plugin_utils.install_local_plugin(source, plugins_dir)

    assert (target / "keep.txt").read_text(encoding="utf-8") == "keep\n"


def test_plugin_install_requires_name_or_editable_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write_astrbot_root(root)
    monkeypatch.chdir(root)

    result = CliRunner().invoke(plug, ["install"])

    assert result.exit_code != 0
    assert "Missing plugin name or local plugin path" in result.output
