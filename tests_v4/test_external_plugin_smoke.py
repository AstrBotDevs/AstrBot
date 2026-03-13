"""可选的外部插件兼容 smoke 测试。

默认不跑；手动验证真实外部插件时，设置
``ASTRBOT_EXTERNAL_PLUGIN_REPO=https://...`` 即可启用。
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
from pathlib import Path

import pytest

from astrbot_sdk.runtime.loader import (
    PluginEnvironmentManager,
    load_plugin_spec,
)

EXTERNAL_PLUGIN_REPO_ENV = "ASTRBOT_EXTERNAL_PLUGIN_REPO"


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
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(clone_dir)],
            check=True,
            cwd=project_root,
            capture_output=True,
            text=True,
        )

        spec = load_plugin_spec(clone_dir)
        manager = PluginEnvironmentManager(project_root)
        python_path = manager.prepare_environment(spec)
        script = textwrap.dedent(
            f"""
            import sys
            from pathlib import Path

            repo_root = Path({str(project_root)!r})
            plugin_dir = Path({str(clone_dir)!r})
            sys.path.insert(0, str((repo_root / "src-new").resolve()))

            from astrbot_sdk.runtime.loader import load_plugin, load_plugin_spec

            spec = load_plugin_spec(plugin_dir)
            loaded = load_plugin(spec)
            print("PLUGIN", loaded.plugin.name)
            print("HANDLERS", len(loaded.handlers))
            print("CAPS", len(loaded.capabilities))
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
