"""grouped env 的真实 smoke 测试。

运行示例：
    python -m pytest tests_v4/test_grouped_environment_smoke.py -m "slow and integration" -v
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest
import yaml

from astrbot_sdk.protocol.messages import InitializeOutput, PeerInfo
from astrbot_sdk.runtime.bootstrap import SupervisorRuntime
from astrbot_sdk.runtime.loader import PluginEnvironmentManager
from astrbot_sdk.runtime.peer import Peer

from tests_v4.helpers import make_transport_pair

pytestmark = [pytest.mark.slow, pytest.mark.integration]

UV_BINARY = shutil.which("uv")


async def start_test_core_peer(transport) -> Peer:
    """Provide an initialize responder for supervisor startup."""
    core = Peer(
        transport=transport,
        peer_info=PeerInfo(name="grouped-env-core", role="core", version="v4"),
    )
    core.set_initialize_handler(
        lambda _message: asyncio.sleep(
            0,
            result=InitializeOutput(
                peer=PeerInfo(name="grouped-env-core", role="core", version="v4"),
                capabilities=[],
                metadata={},
            ),
        )
    )
    await core.start()
    return core


def _build_local_wheel(
    *,
    packages_root: Path,
    wheelhouse: Path,
    project_name: str,
    version: str,
    module_name: str,
) -> Path:
    package_root = packages_root / f"{project_name}-{version}"
    source_dir = package_root / "src" / module_name
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "__init__.py").write_text(
        f'__version__ = "{version}"\n',
        encoding="utf-8",
    )
    (package_root / "pyproject.toml").write_text(
        textwrap.dedent(
            f"""\
            [build-system]
            requires = ["setuptools>=80", "wheel"]
            build-backend = "setuptools.build_meta"

            [project]
            name = "{project_name}"
            version = "{version}"

            [tool.setuptools.packages.find]
            where = ["src"]
            """
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(package_root),
            "--no-build-isolation",
            "--no-deps",
            "-w",
            str(wheelhouse),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"failed to build local wheel {project_name}=={version}:\n"
            f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
        )

    candidates = sorted(
        wheelhouse.glob(f"{module_name}-{version}-*.whl"),
        key=lambda path: path.name,
    )
    if not candidates:
        raise RuntimeError(f"local wheel not found for {project_name}=={version}")
    return candidates[-1]


def build_local_wheelhouse(root: Path) -> dict[str, Path]:
    """Build offline wheels used by the smoke test."""
    packages_root = root / "packages"
    wheelhouse = root / "wheelhouse"
    packages_root.mkdir(parents=True, exist_ok=True)
    wheelhouse.mkdir(parents=True, exist_ok=True)

    return {
        "alpha-1": _build_local_wheel(
            packages_root=packages_root,
            wheelhouse=wheelhouse,
            project_name="alpha-pkg",
            version="1.0.0",
            module_name="alpha_pkg",
        ),
        "alpha-2": _build_local_wheel(
            packages_root=packages_root,
            wheelhouse=wheelhouse,
            project_name="alpha-pkg",
            version="2.0.0",
            module_name="alpha_pkg",
        ),
        "beta-1": _build_local_wheel(
            packages_root=packages_root,
            wheelhouse=wheelhouse,
            project_name="beta-pkg",
            version="1.0.0",
            module_name="beta_pkg",
        ),
    }


def write_smoke_plugin(
    *,
    plugins_dir: Path,
    plugin_name: str,
    command_name: str,
    requirement_line: str,
    import_module: str,
    expected_text: str,
) -> Path:
    plugin_dir = plugins_dir / plugin_name
    commands_dir = plugin_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    (commands_dir / "__init__.py").write_text("", encoding="utf-8")
    (plugin_dir / "requirements.txt").write_text(
        requirement_line + "\n",
        encoding="utf-8",
    )
    (plugin_dir / "plugin.yaml").write_text(
        yaml.dump(
            {
                "_schema_version": 2,
                "name": plugin_name,
                "display_name": plugin_name,
                "desc": "grouped env smoke plugin",
                "author": "codex",
                "version": "0.1.0",
                "runtime": {
                    "python": f"{sys.version_info.major}.{sys.version_info.minor}"
                },
                "components": [
                    {
                        "class": "commands.main:SmokeCommand",
                        "type": "command",
                        "name": command_name,
                        "description": command_name,
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (commands_dir / "main.py").write_text(
        textwrap.dedent(
            f"""\
            from {import_module} import __version__ as DEP_VERSION

            from astrbot_sdk.api.components.command import CommandComponent
            from astrbot_sdk.api.event import AstrMessageEvent, filter
            from astrbot_sdk.api.star.context import Context


            class SmokeCommand(CommandComponent):
                def __init__(self, context: Context):
                    self.context = context

                @filter.command("{command_name}")
                async def handle(self, event: AstrMessageEvent):
                    yield event.plain_result("{expected_text} " + DEP_VERSION)
            """
        ),
        encoding="utf-8",
    )
    return plugin_dir


async def invoke_command(
    runtime: SupervisorRuntime, core: Peer, command_name: str
) -> str:
    """Invoke one remote command and return the emitted text payload."""
    runtime.capability_router.sent_messages.clear()
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
                "text": command_name,
                "session_id": f"smoke-session-{command_name}",
                "user_id": "user-1",
                "platform": "test",
            },
        },
        request_id=f"grouped-env-smoke-{command_name}",
    )

    sent_messages = list(runtime.capability_router.sent_messages)
    assert sent_messages, f"command {command_name} did not emit any message"
    return str(sent_messages[-1].get("text", ""))


@pytest.mark.skipif(
    UV_BINARY is None, reason="uv is required for grouped env smoke tests"
)
@pytest.mark.asyncio
async def test_grouped_environment_smoke_handles_shared_and_conflicting_dependencies():
    """Real uv-backed smoke test for shared and conflicting plugin environments."""
    with tempfile.TemporaryDirectory(prefix="astrbot-grouped-env-smoke-") as temp_dir:
        root = Path(temp_dir)
        wheel_paths = build_local_wheelhouse(root)
        plugins_dir = root / "plugins"
        write_smoke_plugin(
            plugins_dir=plugins_dir,
            plugin_name="plugin_a",
            command_name="probe_alpha_v1",
            requirement_line=f"alpha-pkg @ {wheel_paths['alpha-1'].as_uri()}",
            import_module="alpha_pkg",
            expected_text="alpha-pkg",
        )
        write_smoke_plugin(
            plugins_dir=plugins_dir,
            plugin_name="plugin_b",
            command_name="probe_beta_v1",
            requirement_line=f"beta-pkg @ {wheel_paths['beta-1'].as_uri()}",
            import_module="beta_pkg",
            expected_text="beta-pkg",
        )
        write_smoke_plugin(
            plugins_dir=plugins_dir,
            plugin_name="plugin_c",
            command_name="probe_alpha_v2",
            requirement_line=f"alpha-pkg @ {wheel_paths['alpha-2'].as_uri()}",
            import_module="alpha_pkg",
            expected_text="alpha-pkg",
        )

        env_manager = PluginEnvironmentManager(root)
        left, right = make_transport_pair()
        core = await start_test_core_peer(left)
        runtime = SupervisorRuntime(
            transport=right,
            plugins_dir=plugins_dir,
            env_manager=env_manager,
        )
        shared_venv_path = None
        isolated_venv_path = None

        try:
            await runtime.start()
            await core.wait_until_remote_initialized()

            assert sorted(runtime.loaded_plugins) == [
                "plugin_a",
                "plugin_b",
                "plugin_c",
            ]
            assert runtime.skipped_plugins == {}
            assert env_manager._plan_result is not None
            assert len(env_manager._plan_result.groups) == 2

            shared_group = env_manager._plan_result.plugin_to_group["plugin_a"]
            isolated_group = env_manager._plan_result.plugin_to_group["plugin_c"]
            assert (
                shared_group.id
                == env_manager._plan_result.plugin_to_group["plugin_b"].id
            )
            assert shared_group.id != isolated_group.id
            assert len(runtime.worker_sessions) == 2
            assert core.remote_metadata["worker_group_count"] == 2

            shared_venv_path = shared_group.venv_path
            isolated_venv_path = isolated_group.venv_path
            assert shared_venv_path.exists()
            assert isolated_venv_path.exists()

            alpha_v1_text = await invoke_command(runtime, core, "probe_alpha_v1")
            beta_v1_text = await invoke_command(runtime, core, "probe_beta_v1")
            alpha_v2_text = await invoke_command(runtime, core, "probe_alpha_v2")

            assert "alpha-pkg 1.0.0" in alpha_v1_text
            assert "beta-pkg 1.0.0" in beta_v1_text
            assert "alpha-pkg 2.0.0" in alpha_v2_text
            assert alpha_v1_text != alpha_v2_text
        finally:
            await runtime.stop()
            await core.stop()
            env_manager._planner.cleanup_artifacts([])

        assert shared_venv_path is not None
        assert isolated_venv_path is not None
        assert not shared_venv_path.exists()
        assert not isolated_venv_path.exists()
