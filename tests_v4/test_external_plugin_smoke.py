"""可选的外部插件兼容 smoke 测试。

默认不跑；手动验证真实外部插件时，设置
``ASTRBOT_EXTERNAL_PLUGIN_REPO=https://...`` 即可启用。

如果还希望验证真实 handler 调用，而不是仅验证可加载，可以额外设置：

- ``ASTRBOT_EXTERNAL_PLUGIN_COMMAND=<command>``
- ``ASTRBOT_EXTERNAL_PLUGIN_EVENT_TEXT=<text>`` (可选，默认等于 command)
- ``ASTRBOT_EXTERNAL_PLUGIN_EXPECT_TEXT=<substring>`` (可选)
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import textwrap
from pathlib import Path

import pytest

from astrbot_sdk.protocol.messages import InitializeOutput, PeerInfo
from astrbot_sdk.runtime.bootstrap import SupervisorRuntime
from astrbot_sdk.runtime.loader import (
    PluginEnvironmentManager,
    load_plugin_spec,
)
from astrbot_sdk.runtime.peer import Peer

from tests_v4.helpers import make_transport_pair

EXTERNAL_PLUGIN_REPO_ENV = "ASTRBOT_EXTERNAL_PLUGIN_REPO"
EXTERNAL_PLUGIN_COMMAND_ENV = "ASTRBOT_EXTERNAL_PLUGIN_COMMAND"
EXTERNAL_PLUGIN_EVENT_TEXT_ENV = "ASTRBOT_EXTERNAL_PLUGIN_EVENT_TEXT"
EXTERNAL_PLUGIN_EXPECT_TEXT_ENV = "ASTRBOT_EXTERNAL_PLUGIN_EXPECT_TEXT"


def _clone_external_plugin(
    *,
    project_root: Path,
    repo_url: str,
    clone_dir: Path,
) -> None:
    subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, str(clone_dir)],
        check=True,
        cwd=project_root,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(
    not os.getenv(EXTERNAL_PLUGIN_REPO_ENV),
    reason=f"set {EXTERNAL_PLUGIN_REPO_ENV} to enable external plugin smoke tests",
)
def test_external_plugin_load_smoke():
    """按需 clone 外部插件仓库并验证其能在独立环境里完成加载。"""
    repo_url = os.environ[EXTERNAL_PLUGIN_REPO_ENV]
    project_root = Path(__file__).resolve().parent.parent

    with tempfile.TemporaryDirectory(prefix="astrbot-external-plugin-") as temp_dir:
        clone_dir = Path(temp_dir) / "plugin"
        _clone_external_plugin(
            project_root=project_root,
            repo_url=repo_url,
            clone_dir=clone_dir,
        )

        spec = load_plugin_spec(clone_dir)
        manager = PluginEnvironmentManager(project_root)
        python_path = manager.prepare_environment(spec)
        script = textwrap.dedent(
            f"""
            import asyncio
            import sys
            from pathlib import Path

            repo_root = Path({str(project_root)!r})
            plugin_dir = Path({str(clone_dir)!r})
            sys.path.insert(0, str((repo_root / "src-new").resolve()))

            from astrbot_sdk.runtime.loader import load_plugin, load_plugin_spec

            async def main():
                spec = load_plugin_spec(plugin_dir)
                loaded = load_plugin(spec)
                print("PLUGIN", loaded.plugin.name)
                print("HANDLERS", len(loaded.handlers))
                print("CAPS", len(loaded.capabilities))

            asyncio.run(main())
            """
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str((project_root / "src-new").resolve())
        result = subprocess.run(
            [str(python_path), "-c", script],
            check=False,
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
        )
        assert "HANDLERS" in result.stdout
        assert "PLUGIN" in result.stdout


@pytest.mark.skipif(
    not (
        os.getenv(EXTERNAL_PLUGIN_REPO_ENV) and os.getenv(EXTERNAL_PLUGIN_COMMAND_ENV)
    ),
    reason=(
        f"set {EXTERNAL_PLUGIN_REPO_ENV} and {EXTERNAL_PLUGIN_COMMAND_ENV} "
        "to enable external plugin runtime command smoke tests"
    ),
)
@pytest.mark.asyncio
async def test_external_plugin_runtime_command_smoke():
    """按需拉起真实 supervisor/worker 链路并执行一个外部插件命令。"""
    repo_url = os.environ[EXTERNAL_PLUGIN_REPO_ENV]
    command_name = os.environ[EXTERNAL_PLUGIN_COMMAND_ENV]
    event_text = os.getenv(EXTERNAL_PLUGIN_EVENT_TEXT_ENV) or command_name
    expected_text = os.getenv(EXTERNAL_PLUGIN_EXPECT_TEXT_ENV)
    project_root = Path(__file__).resolve().parent.parent

    with tempfile.TemporaryDirectory(prefix="astrbot-external-runtime-") as temp_dir:
        plugins_root = Path(temp_dir) / "plugins"
        plugin_root = plugins_root / "external_plugin"
        _clone_external_plugin(
            project_root=project_root,
            repo_url=repo_url,
            clone_dir=plugin_root,
        )

        left, right = make_transport_pair()
        core = Peer(
            transport=left,
            peer_info=PeerInfo(name="outer-core", role="core", version="v4"),
        )
        core.set_initialize_handler(
            lambda _message: asyncio.sleep(
                0,
                result=InitializeOutput(
                    peer=PeerInfo(name="outer-core", role="core", version="v4"),
                    capabilities=[],
                    metadata={},
                ),
            )
        )

        runtime = SupervisorRuntime(
            transport=right,
            plugins_dir=plugins_root,
            env_manager=PluginEnvironmentManager(project_root),
        )
        await core.start()
        try:
            await runtime.start()
            await core.wait_until_remote_initialized()

            handler = next(
                (
                    item
                    for item in core.remote_handlers
                    if getattr(item.trigger, "command", None) == command_name
                ),
                None,
            )
            assert handler is not None, (
                f"command handler not found: {command_name}; "
                f"available={[getattr(item.trigger, 'command', None) for item in core.remote_handlers]}"
            )

            await core.invoke(
                "handler.invoke",
                {
                    "handler_id": handler.id,
                    "event": {
                        "text": event_text,
                        "session_id": "external-smoke-session",
                        "user_id": "user-1",
                        "platform": "test",
                    },
                },
                request_id="external-runtime-command",
            )

            sent_messages = list(runtime.capability_router.sent_messages)
            assert sent_messages, (
                "external plugin command completed but did not emit any platform "
                "message; this usually means the command path was not really exercised"
            )

            if expected_text is not None:
                assert any(
                    expected_text in item.get("text", "")
                    for item in sent_messages
                    if "text" in item
                ), sent_messages
        finally:
            await runtime.stop()
            await core.stop()
