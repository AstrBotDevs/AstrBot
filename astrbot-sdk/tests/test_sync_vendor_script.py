from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_sync_vendor_module():
    script_path = (
        Path(__file__).resolve().parent.parent
        / ".github"
        / "scripts"
        / "sync_vendor.py"
    )
    spec = importlib.util.spec_from_file_location("sync_vendor_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_vendor_snapshot_preserves_src_layout_pyproject(tmp_path: Path):
    module = _load_sync_vendor_module()
    repo_root = tmp_path / "repo"
    src_package = repo_root / "src" / "astrbot_sdk"
    cached_dir = src_package / "__pycache__"

    cached_dir.mkdir(parents=True)
    (src_package / "__init__.py").write_text("__all__ = ['demo']\n", encoding="utf-8")
    (cached_dir / "ignored.pyc").write_bytes(b"cache")
    (repo_root / "LICENSE").write_text("demo license\n", encoding="utf-8")
    (repo_root / "pyproject.toml").write_text(
        """
[project]
name = "astrbot-sdk"
readme = "README.md"

# ============================================================
# Package Discovery (src layout)
# ============================================================
[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
astrbot_sdk = ["templates/skills/*/SKILL.md"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    module.build_vendor_snapshot(repo_root)

    vendor_root = repo_root / "vendor"
    assert {path.name for path in vendor_root.iterdir()} == {
        "LICENSE",
        "README.md",
        "VENDORED.md",
        "pyproject.toml",
        "src",
    }
    vendored_pyproject = (vendor_root / "pyproject.toml").read_text(encoding="utf-8")
    assert "# Package Discovery (src layout)" in vendored_pyproject
    assert 'where = ["src"]' in vendored_pyproject
    assert 'include = ["astrbot_sdk*"]' not in vendored_pyproject
    assert not (vendor_root / "src" / "astrbot_sdk" / "__pycache__").exists()
