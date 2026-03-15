from __future__ import annotations

import asyncio
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _source_env() -> dict[str, str]:
    env = os.environ.copy()
    src_new = str(_repo_root() / "src-new")
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src_new}{os.pathsep}{current}" if current else src_new
    return env


def test_testing_module_importable() -> None:
    from astrbot_sdk import testing

    assert testing.PluginHarness is not None
    assert testing.MockContext is not None


def test_cli_help_works_from_source_tree() -> None:
    process = subprocess.run(
        [sys.executable, "-m", "astrbot_sdk", "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=_source_env(),
    )

    assert process.returncode == 0, process.stderr
    assert "Usage" in process.stdout


def test_dev_help_lists_watch_option() -> None:
    process = subprocess.run(
        [sys.executable, "-m", "astrbot_sdk", "dev", "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=_source_env(),
    )

    assert process.returncode == 0, process.stderr
    assert "--watch" in process.stdout


def test_init_plugin_template_includes_readme(tmp_path: Path, monkeypatch) -> None:
    from astrbot_sdk.cli import _init_plugin

    target = tmp_path / "astrbot_plugin_demo_plugin"
    monkeypatch.chdir(tmp_path)

    _init_plugin("demo_plugin")

    assert (target / "README.md").exists()
    readme = (target / "README.md").read_text(encoding="utf-8")
    test_file = (target / "tests" / "test_plugin.py").read_text(encoding="utf-8")

    assert "astrbot-sdk dev --local --watch --event-text hello" in readme
    assert "PluginHarness.from_plugin_dir" in test_file
    assert "test_hello_dispatch" in test_file


def test_mock_context_accepts_plugin_metadata() -> None:
    from astrbot_sdk.testing import MockContext

    ctx = MockContext(
        plugin_id="demo_plugin",
        plugin_metadata={
            "display_name": "Demo Plugin",
            "author": "tester",
            "version": "1.2.3",
        },
    )

    plugin = ctx.router._plugins["demo_plugin"].metadata
    assert plugin["display_name"] == "Demo Plugin"
    assert plugin["author"] == "tester"
    assert plugin["version"] == "1.2.3"


def test_plugin_harness_from_plugin_dir_builds_expected_config() -> None:
    from astrbot_sdk.testing import PluginHarness

    plugin_dir = _repo_root() / "examples" / "hello_plugin"

    harness = PluginHarness.from_plugin_dir(
        plugin_dir,
        session_id="custom-session",
        platform="qq",
    )

    assert harness.config.plugin_dir == plugin_dir
    assert harness.config.session_id == "custom-session"
    assert harness.config.platform == "qq"


@pytest.mark.asyncio
async def test_plugin_harness_dispatches_sample_plugin() -> None:
    from astrbot_sdk.testing import LocalRuntimeConfig, PluginHarness

    plugin_dir = _repo_root() / "test_plugin" / "new"

    async with PluginHarness(LocalRuntimeConfig(plugin_dir=plugin_dir)) as harness:
        records = await harness.dispatch_text("hello")

    assert any(record.text == "Echo: hello" for record in records)


@pytest.mark.asyncio
async def test_plugin_harness_supports_metadata_and_http_commands() -> None:
    from astrbot_sdk.testing import LocalRuntimeConfig, PluginHarness

    plugin_dir = _repo_root() / "test_plugin" / "new"

    async with PluginHarness(LocalRuntimeConfig(plugin_dir=plugin_dir)) as harness:
        plugin_records = await harness.dispatch_text("plugins")
        api_records = await harness.dispatch_text("register_api")

    assert any(
        "astrbot_plugin_v4demo" in (record.text or "") for record in plugin_records
    )
    assert any(
        "已注册 API，当前共 1 个" in (record.text or "") for record in api_records
    )


@pytest.mark.asyncio
async def test_example_hello_plugin_dispatches_commands() -> None:
    from astrbot_sdk.testing import PluginHarness

    plugin_dir = _repo_root() / "examples" / "hello_plugin"

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        hello_records = await harness.dispatch_text("hello")
        about_records = await harness.dispatch_text("about")

    assert any(record.text == "Hello, World!" for record in hello_records)
    # about 命令返回 display_name "Hello Plugin"，不是 name "hello_plugin"
    assert any("Hello Plugin" in (record.text or "") for record in about_records)


def test_dev_infers_plugin_dir_from_current_directory() -> None:
    plugin_dir = _repo_root() / "examples" / "hello_plugin"
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "astrbot_sdk",
            "dev",
            "--local",
            "--event-text",
            "hello",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_source_env(),
        cwd=plugin_dir,
    )

    assert process.returncode == 0, process.stderr
    assert "[text][local-session] Hello, World!" in process.stdout


def test_dev_requires_plugin_dir_or_plugin_yaml_in_cwd(tmp_path: Path) -> None:
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "astrbot_sdk",
            "dev",
            "--local",
            "--event-text",
            "hello",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_source_env(),
        cwd=tmp_path,
    )

    assert process.returncode != 0
    assert "当前目录未找到 plugin.yaml" in process.stderr


@pytest.mark.asyncio
async def test_plugin_harness_reports_component_load_errors(tmp_path: Path) -> None:
    from astrbot_sdk.testing import LocalRuntimeConfig, PluginHarness, _PluginLoadError

    plugin_dir = tmp_path / "broken-plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(
            [
                "name: broken_demo",
                "display_name: Broken Demo",
                "author: test",
                "version: 0.1.0",
                "runtime:",
                '  python: "3.13"',
                "components:",
                "  - class: main:MissingComponent",
            ]
        ),
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        "\n".join(
            [
                "from astrbot_sdk import Star",
                "",
                "class PresentComponent(Star):",
                "    pass",
                "",
            ]
        ),
        encoding="utf-8",
    )

    harness = PluginHarness(LocalRuntimeConfig(plugin_dir=plugin_dir))
    with pytest.raises(_PluginLoadError) as raised:
        await harness.start()
    message = str(raised.value)
    assert "插件 'broken_demo'" in message
    assert "components[0].class='main:MissingComponent'" in message
    assert "加载失败" in message


def _write_watch_plugin(plugin_dir: Path, *, reply_text: str) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(
            [
                "name: watch_demo",
                "display_name: Watch Demo",
                "author: test",
                "version: 0.1.0",
                "runtime:",
                '  python: "3.13"',
                "components:",
                "  - class: main:WatchDemo",
            ]
        ),
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        "\n".join(
            [
                "from astrbot_sdk import Context, MessageEvent, Star, on_command",
                "",
                "class WatchDemo(Star):",
                '    @on_command("hello")',
                "    async def hello(self, event: MessageEvent, ctx: Context) -> None:",
                f'        await event.reply("{reply_text}")',
                "",
            ]
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_run_local_dev_watch_reloads_on_file_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from astrbot_sdk.cli import _run_local_dev

    plugin_dir = tmp_path / "watch-plugin"
    _write_watch_plugin(plugin_dir, reply_text="v1")

    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)

    task = asyncio.create_task(
        _run_local_dev(
            plugin_dir=plugin_dir,
            event_text="hello",
            interactive=False,
            watch=True,
            session_id="local-session",
            user_id="local-user",
            platform="test",
            group_id=None,
            event_type="message",
            watch_poll_interval=0.05,
            max_watch_reloads=1,
        )
    )

    await asyncio.sleep(0.2)
    _write_watch_plugin(plugin_dir, reply_text="v2")

    await asyncio.wait_for(task, timeout=3.0)

    output = stdout.getvalue()
    assert "watch 模式已启动" in output
    assert "检测到文件变更" in output
    assert "[text][local-session] v1" in output
    assert "[text][local-session] v2" in output
