import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures import get_fixture_path


def test_fixture_plugin_files_exist():
    plugin_file = get_fixture_path("plugins/fixture_plugin.py")
    metadata_file = get_fixture_path("plugins/metadata.yaml")

    assert plugin_file.exists()
    assert metadata_file.exists()


@pytest.mark.slow
def test_fixture_plugin_can_be_imported_in_isolated_process():
    plugin_file = get_fixture_path("plugins/fixture_plugin.py")
    repo_root = Path(__file__).resolve().parents[2]

    script = "\n".join(
        [
            "import importlib.util",
            f'plugin_file = r"{plugin_file}"',
            "spec = importlib.util.spec_from_file_location('fixture_test_plugin', plugin_file)",
            "assert spec is not None",
            "assert spec.loader is not None",
            "module = importlib.util.module_from_spec(spec)",
            "spec.loader.exec_module(module)",
            "plugin_cls = getattr(module, 'TestPlugin', None)",
            "assert plugin_cls is not None",
            "assert hasattr(plugin_cls, 'test_command')",
            "assert hasattr(plugin_cls, 'test_llm_tool')",
            "assert hasattr(plugin_cls, 'test_regex_handler')",
        ],
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=repo_root,
        check=False,
    )

    if result.returncode != 0:
        stderr_text = (result.stderr or "").strip()
        if stderr_text:
            raise AssertionError(
                "Fixture plugin import failed with stderr output.\n"
                f"stderr:\n{stderr_text}\n\nstdout:\n{result.stdout}"
            )
        raise AssertionError(
            "Fixture plugin import failed with non-zero return code "
            f"{result.returncode}, but stderr is empty.\nstdout:\n{result.stdout}"
        )
